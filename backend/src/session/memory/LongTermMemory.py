from pydantic import Field
from pymongo import ASCENDING
from src.database import BaseDocument


class LongTermMemory(BaseDocument):
    user_id: str = Field(...)
    memory: list[dict] = Field(default_factory=list)
    metadata: dict = {}

    class Settings:
        name = "long_term_memory"  # MongoDB 集合名
        indexes = [[("user_id", ASCENDING)]]
        use_state_management = True
