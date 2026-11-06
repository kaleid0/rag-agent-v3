import os
import unittest
from unittest.mock import call, patch

from fastapi.testclient import TestClient

from config import dialog_cfg, memory_cfg, mongo_cfg, rag_cfg
from mongo_test_server import temporary_mongo
from src.api.main import app
from src.llm.factory import get_configured_llm


SETTINGS_PATH = "/api/v1/model-settings"
MODEL_SETTINGS = {
    "dialog": {"provider": "deepseek", "model": "test-chat"},
    "memory": {"provider": "bailian", "model": "test-memory"},
    "rag": {"provider": "bailian", "model": "test-rag"},
}


class ModelSettingsValidationTests(unittest.TestCase):
    def test_invalid_requests_do_not_echo_api_keys(self):
        client = TestClient(app)
        marker = "test-secret-never-echo"
        payloads = (
            [MODEL_SETTINGS | {"api_keys": {"deepseek": marker}}],
            MODEL_SETTINGS | {"api_keys": {"deepseek": {"value": marker}}},
            MODEL_SETTINGS | {"api_keys": {marker: "unknown-provider-key"}},
            MODEL_SETTINGS | {"api_keys": {"deepseek": marker + "\ninvalid"}},
            MODEL_SETTINGS
            | {
                "dialog": {"provider": "unknown", "model": "test-chat"},
                "api_keys": {"deepseek": marker},
            },
            MODEL_SETTINGS
            | {
                "dialog": {"provider": "deepseek", "model": "  "},
                "api_keys": {"deepseek": marker},
            },
        )

        for index, payload in enumerate(payloads):
            with self.subTest(index=index):
                response = client.put(SETTINGS_PATH, json=payload)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn(marker, response.text)

    def test_browser_cannot_update_settings_from_another_origin(self):
        response = TestClient(app).put(
            SETTINGS_PATH, json=MODEL_SETTINGS, headers={"Origin": "https://other.example"}
        )
        self.assertEqual(response.status_code, 403)


class FakeChat:
    async def async_stream_chat(self, messages, **kwargs):
        yield "Configured chat"


@unittest.skipUnless(os.environ.get("RAG_TEST_MONGOD"), "Set RAG_TEST_MONGOD to run")
class MongoModelSettingsTests(unittest.TestCase):
    def test_save_preserves_omitted_credentials_and_persists_across_restart(self):
        roles = {
            "dialog": dialog_cfg,
            "memory": memory_cfg,
            "rag": rag_cfg,
        }
        defaults = {
            role: {
                "provider": settings.get("llm_provider", "deepseek"),
                "model": settings.get("llm_model", "deepseek-chat"),
            }
            for role, settings in roles.items()
        }
        environment_key = "test-key-from-environment"
        stored_key = "test-key-from-settings"
        bailian_key = "test-bailian-key-from-settings"
        updated_settings = MODEL_SETTINGS | {
            "dialog": {"provider": "deepseek", "model": "test-chat-v2"}
        }
        stored_credentials = {"credentials": {"deepseek": "stored", "bailian": "stored"}}

        with (
            temporary_mongo() as (_, uri),
            patch.dict(mongo_cfg, {"uri": uri, "database": "model_settings_test"}),
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": environment_key}),
        ):
            os.environ.pop("BAILIAN_API_KEY", None)
            with TestClient(app) as client:
                initial = client.get(SETTINGS_PATH)
                self.assertEqual(initial.status_code, 200, initial.text)
                self.assertEqual(
                    initial.json(),
                    defaults | {"credentials": {"deepseek": "environment", "bailian": "missing"}},
                )

                saved = client.put(
                    SETTINGS_PATH,
                    json=MODEL_SETTINGS
                    | {"api_keys": {"deepseek": stored_key, "bailian": bailian_key}},
                    headers={"Origin": "http://testserver"},
                )
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json(), MODEL_SETTINGS | stored_credentials)
                edited = client.put(SETTINGS_PATH, json=updated_settings)
                self.assertEqual(edited.status_code, 200, edited.text)
                self.assertEqual(edited.json(), updated_settings | stored_credentials)

            with (
                TestClient(app) as client,
                patch("src.llm.factory.DeepseekChatAdapter") as deepseek_adapter,
                patch("src.llm.factory.BailianChatAdapter") as bailian_adapter,
            ):
                persisted = client.get(SETTINGS_PATH)
                self.assertEqual(persisted.status_code, 200, persisted.text)
                self.assertEqual(persisted.json(), updated_settings | stored_credentials)

                assert client.portal is not None
                for role in ("dialog", "memory", "rag"):
                    client.portal.call(get_configured_llm, role)
                deepseek_adapter.assert_called_once_with(api_key=stored_key, model="test-chat-v2")
                self.assertEqual(bailian_adapter.call_args_list, [
                    call(api_key=bailian_key, model="test-memory"),
                    call(api_key=bailian_key, model="test-rag"),
                ])

                cleared = client.put(
                    SETTINGS_PATH, json=updated_settings | {"api_keys": {"deepseek": None}}
                )
                self.assertEqual(cleared.status_code, 200, cleared.text)
                self.assertEqual(
                    cleared.json(),
                    updated_settings | {"credentials": {"deepseek": "environment", "bailian": "stored"}},
                )
                self.assertEqual(client.get(SETTINGS_PATH).json(), cleared.json())
                client.portal.call(get_configured_llm, "dialog")
                deepseek_adapter.assert_called_with(api_key=environment_key, model="test-chat-v2")

    def test_chat_uses_new_key_for_same_model_without_restarting(self):
        model = "test-live-chat"
        settings = MODEL_SETTINGS | {"dialog": {"provider": "deepseek", "model": model}}
        keys = ("test-key-before-rotation", "test-key-after-rotation")

        with (
            temporary_mongo() as (_, uri),
            patch.dict(mongo_cfg, {"uri": uri, "database": "model_settings_test"}),
            patch("src.llm.factory.DeepseekChatAdapter", return_value=FakeChat()) as adapter,
            TestClient(app) as client,
        ):
            created = client.post("/api/v1/sessions", json={"user_id": "model-settings-test"})
            self.assertEqual(created.status_code, 201, created.text)
            chat = {"session_id": created.json()["session_id"], "content": "Hello"}
            for key in keys:
                saved = client.put(SETTINGS_PATH, json=settings | {"api_keys": {"deepseek": key}})
                self.assertEqual(saved.status_code, 200, saved.text)
                answer = client.post("/api/v1/chat-stream", json=chat)
                self.assertEqual(answer.status_code, 200, answer.text)
                self.assertEqual(answer.text, "Configured chat")

            self.assertEqual(adapter.call_args_list, [call(api_key=key, model=model) for key in keys])
