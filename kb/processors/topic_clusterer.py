"""主题聚类处理器 - HDBSCAN + LLM标签"""
import json, logging, sqlite3
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from kb.processors.base import BaseProcessor, ProcessResult
from kb.config import Config
logger = logging.getLogger(__name__)

try:
    from sklearn.cluster import HDBSCAN
except ImportError:
    HDBSCAN = None

class TopicClusterer(BaseProcessor):
    """HDBSCAN主题聚类"""
    def __init__(self, config: Optional[Config] = None, min_cluster_size: int = 3, **kwargs):
        super().__init__(**kwargs)
        self.config = config or Config()
        self.min_cluster_size = min_cluster_size

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        if HDBSCAN is None:
            return ProcessResult(success=False, error="scikit-learn未安装")
        try:
            result = self.cluster_all(kwargs.get("db_path"))
            return ProcessResult(success=True, data=result)
        except Exception as e:
            return ProcessResult(success=False, error=str(e))

    def cluster_all(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        if db_path is None:
            data_dir = self.config.data_dir
            db_path = str(data_dir / "db" / "metadata.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT de.knowledge_id, de.embedding, k.title FROM document_embeddings de JOIN knowledge k ON de.knowledge_id = k.id")
            rows = cursor.fetchall()
            if len(rows) < self.min_cluster_size:
                return {"clusters": 0, "classified": 0, "noise": len(rows)}

            doc_ids, embeddings, titles = [], [], {}
            for row in rows:
                try:
                    emb = json.loads(row[1])
                    doc_ids.append(row[0])
                    embeddings.append(emb)
                    titles[row[0]] = row[2] or ""
                except: continue

            if len(embeddings) < self.min_cluster_size:
                return {"clusters": 0, "classified": 0, "noise": len(embeddings)}

            X = np.array(embeddings)
            clusterer = HDBSCAN(min_cluster_size=self.min_cluster_size, metric="euclidean")
            labels = clusterer.fit_predict(X)

            cursor.execute("DELETE FROM wiki_articles")
            cursor.execute("DELETE FROM wiki_categories")
            cursor.execute("DELETE FROM knowledge_topics")
            cursor.execute("DELETE FROM topic_clusters")
            conn.commit()

            clusters = {}
            noise = 0
            for did, label, emb in zip(doc_ids, labels, embeddings):
                if label == -1: noise += 1; continue
                clusters.setdefault(label, {"doc_ids": [], "embeddings": [], "titles": []})
                clusters[label]["doc_ids"].append(did)
                clusters[label]["embeddings"].append(emb)
                clusters[label]["titles"].append(titles.get(did, ""))

            classified = 0
            for label, cdata in clusters.items():
                centroid = np.array(cdata["embeddings"]).mean(axis=0).tolist()
                topic_label = cdata["titles"][0][:30] if cdata["titles"] else f"Topic ({len(cdata['doc_ids'])} docs)"
                cursor.execute("INSERT INTO topic_clusters (label, description, document_count, centroid_embedding) VALUES (?, ?, ?, ?)",
                               (topic_label, f"Cluster of {len(cdata['doc_ids'])} documents", len(cdata["doc_ids"]), json.dumps(centroid)))
                cluster_id = cursor.lastrowid
                for did in cdata["doc_ids"]:
                    cursor.execute("INSERT INTO knowledge_topics (knowledge_id, cluster_id, confidence) VALUES (?, ?, 1.0)", (did, cluster_id))
                    classified += 1
            conn.commit()
            return {"clusters": len(clusters), "classified": classified, "noise": noise}
        finally:
            conn.close()
