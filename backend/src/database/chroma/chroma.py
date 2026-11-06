from __future__ import annotations

from threading import Lock
from typing import Optional, Callable

import chromadb
from chromadb import (
    Collection,
    EmbeddingFunction,
    PersistentClient,
    HttpClient,
)
from chromadb.api import ClientAPI
from config import chroma_cfg


# 进程内单例存放处
_chroma_client_singleton: Optional[ClientAPI] = None
_chroma_client_lock: Lock = Lock()
_chroma_client_config: Optional[dict] = None


# TODO 配置项
def _resolve_chroma_config(explicit_config: Optional[dict]) -> dict:
    """
    解析 ChromaDB 配置优先级：
    1) 参数传入 explicit_config
    2) pyproject.toml 的 [tool.chroma] 配置（通过 config.py 的 chroma_cfg 读取）
    3) 默认内存模式
    """

    if explicit_config:
        return explicit_config

    # 直接从 chroma_cfg 读取
    config = {}
    if chroma_cfg.get("persist_directory"):
        config["persist_directory"] = chroma_cfg["persist_directory"]
    # 可扩展更多配置项
    return config


def get_chroma_client(config: Optional[dict] = None) -> ClientAPI:
    """
    获取全局单例 ChromaDB 客户端（惰性初始化，线程安全）。

    - 可通过参数或环境变量指定配置。
    - 已初始化后再次调用将复用同一实例。
    - 若传入不同配置，而已有实例存在，将忽略新配置并复用已存在实例。
      如需切换连接，请先调用 close_chroma_client()。

    Args:
        config: ChromaDB 配置字典，支持以下键：
            - persist_directory: 持久化目录路径
            - host: 远程服务器地址
            - port: 远程服务器端口
            - settings: ChromaDB 设置
    """

    global _chroma_client_singleton, _chroma_client_config

    if _chroma_client_singleton is not None:
        return _chroma_client_singleton

    resolved_config = _resolve_chroma_config(config)
    with _chroma_client_lock:
        if _chroma_client_singleton is None:
            if "persist_directory" in resolved_config:
                if resolved_config.get("settings"):
                    _chroma_client_singleton = PersistentClient(
                        path=resolved_config["persist_directory"],
                        settings=resolved_config["settings"],
                    )
                else:
                    _chroma_client_singleton = PersistentClient(
                        path=resolved_config["persist_directory"]
                    )
            elif "host" in resolved_config:
                if resolved_config.get("settings"):
                    _chroma_client_singleton = HttpClient(
                        host=resolved_config["host"],
                        port=resolved_config.get("port", 8000),
                        settings=resolved_config["settings"],
                    )
                else:
                    _chroma_client_singleton = HttpClient(
                        host=resolved_config["host"],
                        port=resolved_config.get("port", 8000),
                    )
            else:
                # 默认内存模式
                if resolved_config.get("settings"):
                    _chroma_client_singleton = chromadb.Client(
                        settings=resolved_config["settings"]
                    )
                else:
                    _chroma_client_singleton = chromadb.Client()
            _chroma_client_config = resolved_config
    return _chroma_client_singleton


def close_chroma_client() -> None:
    """关闭并清空全局单例，通常用于进程退出或测试清理。"""

    global _chroma_client_singleton, _chroma_client_config
    with _chroma_client_lock:
        if _chroma_client_singleton is not None:
            # ChromaDB 客户端通常不需要显式关闭
            _chroma_client_singleton = None
            _chroma_client_config = None


def override_chroma_client(client: ClientAPI) -> None:
    """
    以自定义实例覆盖全局单例，便于依赖注入/测试。
    例如：
        import chromadb
        override_chroma_client(chromadb.Client())
    """

    global _chroma_client_singleton, _chroma_client_config
    with _chroma_client_lock:
        _chroma_client_singleton = client
        # 最好同步记录下配置，但有些实现无法读出，置空以示未知
        _chroma_client_config = None


def set_chroma_client_factory(factory: Callable[[], ClientAPI]) -> None:
    """
    通过工厂方法创建并覆盖全局单例。适合复杂初始化或延迟连接策略。
    """

    override_chroma_client(factory())


def get_collection(
    name: str, embedding_function: EmbeddingFunction | None = None, **kwargs
) -> Collection:
    """
    快捷获取集合对象。

    Args:
        name: 集合名称
        **kwargs: 传递给 create_collection 的其他参数
    """

    client = get_chroma_client()
    try:
        return client.get_collection(name, embedding_function=embedding_function)
    except Exception:
        # 如果集合不存在，创建它
        return client.create_collection(
            name, embedding_function=embedding_function, **kwargs
        )


def create_collection(
    name: str, embedding_function: EmbeddingFunction | None, **kwargs
) -> Collection:
    client = get_chroma_client()
    return client.create_collection(
        name=name, embedding_function=embedding_function, **kwargs
    )


def delete_collection(name: str) -> None:
    client = get_chroma_client()
    client.delete_collection(name)


def delete_content_from_collection(name: str, metadata: dict) -> None:
    client = get_chroma_client()
    collection = client.get_collection(name)
    collection.delete(where=metadata)

    """
from src.database.chroma.chroma import get_collection
from chromadb.utils import embedding_functions

# 假设你有一个 embedding function（这里用 ChromaDB 内置的 OpenAIEmbeddingFunction 举例）
embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
    api_key="你的OpenAI_API_KEY"
)

# 获取或创建集合
collection = get_collection(
    name="demo_collection",
    embedding_function=embedding_fn
)

# 插入数据
collection.add(
    documents=["你好，世界！", "Hello, world!"],
    ids=["doc1", "doc2"]
)

# 查询相似内容
results = collection.query(
    query_texts=["世界"],
    n_results=2
)

    """
