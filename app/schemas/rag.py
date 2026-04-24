from typing import Literal, Any

from pydantic import BaseModel, Field

DocType = Literal[
    "resume",   # 简历
    "project_notes",    # 项目经历笔记
    "company_notes",    # 公司资料
    "interview_notes",  # 面经/八股/面试题笔记
    "jd_archive",   # 岗位 JD 集合
    "other",    # 其他
]


# 通过本地路径导入资料的接口
class LocalPathIngestRequest(BaseModel):
    path: str
    doc_type: DocType = "other"

# 资料导入完成后的记录
class LocalDocumentRecord(BaseModel):
    source: str
    doc_type: DocType
    chunk_count: int
    index_path: str # FAISS 索引存储路径

# 一条具体命中的本地资料
class LocalContextHit(BaseModel):
    content: str
    source: str | None = None
    doc_type: str | None = None
    parent_id: str | None = None    # 父文档 ID。用于父子块策略。如果一整个项目笔记是父文档，切出来的小块是子块，
    chunk_id: str | None = None     # 当前命中 chunk id
    score: float | None = None      # 检索分数
    retrieval_mode: str = "vector"  # 检索模式，vector / bm25 / hybrid 
    metadata: dict[str, Any] = Field(default_factory=dict)  # LangChain Document.metadata 的完整保留字段。

# 一次 query 的完整本地检索结果
class LocalContextBundle(BaseModel):
    query: str
    summary: str
    hits: list[LocalContextHit] = Field(default_factory=list)
