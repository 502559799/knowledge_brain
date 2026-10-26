"""Collect HTTP resources, routing PDF bytes to the file parser before HTML decoding."""
import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict
from urllib.parse import unquote, urlsplit

import httpx
from kb.collectors.base import BaseCollector, CollectResult

logger = logging.getLogger(__name__)


class WebpageCollector(BaseCollector):
    MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024

    def _download(self, url):
        with httpx.stream('GET', url, follow_redirects=True, timeout=30) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                if len(content) + len(chunk) > self.MAX_DOWNLOAD_BYTES:
                    raise ValueError('链接内容超过 30 MB，请下载后通过文件入口导入')
                content.extend(chunk)
            return httpx.Response(response.status_code, headers=response.headers,
                                  content=bytes(content), request=httpx.Request('GET', response.url))

    def collect(self, source: Any, **kwargs: Any) -> CollectResult:
        url = str(source)
        try:
            response = self._download(url)
            mime = response.headers.get('content-type', '').split(';', 1)[0].lower().strip()
            pdf_bytes = response.content.lstrip().startswith(b'%PDF-')
            if pdf_bytes or mime == 'application/pdf':
                if not pdf_bytes:
                    raise ValueError('链接标记为 PDF，但未返回有效 PDF 文件，可能需要登录或链接已失效')
                return self._collect_pdf(response.content, url, str(response.url), **kwargs)
            if mime and not (mime.startswith('text/') or mime in ('application/xhtml+xml', 'application/xml')):
                raise ValueError('此链接不是 HTML 网页或 PDF，请使用文件入口导入')
            content = self._parse_html(response.text)
            if not content.strip():
                return CollectResult(success=False, error='网页内容提取为空')
            title = kwargs.pop('title', None) or self._page_title or url
            metadata = self._generate_metadata(title, content, url, **kwargs)
            filename = self._safe_filename('webpage', title)
            saved_path = self._save_to_file(content, metadata, filename, 'webpages')
            return CollectResult(success=True, file_path=saved_path, title=title,
                                 word_count=self._count_words(content), tags=kwargs.get('tags', []),
                                 metadata=metadata, content_hash=self._generate_content_hash(content))
        except httpx.HTTPStatusError as exc:
            return CollectResult(success=False, error=f'链接请求失败（HTTP {exc.response.status_code}），请检查链接是否有效或需要登录')
        except Exception as exc:
            return CollectResult(success=False, error=str(exc))

    def _collect_pdf(self, content, source_url, final_url, **kwargs):
        from kb.collectors.file_collector import FileCollector
        folder = self.output_dir / 'originals' / uuid.uuid4().hex
        folder.mkdir(parents=True)
        name = Path(unquote(urlsplit(final_url).path).replace('\\', '/')).name or 'document'
        name = re.sub(r'[\x00-\x1f\x7f]', '', name)[:150]
        if not name.lower().endswith('.pdf'):
            name += '.pdf'
        original = folder / name
        try:
            original.write_bytes(content)
            result = FileCollector(self.output_dir).collect(
                original, source_url=source_url, original_file_path=str(original), **kwargs)
            if not result.success:
                shutil.rmtree(folder)
                result.error = 'PDF 解析失败：' + (result.error or '文件格式无效')
            return result
        except Exception:
            shutil.rmtree(folder)
            raise

    def _extract_content(self, source: Any) -> str:
        response = self._download(str(source))
        if response.content.lstrip().startswith(b'%PDF-'):
            raise ValueError('PDF 请通过 collect 自动识别为文件')
        return self._parse_html(response.text)

    def _parse_html(self, text):
        # readability/lxml rejects NUL and XML-illegal control characters even in real HTML.
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '', text)
        from bs4 import BeautifulSoup
        parsed = BeautifulSoup(text, 'html.parser')
        self._page_title = parsed.title.get_text(strip=True) if parsed.title else ''
        try:
            from readability import Document
            from markdownify import markdownify
            return markdownify(Document(text).summary())
        except Exception:
            logger.debug('Readability unavailable or failed; using HTML text fallback', exc_info=True)
            for tag in parsed(['script', 'style', 'nav', 'footer', 'noscript']):
                tag.decompose()
            main = parsed.find('article') or parsed.find('main') or parsed
            return main.get_text(separator='\n\n', strip=True)

    def _generate_metadata(self, title: str, content: str, source: Any, **kwargs: Any) -> Dict[str, Any]:
        return {'title': title, 'source': str(source), 'content_type': 'webpage',
                'collected_at': __import__('datetime').datetime.now().isoformat(),
                'tags': kwargs.get('tags', [])}
