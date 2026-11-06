from typing import Literal, Optional
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from beanie import Insert, Delete, Save, SaveChanges, Update, before_event, after_event

from src.database import BaseDocument


class DocumentRecord(BaseDocument):
    """存储文件解析信息"""

    source: str = Field(default="unknown")  # 文件来源描述
    storage_path: str = Field(...)  # 文件在存储系统中的路径
    file_hash: str = Field(...)
    # Historical duplicate hashes are preserved and excluded from the unique index.
    upload_key: str | None = None
    status: Literal["pending", "processing", "ready", "failed", "deleting"] | None = None

    markdown_path: str = Field(default="")  # 转换后的 Markdown 文件路径
    language: str = Field(default="EN", pattern="^(ZH|EN)$")
    title: str | None = Field(default=None)
    abstract: str | None = Field(default=None)
    keywords: list[str] | None = Field(default=None)
    directory: list[str] | None = Field(default=None)

    class Settings:
        name = "document_record"  # MongoDB 集合名
        indexes = [
            [("file_hash", ASCENDING)],
            [("created_at", DESCENDING)],
            IndexModel(
                [("upload_key", ASCENDING)],
                unique=True,
                partialFilterExpression={"upload_key": {"$type": "string"}},
            ),
        ]
        use_state_management = True

    def __str__(self) -> str:
        return f"DocumentRecord(id={self.id}, title={self.title})"

    @property
    def parse_status(self) -> str:
        return self.status or ("ready" if self.markdown_path else "pending")

    @property
    def metadata(self) -> dict:
        return {
            "is_prased": self.parse_status == "ready",
            "status": self.parse_status,
            "error": "Document parsing failed" if self.status == "failed" else None,
            "language": self.language,
            "title": self.title,
            "abstract": self.abstract,
            "keywords": self.keywords,
            "directory": self.directory,
        }

    @after_event([Insert, Save, SaveChanges, Update])
    def add_id_title_mapping(self):
        if self.title:
            add_id_title_mapping(str(self.id), self.title)

    @before_event([Delete])
    def delete_id_title_mapping(self):
        if self.title:
            delete_id_title_mapping(str(self.id), self.title)


async def get_keywords(document_record_id: str) -> list[str]:
    record = await DocumentRecord.get(document_record_id)
    return record.keywords if record and record.keywords else []


# id:title mapping cache
id_title_mapping: Optional[dict[str, str]] = None


def get_id_title_mapping() -> dict[str, str]:
    global id_title_mapping
    if id_title_mapping is None:
        raise ValueError("id_title_mapping is not built yet.")
    return id_title_mapping


def id_to_title(id: str) -> str:
    mapping = get_id_title_mapping()
    return mapping.get(id, "unknown title")


def add_id_title_mapping(id: str, title: str) -> None:
    global id_title_mapping
    if id_title_mapping is not None:
        id_title_mapping[id] = title


def delete_id_title_mapping(id: str, title: str) -> None:
    global id_title_mapping
    if id_title_mapping is not None:
        id_title_mapping.pop(id, None)


# To use: id_title_mapping = await build_id_title_mapping()

# 插入示例（异步）
"""
record = FileRecord(
    storage_path=file_path,
    markdown_path=f"rag/database/markdown/{id}.md",
    file_hash=file_hash,
    language="ZH" if contains_chinese(file_path) else "EN",
)
await record.insert()

"""

# 查找示例
"""
record = await FileRecord.find_one(FileRecord.file_hash == "XXX")
if record:
    print("记录已存在:", record)
else:
    print("记录不存在")
"""

# 更新示例
"""
record = await FileRecord.find_one(FileRecord.file_hash == "XXX")
if record:
    record.status = "convert_markdown_completed"
    await record.save_changes()
"""
