from pydantic import Field
from pymongo import DESCENDING

from src.database import BaseDocument


# 数据库设计
# KnowledgeBase -> [CollectionRecord ...]
# DocumentRecord -> [CollectionRecord ...]
class KnowledgeBase(BaseDocument):
    """存储知识库信息"""

    name: str
    description: str = Field(default="")  # 知识库描述
    deleting: bool = False

    chunk_size: int = Field(default=300)  # 知识库文本块大小
    chunk_overlap: int = Field(default=50)  # 知识库文本块重叠大小
    split_method: str = Field(default="hierarchical")  #  hierarchical, recursive
    retriever_type: str = Field(default="hybrid")  # 检索器类型 vector, sparse, hybrid

    class Settings:
        name = "knowledge_base"  # MongoDB 集合名
        indexes = [[("created_at", DESCENDING)]]
        use_state_management = True
