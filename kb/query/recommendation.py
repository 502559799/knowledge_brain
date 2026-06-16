"""知识推荐"""
import logging
from typing import Dict, List, Optional
from kb.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """基于相似度和共享实体的知识推荐（双向查询）"""

    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def get_recommendations(self, knowledge_id: str, limit: int = 10) -> List[Dict]:
        """获取推荐文档（双向查询）"""
        c = self.storage.conn.cursor()
        try:
            c.execute("""
                SELECT dr.target_knowledge_id as id, k.title, k.content_type, k.summary, dr.relation_type, dr.score
                FROM document_relations dr
                JOIN knowledge k ON k.id = dr.target_knowledge_id
                WHERE dr.source_knowledge_id = ?
                UNION
                SELECT dr.source_knowledge_id, k.title, k.content_type, k.summary, dr.relation_type, dr.score
                FROM document_relations dr
                JOIN knowledge k ON k.id = dr.source_knowledge_id
                WHERE dr.target_knowledge_id = ?
                ORDER BY score DESC LIMIT ?
            """, (knowledge_id, knowledge_id, limit))
            return [dict(r) for r in c.fetchall()]
        finally:
            c.close()

    def get_recent_unexplored(self, limit: int = 10) -> List[Dict]:
        """获取近期无关系的文档(推荐探索) - 检查双向关系"""
        c = self.storage.conn.cursor()
        try:
            c.execute("""
                SELECT k.id, k.title, k.content_type, k.summary, k.collected_at
                FROM knowledge k
                WHERE NOT EXISTS (
                    SELECT 1 FROM document_relations dr
                    WHERE dr.source_knowledge_id = k.id OR dr.target_knowledge_id = k.id
                )
                ORDER BY k.collected_at DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in c.fetchall()]
        finally:
            c.close()
