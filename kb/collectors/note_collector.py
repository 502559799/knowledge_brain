"""笔记收集器"""
import logging
from typing import Any, Dict
from kb.collectors.base import BaseCollector, CollectResult
logger = logging.getLogger(__name__)

class NoteCollector(BaseCollector):
    """手动笔记收集器"""
    def collect(self, source: Any, **kwargs: Any) -> CollectResult:
        text = str(source)
        if not text.strip():
            return CollectResult(success=False, error="笔记内容不能为空")
        try:
            title = kwargs.pop("title", text[:50])
            metadata = self._generate_metadata(title, text, "note", **kwargs)
            filename = self._safe_filename("note", title)
            saved_path = self._save_to_file(text, metadata, filename, "notes")
            return CollectResult(success=True, file_path=saved_path, title=title,
                                 word_count=self._count_words(text), tags=kwargs.get("tags", []),
                                 metadata=metadata, content_hash=self._generate_content_hash(text),
                                 summary=kwargs.get("summary"))
        except Exception as e:
            return CollectResult(success=False, error=str(e))

    def _extract_content(self, source: Any) -> str:
        return str(source)

    def _generate_metadata(self, title: str, content: str, source: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"title": title, "source": "note", "content_type": "note",
                "collected_at": __import__("datetime").datetime.now().isoformat(),
                "tags": kwargs.get("tags", [])}
