"""Atomic local ingestion. Optional model enrichment follows the committed source."""
import uuid
from kb.processors.chunker import Chunker


def ingest(storage, config, result, content, tags=None):
    if not result.success:
        raise ValueError(result.error or "采集失败")
    kind = result.metadata.get("content_type", "")
    source = result.metadata.get("source", "")
    chunks = Chunker(config.get("chunking.max_chunk_size", 1000),
                     config.get("chunking.chunk_overlap", 100)).chunk(content) if content.strip() else []
    # Duplicate check and writes share one SQLite write transaction, including across processes.
    with storage._transaction() as cursor:
        cursor.execute("BEGIN IMMEDIATE")
        existing = None
        if result.content_hash:
            existing = cursor.execute("SELECT id FROM knowledge WHERE content_hash=? AND content_type=?",
                                      (result.content_hash, kind)).fetchone()
        if not existing and source and kind != "note":
            existing = cursor.execute("SELECT id FROM knowledge WHERE source=? AND content_type=?", (source, kind)).fetchone()
        if existing:
            return existing[0], True
        doc_id = str(uuid.uuid4())
        cursor.execute("""INSERT INTO knowledge(id,title,content_type,source,collected_at,summary,word_count,file_path,content_hash)
                          VALUES (?,?,?,?,CURRENT_TIMESTAMP,?,?,?,?)""",
                       (doc_id, result.title or "", kind, source, result.summary or content[:512],
                        result.word_count, str(result.file_path or ""), result.content_hash or ""))
        if result.metadata.get('original_file_path'):
            cursor.execute('INSERT INTO knowledge_originals VALUES (?,?)',(doc_id,result.metadata['original_file_path']))
        cursor.executemany("INSERT INTO chunks(id,knowledge_id,chunk_index,content) VALUES (?,?,?,?)",
                           [(c["id"], doc_id, c["index"], c["content"]) for c in chunks])
        for tag in set(tags or result.tags):
            cursor.execute("INSERT OR IGNORE INTO tags(name,count) VALUES (?,0)", (tag,))
            tag_id = cursor.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()[0]
            cursor.execute("INSERT INTO knowledge_tags VALUES (?,?)", (doc_id, tag_id))
            cursor.execute("UPDATE tags SET count=count+1 WHERE id=?", (tag_id,))
    return doc_id, False


def read_content(result):
    if result.file_path and result.file_path.exists():
        text = result.file_path.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            sections = text.split("\n---\n", 1)
            if len(sections) == 2:
                return sections[1].lstrip("\n")
        return text
    return result.summary or ""
