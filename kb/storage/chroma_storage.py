"""ChromaDB向量存储"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None


class ChromaStorage:
    """ChromaDB向量存储类"""

    def __init__(self, path: str, collection_name: str = "knowledge", **kwargs):
        if chromadb is None:
            raise ImportError("chromadb未安装，请运行: pip install chromadb>=0.4.0")
        expanded = os.path.expanduser(path)
        self.path = Path(expanded)
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.path), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    def _get_chunks_collection(self):
        return self.client.get_or_create_collection(name="chunks", metadata={"hnsw:space": "cosine"})

    def add_documents(self, ids: List[str], embeddings: List[List[float]],
                      metadatas: Optional[List[Dict]] = None,
                      documents: Optional[List[str]] = None) -> bool:
        """添加文档级向量，使用upsert避免重复ID错误"""
        try:
            if metadatas is None:
                metadatas = [{} for _ in range(len(ids))]
            if documents is None:
                documents = ["" for _ in range(len(ids))]
            self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
            return True
        except Exception as e:
            raise Exception(f"添加文档失败: {e}") from e

    def add_chunks(self, ids: List[str], embeddings: List[List[float]],
                   metadatas: Optional[List[Dict]] = None,
                   documents: Optional[List[str]] = None) -> bool:
        """添加chunk级向量"""
        try:
            chunks_col = self._get_chunks_collection()
            if metadatas is None:
                metadatas = [{} for _ in range(len(ids))]
            if documents is None:
                documents = ["" for _ in range(len(ids))]
            chunks_col.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
            return True
        except Exception as e:
            raise Exception(f"添加chunks失败: {e}") from e

    def query(self, embedding: List[float], top_k: int = 5, where_filter: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            params: Dict[str, Any] = {"query_embeddings": [embedding], "n_results": top_k}
            if where_filter:
                params["where"] = where_filter
            results = self.collection.query(**params)
            return {
                "ids": results["ids"][0] if results["ids"] else [],
                "distances": results["distances"][0] if results["distances"] else [],
                "metadatas": results["metadatas"][0] if results["metadatas"] else [],
                "documents": results["documents"][0] if results["documents"] else [],
            }
        except Exception as e:
            raise Exception(f"查询失败: {e}") from e

    def query_chunks(self, embedding: List[float], top_k: int = 5, where_filter: Optional[Dict] = None) -> Dict[str, Any]:
        """查询chunk级向量"""
        try:
            chunks_col = self._get_chunks_collection()
            params: Dict[str, Any] = {"query_embeddings": [embedding], "n_results": top_k}
            if where_filter:
                params["where"] = where_filter
            results = chunks_col.query(**params)
            return {
                "ids": results["ids"][0] if results["ids"] else [],
                "distances": results["distances"][0] if results["distances"] else [],
                "metadatas": results["metadatas"][0] if results["metadatas"] else [],
                "documents": results["documents"][0] if results["documents"] else [],
            }
        except Exception as e:
            raise Exception(f"Chunk查询失败: {e}") from e

    def delete(self, ids: List[str]) -> bool:
        try:
            self.collection.delete(ids=ids)
            try:
                self._get_chunks_collection().delete(where={"knowledge_id": {"$in": ids}})
            except Exception:
                raise
            return True
        except Exception as e:
            raise Exception(f"删除失败: {e}") from e

    def count(self) -> int:
        return self.collection.count()

    def count_chunks(self) -> int:
        try:
            return self._get_chunks_collection().count()
        except Exception:
            return 0

    def close(self):
        self.client = None
        self.collection = None
