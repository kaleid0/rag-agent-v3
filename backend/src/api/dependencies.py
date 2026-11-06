"""FastAPI 依赖注入"""

from threading import Lock
from typing import Optional

from src.session import SessionService, DialogManager, MemoryManager
from src.rag import EnhancedPipeline, SimplePipeline
from src.llm.factory import get_configured_llm

from config import memory_cfg


# 全局单例
_dialog_manager: Optional[DialogManager] = None
_memory_manager: Optional[MemoryManager] = None
_session_service: Optional[SessionService] = None
_session_service_lock = Lock()


def get_dialog_manager() -> DialogManager:
    """获取 DialogManager 单例

    这个函数确保整个应用共享同一个 DialogManager 实例
    """
    global _dialog_manager

    if _dialog_manager is None:
        _dialog_manager = DialogManager(
            llm_adapter=lambda: get_configured_llm("dialog"),
            retrieve_pipeline=EnhancedPipeline(),
        )

    return _dialog_manager


def get_memory_manager() -> MemoryManager:
    """获取 MemoryManager 单例

    这个函数确保整个应用共享同一个 MemoryManager 实例
    """
    global _memory_manager

    if _memory_manager is None:
        _memory_manager = MemoryManager(
            llm_adapter=lambda: get_configured_llm("memory"),
            retrieve_pipeline=SimplePipeline(),
            retrieve_enabled=memory_cfg.get("retrieve_enabled", False),
            retrieve_timeout_seconds=memory_cfg.get("retrieve_timeout_seconds", 1.0),
        )

    return _memory_manager


def reset_dialog_manager():
    """重置 DialogManager（主要用于测试）"""
    global _dialog_manager, _session_service
    with _session_service_lock:
        _dialog_manager = None
        _session_service = None


def get_session_service() -> SessionService:
    """获取共享的会话服务。"""
    global _session_service
    with _session_service_lock:
        if _session_service is None:
            _session_service = SessionService(
                dialog_manager=get_dialog_manager(),
                memory_manager=get_memory_manager(),
            )
        return _session_service
