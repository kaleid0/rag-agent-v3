from .BaseEmbeddingAdapter import BaseEmbeddingAdapter

import json
import os
from typing import Literal
from openai import Omit, OpenAI, AsyncOpenAI
from chromadb import Embeddings


class BailianEmbeddingAdapter(BaseEmbeddingAdapter):
    """百炼平台 Embedding 适配器"""

    supports_async = True

    @property
    def name(self) -> dict:
        return {"llm_provider": "bailian", "model": self.model}

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-v4"):
        self.api_key = api_key or os.getenv("BAILIAN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Bailian embedding API key is missing. Set BAILIAN_API_KEY environment variable."
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

    def embedding_call(
        self,
        input: list[str] | str,
        dimensions: int = 1024,
        encoding_format: Omit | Literal["float", "base64"] = "float",
        **kwargs,
    ) -> Embeddings:
        completion = self.client.embeddings.create(
            model=self.model,
            input=input,
            dimensions=dimensions,
            encoding_format=encoding_format,
        )
        if isinstance(input, str):
            return json.loads(completion.model_dump_json())["data"][0]["embedding"]
        else:
            return [
                item["embedding"]
                for item in json.loads(completion.model_dump_json())["data"]
            ]

    async def async_embedding_call(
        self,
        input: list[str] | str,
        dimensions: int = 1024,
        encoding_format: Omit | Literal["float", "base64"] = "float",
    ) -> Embeddings:
        completion = await self.async_client.embeddings.create(
            model=self.model,
            input=input,
            dimensions=dimensions,
            encoding_format=encoding_format,
        )
        if isinstance(input, str):
            return json.loads(completion.model_dump_json())["data"][0]["embedding"]
        else:
            return [
                item["embedding"]
                for item in json.loads(completion.model_dump_json())["data"]
            ]
