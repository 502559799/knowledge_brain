"""语义搜索"""
import logging
from typing import Any, Dict, List, Optional
from kb.config import Config
from kb.query.models import SearchResult
logger = logging.getLogger(__name__)

class SemanticSearch:
    """基于向量嵌入的语义搜索"""
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._chroma = None
        self._embedder = None

    def _get_chroma(self):
        if self._chroma is None:
            from kb.storage.chroma_storage import ChromaStorage
            path = self.config.get("storage.persist_directory", "~/.knowledge-brain/db/chroma")
            self._chroma = ChromaStorage(path=path)
        return self._chroma

    def _get_embedder(self):
        if self._embedder is None:
            from kb.processors.embedder import Embedder
            self._embedder = Embedder(config=self.config)
        return self._embedder

    def search(self, query: str, tags: Optional[List[str]] = None, top_k: int = 5) -> List[SearchResult]:
        """语义搜索"""
        try:
            embedder = self._get_embedder()
            query_emb = embedder.embed_single(query)
            chroma = self._get_chroma()
            where_filter = None
            if tags:
                where_filter = {"tags": {"$in": tags}}
            results = chroma.query(embedding=query_emb, top_k=top_k, where_filter=where_filter)
            search_results = []
            for i, doc_id in enumerate(results["ids"]):
                score = 1.0 - results["distances"][i] if results["distances"] else 0.0
                search_results.append(SearchResult(
                    id=doc_id,
                    content=results["documents"][i] if results["documents"] else "",
                    metadata=results["metadatas"][i] if results["metadatas"] else {},
                    score=score
                ))
            return search_results
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        try:
            return {"chroma_count": self._get_chroma().count()}
        except: return {"chroma_count": 0}
