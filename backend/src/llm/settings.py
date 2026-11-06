"""Persistent chat model selections and credentials for the local workspace."""

import os
from typing import Annotated, Literal

from beanie import Document
from beanie.exceptions import CollectionWasNotInitialized
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
)
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from config import dialog_cfg, memory_cfg, rag_cfg


Provider = Literal["deepseek", "bailian"]
CredentialSource = Literal["stored", "environment", "missing"]
ModelName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

_SETTINGS_ID = "default"
_KEY_ENV = {"deepseek": "DEEPSEEK_API_KEY", "bailian": "BAILIAN_API_KEY"}
_DEFAULT_MODELS = {"deepseek": "deepseek-chat", "bailian": "qwen-plus"}


def _validate_key(value: SecretStr) -> SecretStr:
    key = value.get_secret_value().strip()
    if not 1 <= len(key) <= 1024 or any(not 33 <= ord(char) <= 126 for char in key):
        raise ValueError("API Key 必须为 1–1024 个不含空格的可打印 ASCII 字符")
    return SecretStr(key)


ApiKey = Annotated[SecretStr, AfterValidator(_validate_key)]


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider
    model: ModelName


class ModelSelections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialog: ModelSelection
    memory: ModelSelection
    rag: ModelSelection


class ProviderApiKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deepseek: ApiKey | None = None
    bailian: ApiKey | None = None


class ModelSettings(ModelSelections):
    api_keys: ProviderApiKeys = Field(
        default_factory=ProviderApiKeys, exclude=True, repr=False
    )

    def get_api_key(self, provider: Provider) -> str | None:
        stored_key = getattr(self.api_keys, provider)
        if stored_key is not None:
            return stored_key.get_secret_value()
        return os.getenv(_KEY_ENV[provider]) or None

    def credential_source(self, provider: Provider) -> CredentialSource:
        if getattr(self.api_keys, provider) is not None:
            return "stored"
        return "environment" if os.getenv(_KEY_ENV[provider]) else "missing"


class ModelSettingsDocument(Document, ModelSettings):
    id: str = _SETTINGS_ID

    class Settings:
        name = "model_settings"


class ModelSettingsUnavailableError(RuntimeError):
    """The settings collection could not be read or written."""


def _default_selection(config: dict, default_provider: Provider) -> ModelSelection:
    provider = config.get("llm_provider", default_provider)
    return ModelSelection(
        provider=provider, model=config.get("llm_model") or _DEFAULT_MODELS[provider]
    )


def _default_settings() -> ModelSettings:
    return ModelSettings(
        dialog=_default_selection(dialog_cfg, "deepseek"),
        memory=_default_selection(memory_cfg, "deepseek"),
        rag=_default_selection(rag_cfg, "bailian"),
    )


async def get_model_settings() -> ModelSettings:
    """Resolve saved selections or the existing TOML defaults."""
    try:
        collection = ModelSettingsDocument.get_pymongo_collection()
    except CollectionWasNotInitialized:
        return _default_settings()

    try:
        record = await collection.find_one({"_id": _SETTINGS_ID}, {"_id": False})
        if record is None:
            return _default_settings()
        return ModelSettings.model_validate(record)
    except (PyMongoError, ValidationError):
        raise ModelSettingsUnavailableError("无法读取模型配置。") from None


async def save_model_settings(settings: ModelSettings) -> ModelSettings:
    """Atomically replace selections and apply only explicit credential changes."""
    fields = settings.model_dump()
    removed_keys = {}
    for provider in settings.api_keys.model_fields_set:
        key = getattr(settings.api_keys, provider)
        field = f"api_keys.{provider}"
        if key is None:
            removed_keys[field] = ""
        else:
            fields[field] = key.get_secret_value()

    update = {"$set": fields}
    if removed_keys:
        update["$unset"] = removed_keys

    try:
        record = await ModelSettingsDocument.get_pymongo_collection().find_one_and_update(
            {"_id": _SETTINGS_ID},
            update,
            upsert=True,
            projection={"_id": False},
            return_document=ReturnDocument.AFTER,
        )
        return ModelSettings.model_validate(record)
    except (CollectionWasNotInitialized, PyMongoError, ValidationError):
        raise ModelSettingsUnavailableError("无法保存模型配置。") from None
