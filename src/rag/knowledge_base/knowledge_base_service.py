import asyncio
import logging
from pathlib import Path

from beanie import PydanticObjectId
from beanie.odm.operators.update.general import Set
from beanie.odm.queries.update import UpdateResponse
from bson.errors import InvalidId
from chromadb.errors import NotFoundError
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from config import rag_cfg
from src.database import delete_collection
from src.document import DocumentRecord
from src.rag.ingest.ingest import ingest_file

from .odm.CollectionRecord import CollectionRecord
from .odm.KnowledgeBase import KnowledgeBase


logger = logging.getLogger(__name__)

_READY_FILTER = {
    "status": {"$in": ["ready", None]},
    "chunk_path": {"$type": "string", "$ne": ""},
    "num_chunks": {"$gt": 0},
}


async def _ready_associations(where: dict) -> list[CollectionRecord]:
    records = await CollectionRecord.find(where, _READY_FILTER).to_list()
    return [
        record
        for record in records
        if record.status == "ready" or Path(record.chunk_path).is_file()
    ]


def _object_id(value: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except (InvalidId, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid resource ID") from exc


async def get_knowledge_base(knowledge_base_id: str) -> KnowledgeBase:
    knowledge_base = await KnowledgeBase.get(_object_id(knowledge_base_id))
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if knowledge_base.deleting:
        raise HTTPException(status_code=409, detail="Knowledge base is being deleted")
    return knowledge_base


async def _get_document_for_indexing(document_record_id: str) -> DocumentRecord:
    document = await DocumentRecord.get(_object_id(document_record_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document record not found")
    if document.parse_status != "ready" or not document.markdown_path:
        raise HTTPException(status_code=409, detail="Document is not ready to index")
    return document


async def create_knowledge_base(
    name: str,
    description: str = "",
    chunk_size: int = 300,
    chunk_overlap: int = 50,
    split_method: str = "hierarchical",
    retriever_type: str = "hybrid",
    document_record_ids: list[str] | None = None,
) -> KnowledgeBase:
    document_record_ids = list(dict.fromkeys(document_record_ids or []))
    for document_id in document_record_ids:
        await _get_document_for_indexing(document_id)

    knowledge_base = KnowledgeBase(
        name=name,
        description=description,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        split_method=split_method,
        retriever_type=retriever_type,
    )
    await knowledge_base.insert()

    try:
        for document_id in document_record_ids:
            await add_record_to_knowledge_base(str(knowledge_base.id), document_id)
    except (Exception, asyncio.CancelledError):
        try:
            await delete_knowledge_base(str(knowledge_base.id))
        except Exception:
            logger.exception("Could not roll back knowledge base %s", knowledge_base.id)
        raise
    return knowledge_base


def _cleanup_association_artifacts(record: CollectionRecord) -> None:
    if record.retriever_type != "sparse":
        try:
            delete_collection(str(record.id))
        except NotFoundError:
            pass

    chunk_path = record.chunk_path or str(
        Path(rag_cfg["chunk_dir"]) / f"{record.id}.pkl"
    )
    Path(chunk_path).unlink(missing_ok=True)


async def _delete_association(record: CollectionRecord) -> None:
    deleting = await CollectionRecord.find_one(
        {"_id": record.id, "status": {"$ne": "indexing"}}
    ).update(Set({"status": "deleting"}), response_type=UpdateResponse.NEW_DOCUMENT)
    if deleting is None:
        if await CollectionRecord.get(record.id) is not None:
            raise HTTPException(status_code=409, detail="Document is being indexed")
        return

    await asyncio.to_thread(_cleanup_association_artifacts, deleting)
    await deleting.delete()


async def delete_associations(records: list[CollectionRecord]) -> None:
    if any(record.status == "indexing" for record in records):
        raise HTTPException(status_code=409, detail="Document is being indexed")
    for record in records:
        await _delete_association(record)


async def remove_record_from_knowledge_base(
    knowledge_base_id: str, collection_record_id: str
):
    knowledge_base_id = str(_object_id(knowledge_base_id))
    file_id = _object_id(collection_record_id)
    association = await CollectionRecord.get(file_id)
    if association is not None:
        if association.knowledge_base_id != knowledge_base_id:
            raise HTTPException(status_code=404, detail="Document is not in this knowledge base")
        records = [association]
    else:
        # Accept document IDs from the public API in addition to legacy association IDs.
        records = await CollectionRecord.find(
            {"knowledge_base_id": knowledge_base_id, "document_record_id": str(file_id)}
        ).to_list()
    await delete_associations(records)


async def _build_association(record: CollectionRecord, retry: bool) -> None:
    try:
        knowledge_base = await get_knowledge_base(record.knowledge_base_id)
        document = await _get_document_for_indexing(record.document_record_id)
        if retry:
            await asyncio.to_thread(_cleanup_association_artifacts, record)
        result = await asyncio.to_thread(
            ingest_file,
            str(record.id),
            document.markdown_path,
            record.chunk_path,
            document.title or document.source,
            knowledge_base.chunk_size,
            knowledge_base.chunk_overlap,
            knowledge_base.split_method,
            knowledge_base.retriever_type,
        )
        if result.num_chunks == 0:
            raise HTTPException(status_code=422, detail="Document has no indexable content")

        await get_knowledge_base(record.knowledge_base_id)
        await _get_document_for_indexing(record.document_record_id)
        await record.set({"status": "ready", "num_chunks": result.num_chunks})
    except Exception as exc:
        try:
            await asyncio.to_thread(_cleanup_association_artifacts, record)
        except Exception:
            logger.exception("Could not clean incomplete index %s", record.id)

        await record.set({"status": "failed", "num_chunks": 0})
        if isinstance(exc, HTTPException) and exc.status_code == 404:
            # A parent can disappear after the initial read and before this claim.
            await _delete_association(record)
        raise


async def add_record_to_knowledge_base(
    knowledge_base_id: str, document_record_id: str
) -> None:
    knowledge_base = await get_knowledge_base(knowledge_base_id)
    document = await _get_document_for_indexing(document_record_id)
    knowledge_base_id = str(knowledge_base.id)
    document_record_id = str(document.id)
    pair = {
        "knowledge_base_id": knowledge_base_id,
        "document_record_id": document_record_id,
    }

    if await _ready_associations(pair):
        return

    association_key = f"{knowledge_base_id}:{document_record_id}"
    association_id = PydanticObjectId()
    pending = CollectionRecord(
        id=association_id,
        association_key=association_key,
        status="pending",
        chunk_path=str(Path(rag_cfg["chunk_dir"]) / f"{association_id}.pkl"),
        retriever_type=knowledge_base.retriever_type,
        **pair,
    )
    try:
        await pending.insert()
    except DuplicateKeyError:
        # A concurrent request already reserved this pair.
        pass

    retry = await CollectionRecord.find_one(
        {"association_key": association_key, "status": "failed"}
    ).update(Set({"status": "indexing"}), response_type=UpdateResponse.NEW_DOCUMENT)
    record = retry
    if record is None:
        record = await CollectionRecord.find_one(
            {"association_key": association_key, "status": "pending"}
        ).update(Set({"status": "indexing"}), response_type=UpdateResponse.NEW_DOCUMENT)

    if record is None:
        if await _ready_associations(pair):
            return
        raise HTTPException(status_code=409, detail="Document indexing or removal is in progress")

    task = asyncio.create_task(_build_association(record, retry=retry is not None))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancelling the request cannot stop the worker thread. Keep the claim until it finishes.
        try:
            await asyncio.shield(task)
        except Exception:
            logger.exception("Indexing failed after cancellation for %s", record.id)
        raise


async def delete_knowledge_base(knowledge_base_id: str):
    knowledge_base_id = _object_id(knowledge_base_id)
    knowledge_base = await KnowledgeBase.find_one({"_id": knowledge_base_id}).update(
        Set({"deleting": True}), response_type=UpdateResponse.NEW_DOCUMENT
    )
    records = await get_collections_in_knowledge_base(
        str(knowledge_base_id), ready_only=False
    )
    await delete_associations(records)
    if knowledge_base is not None:
        await knowledge_base.delete()


async def list_knowledge_bases(skip: int = 0, limit: int = 100) -> list[KnowledgeBase]:
    return await KnowledgeBase.find_all(skip=skip, limit=limit).to_list()


async def get_collections_in_knowledge_base(
    knowledge_base_id: str | list[str], *, ready_only: bool = True
) -> list[CollectionRecord]:
    """Return readable associations by default, including compatible legacy rows."""
    ids = [knowledge_base_id] if isinstance(knowledge_base_id, str) else knowledge_base_id
    if not ids:
        return []

    if not ready_only:
        return await CollectionRecord.find({"knowledge_base_id": {"$in": ids}}).to_list()

    active = await KnowledgeBase.find(
        {"_id": {"$in": [_object_id(id_) for id_ in ids]}, "deleting": {"$ne": True}}
    ).to_list()
    return await _ready_associations(
        {"knowledge_base_id": {"$in": [str(kb.id) for kb in active]}}
    )
