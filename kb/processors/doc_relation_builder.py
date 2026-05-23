"""文档关系构建器 - embedding相似度 + 共享实体"""
import json, logging, sqlite3
from typing import Any, Dict, Optional
import numpy as np
from kb.processors.base import BaseProcessor, ProcessResult
from kb.config import Config
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
        if db_path is None:
            db_path = str(self.config.data_dir / "db" / "metadata.db")
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT knowledge_id, embedding FROM document_embeddings")
            rows = cursor.fetchall()
            if len(rows) < 2:
                return {"embedding_similarity": 0, "shared_entity": 0}

            emb_sim_count = 0
            doc_embs = [(r[0], np.array(json.loads(r[1]))) for r in rows]
            for i in range(len(doc_embs)):
                for j in range(i+1, len(doc_embs)):
                    sim = self._cosine_sim(doc_embs[i][1], doc_embs[j][1])
                    if sim > self.similarity_threshold:
                        cursor.execute("INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score) VALUES (?, ?, 'embedding_similarity', ?)",
                                       (doc_embs[i][0], doc_embs[j][0], float(sim)))
                        emb_sim_count += 1

            # 共享实体关系
            shared_count = 0
            cursor.execute("SELECT e.id, GROUP_CONCAT(em.knowledge_id) FROM entities e JOIN entity_mentions em ON e.id = em.entity_id GROUP BY e.id HAVING COUNT(DISTINCT em.knowledge_id) > 1")
            for row in cursor.fetchall():
                doc_ids = row[1].split(",")
                for i in range(len(doc_ids)):
                    for j in range(i+1, len(doc_ids)):
                        cursor.execute("INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score) VALUES (?, ?, 'shared_entity', 1.0)",
                                       (doc_ids[i], doc_ids[j]))
                        shared_count += 1
            conn.commit()
            return {"embedding_similarity": emb_sim_count, "shared_entity": shared_count}
        finally:
            conn.close()

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0: return 0.0
        return float(np.dot(a, b) / (na * nb))
