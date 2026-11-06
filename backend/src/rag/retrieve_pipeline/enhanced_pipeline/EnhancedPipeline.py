import asyncio
import logging

from config import rag_cfg
from src.llm.factory import get_configured_llm
from src.prompt import llm_call
from src.rag.retrieve_pipeline.retrieve import (
    get_knowledge_base_sources,
    retrieve_collections,
)
from src.rag.utils import group_by_collection, organize_context
from .context_retrieve import context_retrieve
from .rerank import rerank


logger = logging.getLogger(__name__)


async def _try_query_model(prompt_name: str, args: dict) -> object:
    try:
        llm = await get_configured_llm("rag")
        return await llm_call(prompt_name, llm, args)
    except Exception as exc:
        logger.warning("%s failed: %s", prompt_name, type(exc).__name__)
        return None


class EnhancedPipeline:
    async def retrieve_document(self, query: str, document_record_id: str) -> str:
        raise NotImplementedError

    async def retrieve_knowledge_base(self, query: str, knowledge_base_id: str) -> str:
        knowledge_base, collections, documents = await get_knowledge_base_sources(
            knowledge_base_id
        )
        top_k = rag_cfg.get("top_k", 10)
        if not collections or top_k <= 0:
            return "No documents retrieved."

        tasks = {}
        if rag_cfg.get("query_rewrite"):
            tasks["rewrite"] = _try_query_model("query_rewrite", {"question": query})
        if rag_cfg.get("query_route"):
            sources = []
            for record in collections:
                doc = documents.get(record.document_record_id)
                sources.append(
                    {
                        "collection_id": str(record.id),
                        "title": doc.title if doc else None,
                        "keywords": doc.keywords if doc and doc.keywords else [],
                    }
                )
            tasks["route"] = _try_query_model(
                "query_route", {"question": query, "collections": sources}
            )

        results = dict(zip(tasks, await asyncio.gather(*tasks.values())))
        rewritten = results.get("rewrite")
        search_query: str | dict = query
        if isinstance(rewritten, dict):
            translations = {
                language: text
                for language in ("EN", "ZH")
                if isinstance(text := rewritten.get(language), str) and text.strip()
            }
            search_query = translations or query

        route = results.get("route")
        if not (
            isinstance(route, dict)
            and route.keys() == {str(record.id) for record in collections}
            and all(type(count) is int and 0 <= count <= 5 for count in route.values())
        ):
            if route is not None:
                logger.warning("Invalid collection route. Searching the full knowledge base")
            route = None

        should_rerank = bool(rag_cfg.get("rerank"))
        candidate_k = 2 * top_k if should_rerank else top_k
        hits = await retrieve_collections(
            knowledge_base, collections, documents, search_query, candidate_k, route
        )
        if not hits:
            return "No documents retrieved."

        selected = hits[:top_k]
        if should_rerank:
            try:
                selected = await rerank(search_query, hits, top_k=top_k)
            except Exception as exc:
                logger.warning(
                    "Rerank failed. Keeping retrieval order: %s", type(exc).__name__
                )

        if rag_cfg.get("context_retrieve") and knowledge_base.retriever_type != "sparse":
            grouped = await context_retrieve(selected)
        else:
            grouped = group_by_collection(selected)
        return organize_context(grouped)

    async def retrieve_memory(self, query: str, user_id: str) -> str:
        raise NotImplementedError
