import os
import pickle

from src.rag.retriever import ChromaRetriever, BM25Retriever
from .text_splitter.get_chunks import get_chunks, get_chunks_from_messages

from config import rag_cfg, memory_cfg


class IngestResult:
    __slots__ = "num_chunks"

    def __init__(
        self,
        num_chunks: int,
    ):
        self.num_chunks = num_chunks


def ingest_file(
    collection_record_id: str,
    markdown_path: str,
    chunk_save_path: str,
    document_title: str = "",
    chunk_size: int = rag_cfg["chunk_size"],
    chunk_overlap: int = rag_cfg["chunk_overlap"],
    split_method: str = rag_cfg["split_method"],
    retriever_type: str | None = None,
) -> IngestResult:
    """异步封装的 ingest 函数。

    Args:
        document_record_id (str): DocumentRecord 的 ID。
        chunk_save_path (str): 分块保存路径。
        chunk_size (int): 分块大小。
        chunk_overlap (int): 分块重叠大小。
        retriever_type (list[BaseRetriever]): 检索器类型列表。
    """
    if retriever_type is None:
        retriever_type = rag_cfg["retriever_type"]

    try:
        # 1. chunking
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()

        chunks = get_chunks(
            markdown_content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            split_method=split_method,
            metadata={
                "document_title": document_title,
                "collection_id": collection_record_id,
            },
        )

        os.makedirs(os.path.dirname(chunk_save_path), exist_ok=True)
        with open(chunk_save_path, "wb") as f:
            pickle.dump(chunks, f)

        # 2. ingeset
        if retriever_type == "vector":
            r_type = [ChromaRetriever]
        elif retriever_type == "sparse":
            r_type = [BM25Retriever]
        elif retriever_type == "hybrid":
            r_type = [ChromaRetriever, BM25Retriever]
        for retriever in r_type:
            retriever.ingest(chunks, collection_record_id=collection_record_id)

    except Exception as e:
        raise e

    return IngestResult(num_chunks=len(chunks))


def ingest_memory(
    user_id: str,
    messages: list[dict[str, str]],
    chunk_save_path: str,
    session_id: str = "",
    max_chunk_size: int = memory_cfg["max_chunk_size"],
    retriever_type: str = memory_cfg["retriever_type"],
):
    """将 Memory 对象中的内容分块并存储到 RAG 系统中。"""
    if retriever_type is None:
        retriever_type = rag_cfg["retriever_type"]

    try:
        # 1. chunking

        chunks = get_chunks_from_messages(
            messages,
            max_chunk_size=max_chunk_size,
            metadata={"session_id": session_id},
        )

        os.makedirs(os.path.dirname(chunk_save_path), exist_ok=True)
        with open(chunk_save_path, "wb") as f:
            pickle.dump(chunks, f)

        # 2. ingeset
        if retriever_type == "vector":
            r_type = [ChromaRetriever]
        elif retriever_type == "sparse":
            r_type = [BM25Retriever]
        elif retriever_type == "hybrid":
            r_type = [ChromaRetriever, BM25Retriever]
        for retriever in r_type:
            retriever.ingest(chunks, collection_record_id=user_id)

    except Exception as e:
        raise e

    return IngestResult(num_chunks=len(chunks))
