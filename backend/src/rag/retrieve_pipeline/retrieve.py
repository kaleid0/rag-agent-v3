import asyncio
from itertools import zip_longest
from pathlib import Path

from beanie import PydanticObjectId
from beanie.operators import In
from langchain_core.documents import Document

from config import memory_cfg
from src.document import DocumentRecord
from src.rag.knowledge_base import CollectionRecord, KnowledgeBase, knowledge_base_service
from src.rag.retriever import BM25Retriever, ChromaRetriever
from src.rag.utils import remove_duplicates


async def get_knowledge_base_sources(
    knowledge_base_id: str,
) -> tuple[KnowledgeBase, list[CollectionRecord], dict[str, DocumentRecord]]:
    knowledge_base = await knowledge_base_service.get_knowledge_base(knowledge_base_id)
    collections = await knowledge_base_service.get_collections_in_knowledge_base(
        knowledge_base_id
    )
    if not collections:
        return knowledge_base, [], {}

    document_ids = list({PydanticObjectId(record.document_record_id) for record in collections})
    documents = await DocumentRecord.find(In(DocumentRecord.id, document_ids)).to_list()
    deleting_ids = {str(doc.id) for doc in documents if doc.status == "deleting"}
    readable = [
        record for record in collections if record.document_record_id not in deleting_ids
    ]
    return knowledge_base, readable, {str(doc.id): doc for doc in documents}


async def retrieve_knowledge_base(
    knowledge_base_id: str,
    query: dict | str,
    top_k: int = 10,
    query_route: dict[str, int] | None = None,
) -> list[Document]:
    knowledge_base, collections, documents = await get_knowledge_base_sources(
        knowledge_base_id
    )
    return await retrieve_collections(
        knowledge_base, collections, documents, query, top_k, query_route
    )


async def retrieve_collections(
    knowledge_base: KnowledgeBase,
    collections: list[CollectionRecord],
    documents: dict[str, DocumentRecord],
    query: dict | str,
    top_k: int,
    query_route: dict[str, int] | None = None,
) -> list[Document]:
    collection_ids = [str(record.id) for record in collections]
    chunk_paths = {str(record.id): record.chunk_path for record in collections}
    languages = {
        str(record.id): documents[record.document_record_id].language
        for record in collections
        if record.document_record_id in documents
    }
    return await asyncio.to_thread(
        _retrieve,
        knowledge_base.retriever_type,
        collection_ids,
        query,
        top_k,
        query_route=query_route,
        languages=languages,
        chunk_paths=chunk_paths,
    )


async def retrieve_memory(
    user_id: str,
    query: dict | str,
    top_k: int = 10,
) -> list[Document]:
    chunk_path = str(Path(memory_cfg["chunk_dir"]) / f"{user_id}.pkl")
    return await asyncio.to_thread(
        _retrieve,
        memory_cfg["retriever_type"],
        [user_id],
        query,
        top_k,
        chunk_paths={user_id: chunk_path},
        skip_empty_vectors=True,
    )


def _retrieve(
    retriever_type: str,
    collection_ids: list[str],
    query: dict | str,
    top_k: int,
    *,
    query_route: dict[str, int] | None = None,
    languages: dict[str, str] | None = None,
    chunk_paths: dict[str, str] | None = None,
    skip_empty_vectors: bool = False,
) -> list[Document]:
    if top_k <= 0:
        return []
    if query_route is not None:
        collection_ids = [cid for cid in collection_ids if query_route.get(cid, 0) > 0]
    if not collection_ids:
        return []

    results = []
    if retriever_type in {"vector", "hybrid"}:
        vector = ChromaRetriever(collection_ids, language=languages)
        results.append(
            vector.retrieve(query, top_k, query_route, skip_empty=skip_empty_vectors)
        )
    if retriever_type in {"sparse", "hybrid"}:
        sparse = BM25Retriever(collection_ids, language=languages, chunk_paths=chunk_paths)
        results.append(sparse.retrieve(query, top_k, query_route))
    if not results:
        raise ValueError("Invalid retriever type")

    candidates = [doc for group in zip_longest(*results) for doc in group if doc is not None]
    return remove_duplicates(candidates)[:top_k]
