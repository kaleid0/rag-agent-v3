from beanie import init_beanie
from pymongo import AsyncMongoClient

from config import mongo_cfg


# ---------- 连接与断开 ----------
async def connect_db(
    uri: str | None = None,
    db_name: str | None = None,
    models: list | None = None,
) -> AsyncMongoClient:
    """
    使用 Beanie 和 PyMongo 异步客户端连接 MongoDB。
    Args:
        uri: 可选的 MongoDB URI
        db_name: 数据库名
        models: 要注册的 Document 类列表，如 [FileRecord]
    """
    if uri is None:
        uri = mongo_cfg.get("uri", "mongodb://localhost:27017")
    if db_name is None:
        db_name = mongo_cfg.get("database") or mongo_cfg.get("db_name") or "rag_agent"

    client = AsyncMongoClient(uri)
    try:
        await init_beanie(database=client[db_name], document_models=models or [])
    except BaseException:
        await client.close()
        raise
    return client


async def disconnect_db(client: AsyncMongoClient):
    """关闭 Mongo 连接"""
    await client.close()
