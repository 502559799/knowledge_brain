"""书签收集器"""
import logging, re
from typing import Any, Dict, List
from kb.collectors.base import BaseCollector, CollectResult
logger = logging.getLogger(__name__)

class BookmarkCollector(BaseCollector):
    """浏览器书签收集器"""
    def collect(self, source: Any, **kwargs: Any) -> CollectResult:
        url = str(source)
        try:
            title = kwargs.pop("title", url)
            content = f"# {title}\n\n书签链接: {url}"
            metadata = self._generate_metadata(title, content, url, **kwargs)
            filename = self._safe_filename("bookmark", title)
            saved_path = self._save_to_file(content, metadata, filename, "bookmarks")
            return CollectResult(success=True, file_path=saved_path, title=title,
                                 word_count=self._count_words(content), tags=kwargs.get("tags", []),
                                 metadata=metadata, content_hash=self._generate_content_hash(content))
        except Exception as e:
            return CollectResult(success=False, error=str(e))

    def import_html(self, html_path: str, **kwargs: Any) -> List[CollectResult]:
        """从浏览器书签HTML文件导入"""
        from pathlib import Path
        content = Path(html_path).read_text(encoding="utf-8")
        urls = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]*)</a>', content)
        results = []
        for url, title in urls:
            r = self.collect(url, title=title, **kwargs)
            results.append(r)
        return results

    def _extract_content(self, source: Any) -> str:
        return str(source)

    def _generate_metadata(self, title: str, content: str, source: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"title": title, "source": str(source), "content_type": "bookmark",
                "collected_at": __import__("datetime").datetime.now().isoformat(),
                "tags": kwargs.get("tags", [])}
