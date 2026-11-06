from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic, sleep

from pymongo import MongoClient
from pymongo.errors import PyMongoError


@contextmanager
def temporary_mongo():
    with TemporaryDirectory(prefix="rag-agent-test-") as directory:
        root = Path(directory)
        db_path = root / "mongo"
        db_path.mkdir()
        log_path = root / "mongo.log"

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        uri = f"mongodb://127.0.0.1:{port}"
        process = subprocess.Popen(
            [
                os.environ["RAG_TEST_MONGOD"],
                "--bind_ip", "127.0.0.1",
                "--port", str(port),
                "--dbpath", str(db_path),
                "--logpath", str(log_path),
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_mongo(process, uri, log_path)
            yield root, uri
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def _wait_for_mongo(process, uri, log_path):
    deadline = monotonic() + 15
    with MongoClient(uri, serverSelectionTimeoutMS=250) as client:
        while monotonic() < deadline and process.poll() is None:
            try:
                if client.admin.command("serverStatus")["pid"] == process.pid:
                    return
            except PyMongoError:
                sleep(0.1)
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    raise RuntimeError(f"Temporary MongoDB did not start:\n{log[-2000:]}")
