from chromadb import Documents, EmbeddingFunction, Embeddings

from config import rag_cfg
from src.embedding import get_embedding_model


class SyncEmbeddingFunction(EmbeddingFunction):
    """向 Chroma 提供向量，在首次使用模型时读取凭据。"""

    def __init__(self, llm_provider: str | None = None, model: str | None = None):
        self.llm_provider = llm_provider or rag_cfg.get("embedding_provider", "bailian")
        self.model = model or rag_cfg.get("embedding_model", "text-embedding-v4")

    def __call__(self, input: Documents) -> Embeddings:
        adapter = get_embedding_model(llm_provider=self.llm_provider, model=self.model)
        return adapter.embedding_call(input)


# TODO: 异步版本
# class AsyncEmbeddingFunction(EmbeddingFunction):
#     """_summary_
#     EmbeddingFunction 是一个“向量生成器的包装类”，
#     用来让 Chroma 在插入或查询文本时，自动调用你定义的 embedding_call 函数生成向量。
#     """

#     def __init__(self, llm_provider: str = "bailian", model: str = "text-embedding-v4"):
#         self.embedding_model = get_embedding_model(
#             llm_provider=llm_provider, model=model
#         )

#     async def __call__(self, input: Documents) -> Embeddings:
#         # embed the documents somehow
#         return await self.embedding_model.async_embedding_call(input)
