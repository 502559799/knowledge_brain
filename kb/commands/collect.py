"""采集命令"""
import uuid
import click
from kb.collectors.file_collector import FileCollector
from kb.collectors.webpage_collector import WebpageCollector
from kb.collectors.bookmark_collector import BookmarkCollector
from kb.collectors.note_collector import NoteCollector
from kb.storage.sqlite_storage import SQLiteStorage
from kb.processors.mining_worker import mine_document_async
from kb.config import Config


def _save_to_db(result, tags=None):
    if not result.success:
        click.echo(f"❌ 采集失败: {result.error or 'unknown error'}", err=True)
        return
    config = Config()
    storage = SQLiteStorage(str(config.data_dir / "db" / "metadata.db"))
    from kb.services.ingestion import ingest, read_content
    content = read_content(result)
    try:
        doc_id, duplicate = ingest(storage, config, result, content, list(tags or []))
    finally:
        storage.close()
    if duplicate:
        if result.metadata.get('original_file_path'):
            from pathlib import Path
            original=Path(result.metadata['original_file_path'])
            if original.resolve().is_relative_to((config.data_dir/'1_collect'/'originals').resolve()):
                original.unlink(missing_ok=True)
                original.parent.rmdir()
                if result.file_path:
                    result.file_path.unlink(missing_ok=True)
        click.echo(f"⚠️ 已存在: {result.title} (id: {doc_id[:8]}...)")
        return

    chroma_path = config.get("storage.persist_directory", str(config.data_dir / "db" / "chroma"))
    db_path = str(config.data_dir / "db" / "metadata.db")
    mine_document_async(doc_id, result.title or "", content, db_path, chroma_path=chroma_path)
    click.echo(f"✅ 已采集: {result.title} (id: {doc_id[:8]}...) - 后台挖掘中...")


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
