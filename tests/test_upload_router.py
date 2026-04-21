from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import upload


def test_upload_local_doc_rejects_invalid_doc_type(tmp_path: Path, monkeypatch) -> None:
    app = FastAPI()
    app.include_router(upload.router)

    class FakeIngestResult:
        def model_dump(self) -> dict[str, object]:
            return {
                "source": "demo.txt",
                "doc_type": "not_allowed",
                "chunk_count": 1,
                "index_path": "index",
            }

    monkeypatch.setattr(
        upload,
        "get_settings",
        lambda: SimpleNamespace(knowledge_base_dir=str(tmp_path)),
    )
    monkeypatch.setattr(upload, "ingest_local_document", lambda *args, **kwargs: FakeIngestResult())

    client = TestClient(app)
    response = client.post(
        "/upload/local-doc",
        data={"doc_type": "not_allowed"},
        files={"file": ("demo.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 422
