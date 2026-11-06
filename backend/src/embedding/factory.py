from typing import Dict
from .adapter.BailianEmbeddingAdapter import BailianEmbeddingAdapter
from .adapter.BaseEmbeddingAdapter import BaseEmbeddingAdapter

_instances: Dict[str, BaseEmbeddingAdapter] = {}


def get_embedding_model(llm_provider: str, model: str, api_key: str | None = None):
    """获取或创建指定 LLM 的单例实例"""
    key = f"{llm_provider}:{model}" if model else llm_provider  # 支持多模型缓存
    if key not in _instances:
        if llm_provider == "bailian":
            _instances[key] = BailianEmbeddingAdapter(
                api_key=api_key, model=model or "text-embedding-v4"
            )
        else:
            raise ValueError(f"Unknown LLM provider name: {llm_provider}")
    return _instances[key]
