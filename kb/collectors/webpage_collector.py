"""网页收集器"""
import logging
from typing import Any, Dict
from kb.collectors.base import BaseCollector, CollectResult

logger = logging.getLogger(__name__)

class WebpageCollector(BaseCollector):
    """网页内容收集器"""
    def collect(self, source: Any, **kwargs: Any) -> CollectResult:
        url = str(source)
        try:
            content = self._extract_content(url)
            if not content:
                return CollectResult(success=False, error="网页内容提取为空")
            title = kwargs.pop("title", url)
            metadata = self._generate_metadata(title, content, url, **kwargs)
            filename = self._safe_filename("webpage", title)
            saved_path = self._save_to_file(content, metadata, filename, "webpages")
            return CollectResult(
                success=True, file_path=saved_path, title=title,
                word_count=self._count_words(content), tags=kwargs.get("tags", []),
                metadata=metadata, content_hash=self._generate_content_hash(content),
            )
        except Exception as e:
            return CollectResult(success=False, error=str(e))

    def _extract_content(self, source: Any) -> str:
        import httpx
        url = str(source)
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
        try:
            from readability import Document
            from markdownify import markdownify as md
            doc = Document(resp.text)
            return md(doc.summary())
        except ImportError:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)

    def _generate_metadata(self, title: str, content: str, source: Any, **kwargs: Any) -> Dict[str, Any]:
        return {"title": title, "source": str(source), "content_type": "webpage",
                "collected_at": __import__("datetime").datetime.now().isoformat(),
                "tags": kwargs.get("tags", [])}
