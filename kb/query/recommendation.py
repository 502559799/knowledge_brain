"""知识推荐"""
import logging
from typing import Any, Dict, List, Optional
from kb.storage.sqlite_storage import SQLiteStorage
logger = logging.getLogger(__name__)

class RecommendationEngine:
    """基于相似度和阅读历史的推荐"""
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def get_recommendations(self, knowledge_id: str, limit: int = 10) -> List[Dict]:
        """获取推荐文档"""
        c = self.storage.conn.cursor()
        try:
            c.execute("SELECT dr.target_knowledge_id as id, k.title, k.content_type, dr.relation_type, dr.score FROM document_relations dr JOIN knowledge k ON k.id = dr.target_knowledge_id WHERE dr.source_knowledge_id = ? ORDER BY dr.score DESC LIMIT ?", (knowledge_id, limit))
            return [dict(r) for r in c.fetchall()]
        finally:
            c.close()

    def get_recent_unexplored(self, limit: int = 10) -> List[Dict]:
        """获取近期无关系的文档(推荐探索)"""
        c = self.storage.conn.cursor()
        c.execute("SELECT k.id, k.title, k.content_type, k.collected_at FROM knowledge k LEFT JOIN document_relations dr ON k.id = dr.source_knowledge_id WHERE dr.id IS NULL ORDER BY k.collected_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in c.fetchall()]
