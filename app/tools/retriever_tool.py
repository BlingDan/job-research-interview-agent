from __future__ import annotations

from app.schemas.rag import LocalContextBundle, DocType
from app.services.rag_service import retrive_local_context
from typing import TYPE_CHECKING

def get_local_context(
    query:str, 
    *,
    doc_types: list[DocType] | None = None,
) -> LocalContextBundle:
    """获取本地知识库中的相关内容"""
    return retrive_local_context(
        query=query,
        doc_type_filter=doc_types,
    )