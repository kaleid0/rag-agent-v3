from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Iterator, AsyncGenerator
import asyncio
from ..Message import Messages


class BaseChatAdapter(ABC):
    """抽象基类：定义统一接口，适配不同 LLM 平台"""

    supports_streaming: bool = False
    supports_async: bool = False
    # supports_format_output: bool = False
    # supports_prefix_assistant_message: bool = False
    # supports_stop_sequences: bool = False

    @property
    @abstractmethod
    def name(self) -> dict:
        """返回平台和模型名称"""

    @abstractmethod
    def chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> str | None:
        """同步对话接口，返回完整文本"""

    async def async_chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> str | None:
        """默认异步封装，不阻塞事件循环"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.chat, messages, format, **kwargs)

    def stream_chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> Iterator[str]:
        """同步流式接口"""
        raise NotImplementedError(f"{self.name} does not support streaming")

    async def async_stream_chat(
        self,
        messages: Messages,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """异步流式接口"""
        raise NotImplementedError(f"{self.name} does not support async streaming")

    @abstractmethod
    def call(
        self,
        prompt: str,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
    ) -> str | None:
        """同步调用接口，一次性调用，无对话记录，返回完整文本"""

    async def async_call(
        self,
        prompt: str,
        format: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
    ) -> str | None:
        """异步调用接口，一次性调用，无对话记录，返回完整文本"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.call, prompt, format, max_tokens, temperature
        )
