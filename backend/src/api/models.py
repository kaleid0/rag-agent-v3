"""API 请求和响应的 Pydantic 模型"""

from typing import Optional, List, Dict, Any, Literal, Self
from pydantic import BaseModel, Field, model_validator
from datetime import datetime


# ===== 会话相关模型 =====
class SessionCreateRequest(BaseModel):
    """创建会话请求"""

    user_id: str = Field(..., description="用户ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="会话元数据")


class SessionResponse(BaseModel):
    """会话响应"""

    session_id: str = Field(..., description="会话ID")
    user_id: str
    created_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


# ===== 消息相关模型 =====
class MessageRequest(BaseModel):
    """发送消息请求"""

    session_id: str = Field(..., description="会话ID")
    content: str = Field(..., description="消息内容")
    knowledge_base_id: Optional[str] = Field(default=None, description="知识库ID(可选)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="消息元数据")


class MessageResponse(BaseModel):
    """消息响应"""

    role: str = Field(..., description="角色: user 或 assistant")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """对话响应"""

    session_id: str
    user_message: MessageResponse
    assistant_message: MessageResponse


# ===== 会话历史相关模型 =====
class SessionHistoryResponse(BaseModel):
    """会话历史响应"""

    messages: List[Dict[str, Any]]


# ===== 文档管理相关模型 =====
class FileRecordResponse(BaseModel):
    """文件记录响应"""

    id: str
    source: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""

    file_record_id: str
    filename: str
    status: str
    error_message: Optional[str] = None


class DocumentParseResponse(BaseModel):
    """文档解析响应"""

    file_record_id: str
    filename: str
    num_chunks: int
    status: str
    error_message: Optional[str] = None


class DocumentListResponse(BaseModel):
    """文档列表响应"""

    total: int
    documents: List[FileRecordResponse]


# ===== 知识库相关模型 =====
class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求"""

    name: str = Field(..., min_length=1, description="知识库名称")
    description: str = Field(default="", description="知识库描述")
    chunk_size: int = Field(default=500, gt=0, description="文本块大小")
    chunk_overlap: int = Field(default=50, ge=0, description="文本块重叠大小")
    split_method: Literal["character", "recursive", "hierarchical"] = Field(
        default="recursive", description="文本拆分方法"
    )
    retriever_type: Literal["vector", "sparse", "hybrid"] = Field(
        default="hybrid", description="检索器类型"
    )
    record_ids: List[str] = Field(default_factory=list, description="文件记录ID列表")

    @model_validator(mode="after")
    def validate_knowledge_base(self) -> Self:
        if not self.name.strip():
            raise ValueError("知识库名称不能为空")
        if self.split_method != "hierarchical" and self.chunk_overlap >= self.chunk_size:
            raise ValueError("文本块重叠大小必须小于文本块大小")
        return self


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""

    id: str
    name: str
    description: str
    document_ids: List[str] = Field(default_factory=list, description="文件记录ID列表")
    document_titles: List[str] = Field(
        default_factory=list, description="文件记录标题列表"
    )
    created_at: Optional[datetime] = None


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应"""

    total: int
    knowledge_base_list: List[KnowledgeBaseResponse]


class FileUploadRequest(BaseModel):
    """文件上传请求(用于元数据)"""

    knowledge_base_id: str = Field(..., description="知识库ID")
    filename: str = Field(..., description="文件名")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="文件元数据")


# ===== 通用响应模型 =====
class ErrorResponse(BaseModel):
    """错误响应"""

    error: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(default=None, description="详细错误")


class SuccessResponse(BaseModel):
    """成功响应"""

    message: str = Field(..., description="成功消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="附加数据")
