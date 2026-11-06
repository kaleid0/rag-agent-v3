import asyncio
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from beanie import PydanticObjectId, init_beanie
from chromadb.errors import NotFoundError
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from mongo_test_server import temporary_mongo

from config import rag_cfg
from src.api.routers import document as document_router
from src.document import DocumentRecord
from src.document import document_service
from src.rag.knowledge_base import CollectionRecord, KnowledgeBase
from src.rag.knowledge_base import knowledge_base_service as knowledge_bases


class KnowledgeBaseServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_remove_rejects_an_association_from_another_knowledge_base(self):
        association = SimpleNamespace(knowledge_base_id=str(PydanticObjectId()))
        with (
            patch.object(CollectionRecord, "get", AsyncMock(return_value=association)),
            patch.object(knowledge_bases, "delete_associations", AsyncMock()) as delete,
        ):
            with self.assertRaises(HTTPException) as error:
                await knowledge_bases.remove_record_from_knowledge_base(
                    str(PydanticObjectId()), str(PydanticObjectId())
                )
        self.assertEqual(error.exception.status_code, 404)
        delete.assert_not_awaited()

    async def test_cleanup_failure_preserves_deleting_association_for_retry(self):
        association = SimpleNamespace(id=PydanticObjectId(), delete=AsyncMock())
        find_one = Mock(return_value=SimpleNamespace(update=AsyncMock(return_value=association)))
        with (
            patch.object(CollectionRecord, "find_one", find_one),
            patch.object(
                knowledge_bases,
                "_cleanup_association_artifacts",
                side_effect=[OSError("temporary storage failure"), None],
            ),
        ):
            with self.assertRaises(OSError):
                await knowledge_bases.delete_associations(
                    [SimpleNamespace(id=association.id, status="ready")]
                )
            association.delete.assert_not_awaited()
            await knowledge_bases.delete_associations(
                [SimpleNamespace(id=association.id, status="deleting")]
            )
        association.delete.assert_awaited_once()

    def test_cleanup_accepts_missing_chroma_collection_and_chunk_file(self):
        with TemporaryDirectory() as tmp:
            chunk = Path(tmp) / "chunk.pkl"
            chunk.write_bytes(b"temporary index")
            record = SimpleNamespace(id=PydanticObjectId(), retriever_type="hybrid", chunk_path=str(chunk))
            with patch.object(knowledge_bases, "delete_collection", side_effect=NotFoundError("missing")):
                knowledge_bases._cleanup_association_artifacts(record)
                self.assertFalse(chunk.exists())
                knowledge_bases._cleanup_association_artifacts(record)


class DocumentRouterTests(unittest.TestCase):
    def test_unsupported_upload_returns_client_error(self):
        app = FastAPI()
        app.include_router(document_router.router)
        with TestClient(app) as client:
            response = client.post("/document/upload", files={"file": ("sample.exe", b"data")})
        self.assertEqual(response.status_code, 415)


@unittest.skipUnless(os.getenv("RAG_TEST_MONGOD"), "Set RAG_TEST_MONGOD to the MongoDB executable")
class KnowledgeBaseMongoTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.uri = cls.enterClassContext(temporary_mongo())

    async def asyncSetUp(self):
        self.client = AsyncMongoClient(self.uri, serverSelectionTimeoutMS=2500)
        self.database_name = f"rag_kb_test_{uuid4().hex}"
        self.addAsyncCleanup(self.client.close)
        self.addAsyncCleanup(self.client.drop_database, self.database_name)
        await init_beanie(
            database=self.client[self.database_name],
            document_models=[KnowledgeBase, CollectionRecord, DocumentRecord],
        )
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(
            patch.dict(
                rag_cfg,
                file_storage_dir=str(directory / "files"),
                markdown_storage_dir=str(directory / "markdown"),
                chunk_dir=str(directory / "chunks"),
            )
        )

    async def test_idempotent_upload_parse_and_shared_document_cleanup(self):
        async def parse(_source, output):
            Path(output).write_text("# Topic\n\nThe meeting is in Room 204.", encoding="utf-8")
            return SimpleNamespace(
                title="Topic", abstract="", keywords=[], directory=[], language="EN"
            )

        first, duplicate = await asyncio.gather(
            document_service.upload_file(UploadFile(BytesIO(b"same"), filename="one.md")),
            document_service.upload_file(UploadFile(BytesIO(b"same"), filename="two.md")),
        )
        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(len(list(Path(rag_cfg["file_storage_dir"]).iterdir())), 1)
        self.assertEqual(first.metadata["status"], "pending")

        with (
            patch.object(document_service, "parse", AsyncMock(side_effect=ValueError("parse error"))),
            self.assertLogs(document_service.logger, level="ERROR"),
        ):
            await document_service.parse_file(str(first.id))
        failed = await DocumentRecord.get(first.id)
        self.assertEqual(failed.metadata["status"], "failed")
        self.assertFalse(failed.metadata["is_prased"])

        with patch.object(document_service, "parse", parse):
            await document_service.parse_file(str(first.id))
        parsed = await DocumentRecord.get(first.id)
        self.assertTrue(parsed.metadata["is_prased"])
        self.assertEqual(parsed.metadata["status"], "ready")

        left = await knowledge_bases.create_knowledge_base(
            "left", retriever_type="sparse", document_record_ids=[str(first.id)]
        )
        right = await knowledge_bases.create_knowledge_base("right", retriever_type="sparse")
        results = await asyncio.gather(
            *(
                knowledge_bases.add_record_to_knowledge_base(str(right.id), str(first.id))
                for _ in range(4)
            ),
            return_exceptions=True,
        )
        self.assertIn(None, results)
        for result in results:
            if result is not None:
                self.assertIsInstance(result, HTTPException)
                self.assertEqual(result.status_code, 409)
        await knowledge_bases.add_record_to_knowledge_base(str(right.id), str(first.id))

        left_rows = await knowledge_bases.get_collections_in_knowledge_base(str(left.id))
        right_rows = await knowledge_bases.get_collections_in_knowledge_base(str(right.id))
        self.assertEqual(len(left_rows), 1)
        self.assertEqual(len(right_rows), 1)
        self.assertEqual(await CollectionRecord.find_all().count(), 2)

        await knowledge_bases.delete_knowledge_base(str(left.id))
        await knowledge_bases.delete_knowledge_base(str(left.id))
        self.assertIsNotNone(await DocumentRecord.get(first.id))
        self.assertTrue(Path(parsed.markdown_path).exists())
        self.assertFalse(Path(left_rows[0].chunk_path).exists())
        self.assertTrue(Path(right_rows[0].chunk_path).exists())

        await document_service.delete_document_record(str(first.id))
        await document_service.delete_document_record(str(first.id))
        self.assertIsNone(await DocumentRecord.get(first.id))
        self.assertFalse(Path(parsed.markdown_path).exists())
        self.assertFalse(Path(parsed.storage_path).exists())
        self.assertFalse(Path(right_rows[0].chunk_path).exists())
        self.assertEqual(await CollectionRecord.find_all().count(), 0)
        self.assertIsNotNone(await KnowledgeBase.get(right.id))

    async def test_failed_index_is_hidden_and_retries_same_association(self):
        source = Path(rag_cfg["markdown_storage_dir"]) / "sample.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Topic\n\nUseful content.", encoding="utf-8")
        doc = await DocumentRecord(
            storage_path="unused.md", file_hash="legacy-file", markdown_path=str(source)
        ).insert()
        kb = await knowledge_bases.create_knowledge_base("retry", retriever_type="hybrid")
        ingest = knowledge_bases.ingest_file

        def broken_index(_record_id, _markdown, chunk_path, *args):
            Path(chunk_path).parent.mkdir(parents=True)
            Path(chunk_path).write_bytes(b"incomplete")
            raise RuntimeError("embedding failure")

        def working_index(record_id, markdown, chunk_path, title, size, overlap, split, _kind):
            return ingest(record_id, markdown, chunk_path, title, size, overlap, split, "sparse")

        with (
            patch.object(knowledge_bases, "ingest_file", broken_index),
            patch.object(knowledge_bases, "delete_collection"),
            self.assertRaises(RuntimeError),
        ):
            await knowledge_bases.add_record_to_knowledge_base(str(kb.id), str(doc.id))

        rows = await knowledge_bases.get_collections_in_knowledge_base(str(kb.id), ready_only=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "failed")
        self.assertFalse(Path(rows[0].chunk_path).exists())
        self.assertEqual(await knowledge_bases.get_collections_in_knowledge_base(str(kb.id)), [])

        with (
            patch.object(knowledge_bases, "ingest_file", working_index),
            patch.object(knowledge_bases, "delete_collection"),
        ):
            await knowledge_bases.add_record_to_knowledge_base(str(kb.id), str(doc.id))
        recovered = await knowledge_bases.get_collections_in_knowledge_base(str(kb.id))
        self.assertEqual([row.id for row in recovered], [rows[0].id])
        self.assertEqual(recovered[0].status, "ready")

    async def test_legacy_association_requires_saved_chunks(self):
        markdown = Path(rag_cfg["markdown_storage_dir"]) / "legacy.md"
        markdown.parent.mkdir(parents=True)
        markdown.write_text("Legacy content.", encoding="utf-8")
        doc = await DocumentRecord(
            storage_path="unused.md", file_hash="legacy", markdown_path=str(markdown)
        ).insert()
        kb = await knowledge_bases.create_knowledge_base("legacy", retriever_type="sparse")
        pair = {"knowledge_base_id": str(kb.id), "document_record_id": str(doc.id)}

        chunk = Path(rag_cfg["chunk_dir"]) / "legacy.pkl"
        chunk.parent.mkdir(parents=True)
        chunk.write_bytes(b"legacy chunks")
        ready = await CollectionRecord.get_pymongo_collection().insert_one(
            {"chunk_path": str(chunk), "num_chunks": 1, **pair}
        )
        await CollectionRecord(chunk_path=str(chunk.with_name("missing.pkl")), num_chunks=1, **pair).insert()

        await knowledge_bases.add_record_to_knowledge_base(str(kb.id), str(doc.id))
        self.assertEqual(await CollectionRecord.find_all().count(), 2)
        readable = await knowledge_bases.get_collections_in_knowledge_base(str(kb.id))
        self.assertEqual([row.id for row in readable], [ready.inserted_id])

    async def test_delete_during_indexing_cannot_leave_a_ready_association(self):
        markdown = Path(rag_cfg["markdown_storage_dir"]) / "concurrent.md"
        markdown.parent.mkdir(parents=True)
        markdown.write_text("Concurrent content.", encoding="utf-8")
        doc = await DocumentRecord(
            storage_path="unused.md", file_hash="concurrent", markdown_path=str(markdown)
        ).insert()
        kb = await knowledge_bases.create_knowledge_base("concurrent", retriever_type="sparse")
        started, release = Event(), Event()
        ingest = knowledge_bases.ingest_file

        def blocked_index(*args):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Timed out waiting for the delete request")
            return ingest(*args)

        with patch.object(knowledge_bases, "ingest_file", blocked_index):
            task = asyncio.create_task(
                knowledge_bases.add_record_to_knowledge_base(str(kb.id), str(doc.id))
            )
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 5))
                self.assertEqual(await knowledge_bases.get_collections_in_knowledge_base(str(kb.id)), [])
                with self.assertRaises(HTTPException) as delete_error:
                    await knowledge_bases.delete_knowledge_base(str(kb.id))
                self.assertEqual(delete_error.exception.status_code, 409)
            finally:
                release.set()
                with self.assertRaises(HTTPException) as index_error:
                    await task
                self.assertEqual(index_error.exception.status_code, 409)

        await knowledge_bases.delete_knowledge_base(str(kb.id))
        self.assertIsNone(await KnowledgeBase.get(kb.id))
        self.assertIsNotNone(await DocumentRecord.get(doc.id))
        self.assertEqual(await CollectionRecord.find_all().count(), 0)
        self.assertEqual(list(Path(rag_cfg["chunk_dir"]).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
