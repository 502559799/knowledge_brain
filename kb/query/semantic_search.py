"""语义搜索"""
import logging
from typing import Any, Dict, List, Optional

from kb.config import Config
from kb.query.models import SearchResult

logger = logging.getLogger(__name__)


class SemanticSearch:
    """基于向量嵌入的语义搜索，支持chunk级细粒度搜索"""

    def __init__(self, config: Optional[Config] = None, chroma_storage=None, embedder=None, storage=None):
        self.config = config or Config()
        self._chroma = chroma_storage
        self._embedder = embedder
        self._storage = storage

    def _get_chroma(self):
        if self._chroma is not None:
            return self._chroma
        from kb.storage.chroma_storage import ChromaStorage
        path = self.config.get("storage.persist_directory", "~/.knowledge-brain/db/chroma")
        self._chroma = ChromaStorage(path=path)
        return self._chroma

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        from kb.processors.embedder import Embedder
        self._embedder = Embedder(config=self.config)
        return self._embedder

    def search(self, query: str, tags: Optional[List[str]] = None, top_k: int = 5) -> List[SearchResult]:
        """语义搜索：优先使用chunk级向量（更精确），回退到文档级"""
        if not query.strip() or top_k <= 0:
            return []
        requested_k = top_k
        top_k = min(top_k * 4, 400)
        try:
            embedder = self._get_embedder()
            query_emb = embedder.embed_single(query)
            if not query_emb:
                return []
            chroma = self._get_chroma()

            # Try chunk-level search first (returns more relevant passages)
            chunk_ids_seen: set = set()
            results: List[SearchResult] = []
            try:
                chunk_results = chroma.query_chunks(embedding=query_emb, top_k=top_k * 2)
                if chunk_results.get("ids"):
                    doc_seen: set = set()
                    for i, chunk_id in enumerate(chunk_results["ids"]):
                        meta = chunk_results["metadatas"][i] if chunk_results.get("metadatas") else {}
                        doc_id = meta.get("knowledge_id", chunk_id)
                        if doc_id in doc_seen:
                            continue
                        doc_seen.add(doc_id)
                        score = 1.0 - chunk_results["distances"][i] if chunk_results.get("distances") else 0.0
                        content = chunk_results["documents"][i] if chunk_results.get("documents") else ""
                        results.append(SearchResult(id=doc_id, content=content, metadata={**meta, "chunk_id": chunk_id}, score=score))
                        if len(results) >= top_k:
                            break
            except Exception as ce:
                logger.debug(f"Chunk search failed, falling back to doc-level: {ce}")

            # Also try document-level to supplement
            if len(results) < top_k:
                try:
                    doc_results = chroma.query(embedding=query_emb, top_k=top_k)
                    existing_ids = {r.id for r in results}
                    for i, doc_id in enumerate(doc_results.get("ids", [])):
                        if doc_id in existing_ids:
                            continue
                        score = 1.0 - doc_results["distances"][i] if doc_results.get("distances") else 0.0
                        results.append(SearchResult(
                            id=doc_id,
                            content=doc_results["documents"][i] if doc_results.get("documents") else "",
                            metadata=doc_results["metadatas"][i] if doc_results.get("metadatas") else {},
                            score=score,
                        ))
                        if len(results) >= top_k:
                            break
                except Exception as de:
                    logger.debug(f"Doc-level search failed: {de}")

            if self._storage is None:
                from kb.storage.sqlite_storage import SQLiteStorage
                self._storage = SQLiteStorage(str(self.config.data_dir / "db" / "metadata.db"))
            valid = self._storage.search_metadata([r.id for r in results], tags)
            filtered = []
            for result in results:
                if result.id not in valid:
                    continue
                result.metadata = {**result.metadata, **valid[result.id]}
                filtered.append(result)
            return filtered[:requested_k]
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        try:
            chroma = self._get_chroma()
            return {"chroma_count": chroma.count(), "chunk_count": chroma.count_chunks()}
        except Exception:
            return {"chroma_count": 0, "chunk_count": 0}
