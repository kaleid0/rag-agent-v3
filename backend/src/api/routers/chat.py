"""聊天相关的 API 路由"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse

from src.api.models import (
    SessionCreateRequest,
    SessionResponse,
    MessageRequest,
    ChatResponse,
    SessionHistoryResponse,
    MessageResponse,
    SuccessResponse,
)
from src.session import SessionService

from src.api.dependencies import get_session_service


router = APIRouter()


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    request: SessionCreateRequest,
    session_service: SessionService = Depends(get_session_service),
):
    """创建新的聊天会话"""
    try:

        session = await session_service.create_session(
            user_id=request.user_id, metadata=request.metadata
        )

        return SessionResponse(
            session_id=str(session.id),
            user_id=session.user_id,  # type: ignore
            created_at=session.created_at,
            metadata=session.metadata,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create session: {str(e)}"
        )


@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str, session_service: SessionService = Depends(get_session_service)
):
    """获取会话历史"""
    try:
        return SessionHistoryResponse(
            messages=await session_service.get_session_history(session_id),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.delete("/sessions/{session_id}", response_model=SuccessResponse)
async def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """删除会话"""
    try:
        await session_service.delete_session(session_id)
        return SuccessResponse(message="Session deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete session: {str(e)}"
        )


@router.post(
    "/sessions/{session_id}/exit", response_model=SuccessResponse, status_code=202
)
async def exit_session(
    background_task: BackgroundTasks,
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
):
    """退出会话：如果会话没有任何对话消息，则删除之，否则保留并返回信息。"""
    try:
        await session_service.get_session(session_id)
        background_task.add_task(session_service.exit_session, session_id)
        return SuccessResponse(message="Session exit processing started.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to exit session: {str(e)}")


@router.post("/chat", response_model=ChatResponse)
async def send_message(
    request: MessageRequest,
    session_service: SessionService = Depends(get_session_service),
):
    """发送消息并返回已保存的完整回复。"""
    try:
        user_message, assistant_message = await session_service.send_message(
            session_id=request.session_id,
            content=request.content,
            metadata=request.metadata,
            kb_id=request.knowledge_base_id,
        )
        return ChatResponse(
            session_id=request.session_id,
            user_message=MessageResponse.model_validate(
                user_message, from_attributes=True
            ),
            assistant_message=MessageResponse.model_validate(
                assistant_message, from_attributes=True
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process message: {str(e)}"
        )


@router.post("/chat-stream")
async def send_message_stream(
    request: MessageRequest,
    session_service: SessionService = Depends(get_session_service),
):
    """发送消息并获取回复

    这是核心的对话接口，支持基于RAG的智能回复
    """
    try:

        token_stream = await session_service.send_message_stream(
            session_id=request.session_id,
            content=request.content,
            metadata=request.metadata,
            kb_id=request.knowledge_base_id,
        )

        return StreamingResponse(token_stream, media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to process message: {str(e)}"
        )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    session_service: SessionService = Depends(get_session_service),
):
    """获取会话的消息列表（支持分页）"""
    try:
        messages = await session_service.get_messages(session_id, offset, limit)
        return [
            MessageResponse.model_validate(msg, from_attributes=True)
            for msg in messages
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")


@router.get("/session-list", response_model=list[SessionResponse])
async def list_sessions(
    user_id: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    order: Literal["asc", "desc"] = "asc",
    session_service: SessionService = Depends(get_session_service),
):
    """列出指定用户的会话。"""
    try:
        sessions = await session_service.list_sessions(user_id, offset, limit, order=order)

        return [
            SessionResponse(
                session_id=str(session.id),
                user_id=session.user_id,  # type: ignore
                created_at=session.created_at,
                metadata=session.metadata,
            )
            for session in sessions
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list sessions: {str(e)}"
        )
