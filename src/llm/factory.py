from typing import Dict
from .adapter.DeepseekChatAdapter import DeepseekChatAdapter
from .adapter.BaseChatAdapter import BaseChatAdapter
from .adapter.BailianChatAdapter import BailianChatAdapter


_instances: Dict[str, BaseChatAdapter] = {}


def get_llm(
    llm_provider: str, model: str, api_key: str | None = None
) -> BaseChatAdapter:
    """获取或创建指定 LLM 的单例实例"""
    key = f"{llm_provider}:{model}" if model else llm_provider  # 支持多模型缓存
    if key not in _instances:
        if llm_provider == "deepseek":
            _instances[key] = DeepseekChatAdapter(
                api_key=api_key, model=model or "deepseek-chat"
            )
        elif llm_provider == "openai":
            raise NotImplementedError("OpenAI adapter not added yet")
        elif llm_provider == "bailian":
            _instances[key] = BailianChatAdapter(
                api_key=api_key, model=model or "qwen-plus"
            )
        else:
            raise ValueError(f"Unknown LLM provider name: {llm_provider}")
    return _instances[key]
