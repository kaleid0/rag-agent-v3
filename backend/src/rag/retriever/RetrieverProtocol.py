# from abc import ABC, abstractmethod
from typing import Protocol
from langchain_core.documents import Document


# Protocol 函数参数可以更多，但是需要有默认值
class RetrieverProtocol(Protocol):
    # @property
    # def name(self) -> str: ...

    @classmethod
    def ingest(
        cls,
        documents: list[Document],
        collection_record_id: str,
        **kwargs,
    ) -> None:
        """将文档切片并存储到检索器中"""
        ...

    def retrieve(
        self, query: dict | str, top_k: int = 10, query_route: dict | None = None
    ) -> list[Document]:
        """根据 query 检索 top_k 个文档"""
        ...
