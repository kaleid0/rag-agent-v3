import asyncio

from langchain_core.documents import Document

from src.llm.factory import get_configured_llm
from src.prompt import llm_call
from src.rag.utils import query_for_language


async def rerank(
    query: str | dict, documents: list[Document], top_k: int = 10
) -> list[Document]:
    if not documents or top_k <= 0:
        return []

    query_text = query_for_language(query, "EN")
    llm = await get_configured_llm("rag")
    batch_size = 5
    batches = [
        documents[start : start + batch_size]
        for start in range(0, len(documents), batch_size)
    ]
    tasks = []
    for batch in batches:
        texts = [doc.page_content for doc in batch] + [""] * (batch_size - len(batch))
        args = {f"text{index}": text for index, text in enumerate(texts, start=1)}
        tasks.append(llm_call("grade_texts", llm, {"query": query_text, **args}))

    grades_by_batch = await asyncio.gather(*tasks)
    ranked = []
    for batch, grades in zip(batches, grades_by_batch):
        if not isinstance(grades, dict):
            raise ValueError("Invalid rerank response")
        for index, doc in enumerate(batch, start=1):
            score = grades.get(f"text{index}")
            if type(score) is not int or not 0 <= score <= 5:
                raise ValueError("Invalid rerank score")
            ranked.append((score, doc))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in ranked[:top_k]]
