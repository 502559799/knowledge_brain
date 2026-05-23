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
            raise ImportError("chromadb未安装")
        expanded = os.path.expanduser(path)
        self.path = Path(expanded)
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.path), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    def add_documents(self, ids: List[str], embeddings: List[List[float]], metadatas: Optional[List[Dict]] = None, documents: Optional[List[str]] = None) -> bool:
        try:
            self.collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas or [{}]*len(ids), documents=documents or [""]*len(ids))
            return True
        except Exception as e:
            raise Exception(f"添加文档失败: {e}")

    def query(self, embedding: List[float], top_k: int = 5, where_filter: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            params = {"query_embeddings": [embedding], "n_results": top_k}
            if where_filter: params["where"] = where_filter
            results = self.collection.query(**params)
            return {"ids": results["ids"][0], "distances": results["distances"][0], "metadatas": results["metadatas"][0], "documents": results["documents"][0]}
        except Exception as e:
            raise Exception(f"查询失败: {e}")

    def delete(self, ids: List[str]) -> bool:
        try: self.collection.delete(ids=ids); return True
        except Exception as e: raise Exception(f"删除失败: {e}")

    def count(self) -> int:
        return self.collection.count()

    def close(self):
        self.client = None
        self.collection = None
