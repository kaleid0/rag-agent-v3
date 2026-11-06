from functools import lru_cache
from pathlib import Path
import pickle

from langchain_community.retrievers import BM25Retriever as LangchainBM25Retriever
from langchain_core.documents import Document

from config import rag_cfg
from src.rag.utils import query_for_language


@lru_cache(maxsize=16)
def _load_index(
    sources: tuple[tuple[str, Path, int, int], ...],
) -> LangchainBM25Retriever | None:
    documents = []
    for collection_id, path, _, _ in sources:
        try:
            with path.open("rb") as file:
                chunks = pickle.load(file)
        except FileNotFoundError:
            continue
        for doc in chunks:
            doc.metadata["collection_id"] = collection_id
            documents.append(doc)
    return LangchainBM25Retriever.from_documents(documents) if documents else None


class BM25Retriever:
    def __init__(
        self,
        collection_record_ids: list[str] | str,
        language: dict[str, str] | None = None,
        *,
        chunk_paths: dict[str, str] | None = None,
    ):
        if isinstance(collection_record_ids, str):
            collection_record_ids = [collection_record_ids]
        self.language = language or {}
        sources = []
        for collection_id in sorted(collection_record_ids):
            path = (
                Path(chunk_paths[collection_id])
                if chunk_paths is not None
                else Path(rag_cfg["chunk_dir"]) / f"{collection_id}.pkl"
            )
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            sources.append((collection_id, path, stat.st_mtime_ns, stat.st_size))
        self.index = _load_index(tuple(sources))

    @classmethod
    def ingest(
        cls,
        documents: list[Document],
        collection_record_id: str,
        **_: dict,
    ) -> None:
        """入库流程已经持久化原始分块，BM25 在读取时从文件构建。"""

    def retrieve(
        self, query: dict | str, top_k: int = 10, query_route: dict[str, int] | None = None
    ) -> list[Document]:
        if self.index is None or top_k <= 0:
            return []

        docs = self.index.docs
        languages = [
            self.language.get(doc.metadata["collection_id"], "EN") for doc in docs
        ]
        queries = [query_for_language(query, language) for language in languages]
        scores = {
            text: self.index.vectorizer.get_scores(self.index.preprocess_func(text))
            for text in set(queries)
        }
        ranking = sorted(
            range(len(docs)), key=lambda index: scores[queries[index]][index], reverse=True
        )
        if query_route is None:
            return [docs[index] for index in ranking[:top_k]]

        budgets = dict(query_route)
        results = []
        for index in ranking:
            doc = docs[index]
            collection_id = doc.metadata["collection_id"]
            if budgets.get(collection_id, 0) > 0:
                results.append(doc)
                budgets[collection_id] -= 1
                if len(results) >= top_k:
                    break
        return results
