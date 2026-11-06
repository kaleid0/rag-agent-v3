import asyncio
import logging
import os
from pathlib import PureWindowsPath

from bson import ObjectId
from chromadb.errors import NotFoundError

# from llm.Message import Messages
from .LongTermMemory import LongTermMemory
from src.session import Session
from src.prompt import llm_call
from src.llm.factory import AdapterResult, AdapterSource, resolve_adapter
from src.rag import ingest_memory, RetrievePipelineProtocol
from src.database import delete_content_from_collection
from config import memory_cfg

logger = logging.getLogger(__name__)


def _memory_user_id(session: Session) -> str | None:
    user_id = session.user_id
    # User IDs name both a local pickle and a Chroma collection. Document collections use ObjectIds.
    if (
        not user_id
        or user_id in {".", ".."}
        or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in user_id)
        or PureWindowsPath(f"{user_id}.pkl").is_reserved()
        or ObjectId.is_valid(user_id)
    ):
        return None
    return user_id


class MemoryManager:

    def __init__(
        self,
        llm_adapter: AdapterSource,
        short_term_memory_period: int = 10,
        retrieve_pipeline: RetrievePipelineProtocol | None = None,
        *,
        retrieve_enabled: bool = False,
        retrieve_timeout_seconds: float = 1.0,
    ) -> None:
        self._llm_adapter = llm_adapter
        self.short_term_memory_period = short_term_memory_period
        self.retrieve_pipeline = retrieve_pipeline
        self.retrieve_enabled = retrieve_enabled
        self.retrieve_timeout_seconds = retrieve_timeout_seconds

    @property
    def llm_adapter(self) -> AdapterResult:
        adapter = self._llm_adapter
        return adapter() if callable(adapter) else adapter

    def should_update_short_term_memory(self, session: Session) -> bool:
        return (
            session.message_count - session.last_summary_count
            == self.short_term_memory_period * 2
        )

    async def update_short_term_memory(self, session: Session):
        new_messages = session.get_history(
            start_rev_index=session.last_summary_count + 1,
            end_rev_index=session.message_count - self.short_term_memory_period,
        )

        adapter = await resolve_adapter(self.llm_adapter)
        new_memory = await llm_call(
            prompt_name="short_term_memory_summary",
            llm=adapter,
            args={"messages": new_messages},
        )
        if len(session.memory) > 0:
            new_memory = await llm_call(
                prompt_name="memory_merge",
                llm=adapter,
                args={
                    "existing_summary": session.memory,
                    "new_summary": new_memory,
                },
            )

        session.memory = new_memory
        session.last_summary_count = (
            session.message_count - self.short_term_memory_period
        )
        await session.save_changes()

    async def update_long_term_memory(self, session: Session):
        history = session.messages
        long_term_memory = await LongTermMemory.find_one(
            LongTermMemory.user_id == session.user_id
        )

        adapter = await resolve_adapter(self.llm_adapter)
        new_memory = await llm_call(
            prompt_name="long_term_memory_summary",
            llm=adapter,
            args={"messages": str(history)},
        )
        if long_term_memory and len(long_term_memory.memory) > 0:
            new_memory = await llm_call(
                prompt_name="memory_merge",
                llm=adapter,
                args={
                    "existing_summary": long_term_memory.memory,
                    "new_summary": new_memory,
                },
            )

        session.set_long_term_memory(new_memory)

    async def ingest_memory_to_rag(self, session: Session):
        user_id = _memory_user_id(session)
        if user_id is None:
            return
        history = session.get_history()
        chunk_save_path = os.path.join(memory_cfg["chunk_dir"], user_id + ".pkl")
        await asyncio.to_thread(
            ingest_memory,
            user_id=user_id,
            messages=history,
            chunk_save_path=chunk_save_path,
            session_id=str(session.id),
        )

    async def retrieve_memory_from_rag(self, query: str, session: Session) -> str:
        if not self.retrieve_enabled or not self.retrieve_pipeline:
            return ""
        user_id = _memory_user_id(session)
        if user_id is None:
            return ""

        try:
            retrieved_memories = await asyncio.wait_for(
                self.retrieve_pipeline.retrieve_memory(query=query, user_id=user_id),
                timeout=self.retrieve_timeout_seconds,
            )
        except TimeoutError:
            logger.warning("Session memory lookup timed out for session %s", session.id)
            return ""
        except Exception:
            logger.warning(
                "Session memory lookup failed for session %s", session.id, exc_info=True
            )
            return ""

        session.set_retrieved_memory(retrieved_memories)

        return retrieved_memories

    async def delete_memory_from_rag(self, session: Session):
        user_id = _memory_user_id(session)
        if user_id is None:
            return
        try:
            await asyncio.to_thread(
                delete_content_from_collection,
                name=user_id,
                metadata={"session_id": str(session.id)},
            )
        except NotFoundError:
            pass

    async def memory_assemble(
        self,
    ): ...
