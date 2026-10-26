"""知识项CRUD路由"""
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, field_validator
from kb.web.dependencies import get_sqlite, get_config

router = APIRouter()


def display_title(item):
    if not item.get("title") and item.get("content_type") == "file":
        from pathlib import Path
        item["title"] = Path(item.get("source") or item.get("file_path") or "未命名文件").stem
    return item



class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    user_notes: Optional[str] = None
    content: Optional[str] = None
    revision: int = 0
    tags: Optional[List[str]] = None

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, value):
        if value is None:
            return value
        tags = list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))
        if len(tags)>100 or any(len(tag)>100 for tag in tags):
            raise ValueError('最多 100 个标签，每个标签最多 100 字')
        return tags


@router.get("/items")
def list_items(content_type: Optional[str] = None, limit: int = Query(50, ge=1, le=100),
               offset: int = Query(0, ge=0), q: str = "", tag: str = "",
               tags: Optional[List[str]] = Query(default=None, max_length=100),
               tag_mode: Literal["and", "or"] = "and"):
    storage = get_sqlite()
    selected = list(dict.fromkeys(t.strip() for t in [*(tags or []), tag] if t.strip()))
    if q.strip():
        rows = storage.fts_search(q, offset+limit, selected, tag_mode, content_type)[offset:offset+limit]
    else:
        rows = storage.list_filtered_knowledge(content_type, selected, tag_mode, limit, offset)
    with storage._lock:
        for row in rows:
            if not row.get('summary'):
                chunk = storage.conn.execute("SELECT content FROM chunks WHERE knowledge_id=? ORDER BY chunk_index LIMIT 1", (row['id'],)).fetchone()
                row['preview'] = chunk[0][:200] if chunk else ''
            else:
                row['preview'] = row['summary'][:200]
    with storage._lock:
        for row in rows:
            row['tags'] = [r[0] for r in storage.conn.execute('SELECT t.name FROM tags t JOIN knowledge_tags kt ON kt.tag_id=t.id WHERE kt.knowledge_id=? ORDER BY t.name',(row['id'],))]
            version=storage.conn.execute('SELECT revision FROM knowledge_content WHERE knowledge_id=?',(row['id'],)).fetchone()
            row['revision']=version[0] if version else 0
    return [display_title(row) for row in rows]


@router.get("/items/{item_id}")
def get_item(item_id: str):
    item = get_sqlite().get_knowledge(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item["tags"] = get_sqlite().get_knowledge_tags(item_id)
    storage=get_sqlite()
    with storage._lock:
        original=storage.conn.execute('SELECT file_path FROM knowledge_originals WHERE knowledge_id=?',(item_id,)).fetchone()
        if original:
            item['original_file_path']=original[0]
    return display_title(item)


@router.patch("/items/{item_id}")
def update_item(item_id: str, req: UpdateItemRequest):
    storage = get_sqlite()
    from kb.processors.chunker import Chunker
    values = req.model_dump(exclude_none=True)
    values.pop('revision', None)
    tag_values = values.pop('tags', None)
    if not values and tag_values is None:
        raise HTTPException(400, "No fields to update")
    from kb.services.reading import read_item
    old = get_item(item_id)
    current = read_item(storage, get_config(), old)
    content = values.pop('content', current['content'])
    if content != current['content'] and values.get('summary', old.get('summary')) == old.get('summary'):
        values['summary'] = content[:512]
    chunks = Chunker(get_config().get('chunking.max_chunk_size',1000), get_config().get('chunking.chunk_overlap',100)).chunk(content) if content else []
    with storage._transaction() as c:
        row = c.execute('SELECT revision FROM knowledge_content WHERE knowledge_id=?', (item_id,)).fetchone()
        if (row[0] if row else 0) != req.revision:
            raise HTTPException(409, "条目已更新，请重新打开后编辑")
        if not c.execute('SELECT 1 FROM knowledge WHERE id=?',(item_id,)).fetchone():
            raise HTTPException(404, "Item not found")
        c.execute('INSERT INTO knowledge_content VALUES (?,?,?) ON CONFLICT(knowledge_id) DO UPDATE SET content=excluded.content,revision=excluded.revision', (item_id,content,req.revision+1))
        if tag_values is not None:
            c.execute('UPDATE tags SET count=MAX(count-1,0) WHERE id IN (SELECT tag_id FROM knowledge_tags WHERE knowledge_id=?)',(item_id,))
            c.execute('DELETE FROM knowledge_tags WHERE knowledge_id=?',(item_id,))
            for tag in tag_values:
                c.execute('INSERT OR IGNORE INTO tags(name,count) VALUES (?,0)',(tag,))
                tag_id=c.execute('SELECT id FROM tags WHERE name=?',(tag,)).fetchone()[0]
                c.execute('INSERT INTO knowledge_tags VALUES (?,?)',(item_id,tag_id))
                c.execute('UPDATE tags SET count=count+1 WHERE id=?',(tag_id,))
        for key,value in values.items():
            c.execute(f'UPDATE knowledge SET {key}=? WHERE id=?',(value,item_id))
        if content != current['content']:
            c.execute('UPDATE knowledge SET word_count=? WHERE id=?',(len(content),item_id))
            c.execute('DELETE FROM chunks WHERE knowledge_id=?',(item_id,))
            c.executemany('INSERT INTO chunks(id,knowledge_id,chunk_index,content) VALUES (?,?,?,?)',[(ck['id'],item_id,ck['index'],ck['content']) for ck in chunks])
        if content != current['content']:
            import hashlib
            c.execute('UPDATE knowledge SET content_hash=? WHERE id=?',(hashlib.sha256(content.encode()).hexdigest(),item_id))
            c.execute('DELETE FROM entity_mentions WHERE knowledge_id=?',(item_id,))
            c.execute('DELETE FROM entity_relation_sources WHERE knowledge_id=?',(item_id,))
            c.execute('DELETE FROM document_relations WHERE source_knowledge_id=? OR target_knowledge_id=?',(item_id,item_id))
        if content != current['content'] or values.get('title',old['title']) != old['title']:
            c.execute('DELETE FROM document_embeddings WHERE knowledge_id=?',(item_id,))
            c.execute('INSERT OR IGNORE INTO vector_deletions VALUES (?)',(item_id,))
    return {"success": True, "revision": req.revision+1}


@router.delete("/items/{item_id}")
def delete_item(item_id: str):
    storage = get_sqlite()
    if not storage.delete_knowledge(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    from kb.web.dependencies import get_chroma
    get_chroma()  # Drain durable cleanup outbox; SQLite deletion remains authoritative.
    return {"success": True}


@router.get("/items/{item_id}/chunks")
def get_chunks(item_id: str):
    return get_sqlite().get_chunks(item_id)


@router.get("/items/{item_id}/related")
def get_related(item_id: str, limit: int = 10):
    from kb.query.graph_query import GraphQuery
    gq = GraphQuery(get_sqlite())
    return gq.get_related_documents(item_id, limit)


@router.get("/items/{item_id}/content")
def get_content(item_id: str):
    from kb.services.reading import read_item
    item = get_item(item_id)
    result = {**item, 'revision': 0, **read_item(get_sqlite(), get_config(), item)}
    result['pdf_available'] = _pdf_path(item) is not None
    return result


@router.get("/items/{item_id}/download")
def download_content(item_id: str):
    item = get_content(item_id)
    return Response(item['content'], media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="knowledge.md"'})


def _pdf_path(item):
    from pathlib import Path
    if item.get('content_type') != 'file':
        return None
    path = Path(item.get('original_file_path') or item.get('source') or '').expanduser()
    try:
        if path.suffix.lower() == '.pdf' and path.is_file():
            with path.open('rb') as stream:
                if stream.read(5) == b'%PDF-':
                    return path
    except OSError:
        pass
    return None


@router.get("/items/{item_id}/pdf")
def original_pdf(item_id: str):
    path = _pdf_path(get_item(item_id))
    if not path:
        raise HTTPException(404, "原始 PDF 已移动或不存在")
    return FileResponse(path, media_type="application/pdf", content_disposition_type="inline",
                        headers={"X-Content-Type-Options":"nosniff"})


@router.get('/items/{item_id}/pdf/info')
def pdf_info(item_id: str):
    import shutil
    from PyPDF2 import PdfReader
    path=_pdf_path(get_item(item_id))
    if not path:
        raise HTTPException(404,'原始 PDF 不存在')
    return {'pages':len(PdfReader(str(path)).pages),'page_preview':bool(shutil.which('pdftoppm'))}


from functools import lru_cache


@lru_cache(maxsize=8)
def _render_pdf_page(path, modified, size, page):
    import shutil,subprocess,tempfile
    from pathlib import Path
    tool=shutil.which('pdftoppm')
    if not tool:
        raise HTTPException(503,'未安装 Poppler，请使用原始 PDF 链接打开')
    with tempfile.TemporaryDirectory(prefix='kb-pdf-') as folder:
        prefix=str(Path(folder)/'page')
        subprocess.run([tool,'-f',str(page),'-l',str(page),'-singlefile','-scale-to','1600','-png',path,prefix],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30)
        return Path(prefix+'.png').read_bytes()


@router.get('/items/{item_id}/pdf/page/{page}')
def pdf_page(item_id: str, page: int):
    from PyPDF2 import PdfReader
    path=_pdf_path(get_item(item_id))
    if not path:
        raise HTTPException(404,'原始 PDF 不存在')
    if page<1 or page>len(PdfReader(str(path)).pages):
        raise HTTPException(404,'页码超出范围')
    stat=path.stat()
    return Response(_render_pdf_page(str(path.resolve()),stat.st_mtime_ns,stat.st_size,page),media_type='image/png')
