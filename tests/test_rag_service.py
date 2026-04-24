from pathlib import Path
from types import SimpleNamespace

from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from pydantic import SecretStr


class FakeEmbeddings(Embeddings):
    def _vec(self, text: str) -> list[float]:
        lower = text.lower()
        tokens = ["fastapi", "sse", "agent", "bm25", "rag", "resume", "company", "python"]
        dims = [1.0 if token in lower else 0.0 for token in tokens]
        if not any(dims):
            dims[0] = float(len(text) % 7 + 1) / 10
        return dims

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def _patch_rag_runtime(tmp_path: Path, monkeypatch):
    from app.services import rag_service

    monkeypatch.setattr(
        rag_service,
        "get_settings",
        lambda: SimpleNamespace(
            knowledge_base_dir=str(tmp_path / "kb"),
            rag_index_dir=str(tmp_path / "kb" / "vector_index"),
            rag_embedding_backend="huggingface",
            rag_embedding_model="fake",
            rag_model_cache_dir=str(tmp_path / "model"),
            rag_openai_embedding_model="text-embedding-3-small",
            llm_api_key="test",
            llm_base_url="https://example.com/v1",
            rag_top_k=2,
            rag_vector_k=3,
            rag_bm25_k=3,
            rag_rrf_k=60,
            rag_max_context_chars=2000,
        ),
    )
    monkeypatch.setattr(rag_service, "get_embeddings", lambda: FakeEmbeddings())
    return rag_service


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


def test_load_all_index_documents_reads_documents_through_docstore_search(monkeypatch):
    from app.services import rag_service

    docs_by_id = {
        "doc-1": Document(page_content="first"),
        "doc-2": Document(page_content="second"),
    }

    class FakeDocstore:
        def search(self, docstore_id: str):
            return docs_by_id[docstore_id]

    fake_vectorstore = SimpleNamespace(
        index_to_docstore_id={0: "doc-1", 1: "doc-2"},
        docstore=FakeDocstore(),
    )

    monkeypatch.setattr(rag_service, "load_vectorstore", lambda: fake_vectorstore)

    docs = rag_service.load_all_index_documents()

    assert docs == [docs_by_id["doc-1"], docs_by_id["doc-2"]]


def test_ingest_and_retrieve_markdown_with_hybrid_mode(tmp_path: Path, monkeypatch):
    rag_service = _patch_rag_runtime(tmp_path, monkeypatch)

    sample = tmp_path / "project.md"
    sample.write_text(
        "# 项目经历\n\n我做过 FastAPI SSE Agent 项目，也实现过 BM25 RAG 检索。",
        encoding="utf-8",
    )

    record = rag_service.ingest_local_document(sample, doc_type="project_notes")
    bundle = rag_service.retrieve_local_context("FastAPI SSE Agent RAG", doc_type_filter=["project_notes"])

    assert record.chunk_count > 0
    assert (tmp_path / "kb" / "vector_index").exists()
    assert (tmp_path / "kb" / "documents.json").exists()
    assert (tmp_path / "kb" / "parents.json").exists()
    assert bundle.hits
    assert bundle.hits[0].retrieval_mode == "hybrid"
    assert "FastAPI" in bundle.summary
    assert "- parent_id:" in bundle.summary


def test_retrieve_returns_empty_bundle_when_filter_has_no_candidates(tmp_path: Path, monkeypatch):
    rag_service = _patch_rag_runtime(tmp_path, monkeypatch)

    sample = tmp_path / "resume.md"
    sample.write_text("# 简历\n\n我做过 FastAPI SSE Agent 项目。", encoding="utf-8")
    rag_service.ingest_local_document(sample, doc_type="resume")

    bundle = rag_service.retrieve_local_context("FastAPI SSE Agent", doc_type_filter=["company_notes"])

    assert bundle.hits == []
    assert bundle.summary == "本地知识库未命中与当前任务相关的内容。"


def test_other_documents_remain_searchable_for_category_filters(tmp_path: Path, monkeypatch):
    from app.tools.retriever_tool import get_doc_type_filter

    rag_service = _patch_rag_runtime(tmp_path, monkeypatch)

    sample = tmp_path / "local_context.md"
    sample.write_text("# 本地资料\n\nFastAPI SSE Agent 项目经验。", encoding="utf-8")
    rag_service.ingest_local_document(sample, doc_type="other")

    bundle = rag_service.retrieve_local_context(
        "FastAPI SSE Agent",
        doc_type_filter=get_doc_type_filter("candidate_gap"),
    )

    assert bundle.hits
    assert bundle.hits[0].doc_type == "other"
    assert "FastAPI" in bundle.summary


def test_rrf_promotes_doc_appearing_in_both_lists():
    from app.services.rag_service import rrf_rerank

    shared = Document(page_content="FastAPI SSE 项目经验", metadata={"chunk_id": "shared"})
    vector_only = Document(page_content="向量检索", metadata={"chunk_id": "vector"})
    bm25_only = Document(page_content="BM25 检索", metadata={"chunk_id": "bm25"})

    result = rrf_rerank(
        vector_docs=[shared, vector_only],
        bm25_docs=[shared, bm25_only],
        k=60,
    )

    assert result[0].metadata["chunk_id"] == "shared"
    assert result[0].metadata["retrieval_mode"] == "hybrid"
