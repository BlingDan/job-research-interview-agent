from __future__ import annotations

from app.schemas.rag import LocalContextBundle, DocType
from app.services.rag_service import retrieve_local_context

def get_local_context(
    query:str, 
    *,
    doc_types: list[DocType] | None = None,
) -> LocalContextBundle:
    """获取本地知识库中的相关内容"""
    return retrieve_local_context(
        query=query,
        doc_type_filter=doc_types,
    )


def get_doc_type_filter(category: str | None) -> list[DocType] | None:
    mapping: dict[str, list[DocType]] = {
        "jd": ["jd_archive", "resume", "project_notes", "other"],
        "company": ["company_notes", "jd_archive", "other"],
        "interview": ["interview_notes", "project_notes", "resume", "other"],
        "candidate_gap": ["resume", "project_notes", "jd_archive", "other"],
    }
    return mapping.get(category or "")
