"""知识图谱查询 - N-hop遍历"""
import logging, time
from typing import Any, Dict, List, Optional
from kb.storage.sqlite_storage import SQLiteStorage
logger = logging.getLogger(__name__)

_cache: Dict[str, tuple] = {}

class GraphQuery:
    """知识图谱查询服务"""
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def get_graph(self, entity_type: Optional[str] = None, depth: int = 2, limit: int = 100, entity_id: Optional[int] = None) -> Dict[str, Any]:
        cursor = self.storage.conn.cursor()
        try:
            if entity_id is not None:
                return self._get_subgraph(cursor, entity_id, depth, limit)
            return self._get_full_graph(cursor, entity_type, limit)
        finally:
            cursor.close()

    def _get_full_graph(self, cursor, entity_type: Optional[str], limit: int) -> Dict[str, Any]:
        if entity_type:
            cursor.execute("SELECT id, name, display_name, type, description, mention_count FROM entities WHERE type = ? ORDER BY mention_count DESC LIMIT ?", (entity_type, limit))
        else:
            cursor.execute("SELECT id, name, display_name, type, description, mention_count FROM entities ORDER BY mention_count DESC LIMIT ?", (limit,))
        nodes = [dict(r) for r in cursor.fetchall()]
        node_ids = {n["id"] for n in nodes}
        edges = []
        if node_ids:
            ph = ",".join("?" for _ in node_ids)
            cursor.execute(f"SELECT id, source_entity_id, target_entity_id, relation_type, weight FROM entity_relations WHERE source_entity_id IN ({ph}) AND target_entity_id IN ({ph})", list(node_ids)*2)
            edges = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM entities")
        total_e = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM entity_relations")
        total_r = cursor.fetchone()[0]
        return {"nodes": nodes, "edges": edges, "stats": {"total_entities": total_e, "total_relations": total_r, "displayed_nodes": len(nodes), "displayed_edges": len(edges)}}

    def _get_subgraph(self, cursor, entity_id: int, depth: int, limit: int) -> Dict[str, Any]:
        cursor.execute("""WITH RECURSIVE related(entity_id, d) AS (SELECT ?, 0 UNION
            SELECT CASE WHEN er.source_entity_id = r.entity_id THEN er.target_entity_id ELSE er.source_entity_id END, r.d + 1
            FROM entity_relations er JOIN related r ON (er.source_entity_id = r.entity_id OR er.target_entity_id = r.entity_id) WHERE r.d < ?)
            SELECT DISTINCT entity_id FROM related LIMIT ?""", (entity_id, depth, limit))
        ids = [r[0] for r in cursor.fetchall()]
        if not ids: return {"nodes": [], "edges": [], "stats": {"total_entities": 0, "total_relations": 0, "displayed_nodes": 0, "displayed_edges": 0}}
        ph = ",".join("?" for _ in ids)
        cursor.execute(f"SELECT id, name, display_name, type, description, mention_count FROM entities WHERE id IN ({ph})", ids)
        nodes = [dict(r) for r in cursor.fetchall()]
        cursor.execute(f"SELECT id, source_entity_id, target_entity_id, relation_type, weight FROM entity_relations WHERE source_entity_id IN ({ph}) AND target_entity_id IN ({ph})", ids*2)
        edges = [dict(r) for r in cursor.fetchall()]
        return {"nodes": nodes, "edges": edges, "stats": {"total_entities": 0, "total_relations": 0, "displayed_nodes": len(nodes), "displayed_edges": len(edges)}}

    def get_entity(self, entity_id: int) -> Optional[Dict]:
        cursor = self.storage.conn.cursor()
        try:
            cursor.execute("SELECT id, name, display_name, type, description, mention_count FROM entities WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            if not row: return None
            entity = dict(row)
            cursor.execute("SELECT em.context, k.id as knowledge_id, k.title FROM entity_mentions em JOIN knowledge k ON k.id = em.knowledge_id WHERE em.entity_id = ?", (entity_id,))
            entity["mentions"] = [dict(r) for r in cursor.fetchall()]
            cursor.execute("SELECT er.id, er.relation_type, er.weight, e.id as related_id, e.name as related_name, e.type as related_type FROM entity_relations er JOIN entities e ON e.id = er.target_entity_id WHERE er.source_entity_id = ? UNION ALL SELECT er.id, er.relation_type, er.weight, e.id, e.name, e.type FROM entity_relations er JOIN entities e ON e.id = er.source_entity_id WHERE er.target_entity_id = ?", (entity_id, entity_id))
            entity["relations"] = [dict(r) for r in cursor.fetchall()]
            return entity
        finally:
            cursor.close()

    def get_related_documents(self, knowledge_id: str, limit: int = 10) -> List[Dict]:
        cursor = self.storage.conn.cursor()
        try:
            cursor.execute("SELECT dr.target_knowledge_id as knowledge_id, k.title, dr.relation_type, dr.score FROM document_relations dr JOIN knowledge k ON k.id = dr.target_knowledge_id WHERE dr.source_knowledge_id = ? UNION SELECT dr.source_knowledge_id, k.title, dr.relation_type, dr.score FROM document_relations dr JOIN knowledge k ON k.id = dr.source_knowledge_id WHERE dr.target_knowledge_id = ? ORDER BY score DESC LIMIT ?", (knowledge_id, knowledge_id, limit))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            cursor.close()
