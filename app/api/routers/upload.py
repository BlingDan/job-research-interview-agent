from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.schemas.rag import DocType, LocalPathIngestRequest
from app.services.rag_service import ingest_local_document

router = APIRouter(tags=["upload"])

@router.post("/upload/local-doc")
async def load_local_document(
    file: Annotated[UploadFile, File(description="需要上传的文件")],
    doc_type: Annotated[DocType, Form(description="文档类型，resume/project_notes/company_notes/interview_notes/jd_archive/other")] = "other",
):
    settings = get_settings()
    upload_dir = Path(settings.knowledge_base_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in [".pdf", ".txt", ".md", ".docx"]:
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    target_path = upload_dir / f"{uuid4().hex}{suffix}"
    target_path.write_bytes(await file.read())

    result = ingest_local_document(
        target_path,
        doc_type=doc_type,
        original_filename=file.filename or target_path.name,
    )
    return result.model_dump()

@router.post("/upload/local-path")
def ingest_local_path(payload: LocalPathIngestRequest):
    path = Path(payload.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    result = ingest_local_document(
        path,
        doc_type=payload.doc_type,
        original_filename=path.name,
    )
    return result.model_dump()
