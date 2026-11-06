import os
from typing import Any, Iterator, AsyncGenerator, Optional
from openai import OpenAI, AsyncOpenAI
from .BaseChatAdapter import BaseChatAdapter, Messages


def add_assistant_prefix(messages: Messages, prefix: str):
    messages.append({"role": "assistant", "content": prefix, "prefix": True}) # type: ignore
    return messages


class OpenaiChatAdapter(BaseChatAdapter):
    """DeepSeek API 适配器，实现 sync 与 stream 调用"""

    supports_streaming = True
    supports_async = False  # 如果要加 async 可扩展
    supports_format_output = False
    supports_prefix_assistant_message = True
    supports_stop_sequences = True

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is missing. Set OPENAI_API_KEY environment variable."
            )
        self.client = OpenAI(api_key=self.api_key, base_url="")  # TODO
        self.async_client = AsyncOpenAI(api_key=self.api_key, base_url="")  # TODO
        self.model = model

    @property
    def name(self) -> dict:
        return {"llm_provider": "openai", "model": self.model}

    def chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> str | None:
        """同步调用：返回完整回复文本"""
        if format:
            add_assistant_prefix(messages, "```" + format)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            temperature=temperature,
            stop="```" if format else None,
        )

        return response.choices[0].message.content

    async def async_chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> str | None:
        if format:
            add_assistant_prefix(messages, "```" + format)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore
            max_tokens=max_tokens,
            temperature=temperature,
            stop="```" if format else None,
        )

        return response.choices[0].message.content

    def stream_chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> Iterator[str]:
        """流式同步接口：逐段返回"""
        with self.client.chat.completions.stream(
            model=self.model,
            messages=messages,  # type: ignore
            temperature=kwargs.get("temperature", 0.7),
            stop=kwargs.get("stop"),
        ) as stream:
            for event in stream:
                if event.type == "message.delta" and event.delta.get("content"):
                    yield event.delta["content"]
                elif event.type == "message.completed":
                    break
