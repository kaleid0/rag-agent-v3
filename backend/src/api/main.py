"""FastAPI 主应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.database import connect_db, disconnect_db
from src.session import Session, LongTermMemory
from src.document import DocumentRecord
import src.document.odm.DocumentRecord as dr
from src.rag import KnowledgeBase, CollectionRecord
from src.prompt import load_all_prompts
from src.llm.settings import ModelSettingsDocument

from .routers import chat, document, knowledge_base, model_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    client = await connect_db(
        models=[
            Session,
            KnowledgeBase,
            DocumentRecord,
            CollectionRecord,
            LongTermMemory,
            ModelSettingsDocument,
        ],
    )

    try:
        load_all_prompts()
        records = await DocumentRecord.find_all().to_list()
        dr.id_title_mapping = {
            str(record.id): record.title for record in records if record.title
        }
        yield
    finally:
        await disconnect_db(client)


# 创建 FastAPI 应用
app = FastAPI(
    title="RAG Chatbot API",
    description="基于RAG的对话机器人后端API",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境请配置具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(knowledge_base.router, prefix="/api/v1", tags=["Knowledge Base"])
app.include_router(document.router, prefix="/api/v1", tags=["Document Management"])
app.include_router(model_settings.router, prefix="/api/v1", tags=["Model Settings"])


@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "message": "RAG Chatbot API is running",
        "version": "1.0.0",
        "status": "healthy",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}
