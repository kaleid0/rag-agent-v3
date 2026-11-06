import asyncio
import hashlib
import logging
import uuid
from pathlib import Path

from beanie import PydanticObjectId
from beanie.odm.operators.update.general import Set
from beanie.odm.queries.update import UpdateResponse
from fastapi import HTTPException, UploadFile
from pymongo.errors import DuplicateKeyError

from config import rag_cfg
from src.rag import CollectionRecord, knowledge_base_service

from .odm.DocumentRecord import DocumentRecord
from .parse import parse


logger = logging.getLogger(__name__)
_SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".md"}


def _object_id(value: str) -> PydanticObjectId:
    if not PydanticObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    return PydanticObjectId(value)


def _markdown_path(record: DocumentRecord) -> Path:
    if record.markdown_path:
        return Path(record.markdown_path)
    filename = Path(record.storage_path).with_suffix(".md").name
    return Path(rag_cfg["markdown_storage_dir"]) / filename


def _remove_document_files(record: DocumentRecord) -> None:
    markdown_path = _markdown_path(record)
    markdown_path.with_suffix(".md.partial").unlink(missing_ok=True)
    markdown_path.unlink(missing_ok=True)
    Path(record.storage_path).unlink(missing_ok=True)


async def list_document_records() -> list[DocumentRecord]:
    return await DocumentRecord.find_all().to_list()


async def delete_document_record(document_record_id: str) -> None:
    document_id = _object_id(document_record_id)
    document = await DocumentRecord.find_one(
        {"_id": document_id, "status": {"$ne": "processing"}}
    ).update(Set({"status": "deleting"}), response_type=UpdateResponse.NEW_DOCUMENT)
    if document is None and await DocumentRecord.get(document_id) is not None:
        raise HTTPException(status_code=409, detail="Document is being parsed")

    associations = await CollectionRecord.find(
        {"document_record_id": str(document_id)}
    ).to_list()
    await knowledge_base_service.delete_associations(associations)
    if document is not None:
        await asyncio.to_thread(_remove_document_files, document)
        await document.delete()


def _write_upload(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


async def _find_duplicate(file_hash: str) -> DocumentRecord | None:
    document = await DocumentRecord.find_one(
        {"file_hash": file_hash, "status": {"$ne": "deleting"}}
    )
    if document is not None:
        return document
    if await DocumentRecord.find_one({"file_hash": file_hash, "status": "deleting"}):
        raise HTTPException(status_code=409, detail="Document is being deleted")
    return None


async def upload_file(file: UploadFile) -> DocumentRecord:
    filename = file.filename or "unknown_file"
    suffix = Path(filename).suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported file extension")

    max_size = rag_cfg.get("max_file_size_mb", 10) * 1024 * 1024
    content = await file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File exceeds the size limit")

    file_hash = hashlib.md5(content).hexdigest()
    duplicate = await _find_duplicate(file_hash)
    if duplicate is not None:
        return duplicate

    save_path = Path(rag_cfg["file_storage_dir"]) / f"{uuid.uuid4().hex}{suffix}"
    record = DocumentRecord(
        id=PydanticObjectId(),
        source=filename,
        storage_path=str(save_path),
        file_hash=file_hash,
        upload_key=file_hash,
        status="pending",
    )
    try:
        await asyncio.to_thread(_write_upload, save_path, content)
        await record.insert()
    except DuplicateKeyError:
        await asyncio.to_thread(save_path.unlink, missing_ok=True)
        duplicate = await _find_duplicate(file_hash)
        if duplicate is not None:
            return duplicate
        raise HTTPException(
            status_code=409, detail="Concurrent upload changed; retry the upload"
        )
    except Exception:
        # A failed acknowledgement can still mean MongoDB inserted the record.
        try:
            if await DocumentRecord.get(record.id) is None:
                await asyncio.to_thread(save_path.unlink, missing_ok=True)
        except Exception:
            logger.exception("Could not reconcile interrupted upload %s", record.id)
        raise
    return record


async def parse_file(document_record_id: str) -> None:
    document = await DocumentRecord.find_one(
        {
            "_id": _object_id(document_record_id),
            "$or": [
                {"status": {"$in": ["pending", "failed"]}},
                {"status": None, "markdown_path": {"$in": ["", None]}},
            ],
        }
    ).update(Set({"status": "processing"}), response_type=UpdateResponse.NEW_DOCUMENT)
    if document is None:
        return

    task = asyncio.create_task(_parse_document(document))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(task)
        except Exception:
            logger.exception("Parsing failed after cancellation for %s", document.id)
        raise


async def _parse_document(document: DocumentRecord) -> None:
    output_path = _markdown_path(document)
    temp_path = output_path.with_suffix(".md.partial")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = await parse(document.storage_path, str(temp_path))
        temp_path.replace(output_path)
        await document.set(
            {
                "markdown_path": str(output_path),
                "title": result.title,
                "abstract": result.abstract,
                "keywords": result.keywords,
                "directory": result.directory,
                "language": result.language,
                "status": "ready",
            }
        )
    except Exception:
        logger.exception("Could not parse document %s", document.id)
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove partial Markdown for %s", document.id)
        await document.set({"status": "failed"})
