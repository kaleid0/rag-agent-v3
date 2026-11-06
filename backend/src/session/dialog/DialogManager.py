import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import datetime, timezone

from fastapi import HTTPException
from openai import APIError

from src.llm import BaseChatAdapter
from src.llm.factory import AdapterResult, AdapterSource, resolve_adapter
from src.rag import RetrievePipelineProtocol

from .DialogMessage import DialogMessage, RoleEnum
from src.session.odm.Session import Session

from src.prompt import llm_chat_stream, llm_call


DialogTurn = tuple[DialogMessage, DialogMessage]


class DialogManager:
    """协调知识库检索、回答生成和完整轮次的保存。"""

    def __init__(
        self,
        llm_adapter: AdapterSource,
        retrieve_pipeline: RetrievePipelineProtocol | None = None,
    ):
        self.retrieve_pipeline = retrieve_pipeline
        self._llm_adapter = llm_adapter

    @property
    def llm_adapter(self) -> AdapterResult:
        adapter = self._llm_adapter
        return adapter() if callable(adapter) else adapter

    async def set_llm_adapter(self, llm_adapter: BaseChatAdapter):
        self._llm_adapter = llm_adapter

    async def set_retrieve_pipeline(self, retrieve_pipeline: RetrievePipelineProtocol):
        self.retrieve_pipeline = retrieve_pipeline

    async def generate_response(
        self,
        session: Session,
        message_content: str,
        message_metadata: dict | None = None,
        knowledge_base_id: str | None = None,
    ) -> DialogTurn:
        events = await self._prepare_response(
            session, message_content, message_metadata, knowledge_base_id
        )
        async with aclosing(events):
            async for event in events:
                if isinstance(event, tuple):
                    return event
        raise RuntimeError("Model response ended before the turn was saved")

    async def generate_response_stream(
        self,
        session: Session,
        message_content: str,
        message_metadata: dict | None = None,
        knowledge_base_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        events = await self._prepare_response(
            session, message_content, message_metadata, knowledge_base_id
        )

        async def token_stream():
            async with aclosing(events):
                async for event in events:
                    if isinstance(event, str):
                        yield event

        return token_stream()

    async def _prepare_response(
        self,
        session: Session,
        message_content: str,
        message_metadata: dict | None,
        knowledge_base_id: str | None,
    ) -> AsyncGenerator[str | DialogTurn, None]:
        metadata = dict(message_metadata or {})
        if knowledge_base_id and self.retrieve_pipeline:
            retrieved = await self.retrieve_pipeline.retrieve_knowledge_base(
                query=message_content,
                knowledge_base_id=knowledge_base_id,
            )
            metadata["retrieved_context"] = retrieved
            prompt_name = "RAG_answer"
            prompt_args = {"information": retrieved, "question": message_content}
        else:
            prompt_name = "plain_chat"
            prompt_args = {"user_message": message_content}

        adapter = await resolve_adapter(self.llm_adapter)
        try:
            stream_source = await llm_chat_stream(
                prompt_name, adapter, session.messages, prompt_args
            )
            if asyncio.iscoroutine(stream_source):
                stream_source = await stream_source
        except APIError:
            raise HTTPException(status_code=502, detail="Model request failed") from None

        async def response_events():
            chunks = []
            try:
                async with aclosing(stream_source):
                    async for chunk in stream_source:
                        if chunk:
                            chunks.append(chunk)
                            yield chunk
            except APIError:
                raise RuntimeError("Model request failed") from None

            if not chunks:
                raise HTTPException(
                    status_code=502, detail="Model returned an empty response"
                )

            user_message = DialogMessage(
                role=RoleEnum.user,
                content=message_content,
                metadata=metadata,
            )
            assistant_message = DialogMessage(
                role=RoleEnum.assistant,
                content="".join(chunks),
                metadata={"generated_at": datetime.now(timezone.utc).isoformat()},
            )
            if not await session.append_turn(user_message, assistant_message):
                raise HTTPException(status_code=404, detail="Session not found")
            yield user_message, assistant_message

        return response_events()

    async def generate_dialog_title(
        self,
        session: Session,
    ) -> str:
        """为会话生成标题"""
        title = await llm_call(
            prompt_name="generate_dialog_title",
            llm=await resolve_adapter(self.llm_adapter),
            args={"text": session.messages},
        )
        session.metadata["title"] = title
        await session.save_changes()
        return title
