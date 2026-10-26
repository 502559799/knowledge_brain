"""主题聚类查询"""
import logging
from typing import Any, Dict, List, Optional
from kb.storage.sqlite_storage import SQLiteStorage
logger = logging.getLogger(__name__)

class TopicQuery:
    """主题聚类查询服务"""
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def get_topics(self) -> List[Dict]:
        c = self.storage.conn.cursor()
        c.execute("SELECT id, label, description, document_count, created_at FROM topic_clusters ORDER BY document_count DESC")
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    def get_topic_documents(self, cluster_id: int, limit: int = 20) -> List[Dict]:
        c = self.storage.conn.cursor()
        c.execute("SELECT k.id, k.title, k.content_type, k.collected_at, k.source, kt.confidence FROM knowledge_topics kt JOIN knowledge k ON kt.knowledge_id = k.id WHERE kt.cluster_id = ? ORDER BY kt.confidence DESC LIMIT ?", (cluster_id, limit))
        rows = [dict(r) for r in c.fetchall()]
        from pathlib import Path
        for row in rows:
            if not row['title']:
                row['title']=Path(row.get('source') or '').name if row['content_type']=='file' else '未命名资料'
        c.close()
        return rows
