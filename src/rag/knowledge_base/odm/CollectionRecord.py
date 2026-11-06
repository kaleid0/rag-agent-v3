from typing import Literal

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.database import BaseDocument


# 数据库设计
# KnowledgeBase -> [CollectionRecord ...]
# DocumentRecord -> [CollectionRecord ...]
class CollectionRecord(BaseDocument):
    """知识库中的集合记录信息，一个集合记录对应一个文档记录"""

    chunk_path: str = Field(default="")
    num_chunks: int = Field(default=0)

    document_record_id: str = Field(...)  # 关联的文档记录ID
    knowledge_base_id: str = Field(...)  # 关联的知识库ID
    status: Literal["pending", "indexing", "ready", "failed", "deleting"] | None = None
    # New reservations opt into uniqueness without rewriting existing associations.
    association_key: str | None = None
    retriever_type: Literal["vector", "sparse", "hybrid"] | None = None

    class Settings:
        name = "collection_record"  # MongoDB 集合名
        indexes = [
            [("created_at", DESCENDING)],  # 单字段索引 (列表格式)
            [
                ("document_record_id", ASCENDING),  # 字段 1
                ("knowledge_base_id", ASCENDING),  # 字段 2
            ],
            [("knowledge_base_id", ASCENDING)],
            [("document_record_id", ASCENDING)],
            IndexModel(
                [("association_key", ASCENDING)],
                unique=True,
                partialFilterExpression={"association_key": {"$type": "string"}},
            ),
        ]
        use_state_management = True
