"""知识采集API路由 - 支持Web端采集"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from pydantic import BaseModel, field_validator

from kb.web.dependencies import get_sqlite, get_config, get_chroma
from kb.processors.mining_worker import mine_document_async

router = APIRouter()


class NoteRequest(BaseModel):
    text: str
    title: Optional[str] = None
    tags: Optional[List[str]] = None


class WebpageRequest(BaseModel):
    url: str
    title: Optional[str] = None
    tags: Optional[List[str]] = None

    @field_validator('url')
    @classmethod
    def valid_url(cls,value):
        from urllib.parse import urlsplit
        parsed=urlsplit(value.strip())
        if parsed.scheme not in ('http','https') or not parsed.hostname:
            raise ValueError('请输入 http 或 https 网页链接')
        return value.strip()


def _store(result, content):
    from kb.services.ingestion import ingest
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "采集失败")
    config = get_config()
    doc_id, duplicate = ingest(get_sqlite(), config, result, content)
    if duplicate and result.metadata.get('original_file_path'):
        from pathlib import Path
        original=Path(result.metadata['original_file_path'])
        if original.resolve().is_relative_to((config.data_dir/'1_collect'/'originals').resolve()):
            original.unlink(missing_ok=True)
            original.parent.rmdir()
            if result.file_path and result.file_path.resolve().is_relative_to(config.data_dir.resolve()):
                result.file_path.unlink(missing_ok=True)
    if not duplicate:
        mine_document_async(doc_id, result.title or "", content,
                            str(config.data_dir / "db" / "metadata.db"),
                            chroma_path=config.get("storage.persist_directory"))
    return {"success": True, "id": doc_id, "duplicate": duplicate}


@router.post("/collect/note")
def collect_note(req: NoteRequest):
    from kb.collectors.note_collector import NoteCollector
    collector = NoteCollector(output_dir=get_config().data_dir / "1_collect")
    result = collector.collect(req.text, tags=req.tags or [], title=req.title)
    return _store(result, req.text)


@router.post("/collect/webpage")
def collect_webpage(req: WebpageRequest):
    from kb.collectors.webpage_collector import WebpageCollector
    from kb.services.ingestion import read_content
    collector = WebpageCollector(output_dir=get_config().data_dir / "1_collect")
    result = collector.collect(req.url, tags=req.tags or [], title=req.title)
    return _store(result, read_content(result))


@router.post('/collect/bookmark')
def collect_bookmark(req: WebpageRequest):
    from kb.collectors.bookmark_collector import BookmarkCollector
    from kb.services.ingestion import read_content
    result=BookmarkCollector(get_config().data_dir/'1_collect').collect(req.url,title=req.title,tags=req.tags or [])
    return _store(result,read_content(result))


@router.post('/collect/file')
def collect_file(file: UploadFile = File(...), title: str = Form(''), tags: str = Form('')):
    from pathlib import Path
    from kb.collectors.file_collector import FileCollector
    from kb.services.ingestion import read_content
    name=Path((file.filename or '').replace('\\','/')).name
    if Path(name).suffix.lower() not in FileCollector.SUPPORTED_EXTENSIONS:
        raise HTTPException(400,'支持 PDF、Markdown、TXT 和 RST 文件')
    content=file.file.read(30*1024*1024+1)
    if len(content)>30*1024*1024:
        raise HTTPException(413,'文件大小不能超过 30 MB')
    if not content:
        raise HTTPException(400,'文件为空')
    folder=get_config().data_dir/'originals'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    original=folder/name
    original.write_bytes(content)
    result=None
    try:
        parsed_tags=list(dict.fromkeys(t.strip() for t in tags.replace('，',',').split(',') if t.strip()))
        result=FileCollector(get_config().data_dir/'1_collect').collect(original,title=title or name,tags=parsed_tags)
        response=_store(result,read_content(result))
        if response['duplicate']:
            original.unlink();folder.rmdir()
            if result.file_path:
                result.file_path.unlink(missing_ok=True)
        return response
    except Exception:
        if original.exists():
            original.unlink();folder.rmdir()
        if result and result.file_path:
            result.file_path.unlink(missing_ok=True)
        raise
