from config import memory_cfg, rag_cfg
from src.rag.retrieve_pipeline.retrieve import retrieve_knowledge_base, retrieve_memory
from src.rag.utils import group_by_collection, organize_context


class SimplePipeline:
    async def retrieve_document(self, query: str, document_record_id: str) -> str:
        raise NotImplementedError("This method is not implemented yet.")

    async def retrieve_knowledge_base(self, query: str, knowledge_base_id: str) -> str:
        documents = await retrieve_knowledge_base(
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=rag_cfg.get("top_k", 10),
        )
        return organize_context(group_by_collection(documents))

    async def retrieve_memory(self, query: str, user_id: str) -> str:
        documents = await retrieve_memory(user_id=user_id, query=query, top_k=memory_cfg["top_k"])
        return "".join(doc.page_content for doc in documents)
