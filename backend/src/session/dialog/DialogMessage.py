from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
from enum import Enum
import uuid


# 假设您的 RoleEnum 定义如下
class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


# 🌟 关键：继承自 pydantic.BaseModel
class DialogMessage(BaseModel):
    # 字段定义 (与 Pydantic Model 保持一致)
    role: RoleEnum
    content: str

    # 使用 Field(default_factory=...) 来处理可变类型和动态默认值
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 存储为字符串 UUID，并设置默认工厂
    # TODO 删除这条
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def message(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}
