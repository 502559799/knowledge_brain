"""知识采集API路由 - 支持Web端采集"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kb.web.dependencies import get_sqlite, get_config, get_chroma
from kb.processors.mining_worker import mine_document_async

router = APIRouter()


class NoteRequest(BaseModel):
    text: str
    title: Optional[str] = None
    tags: Optional[List[str]] = None


class WebpageRequest(BaseModel):
    url: str
    tags: Optional[List[str]] = None


@router.post("/collect/note")
def collect_note(req: NoteRequest):
    """通过API添加笔记"""
    from kb.collectors.note_collector import NoteCollector
    collector = NoteCollector()
    result = collector.collect(req.text, tags=req.tags or [], title=req.title)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "采集失败")
    config = get_config()
    storage = get_sqlite()
    doc_id = str(uuid.uuid4())
    existing = None
    if result.metadata.get("source"):
        existing = storage.source_exists(result.metadata["source"], result.metadata.get("content_type"))
    if existing:
        return {"success": True, "id": existing["id"], "duplicate": True}
    storage.add_knowledge(
        id=doc_id, title=result.title or req.title or "笔记",
        content_type="note",
        source=result.metadata.get("source", ""),
        summary=result.summary or req.text[:200],
        word_count=result.word_count,
    )
    for tag in (req.tags or []):
        storage.link_tag(doc_id, tag)
    chroma = get_chroma()
    chroma_path = str(chroma.path) if chroma else str(config.data_dir / "db" / "chroma")
    mine_document_async(doc_id, result.title or "笔记", req.text[:30000],
                        str(config.data_dir / "db" / "metadata.db"),
                        chroma_path=chroma_path)
    return {"success": True, "id": doc_id, "duplicate": False}


@router.post("/collect/webpage")
def collect_webpage(req: WebpageRequest):
    """通过API采集网页"""
    from kb.collectors.webpage_collector import WebpageCollector
    collector = WebpageCollector()
    result = collector.collect(req.url, tags=req.tags or [])
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "网页采集失败")
    config = get_config()
    storage = get_sqlite()
    doc_id = str(uuid.uuid4())
    existing = storage.source_exists(req.url, "webpage")
    if existing:
        return {"success": True, "id": existing["id"], "duplicate": True}
    content = ""
    if result.file_path and result.file_path.exists():
        try:
            content = result.file_path.read_text(encoding="utf-8", errors="ignore")[:30000]
        except Exception:
            pass
    storage.add_knowledge(
        id=doc_id, title=result.title or req.url,
        content_type="webpage", source=req.url,
        summary=result.summary or "",
        word_count=result.word_count,
        file_path=str(result.file_path or ""),
    )
    for tag in (req.tags or []):
        storage.link_tag(doc_id, tag)
    chroma = get_chroma()
    chroma_path = str(chroma.path) if chroma else str(config.data_dir / "db" / "chroma")
    mine_document_async(doc_id, result.title or req.url, content,
                        str(config.data_dir / "db" / "metadata.db"),
                        chroma_path=chroma_path)
    return {"success": True, "id": doc_id, "duplicate": False}
