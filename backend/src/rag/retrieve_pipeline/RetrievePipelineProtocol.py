from typing import Protocol
from langchain_core.documents import Document


class RetrievePipelineProtocol(Protocol):

    async def retrieve_document(self, query: str, document_record_id: str) -> str:
        """Retrieve documents based on the query."""
        ...

    async def retrieve_knowledge_base(self, query: str, knowledge_base_id: str) -> str:
        """Retrieve knowledge base based on the query."""
        ...

    async def retrieve_memory(self, query: str, user_id: str) -> str:
        """Retrieve memory based on the query."""
        ...
