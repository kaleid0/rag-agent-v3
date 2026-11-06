from abc import ABC, abstractmethod
from typing import Optional, Iterator, AsyncGenerator
import asyncio
import json
import os
from typing import Literal
from openai import Omit, OpenAI, AsyncOpenAI
from chromadb import Embeddings


class BaseEmbeddingAdapter(ABC):
    """抽象基类：定义统一接口，适配不同 Embedding 平台"""

    supports_async: bool = False

    @property
    @abstractmethod
    def name(self) -> dict:
        """返回平台和模型名称"""

    @abstractmethod
    def embedding_call(
        self,
        input: list[str] | str,
        dimensions: int = 1024,
        encoding_format: Omit | Literal["float", "base64"] = "float",
        **kwargs,
    ) -> Embeddings:
        """同步获取嵌入向量的生成器"""

    @abstractmethod
    async def async_embedding_call(
        self,
        input: list[str] | str,
        dimensions: int = 1024,
        encoding_format: Omit | Literal["float", "base64"] = "float",
    ) -> Embeddings:
        """默认异步封装，不阻塞事件循环"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.embedding_call, input, dimensions, encoding_format
        )
