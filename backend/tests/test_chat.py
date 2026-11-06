import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from beanie import PydanticObjectId
from chromadb.errors import NotFoundError
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from requests import Response

from src.api.dependencies import get_session_service
from src.api.routers.chat import router
from src.session import DialogManager, MemoryManager, Session, SessionService
from src.session.dialog.DialogMessage import DialogMessage, RoleEnum


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session_id = PydanticObjectId()
        self.user_id = "test-user"
        self.messages = []
        self.message_count = 0
        self.session_exists = True
        self.collection = SimpleNamespace(
            update_one=AsyncMock(side_effect=self.update_session),
            delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
        )
        self.get_session = self.enterContext(patch.object(Session, "get", side_effect=self.load_session))
        self.enterContext(patch.object(Session, "get_pymongo_collection", return_value=self.collection))
        self.adapter_factory = Mock(return_value=object())
        self.service = SessionService(
            DialogManager(self.adapter_factory),
            MemoryManager(self.adapter_factory),
        )
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_session_service] = lambda: self.service
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def load_session(self, session_id):
        if not self.session_exists or session_id != self.session_id:
            return None
        return Session.model_construct(
            id=self.session_id,
            user_id=self.user_id,
            dialog_messages=[DialogMessage.model_validate(message) for message in self.messages],
            message_count=self.message_count,
        )

    async def update_session(self, selector, changes, *, upsert):
        self.assertEqual(selector, {"_id": self.session_id})
        self.assertFalse(upsert)
        if not self.session_exists:
            return SimpleNamespace(matched_count=0)
        self.messages.extend(changes["$push"]["dialog_messages"]["$each"])
        self.message_count += changes["$inc"]["message_count"]
        return SimpleNamespace(matched_count=1)

    async def test_stream_and_nonstream_commit_separate_turns_from_stale_snapshots(self):
        arrived = 0
        both_started = asyncio.Event()

        async def model_stream(prompt_name, adapter, messages, args):
            self.assertEqual(prompt_name, "plain_chat")
            self.assertEqual(len(messages), 1)

            async def chunks():
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), timeout=1)
                yield args["user_message"]
                yield " reply"

            return chunks()

        with patch("src.session.dialog.DialogManager.llm_chat_stream", side_effect=model_stream):
            complete, stream = await asyncio.gather(
                self.client.post(
                    "/api/v1/chat",
                    json={"session_id": str(self.session_id), "content": "first", "metadata": {"source": "test"}},
                ),
                self.client.post(
                    "/api/v1/chat-stream",
                    json={"session_id": str(self.session_id), "content": "second"},
                ),
            )

        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.json()["user_message"]["metadata"], {"source": "test"})
        self.assertEqual(complete.json()["assistant_message"]["content"], "first reply")
        self.assertEqual(stream.status_code, 200)
        self.assertEqual(stream.headers["content-type"], "text/plain; charset=utf-8")
        self.assertEqual(stream.text, "second reply")
        self.assertEqual(self.get_session.await_count, 2)
        self.assertEqual(self.collection.update_one.await_count, 2)
        self.assertEqual(self.message_count, 4)
        self.assertEqual([message["role"] for message in self.messages], ["user", "assistant"] * 2)
        self.assertEqual(
            {tuple(item["content"] for item in self.messages[i : i + 2]) for i in (0, 2)},
            {("first", "first reply"), ("second", "second reply")},
        )

    async def test_interrupted_stream_and_closed_consumer_do_not_commit(self):
        closed = asyncio.Event()

        async def failing_chunks():
            try:
                yield "partial"
                raise RuntimeError("upstream interrupted")
            finally:
                closed.set()

        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect), patch(
                "src.session.dialog.DialogManager.llm_chat_stream", return_value=failing_chunks()
            ):
                closed.clear()
                stream = await self.service.send_message_stream(str(self.session_id), "question")
                self.assertEqual(await anext(stream), "partial")
                if disconnect:
                    await stream.aclose()
                else:
                    with self.assertRaisesRegex(RuntimeError, "upstream interrupted"):
                        await anext(stream)
                self.assertTrue(closed.is_set())
        self.collection.update_one.assert_not_awaited()

    async def test_delete_during_generation_cannot_recreate_the_session(self):
        async def chunks():
            self.session_exists = False
            yield "answer"

        with patch("src.session.dialog.DialogManager.llm_chat_stream", return_value=chunks()):
            response = await self.client.post(
                "/api/v1/chat", json={"session_id": str(self.session_id), "content": "question"}
            )
        self.assertEqual(response.status_code, 404)
        self.collection.update_one.assert_awaited_once()
        self.assertEqual(self.messages, [])

    async def test_message_pagination_includes_metadata_and_handles_short_history(self):
        self.messages = [
            DialogMessage(role=RoleEnum.user, content="one", metadata={"source": "test"}).model_dump(),
            DialogMessage(role=RoleEnum.assistant, content="two").model_dump(),
            DialogMessage(role=RoleEnum.user, content="three").model_dump(),
        ]
        route = f"/api/v1/sessions/{self.session_id}/messages"
        default_page = await self.client.get(route)
        self.assertEqual(default_page.status_code, 200)
        self.assertEqual([message["content"] for message in default_page.json()], ["one", "two", "three"])
        self.assertIsNotNone(default_page.json()[0]["timestamp"])
        self.assertEqual(default_page.json()[0]["metadata"], {"source": "test"})

        older_page = await self.client.get(route, params={"offset": 1, "limit": 2})
        self.assertEqual([message["content"] for message in older_page.json()], ["one", "two"])
        self.assertEqual((await self.client.get(route, params={"offset": 100})).json(), [])
        self.assertEqual((await self.client.get(route, params={"offset": -1})).status_code, 422)

    async def test_session_list_applies_sort_offset_and_limit_without_initializing_models(self):
        query = Mock()
        query.sort.return_value = query.skip.return_value = query.limit.return_value = query
        query.to_list = AsyncMock(return_value=[])
        with patch.object(Session, "find", return_value=query) as find:
            response = await self.client.get(
                "/api/v1/session-list", params={"user_id": "test-user", "offset": 3, "limit": 4}
            )

        self.assertEqual(response.status_code, 200)
        find.assert_called_once_with({"user_id": "test-user"})
        query.sort.assert_called_once_with("created_at", "_id")
        query.skip.assert_called_once_with(3)
        query.limit.assert_called_once_with(4)
        self.adapter_factory.assert_not_called()

    async def test_session_list_can_page_newest_first(self):
        query = Mock()
        query.sort.return_value = query.skip.return_value = query.limit.return_value = query
        query.to_list = AsyncMock(return_value=[])
        with patch.object(Session, "find", return_value=query):
            response = await self.client.get(
                "/api/v1/session-list", params={"user_id": self.user_id, "offset": 3, "limit": 4, "order": "desc"}
            )
            invalid = await self.client.get(
                "/api/v1/session-list", params={"user_id": self.user_id, "order": "invalid"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(invalid.status_code, 422)
        query.sort.assert_called_once_with("-created_at", "-_id")
        query.skip.assert_called_once_with(3)
        query.limit.assert_called_once_with(4)

    async def test_exit_checks_existence_and_only_deletes_empty_session(self):
        route = f"/api/v1/sessions/{self.session_id}/exit"
        self.assertEqual((await self.client.post(route)).status_code, 202)
        self.collection.delete_one.assert_awaited_once_with(
            {"_id": self.session_id, "dialog_messages.0": {"$exists": False}}
        )
        self.session_exists = False
        self.assertEqual((await self.client.post(route)).status_code, 404)

    async def test_delete_targets_user_collection_and_tolerates_missing_collection(self):
        route = f"/api/v1/sessions/{self.session_id}"
        with (
            patch("src.session.memory.MemoryManager.delete_content_from_collection", side_effect=NotFoundError("missing")) as cleanup,
            patch.object(Session, "delete", new_callable=AsyncMock) as delete,
        ):
            self.assertEqual((await self.client.delete(route)).status_code, 200)
            cleanup.assert_called_once_with(name="test-user", metadata={"session_id": str(self.session_id)})
            delete.assert_awaited_once()
        self.adapter_factory.assert_not_called()

    async def test_optional_memory_failure_or_timeout_keeps_chat_available(self):
        async def delayed_memory(**kwargs):
            await asyncio.Event().wait()

        async def chunks():
            yield "answer"

        for retrieve in (AsyncMock(side_effect=RuntimeError("memory unavailable")), AsyncMock(side_effect=delayed_memory)):
            self.service.memory_manager = MemoryManager(
                self.adapter_factory,
                retrieve_pipeline=SimpleNamespace(retrieve_memory=retrieve),
                retrieve_enabled=True,
                retrieve_timeout_seconds=0.01,
            )
            with (
                self.assertLogs("src.session.memory.MemoryManager", level="WARNING"),
                patch("src.session.dialog.DialogManager.llm_chat_stream", return_value=chunks()),
            ):
                response = await self.client.post(
                    "/api/v1/chat", json={"session_id": str(self.session_id), "content": "question"}
                )
            self.assertEqual(response.status_code, 200)
            retrieve.assert_awaited_once()

    async def test_unsafe_user_ids_cannot_read_write_or_delete_memory_indexes(self):
        retrieve = AsyncMock()
        manager = MemoryManager(
            self.adapter_factory,
            retrieve_pipeline=SimpleNamespace(retrieve_memory=retrieve),
            retrieve_enabled=True,
        )
        unsafe_ids = (
            "../outside",
            "/outside",
            r"C:\outside",
            "C:outside",
            r"\\host\share",
            "NUL.txt",
            "COM\u00b9",
            "0123456789abcdefABCDEF01",
        )

        with (
            patch("src.session.memory.MemoryManager.ingest_memory") as ingest,
            patch("src.session.memory.MemoryManager.delete_content_from_collection") as delete,
        ):
            for user_id in unsafe_ids:
                with self.subTest(user_id=user_id):
                    session = Session.model_construct(id=self.session_id, user_id=user_id)
                    self.assertEqual(await manager.retrieve_memory_from_rag("question", session), "")
                    await manager.ingest_memory_to_rag(session)
                    await manager.delete_memory_from_rag(session)

        retrieve.assert_not_awaited()
        ingest.assert_not_called()
        delete.assert_not_called()

        async def chunks():
            yield "answer"

        self.user_id = "../outside"
        self.service.memory_manager = manager
        with patch("src.session.dialog.DialogManager.llm_chat_stream", return_value=chunks()):
            response = await self.client.post(
                "/api/v1/chat", json={"session_id": str(self.session_id), "content": "question"}
            )
        self.assertEqual(response.status_code, 200)
        retrieve.assert_not_awaited()


class StreamlitTests(unittest.TestCase):
    def test_utf8_stream_decodes_across_network_chunk_boundaries(self):
        with patch("streamlit.session_state", MagicMock()):
            from streamlit_demo import send_message_stream

        raw_text = "你好 👋".encode("utf-8")
        response = Response()
        response.status_code = 200
        response.raw = Mock()
        response.raw.stream.return_value = iter((raw_text[:2], raw_text[2:8], raw_text[8:]))
        with patch("streamlit_demo.requests.post", return_value=response):
            self.assertEqual("".join(send_message_stream("session", "message")), "你好 👋")
