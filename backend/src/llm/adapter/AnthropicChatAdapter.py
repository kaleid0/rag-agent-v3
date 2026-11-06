from typing import List, Dict, Optional
import os

from .BaseChatAdapter import BaseChatAdapter, Messages
from anthropic import Anthropic


class AnthropicChatAdapter(BaseChatAdapter):
    supports_streaming = False
    supports_async = True

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = Anthropic(api_key=self._api_key)

    @property
    def name(self) -> str:
        return "anthropic"

    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        return "\n".join([f"{m.get('role')}: {m.get('content')}" for m in messages])

    def chat(self, messages: List[Dict], model: str = "claude-2", **kwargs) -> str:
        raise NotImplementedError(
            "Synchronous chat is not supported. Use async_chat instead."
        )

    async def async_chat(
        self, messages: List[Dict], model: str = "claude-2", **kwargs
    ) -> str:
        raise NotImplementedError("Async chat is not implemented yet.")
