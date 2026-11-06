import os
from typing import Iterator, AsyncGenerator
from openai import OpenAI, AsyncOpenAI
from .BaseChatAdapter import BaseChatAdapter, Messages



# def add_assistant_prefix(messages: Messages, prefix: str):
#     messages.append({"role": "assistant", "content": prefix, "prefix": True})  # type: ignore
#     return messages


class BailianChatAdapter(BaseChatAdapter):
    """百炼对话适配器，支持同步和流式调用。"""

    supports_streaming = True
    supports_async = True  # 如果要加 async 可扩展
    supports_format_output = True
    supports_prefix_assistant_message = False
    supports_stop_sequences = True

    def __init__(self, api_key: str | None = None, model: str = "qwen-plus"):
        self.api_key = api_key or os.getenv("BAILIAN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Bailian API key is missing. Set BAILIAN_API_KEY environment variable."
            )
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.async_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.model = model

    @property
    def name(self) -> dict:
        return {"llm_provider": "bailian", "model": self.model}

    def chat(
        self,
        messages: Messages,
        format: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> str | None:
        """同步调用：返回完整回复文本"""
        # if format:
        #     add_assistant_prefix(messages, "```" + format)
        if format == "text":
            response_format = {"type": "text"}
        elif format == "json":
            response_format = {"type": "json_object"}
        else:
            response_format = None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                max_tokens=max_tokens,
                temperature=temperature,
                response_format=response_format,  # type: ignore
            )
        except Exception as e:
            raise e

        return response.choices[0].message.content

    async def async_chat(
        self,
        messages: Messages,
        format: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> str | None:
        # if format:
        #     add_assistant_prefix(messages, "```" + format)

        if format == "text":
            response_format = {"type": "text"}
        elif format == "json":
            response_format = {"type": "json_object"}
        else:
            response_format = None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                max_tokens=max_tokens,
                temperature=temperature,
                response_format=response_format,  # type: ignore
            )
        except Exception as e:
            raise e

        return response.choices[0].message.content

    def stream_chat(
        self,
        messages: Messages,
        format: str | None = None,
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

    async def async_stream_chat(
        self,
        messages: Messages,
        format: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """异步流式接口：逐段返回"""

        async def _stream():
            stream = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            async with stream:
                async for chunk in stream:
                    if (
                        chunk.choices
                        and chunk.choices[0].delta
                        and chunk.choices[0].delta.content
                    ):
                        yield chunk.choices[0].delta.content

        return _stream()

    def call(
        self,
        prompt: str,
        format: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
    ) -> str | None:
        """同步调用接口，一次性调用，无对话记录，返回完整文本"""
        messages: Messages = [{"role": "user", "content": prompt}]
        # if format:
        #     add_assistant_prefix(messages, "```" + format)

        return self.chat(
            messages,
            format=format,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def async_call(
        self,
        prompt: str,
        format: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.5,
    ) -> str | None:
        """异步调用接口，一次性调用，无对话记录，返回完整文本"""
        messages: Messages = [{"role": "user", "content": prompt}]
        # if format:
        #     add_assistant_prefix(messages, "```" + format)

        return await self.async_chat(
            messages,
            format=format,
            max_tokens=max_tokens,
            temperature=temperature,
        )
