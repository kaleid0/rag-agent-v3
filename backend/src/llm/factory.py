import os
from collections.abc import Awaitable, Callable
from functools import lru_cache
from inspect import isawaitable
from typing import Literal

from .adapter.DeepseekChatAdapter import DeepseekChatAdapter
from .adapter.BaseChatAdapter import BaseChatAdapter
from .adapter.BailianChatAdapter import BailianChatAdapter
from .settings import get_model_settings


ModelRole = Literal["dialog", "memory", "rag"]
AdapterResult = BaseChatAdapter | Awaitable[BaseChatAdapter]
AdapterSource = BaseChatAdapter | Callable[[], AdapterResult]


def get_llm(
    llm_provider: str, model: str, api_key: str | None = None
) -> BaseChatAdapter:
    """按供应商、模型和实际密钥复用适配器。"""
    if llm_provider == "deepseek":
        return _get_adapter(
            DeepseekChatAdapter,
            model or "deepseek-chat",
            api_key or os.getenv("DEEPSEEK_API_KEY"),
        )
    if llm_provider == "bailian":
        return _get_adapter(
            BailianChatAdapter,
            model or "qwen-plus",
            api_key or os.getenv("BAILIAN_API_KEY"),
        )
    if llm_provider == "openai":
        raise NotImplementedError("OpenAI adapter not added yet")
    raise ValueError(f"Unknown LLM provider name: {llm_provider}")


@lru_cache(maxsize=32)
def _get_adapter(
    adapter: type[BaseChatAdapter], model: str, api_key: str | None
) -> BaseChatAdapter:
    return adapter(api_key=api_key, model=model)


async def get_configured_llm(role: ModelRole) -> BaseChatAdapter:
    settings = await get_model_settings()
    selection = getattr(settings, role)
    return get_llm(
        llm_provider=selection.provider,
        model=selection.model,
        api_key=settings.get_api_key(selection.provider),
    )


async def resolve_adapter(result: AdapterResult) -> BaseChatAdapter:
    return await result if isawaitable(result) else result
