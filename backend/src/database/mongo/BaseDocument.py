from datetime import datetime, timezone
from beanie import Document, Insert, Replace, before_event, Update
from pydantic import Field


class BaseDocument(Document):
    # 时间戳 Mixin
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 不需要 Save，因为 Save 通常是一个更高层次的方法
    @before_event([Replace, Insert, Update])
    def update_timestamp(self):
        self.updated_at = datetime.now(timezone.utc)
