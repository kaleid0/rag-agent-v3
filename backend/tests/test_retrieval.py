from importlib import import_module
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from chromadb.errors import NotFoundError
from langchain_core.documents import Document

from src.prompt.rag.register import query_route_input_builder
from src.rag.ingest.text_splitter.get_chunks import get_chunks
from src.rag.retriever import BM25Retriever, ChromaRetriever


chroma_module = import_module("src.rag.retriever.chroma_retriever.ChromaRetriever")
enhanced_module = import_module(
    "src.rag.retrieve_pipeline.enhanced_pipeline.EnhancedPipeline"
)
context_module = import_module(
    "src.rag.retrieve_pipeline.enhanced_pipeline.context_retrieve"
)
rerank_module = import_module("src.rag.retrieve_pipeline.enhanced_pipeline.rerank")
retrieve_module = import_module("src.rag.retrieve_pipeline.retrieve")


def chunk(collection_id: str, chunk_id: str, content: str) -> Document:
    return Document(
        id=chunk_id,
        page_content=content,
        metadata={
            "collection_id": collection_id,
            "document_title": "Shared title",
            "num_chunks": 4,
        },
    )


def vector_response(collection_id: str, distance: float) -> dict:
    doc = chunk(collection_id, "0", collection_id)
    return {
        "ids": [[doc.id]],
        "documents": [[doc.page_content]],
        "metadatas": [[doc.metadata]],
        "distances": [[distance]],
    }


class RetrieverTests(unittest.TestCase):
    def test_route_prompt_renders_id_and_score_requirements(self):
        prompt = query_route_input_builder({
            "collections": [{"collection_id": "record-123", "title": "Title", "keywords": []}],
            "question": "Question",
        })
        self.assertIn('every supplied collection_id exactly once', prompt)
        self.assertIn('an integer score from 0', prompt)
        self.assertIn('"collection-A": 5', prompt)
        self.assertIn('"collection_id": "record-123"', prompt)

    def test_recursive_chunking_uses_default_separators(self):
        chunks = get_chunks("first words\n\nsecond words", 15, 0, "recursive")
        self.assertEqual(
            [(doc.id, doc.page_content) for doc in chunks],
            [("0", "first words"), ("1", "second words")],
        )

    def test_vector_uses_collection_language_and_reuses_query_embedding(self):
        collections = {"en-a": Mock(), "zh": Mock(), "en-b": Mock()}
        for index, (collection_id, collection) in enumerate(collections.items(), 1):
            response = vector_response(collection_id, 1 / index)
            response["metadatas"][0][0].pop("collection_id")
            collection.query.return_value = response
        client = Mock()
        client.get_collection.side_effect = lambda name, **_: collections[name]
        embedding = Mock()
        embedding.embed_query.side_effect = [[[1.0, 0.0]], [[0.0, 1.0]]]

        with patch.object(chroma_module, "get_chroma_client", return_value=client):
            retriever = ChromaRetriever(
                list(collections), {"zh": "ZH"}, embedding_function=embedding
            )
        hits = retriever.retrieve({"EN": "English", "ZH": "Chinese"}, top_k=2)
        self.assertEqual(
            embedding.embed_query.call_args_list, [call(["English"]), call(["Chinese"])]
        )
        collections["en-b"].query.assert_called_once_with(
            query_embeddings=[[1.0, 0.0]], n_results=2
        )
        self.assertEqual(
            [(doc.metadata["collection_id"], doc.id) for doc in hits],
            [("en-b", "0"), ("zh", "0")],
        )

    def test_sparse_uses_saved_paths_and_matches_each_collection_language(self):
        with TemporaryDirectory() as tmp:
            paths = {}
            for collection_id, texts in {
                "en": ["alpha", "noise alpha-less"],
                "zh": ["中文", "无关"],
            }.items():
                path = Path(tmp) / f"stored-{collection_id}.pkl"
                paths[collection_id] = str(path)
                with path.open("wb") as file:
                    pickle.dump(
                        [chunk(collection_id, str(i), text) for i, text in enumerate(texts)],
                        file,
                    )

            retriever = BM25Retriever(list(paths), {"zh": "ZH"}, chunk_paths=paths)
            results = retriever.retrieve({"EN": "alpha", "ZH": "中文"}, top_k=2)
            self.assertCountEqual([doc.page_content for doc in results], ["alpha", "中文"])
            routed = retriever.retrieve(
                {"EN": "alpha", "ZH": "中文"}, top_k=2, query_route={"zh": 1}
            )
            self.assertEqual([doc.page_content for doc in routed], ["中文"])

    def test_hybrid_deduplicates_within_collection_and_caps_results(self):
        a = chunk("a", "0", "first")
        b = chunk("b", "0", "other collection")
        c = chunk("a", "1", "different chunk")
        with (
            patch.object(retrieve_module, "ChromaRetriever") as vector,
            patch.object(retrieve_module, "BM25Retriever") as sparse,
        ):
            vector.return_value.retrieve.return_value = [a, c]
            sparse.return_value.retrieve.return_value = [a, b]
            result = retrieve_module._retrieve("hybrid", ["a", "b"], "query", 3)
        self.assertEqual(result, [a, c, b])

    def test_explicit_zero_route_never_opens_retrievers(self):
        with (
            patch.object(retrieve_module, "ChromaRetriever") as vector,
            patch.object(retrieve_module, "BM25Retriever") as sparse,
        ):
            result = retrieve_module._retrieve(
                "hybrid", ["a"], "query", 3, query_route={"a": 0}
            )
        self.assertEqual(result, [])
        vector.assert_not_called()
        sparse.assert_not_called()


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_stable_route_and_context_with_expansion_disabled(self):
        collections = [
            SimpleNamespace(id="first", document_record_id="doc-a"),
            SimpleNamespace(id="second", document_record_id="doc-b"),
        ]
        docs = {
            record.document_record_id: SimpleNamespace(title="Shared title", keywords=[])
            for record in collections
        }
        hits = [
            chunk("first", "0", "First excerpt"),
            chunk("first", "1", "Second excerpt"),
            chunk("second", "0", "Third excerpt"),
        ]
        route = {"second": 2, "first": 5}
        with (
            patch.dict(
                enhanced_module.rag_cfg,
                dict(query_route=True, query_rewrite=False, rerank=False,
                     context_retrieve=False, top_k=3),
            ),
            patch.object(
                enhanced_module, "get_knowledge_base_sources",
                return_value=(SimpleNamespace(retriever_type="hybrid"), collections, docs),
            ),
            patch.object(enhanced_module, "_try_query_model", return_value=route) as model,
            patch.object(enhanced_module, "retrieve_collections", return_value=hits) as retrieve,
        ):
            result = await enhanced_module.EnhancedPipeline().retrieve_knowledge_base(
                "Question", "knowledge-base"
            )

        self.assertEqual(retrieve.await_args.args[-1], route)
        self.assertEqual(retrieve.await_args.args[-2], 3)
        self.assertEqual(
            [source["collection_id"] for source in model.await_args.args[1]["collections"]],
            ["first", "second"],
        )
        for doc in hits:
            self.assertIn(doc.page_content, result)
        self.assertEqual(result.count("Shared title"), 2)

    async def test_invalid_route_falls_back_and_sparse_retains_hits(self):
        collections = [SimpleNamespace(id="known", document_record_id="doc")]
        hits = [chunk("known", "0", "Sparse excerpt")]
        with (
            patch.dict(
                enhanced_module.rag_cfg,
                dict(query_route=True, query_rewrite=False, rerank=False,
                     context_retrieve=True, top_k=1),
            ),
            patch.object(
                enhanced_module, "get_knowledge_base_sources",
                return_value=(SimpleNamespace(retriever_type="sparse"), collections, {}),
            ),
            patch.object(enhanced_module, "_try_query_model", return_value={"unknown": 4}),
            patch.object(enhanced_module, "retrieve_collections", return_value=hits) as retrieve,
            patch.object(enhanced_module, "context_retrieve") as expand,
            self.assertLogs(enhanced_module.logger, "WARNING"),
        ):
            result = await enhanced_module.EnhancedPipeline().retrieve_knowledge_base(
                "Question", "knowledge-base"
            )
        self.assertIsNone(retrieve.await_args.args[-1])
        expand.assert_not_awaited()
        self.assertIn("Sparse excerpt", result)

    async def test_context_expands_neighbors_without_discarding_hits(self):
        a = chunk("a", "1", "hit a")
        b = chunk("b", "1", "hit b")
        neighbor = chunk("b", "0", "neighbor")
        with patch.object(context_module, "ChromaRetriever") as retriever:
            retriever.return_value.get_by_ids = AsyncMock(return_value={"b": [neighbor, b]})
            result = await context_module.context_retrieve([a, b], num_context=1)
        self.assertEqual(result, {"a": [a], "b": [neighbor, b]})

    async def test_model_errors_preserve_query_and_retrieval_order(self):
        collections = [SimpleNamespace(id="a", document_record_id="doc")]
        hits = [chunk("a", "0", "First excerpt"), chunk("a", "1", "Second excerpt")]
        with (
            patch.dict(
                enhanced_module.rag_cfg,
                dict(query_route=True, query_rewrite=True, rerank=True,
                     context_retrieve=False, top_k=1),
            ),
            patch.object(
                enhanced_module, "get_knowledge_base_sources",
                return_value=(SimpleNamespace(retriever_type="hybrid"), collections, {}),
            ),
            patch.object(enhanced_module, "get_configured_llm", side_effect=RuntimeError),
            patch.object(enhanced_module, "retrieve_collections", return_value=hits) as retrieve,
            patch.object(enhanced_module, "rerank", side_effect=ValueError),
            self.assertLogs(enhanced_module.logger, "WARNING"),
        ):
            result = await enhanced_module.EnhancedPipeline().retrieve_knowledge_base(
                "Original question", "knowledge-base"
            )

        self.assertEqual(retrieve.await_args.args[-3:], ("Original question", 2, None))
        self.assertIn("First excerpt", result)
        self.assertNotIn("Second excerpt", result)

    async def test_rerank_matches_score_keys_and_respects_top_k(self):
        docs = [chunk("a", "0", "lower"), chunk("b", "0", "higher")]
        with (
            patch.object(rerank_module, "get_configured_llm"),
            patch.object(rerank_module, "llm_call", return_value={"text2": 5, "text1": 1}),
        ):
            result = await rerank_module.rerank("query", docs, top_k=1)
        self.assertEqual(result, [docs[1]])

    async def test_missing_or_empty_memory_does_not_create_or_embed(self):
        client = Mock()
        empty = Mock()
        empty.count.return_value = 0
        client.get_collection.side_effect = [NotFoundError("missing"), empty]
        with (
            patch.dict(retrieve_module.memory_cfg, {"retriever_type": "vector"}),
            patch.object(chroma_module, "get_chroma_client", return_value=client),
            patch.object(chroma_module, "SyncEmbeddingFunction") as embedding,
        ):
            self.assertEqual(await retrieve_module.retrieve_memory("missing", "question"), [])
            self.assertEqual(await retrieve_module.retrieve_memory("empty", "question"), [])
        client.create_collection.assert_not_called()
        empty.query.assert_not_called()
        embedding.return_value.embed_query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
