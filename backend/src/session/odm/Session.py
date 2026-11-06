from datetime import datetime, timezone

from pydantic import Field, PrivateAttr
from pymongo import ASCENDING, DESCENDING

# from src.memory import ShortTermMemory
from src.session.dialog.DialogMessage import DialogMessage
from src.database import BaseDocument


class Session(BaseDocument):
    user_id: str | None = None
    metadata: dict = Field(default_factory=dict)

    message_count: int = Field(default=0)
    last_summary_count: int = Field(default=-1)
    # last_ingest_count: int = Field(default=-1) # XXX

    system_prompt: str = Field(default="")  # 系统消息
    dialog_messages: list[DialogMessage] = Field(default_factory=list)
    memory: list[dict] = Field(default_factory=list)

    _long_term_memory: list[dict] = PrivateAttr(default_factory=list)
    _retrieved_memory: str = PrivateAttr(default="")

    class Settings:
        name = "session"  # MongoDB 集合名
        # 定义索引列表
        indexes = [
            # 复合索引：(user_id 升序, created_at 降序)
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            # user_id 上的单键索引
            "user_id",
        ]
        use_state_management = True

    async def append_turn(
        self, user_message: DialogMessage, assistant_message: DialogMessage
    ) -> bool:
        result = await self.get_pymongo_collection().update_one(
            {"_id": self.id},
            {
                "$push": {
                    "dialog_messages": {
                        "$each": [
                            user_message.model_dump(),
                            assistant_message.model_dump(),
                        ]
                    }
                },
                "$inc": {"message_count": 2},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=False,
        )
        return result.matched_count == 1

    def get_history(
        self,
        limit: int | None = None,
        start_rev_index: int | None = None,
        end_rev_index: int | None = None,
    ) -> list[dict[str, str]]:
        """排除 system message
        获取会话历史消息的切片。"""
        msgs = [msg.message for msg in self.dialog_messages]

        if not limit and not start_rev_index and not end_rev_index:
            return msgs

        if limit:
            return msgs[-limit:]

        length = len(msgs)
        start_rev_index = start_rev_index or 0
        end_rev_index = end_rev_index or length
        if (
            end_rev_index <= start_rev_index
            or end_rev_index <= 0
            or start_rev_index <= 0
        ):
            raise ValueError(
                "错误: 参数设置无效。请确保 end_rev_index > start_rev_index 且两者都大于 0。"
            )
        if length < end_rev_index:
            raise ValueError(
                f"警告: 数组长度 ({length}) 小于 {end_rev_index}，无法安全提取。"
            )

        slice_start_index = -end_rev_index

        # 2. 切片的结束负索引（不包含）
        # 要包含倒数第 start_rev_index 个元素，切片的结束点必须是其负索引加 1
        slice_end_index = -start_rev_index + 1

        # 执行切片操作
        return msgs[slice_start_index:slice_end_index]

    def set_long_term_memory(self, long_term_memory: list[dict]):
        self._long_term_memory = long_term_memory

    def set_retrieved_memory(self, retrieved_memory: str):
        self._retrieved_memory = retrieved_memory

    @property
    def messages(self) -> list[dict[str, str]]:
        """
        assamble system message and dialog messages, for LLM input.
        return: system message + dialog messages
        """
        # system_message = self.get_system_message()
        # msg = self.get_history(start_rev_index=self.last_summary_count + 1)
        # return [system_message] + msg
        return [self.get_system_message()] + self.get_history(
            start_rev_index=self.last_summary_count + 1
        )

    def get_system_message(self) -> dict[str, str]:
        content = self.system_prompt.format(
            long_term_memory=(
                self._long_term_memory if hasattr(self, "long_term_memory") else ""
            ),
            retrieved_memory=(
                self._retrieved_memory if hasattr(self, "retrieved_memory") else ""
            ),
            short_term_memory=self.memory if self.memory else "",
        )
        return {"role": "system", "content": content}


# 保存和加载由 ODM 自动完成
# s = Session(user_id="u1", messages=[Message(role=RoleEnum.user, content="hi")])
# await s.insert()
# loaded = await Session.get(s.id)
# print(loaded.dict())

"""
[
{"role": "system", "content": "..."},
{"role": "user", "content": "..."},
{"role": "assistant", "content": "..."},
{"role": "user", "content": "..."},
...
]
"""
