import asyncio

from langchain_core.documents import Document

from src.rag.retriever import ChromaRetriever
from src.rag.utils import group_by_collection, remove_duplicates


async def context_retrieve(
    documents: list[Document], num_context: int = 3
) -> dict[str, list[Document]]:
    """用同一集合中的相邻分块补充上下文，保留每个原始命中。"""
    groups = group_by_collection(documents)
    lookup = {}
    for collection_id, chunks in groups.items():
        ids = [
            chunk.id
            for chunk in chunks
            if chunk.metadata.get("collection_id") and chunk.id and chunk.id.isdecimal()
        ]
        counts = [chunk.metadata.get("num_chunks", 0) for chunk in chunks]
        num_chunks = max((count for count in counts if type(count) is int), default=0)
        if ids and num_chunks > 0:
            lookup[collection_id] = extend_array(ids, num_context, 0, num_chunks - 1)

    if not lookup:
        return groups

    retriever = await asyncio.to_thread(ChromaRetriever, list(lookup))
    neighbors = await retriever.get_by_ids(list(lookup), list(lookup.values()))
    for collection_id, chunks in neighbors.items():
        if not chunks:
            continue
        combined = remove_duplicates(groups[collection_id] + chunks)
        groups[collection_id] = sorted(
            combined,
            key=lambda chunk: int(chunk.id) if chunk.id and chunk.id.isdecimal() else float("inf"),
        )
    return groups


def extend_array(
    arr: list[int | str], n: int, min_range: int, max_range: int
) -> list[str]:
    """返回所有原始分块及范围内的相邻分块 ID。"""
    expanded = set()
    for value in arr:
        index = int(value)
        expanded.update(range(max(min_range, index - n), min(max_range, index + n) + 1))
    return [str(index) for index in sorted(expanded)]
