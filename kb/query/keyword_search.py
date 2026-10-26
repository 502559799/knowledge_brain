"""关键词搜索"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from kb.query.models import SearchResult
logger = logging.getLogger(__name__)

class KeywordSearch:
    """基于FTS5的关键词搜索"""
    def __init__(self, data_dir: str = "~/.knowledge-brain"):
        self.data_dir = Path(data_dir).expanduser()
        self._storage = None

    def _get_storage(self):
        if self._storage is None:
            from kb.storage.sqlite_storage import SQLiteStorage
            self._storage = SQLiteStorage(str(self.data_dir / "db" / "metadata.db"))
        return self._storage

    def search(self, keywords: str, limit: int = 20, tags: Optional[List[str]] = None) -> List[SearchResult]:
        try:
            storage = self._get_storage()
            rows = storage.fts_search(keywords, limit, tags)
            return [SearchResult(id=r["id"], content=r.get("matched_content") or r.get("summary") or r.get("title", ""), metadata=r, score=1.0) for r in rows]
        except Exception as e:
            logger.error(f"关键词搜索失败: {e}")
            return []
