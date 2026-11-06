"""知识库相关的 API 路由"""

import logging

from fastapi import APIRouter, HTTPException

from typing import List

from src.api.models import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseListResponse,
    FileRecordResponse,
    SuccessResponse,
)
from src.rag import (
    CollectionRecord,
    knowledge_base_service as kb_service,
)
from src.document import DocumentRecord, id_to_title


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/knowledge-bases", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(request: KnowledgeBaseCreateRequest):
    """创建新的知识库"""
    try:
        kb = await kb_service.create_knowledge_base(
            name=request.name,
            description=request.description,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            split_method=request.split_method,
            retriever_type=request.retriever_type,
            document_record_ids=request.record_ids,
        )

        collections = await kb_service.get_collections_in_knowledge_base(str(kb.id))
        return KnowledgeBaseResponse(
            id=str(kb.id),
            name=kb.name,
            description=kb.description,
            document_ids=[record.document_record_id for record in collections],
            created_at=kb.created_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create knowledge base")
        raise HTTPException(status_code=500, detail="Failed to create knowledge base") from exc


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(skip: int = 0, limit: int = 100):
    """获取知识库列表"""
    try:
        # 1) 分页后的 KB 列表
        knowledge_bases = await kb_service.list_knowledge_bases(skip, limit)
        total = len(knowledge_bases)

        if not knowledge_bases:
            return KnowledgeBaseListResponse(total=0, knowledge_base_list=[])

        kb_ids = [str(kb.id) for kb in knowledge_bases]

        # 2) 拉取所有 collections
        collections = await kb_service.get_collections_in_knowledge_base(kb_ids)

        # 3) 先按 kb_id 分组（避免重复过滤）
        kb_to_docs: dict[str, list[CollectionRecord]] = {kb_id: [] for kb_id in kb_ids}
        for col in collections:
            kb_to_docs[col.knowledge_base_id].append(col)

        # 4) 构建响应
        kb_list = []
        for kb in knowledge_bases:
            kb_id = str(kb.id)
            cols = kb_to_docs.get(kb_id, [])

            kb_list.append(
                KnowledgeBaseResponse(
                    id=kb_id,
                    name=kb.name,
                    description=kb.description,
                    document_ids=[str(c.document_record_id) for c in cols],
                    document_titles=[id_to_title(c.document_record_id) for c in cols],
                    created_at=kb.created_at,
                )
            )

        return KnowledgeBaseListResponse(total=total, knowledge_base_list=kb_list)

    except Exception as exc:
        logger.exception("Failed to list knowledge bases")
        raise HTTPException(
            status_code=500,
            detail="Failed to list knowledge bases",
        ) from exc


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(kb_id: str):
    """获取知识库详情"""
    try:
        kb = await kb_service.get_knowledge_base(kb_id)

        docs = await kb_service.get_collections_in_knowledge_base(kb_id)
        doc_ids = [doc.document_record_id for doc in docs]

        return KnowledgeBaseResponse(
            id=str(kb.id),
            name=kb.name,
            description=kb.description,
            document_ids=doc_ids,
            created_at=kb.created_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get knowledge base %s", kb_id)
        raise HTTPException(status_code=500, detail="Failed to get knowledge base") from exc


@router.delete("/knowledge-bases/{kb_id}", response_model=SuccessResponse)
async def delete_knowledge_base(kb_id: str):
    """删除知识库"""
    try:
        await kb_service.delete_knowledge_base(kb_id)
        return SuccessResponse(message="Knowledge base deleted successfully")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete knowledge base %s", kb_id)
        raise HTTPException(
            status_code=500, detail="Failed to delete knowledge base"
        ) from exc


@router.get("/knowledge-bases/{kb_id}/files", response_model=List[FileRecordResponse])
async def list_files_in_knowledge_base(kb_id: str):
    """获取知识库中的所有文件"""
    try:
        await kb_service.get_knowledge_base(kb_id)

        collections = await kb_service.get_collections_in_knowledge_base(kb_id)
        files = []
        for col in collections:
            doc_record = await DocumentRecord.get(col.document_record_id)
            if doc_record:
                files.append(
                    FileRecordResponse(
                        id=str(doc_record.id),
                        source=doc_record.source,
                        metadata=doc_record.metadata,
                        created_at=doc_record.created_at,
                    )
                )

        return files
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list files in knowledge base %s", kb_id)
        raise HTTPException(status_code=500, detail="Failed to list files") from exc


@router.post("/knowledge-bases/{kb_id}/files/{file_id}", response_model=SuccessResponse)
async def add_file_to_knowledge_base(kb_id: str, file_id: str):
    """将文件添加到知识库"""
    try:
        await kb_service.add_record_to_knowledge_base(
            knowledge_base_id=kb_id,
            document_record_id=file_id,
        )
        return SuccessResponse(message="File added to knowledge base successfully")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to add file %s to knowledge base %s", file_id, kb_id)
        raise HTTPException(status_code=500, detail="Failed to add file") from exc


@router.post("/knowledge-bases/{kb_id}/files", response_model=SuccessResponse)
async def add_multiple_files_to_knowledge_base(
    kb_id: str, file_ids: List[str]
) -> SuccessResponse:
    """将多个文件添加到知识库"""
    try:
        for file_id in dict.fromkeys(file_ids):
            await kb_service.add_record_to_knowledge_base(
                knowledge_base_id=kb_id,
                document_record_id=file_id,
            )
        return SuccessResponse(message="Files added to knowledge base successfully")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to add files to knowledge base %s", kb_id)
        raise HTTPException(status_code=500, detail="Failed to add files") from exc


@router.delete(
    "/knowledge-bases/{kb_id}/files/{file_id}", response_model=SuccessResponse
)
async def remove_collection_from_knowledge_base(kb_id: str, file_id: str):
    """从知识库中移除文件"""
    try:
        await kb_service.remove_record_from_knowledge_base(
            knowledge_base_id=kb_id,
            collection_record_id=file_id,
        )
        return SuccessResponse(message="File removed from knowledge base successfully")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to remove file %s from knowledge base %s", file_id, kb_id)
        raise HTTPException(status_code=500, detail="Failed to remove file") from exc
