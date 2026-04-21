from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr


def test_get_embeddings_uses_project_model_cache_dir(tmp_path: Path, monkeypatch):
    from app.services import rag_service

    captured: dict[str, object] = {}

    class FakeHuggingFaceEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(rag_service, "HuggingFaceEmbeddings", FakeHuggingFaceEmbeddings)
    monkeypatch.setattr(
        rag_service,
        "get_settings",
        lambda: SimpleNamespace(
            rag_embedding_backend="huggingface",
            rag_embedding_model="BAAI/bge-small-zh-v1.5",
            rag_model_cache_dir=str(tmp_path / "model"),
        ),
    )

    embedding = rag_service.get_embeddings()

    assert isinstance(embedding, FakeHuggingFaceEmbeddings)
    assert captured["model_name"] == "BAAI/bge-small-zh-v1.5"
    assert captured["cache_folder"] == str(tmp_path / "model")
    assert Path(captured["cache_folder"]).exists()


def test_get_embeddings_wraps_openai_api_key_as_secret_str(monkeypatch):
    from app.services import rag_service

    captured: dict[str, object] = {}

    class FakeOpenAIEmbeddings:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(rag_service, "OpenAIEmbeddings", FakeOpenAIEmbeddings)
    monkeypatch.setattr(
        rag_service,
        "get_settings",
        lambda: SimpleNamespace(
            rag_embedding_backend="openai",
            rag_openai_embedding_model="text-embedding-3-small",
            llm_api_key="sk-test",
            llm_base_url="https://example.com/v1",
        ),
    )

    embedding = rag_service.get_embeddings()

    assert isinstance(embedding, FakeOpenAIEmbeddings)
    assert isinstance(captured["api_key"], SecretStr)
    assert captured["api_key"].get_secret_value() == "sk-test"
