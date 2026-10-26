"""Retryable vector cleanup. A failed derived index never resurrects a source."""
import logging

logger = logging.getLogger(__name__)


def flush_vector_deletions(storage, chroma):
    with storage._lock:
        ids = [r[0] for r in storage.conn.execute('SELECT knowledge_id FROM vector_deletions LIMIT 100')]
    if not ids:
        return
    try:
        chroma.delete(ids)
    except Exception:
        logger.warning('向量删除暂时失败，已保存待重试任务', exc_info=True)
        return
    with storage._transaction() as cursor:
        cursor.executemany('DELETE FROM vector_deletions WHERE knowledge_id=?', [(id,) for id in ids])
