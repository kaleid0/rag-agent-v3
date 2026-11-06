import asyncio
from collections.abc import AsyncGenerator
from weakref import WeakValueDictionary

from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import HTTPException

from .dialog.DialogManager import DialogManager, DialogTurn
from .dialog.DialogMessage import DialogMessage
from .odm.Session import Session
from .memory.MemoryManager import MemoryManager
from src.prompt import get_prompt


# SessionService -> DialogManager（业务层） -> Session.messages（数据层）, Session.memory（数据层）
# SessionService -> MemoryManager（业务层） -› Session.memory（数据层）, LongTermMemory (user_id, RAG)
class SessionService:
    def __init__(self, dialog_manager: DialogManager, memory_manager: MemoryManager):
        self.dialog_manager = dialog_manager
        self.memory_manager = memory_manager
        self._lifecycle_locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )

    async def create_session(
        self,
        user_id: str,
        system_prompt: str = "default_system_prompt",
        metadata: dict | None = None,
    ) -> Session:
        session = Session(
            user_id=user_id,
            system_prompt=get_prompt(system_prompt, "system"),
            metadata=metadata or {},
        )
        session.set_long_term_memory([])
        session.set_retrieved_memory("")

        await session.insert()
        if session.id is None:
            raise RuntimeError("Failed to create session - ID is None")
        return session

    async def get_session(self, session_id: str) -> Session:
        try:
            session_key = PydanticObjectId(session_id)
        except InvalidId as exc:
            raise HTTPException(status_code=422, detail="Invalid session ID") from exc
        session = await Session.get(session_key)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    def _lifecycle_lock(self, session_id: str) -> asyncio.Lock:
        # 退出写入和删除清理使用同一把锁，避免本进程在删除后重新写入记忆。
        return self._lifecycle_locks.setdefault(session_id.lower(), asyncio.Lock())

    async def delete_session(self, session_id: str):
        async with self._lifecycle_lock(session_id):
            session = await self.get_session(session_id)
            await self.memory_manager.delete_memory_from_rag(session)
            await session.delete()

    async def exit_session(self, session_id: str) -> str:
        async with self._lifecycle_lock(session_id):
            try:
                session = await self.get_session(session_id)
            except HTTPException as exc:
                if exc.status_code == 404:
                    return "Session no longer exists."
                raise

            if not session.dialog_messages:
                # A chat may finish while exit is queued. Only delete a still-empty session.
                await session.get_pymongo_collection().delete_one(
                    {"_id": session.id, "dialog_messages.0": {"$exists": False}}
                )
                return "Empty session exit processed."

            results = await asyncio.gather(
                self.memory_manager.update_long_term_memory(session),
                self.memory_manager.ingest_memory_to_rag(session),
                self.dialog_manager.generate_dialog_title(session),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            return "Session exited successfully."

    async def send_message(
        self,
        session_id: str,
        content: str,
        metadata: dict | None = None,
        kb_id: str | None = None,
    ) -> DialogTurn:
        session = await self._prepare_session_for_message(session_id, content)
        return await self.dialog_manager.generate_response(
            session=session,
            message_content=content,
            message_metadata=metadata,
            knowledge_base_id=kb_id,
        )

    async def send_message_stream(
        self,
        session_id: str,
        content: str,
        metadata: dict | None = None,
        kb_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        session = await self._prepare_session_for_message(session_id, content)
        return await self.dialog_manager.generate_response_stream(
            session=session,
            message_content=content,
            message_metadata=metadata,
            knowledge_base_id=kb_id,
        )

    async def _prepare_session_for_message(
        self, session_id: str, content: str
    ) -> Session:
        session = await self.get_session(session_id)
        await self.memory_manager.retrieve_memory_from_rag(query=content, session=session)
        if self.memory_manager.should_update_short_term_memory(session):
            asyncio.create_task(self.memory_manager.update_short_term_memory(session))
        return session

    async def get_session_history(self, session_id: str) -> list[dict[str, str]]:
        session = await self.get_session(session_id)
        return session.get_history()

    async def get_messages(
        self, session_id: str, offset: int = 0, limit: int = 20
    ) -> list[DialogMessage]:
        session = await self.get_session(session_id)
        end = max(0, len(session.dialog_messages) - offset)
        return session.dialog_messages[max(0, end - limit) : end]

    async def list_sessions(
        self, user_id: str, offset: int = 0, limit: int = 20
    ) -> list[Session]:
        return (
            await Session.find({"user_id": user_id})
            .sort("created_at", "_id")
            .skip(offset)
            .limit(limit)
            .to_list()
        )
