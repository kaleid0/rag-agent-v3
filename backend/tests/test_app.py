import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

import chromadb
from chromadb.config import Settings
from fastapi.testclient import TestClient
from pymongo import MongoClient

from config import mongo_cfg, rag_cfg
from mongo_test_server import temporary_mongo
from src.api.main import app
from src.database.chroma.chroma import close_chroma_client, override_chroma_client


class AppTests(unittest.TestCase):
    def test_health_and_api_without_model_keys(self):
        with patch.dict(os.environ):
            os.environ.pop("BAILIAN_API_KEY", None)
            os.environ.pop("DEEPSEEK_API_KEY", None)
            client = TestClient(app)
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            self.assertEqual(client.get("/openapi.json").status_code, 200)
            for fields in (
                {"chunk_size": 0},
                {"chunk_size": 50, "chunk_overlap": 50},
                {"split_method": "other"},
                {"retriever_type": "other"},
                {"name": "  "},
            ):
                response = client.post(
                    "/api/v1/knowledge-bases", json={"name": "Demo"} | fields
                )
                self.assertEqual(response.status_code, 422, response.text)


class FakeChat:
    async def async_stream_chat(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if "Which room" in prompt:
            if "B-204" not in prompt:
                raise AssertionError("Expected a retrieved excerpt in the prompt")
            yield "The meeting is in "
            yield "B-204."
        else:
            yield "Hello."


@unittest.skipUnless(os.environ.get("RAG_TEST_MONGOD"), "Set RAG_TEST_MONGOD to run")
class MongoAppTests(unittest.TestCase):
    def test_upload_default_index_and_chat(self):
        with temporary_mongo() as (root, uri):
            self.exercise_app(root, uri)

    def exercise_app(self, root, uri):
        rag_settings = {
            "file_storage_dir": str(root / "files"),
            "markdown_storage_dir": str(root / "markdown"),
            "chunk_dir": str(root / "chunks"),
            "query_route": False,
            "query_rewrite": False,
            "rerank": False,
            "context_retrieve": True,
        }
        embedding = Mock()
        embedding.embedding_call.side_effect = lambda texts: [
            [1.0, 0.0, 0.0] for _ in texts
        ]
        chroma = chromadb.Client(Settings(anonymized_telemetry=False, allow_reset=True))
        override_chroma_client(chroma)
        try:
            with (
                patch.dict(os.environ),
                patch.dict(mongo_cfg, {"uri": uri, "database": "integration"}),
                patch.dict(rag_cfg, rag_settings),
                patch("src.api.dependencies.get_configured_llm", return_value=FakeChat()) as chat,
                patch("src.document.parse.get_configured_llm"),
                patch(
                    "src.document.parse.llm_call",
                    new_callable=AsyncMock,
                    side_effect=lambda prompt_name, **kwargs: (
                        {"title": "Meeting"}
                        if prompt_name == "extract_title"
                        else {"abstract": "Meeting room", "keywords": ["meeting"]}
                    ),
                ),
                patch(
                    "src.rag.retriever.chroma_retriever.EmbeddingFunction.get_embedding_model",
                    return_value=embedding,
                ),
            ):
                os.environ.pop("BAILIAN_API_KEY", None)
                os.environ.pop("DEEPSEEK_API_KEY", None)
                with TestClient(app) as client:
                    self.check_endpoints(client, chat, embedding, chroma)
            for name in ("files", "markdown", "chunks"):
                self.assertEqual(list((root / name).iterdir()), [], name)
            self.assertEqual(chroma.list_collections(), [])
            with MongoClient(uri) as mongo:
                self.assertIn("session", mongo.integration.list_collection_names())
                self.assertNotIn("rag_agent", mongo.list_database_names())
        finally:
            chroma.reset()
            close_chroma_client()

    def check_endpoints(self, client, chat, embedding, chroma):
        api = "/api/v1"
        response = client.post(f"{api}/sessions", json={"user_id": "integration_user"})
        self.assertEqual(response.status_code, 201, response.text)
        session_id = response.json()["session_id"]
        chat.assert_not_called()

        plain = client.post(f"{api}/chat", json={"session_id": session_id, "content": "Hi"})
        self.assertEqual(plain.status_code, 200, plain.text)
        self.assertEqual(plain.json()["assistant_message"]["content"], "Hello.")
        embedding.embedding_call.assert_not_called()

        uploaded = client.post(
            f"{api}/document/upload",
            files={"file": ("meeting.md", b"# Meeting\n\nThe meeting is in B-204.\n", "text/markdown")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        doc_id = uploaded.json()["id"]
        docs = client.get(f"{api}/document").json()["documents"]
        self.assertTrue(docs[0]["metadata"]["is_prased"], docs[0])

        created = client.post(f"{api}/knowledge-bases", json={"name": "Meeting"})
        self.assertEqual(created.status_code, 201, created.text)
        kb_id = created.json()["id"]
        kb_path = f"{api}/knowledge-bases/{kb_id}"
        embed = embedding.embedding_call.side_effect
        embedding.embedding_call.side_effect = RuntimeError("Simulated embedding failure")
        failed = client.post(f"{kb_path}/files/{doc_id}")
        self.assertEqual(failed.status_code, 500, failed.text)
        self.assertEqual(client.get(kb_path).json()["document_ids"], [])
        self.assertEqual(chroma.list_collections(), [])

        embedding.embedding_call.side_effect = embed
        for _ in range(2):
            added = client.post(f"{kb_path}/files/{doc_id}")
            self.assertEqual(added.status_code, 200, added.text)
        self.assertEqual(client.get(kb_path).json()["document_ids"], [doc_id])

        chat_payload = {
            "session_id": session_id,
            "knowledge_base_id": kb_id,
            "content": "Which room is the meeting in?",
        }
        streamed = client.post(f"{api}/chat-stream", json=chat_payload)
        self.assertEqual(streamed.status_code, 200, streamed.text)
        self.assertEqual(streamed.text, "The meeting is in B-204.")
        complete = client.post(f"{api}/chat", json=chat_payload)
        self.assertEqual(complete.status_code, 200, complete.text)
        self.assertEqual(complete.json()["assistant_message"]["content"], streamed.text)
        messages = client.get(f"{api}/sessions/{session_id}").json()["messages"]
        self.assertEqual([message["role"] for message in messages], ["user", "assistant"] * 3)
        self.assertEqual(messages[-1]["content"], streamed.text)

        deleted = client.delete(kb_path)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(client.get(kb_path).status_code, 404)
        self.assertEqual(client.delete(f"{api}/document/{doc_id}").status_code, 200)
        self.assertEqual(client.get(f"{api}/document").json()["documents"], [])
        self.assertEqual(client.delete(f"{api}/sessions/{session_id}").status_code, 200)
        self.assertEqual(client.get(f"{api}/sessions/{session_id}").status_code, 404)
