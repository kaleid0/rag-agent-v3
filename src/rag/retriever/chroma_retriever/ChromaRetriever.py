import asyncio
from itertools import chain
from logging import getLogger

from chromadb import Collection, EmbeddingFunction, Embeddings, GetResult, QueryResult
from chromadb.errors import NotFoundError
from langchain_core.documents import Document

from src.database import get_chroma_client, get_collection
from src.rag.utils import query_for_language
from .EmbeddingFunction import SyncEmbeddingFunction


logger = getLogger(__name__)


class ChromaRetriever:
    def __init__(
        self,
        collection_record_ids: list[str] | str,
        language: dict[str, str] | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ):
        self.embedding_function = (
            embedding_function if embedding_function is not None else SyncEmbeddingFunction()
        )
        self.language = language or {}
        self.vector_stores: dict[str, Collection] = {}
        if isinstance(collection_record_ids, str):
            collection_record_ids = [collection_record_ids]
        if not collection_record_ids:
            return

        client = get_chroma_client()
        for collection_id in collection_record_ids:
            try:
                self.vector_stores[collection_id] = client.get_collection(
                    collection_id, embedding_function=self.embedding_function
                )
            except NotFoundError:
                continue

    @classmethod
    def ingest(
        cls,
        documents: list[Document],
        collection_record_id: str,
        embedding_function: EmbeddingFunction | None = None,
        **_: dict,
    ):
        if not documents:
            return
        if collection_record_id is None:
            collection_record_id = "default_record"
        if embedding_function is None:
            embedding_function = SyncEmbeddingFunction()

        try:
            collection = get_collection(
                collection_record_id, embedding_function=embedding_function
            )
            batch_size = 10
            for start in range(0, len(documents), batch_size):
                batch = documents[start : start + batch_size]
                collection.add(
                    ids=[doc.id for doc in batch],  # type: ignore
                    documents=[doc.page_content for doc in batch],
                    metadatas=[doc.metadata for doc in batch],
                )
        except Exception as exc:
            logger.error("文档向量化失败: %s", collection_record_id, exc_info=exc)
            raise RuntimeError(f"文档切片或向量化失败: {collection_record_id}") from exc

    def retrieve(
        self,
        query: dict | str,
        top_k: int = 10,
        query_route: dict[str, int] | None = None,
        *,
        skip_empty: bool = False,
    ) -> list[Document]:
        results: list[QueryResult] = []
        embeddings: dict[str, Embeddings] = {}
        for collection_id, collection in self.vector_stores.items():
            count = top_k if query_route is None else min(
                top_k, query_route.get(collection_id, 0)
            )
            if count <= 0:
                continue
            query_text = query_for_language(query, self.language.get(collection_id, "EN"))
            try:
                if skip_empty and collection.count() == 0:
                    continue
                if query_text not in embeddings:
                    embeddings[query_text] = self.embedding_function.embed_query([query_text])
                result = collection.query(
                    query_embeddings=embeddings[query_text], n_results=count
                )
            except NotFoundError:
                continue
            result["metadatas"] = [
                [{**(metadata or {}), "collection_id": collection_id} for metadata in group]
                for group in result.get("metadatas") or []
            ]
            results.append(result)

        return [doc for _, doc in get_topk_query_result(results, top_k)]

    async def get_by_ids(
        self, record_ids: list[str], ids: list[list[str]]
    ) -> dict[str, list[Document]]:
        if len(record_ids) != len(ids):
            raise ValueError("record_ids 和 ids 长度不匹配")

        result: dict[str, list[Document]] = {}
        for record_id, chunk_ids in zip(record_ids, ids):
            collection = self.vector_stores.get(record_id)
            if collection is not None and chunk_ids:
                try:
                    chunks = await asyncio.to_thread(collection.get, ids=chunk_ids)
                except NotFoundError:
                    continue
                docs = flatten_query_result(chunks)
                for doc in docs:
                    doc.metadata["collection_id"] = record_id
                result[record_id] = docs
        return result


def get_topk_query_result(results: list[QueryResult], k: int) -> list[tuple[float, Document]]:
    merged = []
    for result in results:
        distances = chain.from_iterable(result.get("distances") or [])
        merged.extend(zip(distances, flatten_query_result(result)))
    return sorted(merged, key=lambda pair: pair[0])[:k]


def flatten_query_result(result: QueryResult | GetResult) -> list[Document]:
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadata = result.get("metadatas") or []
    if "distances" in result:
        ids = chain.from_iterable(ids)
        documents = chain.from_iterable(documents)
        metadata = chain.from_iterable(metadata)

    return [
        Document(id=chunk_id, page_content=content, metadata=chunk_metadata or {})
        for chunk_id, content, chunk_metadata in zip(ids, documents, metadata)
    ]
