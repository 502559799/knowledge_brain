"""文档关系构建器 - embedding相似度 + 共享实体"""
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

import numpy as np

from kb.config import Config
from kb.processors.base import BaseProcessor, ProcessResult

logger = logging.getLogger(__name__)


class DocRelationBuilder(BaseProcessor):
    """文档间关系发现"""

    def __init__(self, config: Optional[Config] = None, similarity_threshold: float = 0.7, **kwargs):
        super().__init__(**kwargs)
        self.config = config or Config()
        self.similarity_threshold = similarity_threshold

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        try:
            counts = self.build_all(kwargs.get("db_path"))
            return ProcessResult(success=True, data=counts)
        except Exception as e:
            return ProcessResult(success=False, error=str(e))

    def build_all(self, db_path: Optional[str] = None) -> Dict[str, int]:
        """全量重建文档关系（先清除旧关系）"""
        if db_path is None:
            db_path = str(self.config.data_dir / "db" / "metadata.db")
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            # Clear old relations to avoid stale data accumulation
            cursor.execute("DELETE FROM document_relations")

            cursor.execute("SELECT knowledge_id, embedding FROM document_embeddings")
            rows = cursor.fetchall()
            if len(rows) < 2:
                conn.commit()
                return {"embedding_similarity": 0, "shared_entity": 0}

            emb_sim_count = 0
            doc_embs: List[tuple] = []
            for r in rows:
                try:
                    doc_embs.append((r[0], np.array(json.loads(r[1]))))
                except Exception:
                    continue

            for i in range(len(doc_embs)):
                for j in range(i + 1, len(doc_embs)):
                    sim = self._cosine_sim(doc_embs[i][1], doc_embs[j][1])
                    if sim > self.similarity_threshold:
                        # Insert both directions for easier bidirectional queries
                        for src, tgt in [(doc_embs[i][0], doc_embs[j][0]),
                                         (doc_embs[j][0], doc_embs[i][0])]:
                            cursor.execute(
                                "INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score) VALUES (?, ?, 'embedding_similarity', ?)",
                                (src, tgt, float(sim)))
                        emb_sim_count += 1

            # 共享实体关系
            shared_count = 0
            cursor.execute("""SELECT e.id, GROUP_CONCAT(DISTINCT em.knowledge_id)
                              FROM entities e
                              JOIN entity_mentions em ON e.id = em.entity_id
                              GROUP BY e.id
                              HAVING COUNT(DISTINCT em.knowledge_id) > 1""")
            for row in cursor.fetchall():
                doc_ids = row[1].split(",")
                for i in range(len(doc_ids)):
                    for j in range(i + 1, len(doc_ids)):
                        for src, tgt in [(doc_ids[i], doc_ids[j]),
                                         (doc_ids[j], doc_ids[i])]:
                            cursor.execute(
                                "INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score) VALUES (?, ?, 'shared_entity', 1.0)",
                                (src, tgt))
                        shared_count += 1
            conn.commit()
            return {"embedding_similarity": emb_sim_count, "shared_entity": shared_count}
        finally:
            conn.close()

    def build_incremental(self, new_knowledge_id: str, db_path: Optional[str] = None) -> Dict[str, int]:
        """增量构建：只为新文档查找相似文档，避免O(n^2)全量重建"""
        if db_path is None:
            db_path = str(self.config.data_dir / "db" / "metadata.db")
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT embedding FROM document_embeddings WHERE knowledge_id = ?", (new_knowledge_id,))
            row = cursor.fetchone()
            if not row:
                return {"embedding_similarity": 0, "shared_entity": 0}
            try:
                new_emb = np.array(json.loads(row[0]))
            except Exception:
                return {"embedding_similarity": 0, "shared_entity": 0}

            cursor.execute("SELECT knowledge_id, embedding FROM document_embeddings WHERE knowledge_id != ?", (new_knowledge_id,))
            emb_sim_count = 0
            for existing_id, emb_json in cursor.fetchall():
                try:
                    existing_emb = np.array(json.loads(emb_json))
                    sim = self._cosine_sim(new_emb, existing_emb)
                    if sim > self.similarity_threshold:
                        for src, tgt in [(new_knowledge_id, existing_id),
                                         (existing_id, new_knowledge_id)]:
                            cursor.execute(
                                "INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score) VALUES (?, ?, 'embedding_similarity', ?)",
                                (src, tgt, float(sim)))
                        emb_sim_count += 1
                except Exception:
                    continue

            # Shared entities for the new document
            cursor.execute("""SELECT DISTINCT em2.knowledge_id
                              FROM entity_mentions em1
                              JOIN entity_mentions em2 ON em1.entity_id = em2.entity_id AND em2.knowledge_id != em1.knowledge_id
                              WHERE em1.knowledge_id = ?""", (new_knowledge_id,))
            shared_count = 0
            for (related_id,) in cursor.fetchall():
                for src, tgt in [(new_knowledge_id, related_id),
                                 (related_id, new_knowledge_id)]:
                    cursor.execute(
                        "INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score) VALUES (?, ?, 'shared_entity', 1.0)",
                        (src, tgt))
                shared_count += 1

            conn.commit()
            return {"embedding_similarity": emb_sim_count, "shared_entity": shared_count}
        finally:
            conn.close()

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))
