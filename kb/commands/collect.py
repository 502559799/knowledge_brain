"""采集命令"""
import uuid, click
from kb.collectors.file_collector import FileCollector
from kb.collectors.webpage_collector import WebpageCollector
from kb.collectors.bookmark_collector import BookmarkCollector
from kb.collectors.note_collector import NoteCollector
from kb.storage.sqlite_storage import SQLiteStorage
from kb.processors.mining_worker import mine_document_async
from kb.config import Config

def _save_to_db(result, tags=None):
    if not result.success: return
    config = Config()
    storage = SQLiteStorage(str(config.data_dir / "db" / "metadata.db"))
    doc_id = str(uuid.uuid4())
    storage.add_knowledge(id=doc_id, title=result.title or "", content_type=result.metadata.get("content_type", ""),
                          source=result.metadata.get("source", ""), summary=result.summary or "",
                          word_count=result.word_count, file_path=str(result.file_path or ""),
                          content_hash=result.content_hash or "")
    for tag in (tags or []):
        storage.link_tag(doc_id, tag)
    # 异步挖掘
    content = ""
    if result.file_path and result.file_path.exists():
        content = result.file_path.read_text(encoding="utf-8", errors="ignore")[:3000]
    mine_document_async(doc_id, result.title or "", content, str(config.data_dir / "db" / "metadata.db"))
    storage.close()
    click.echo(f"✅ 已采集: {result.title} (id: {doc_id[:8]}...)")

def collect_file_cmd(path, tags, title):
    collector = FileCollector()
    result = collector.collect(path, tags=list(tags), title=title)
    _save_to_db(result, tags)

def collect_webpage_cmd(url, tags):
    collector = WebpageCollector()
    result = collector.collect(url, tags=list(tags))
    _save_to_db(result, tags)

def collect_bookmark_cmd(url, tags, title):
    collector = BookmarkCollector()
    result = collector.collect(url, tags=list(tags), title=title)
    _save_to_db(result, tags)

def collect_note_cmd(text, tags, title):
    collector = NoteCollector()
    result = collector.collect(text, tags=list(tags), title=title)
    _save_to_db(result, tags)
