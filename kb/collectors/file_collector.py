"""文件收集器 - 支持 PDF/Markdown/TXT"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from kb.collectors.base import BaseCollector, CollectResult

logger = logging.getLogger(__name__)

class FileCollector(BaseCollector):
    """本地文件收集器"""
    SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown", ".rst"}

    def collect(self, source: Any, **kwargs: Any) -> CollectResult:
        file_path = Path(source)
        if not file_path.exists():
            return CollectResult(success=False, error=f"文件不存在: {source}")
        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return CollectResult(success=False, error=f"不支持的文件类型: {file_path.suffix}")

        try:
            content = self._extract_content(file_path)
            title = kwargs.pop("title", file_path.stem)
            metadata = self._generate_metadata(title, content, file_path, **kwargs)
            filename = self._safe_filename("file", title)
            saved_path = self._save_to_file(content, metadata, filename, "files")
            return CollectResult(
                success=True, file_path=saved_path, title=title,
                word_count=self._count_words(content),
                tags=kwargs.get("tags", []),
                metadata=metadata,
                content_hash=self._generate_content_hash(content),
                summary=kwargs.get("summary"),
            )
        except Exception as e:
            logger.error(f"文件收集失败: {e}")
            return CollectResult(success=False, error=str(e))

    def _extract_content(self, source: Any) -> str:
        path = Path(source)
        if path.suffix.lower() == ".pdf":
            return self._extract_pdf(path)
        return path.read_text(encoding="utf-8", errors="ignore")

    def _extract_pdf(self, path: Path) -> str:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            logger.warning("PyPDF2未安装，无法读取PDF")
            return ""

    def _generate_metadata(self, title: str, content: str, source: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            "title": title, "source": str(source), "content_type": "file",
            "collected_at": __import__("datetime").datetime.now().isoformat(),
            "tags": kwargs.get("tags", []),
        }
