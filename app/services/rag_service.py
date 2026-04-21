import json
import uuid
from pathlib import Path
from typing import cast, get_args

from pydantic import SecretStr
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredWordDocumentLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.core.config import get_settings
from app.schemas.rag import DocType, LocalContextBundle, LocalContextHit, LocalDocumentRecord


VALID_DOC_TYPES = set(get_args(DocType))


# 1. 加载文件
# 2. 切块
# 3. 建 FAISS
# 4. 向量检索
def ingest_local_document(
    file_path: str | Path,
    *,
    doc_type: DocType = "other",
    original_filename: str | None = None,
) -> LocalDocumentRecord:
    """从本地文件路径导入资料，构建向量库，并返回导入记录"""
    settings = get_settings()
    source_path = Path(file_path)
    kb_dir = Path(settings.knowledge_base_dir)
    kb_dir.mkdir(parents=True, exist_ok=True)

    # 1. 加载文件
    docs = load_files(source_path, doc_type=doc_type, original_filename=original_filename)
    # 2. 切块
    chunks = split_documents(docs)
    # 3. 建 FAISS
    vectorstore = build_or_update_vectorstore(chunks)

    save_manifest_record(
        source=str(source_path),
        doc_type=doc_type,
        chunk_count=len(chunks),
        index_path=settings.rag_index_dir,
    )
    return LocalDocumentRecord(
        source=str(source_path),
        doc_type=doc_type,
        chunk_count=len(chunks),
        index_path=settings.rag_index_dir,
    )

def load_files(
    file_path: Path,
    *,
    doc_type: DocType = "other",
    original_filename: str | None = None,
) -> list[Document]:
    """根据文件后缀，选择不同的加载器来加载文件内容"""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        loader = PyPDFLoader(str(file_path))
    elif suffix in [".txt", ".md"]:
        loader = TextLoader(str(file_path), encoding="utf-8")
    elif suffix in [".docx", ".doc"]:
        loader = UnstructuredWordDocumentLoader(str(file_path))
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    
    documents = loader.load()
    parent_id = uuid.uuid4().hex

    for doc in documents:
        doc.metadata.update({
            "source": str(file_path),
            "original_filename": original_filename or file_path.name,
            "doc_type": doc_type,
            "parent_id": parent_id,
        })
    
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """根据文档类型，选择不同的切块策略"""

    chunks: list[Document] = []

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
        ],
        strip_headers=False,
    )

    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
    )

    for doc in documents:
        source = str(doc.metadata.get("source", ""))
        if source.lower().endswith((".md", ".txt")) and "#" in doc.page_content[:500]:
            split_docs = markdown_splitter.split_text(doc.page_content)
            for index, chunk in enumerate(split_docs):
                chunk.metadata.update(doc.metadata)
                chunk.metadata["chunk_id"] = uuid.uuid4().hex
                chunk.metadata["chunk_index"] = index
                chunks.append(chunk)
        else:
            split_docs = fallback_splitter.split_documents([doc])
            for index, chunk in enumerate(split_docs):
                chunk.metadata.update(doc.metadata)
                chunk.metadata["chunk_id"] = uuid.uuid4().hex
                chunk.metadata["chunk_index"] = index
                chunks.append(chunk)

    return chunks


def build_or_update_vectorstore(
    chunks: list[Document],
) -> FAISS:
    """构建或者更新FAISS向量库"""
    settings = get_settings()
    embeddings = get_embeddings()
    index_path = Path(settings.rag_index_dir)

    if index_path.exists():
        # 从已有索引加载
        vectorstore = FAISS.load_local(
            str(index_path),
            embeddings,
            allow_dangerous_deserialization=True,
        )
        vectorstore.add_documents(chunks)
    else:
        vectorstore = FAISS.from_documents(chunks, embeddings)
    
    index_path.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(index_path))
    return vectorstore

def load_vectorstore() -> FAISS | None:
    """加载已有的 FAISS 向量库，如果不存在则返回 None"""
    settings = get_settings()
    index_path = Path(settings.rag_index_dir)

    if not index_path.exists():
        return None
    
    return FAISS.load_local(
        str(index_path),
        get_embeddings(),
        allow_dangerous_deserialization=True, 
    )

def retrive_local_context(
    query: str,
    *,
    top_k: int | None = None,
    doc_type_filter: list[DocType] | None = None,
) -> LocalContextBundle:
    """根据查询，从本地向量库中检索相关内容"""
    settings = get_settings()
    vectorstore = load_vectorstore()
    if vectorstore is None:
        return LocalContextBundle(
            query=query,
            summary="本地知识库还没有可用索引。",
            hits=[],
        )
    
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": top_k or settings.rag_top_k},
    )
    docs = retriever.invoke(query)

    # 按照文档类型过略检索结果
    if doc_type_filter:
        docs = [
            doc for doc in docs
            if _metadata_doc_type(doc) in doc_type_filter
        ]
    
    hits = [
        LocalContextHit(
            content=doc.page_content,
            source=_metadata_text(doc, "source"),
            doc_type=_metadata_doc_type(doc),
            parent_id=_metadata_text(doc, "parent_id"),
            chunk_id=_metadata_text(doc, "chunk_id"),
            retrieval_mode="vector",
            metadata=dict(doc.metadata),
        )
        for doc in docs[: settings.rag_top_k]
    ]

    return LocalContextBundle(
        query=query,
        summary=render_local_context(query, hits),
        hits=hits,
    )

def render_local_context(query: str, hits: list[LocalContextHit]) -> str:
    """把检索到的本地资料渲染成文本形式，方便 LLM 直接阅读"""
    settings = get_settings()
    if not hits:
        return "本地知识库未命中与当前任务相关的内容。"

    lines = [f"本地检索 query: {query}", ""]
    current_length = 0

    for index, hit in enumerate(hits, start=1):
        block = "\n".join(
            [
                f"[本地资料 {index}]",
                f"- doc_type: {hit.doc_type or 'unknown'}",
                f"- source: {hit.source or 'unknown'}",
                f"- retrieval_mode: {hit.retrieval_mode}",
                hit.content,
                "",
            ]
        )
        if current_length + len(block) > settings.rag_max_context_chars:
            break
        lines.append(block)
        current_length += len(block)

    return "\n".join(lines).strip()

def get_embeddings():
    """获取 embeddings 实例，根据配置选择 OpenAI 还是 HuggingFace"""
    settings = get_settings()

    if settings.rag_embedding_backend == "openai":
        return OpenAIEmbeddings(
            model=settings.rag_openai_embedding_model,
            api_key=SecretStr(settings.llm_api_key) if settings.llm_api_key else None,
            base_url=settings.llm_base_url,
        )

    model_cache_dir = Path(settings.rag_model_cache_dir)
    model_cache_dir.mkdir(parents=True, exist_ok=True)

    return HuggingFaceEmbeddings(
        model_name=settings.rag_embedding_model,
        cache_folder=str(model_cache_dir),
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def save_manifest_record(
    *,
    source: str,
    doc_type: DocType,
    chunk_count: int,
    index_path: str,
) -> None:
    """把每次导入的资料记录到一个 manifest 文件中，方便后续管理和查询"""
    settings = get_settings()
    manifest_path = Path(settings.knowledge_base_dir) / "documents.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    if manifest_path.exists():
        records = json.loads(manifest_path.read_text(encoding="utf-8"))

    records.append(
        {
            "source": source,
            "doc_type": doc_type,
            "chunk_count": chunk_count,
            "index_path": index_path,
        }
    )

    manifest_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _metadata_text(doc: Document, key: str) -> str | None:
    value = doc.metadata.get(key)
    if value is None:
        return None
    return str(value)


def _metadata_doc_type(doc: Document) -> DocType | None:
    value = doc.metadata.get("doc_type")
    if isinstance(value, str) and value in VALID_DOC_TYPES:
        return cast(DocType, value)
    return None
