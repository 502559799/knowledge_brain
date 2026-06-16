"""文本分块处理器 - 递归字符分割"""
import logging, uuid
from typing import Any, Dict, List
from kb.processors.base import BaseProcessor, ProcessResult
logger = logging.getLogger(__name__)

class Chunker(BaseProcessor):
    """递归字符分割分块器"""
    def __init__(self, max_chunk_size: int = 1000, chunk_overlap: int = 100, **kwargs):
        super().__init__(**kwargs)
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        content = str(data) if not isinstance(data, str) else data
        if not content.strip():
            return ProcessResult(success=False, error="内容为空")
        doc_id = kwargs.get("doc_id", "")
        chunks = self.chunk(content, doc_id=doc_id)
        return ProcessResult(success=True, data=chunks, metadata={"chunk_count": len(chunks)})

    def chunk(self, content: str, doc_id: str = "") -> List[Dict[str, Any]]:
        """将文本分块"""
        if len(content) <= self.max_chunk_size:
            return [{"id": str(uuid.uuid4()), "content": content, "index": 0, "doc_id": doc_id}]

        chunks = []
        start = 0
        idx = 0
        while start < len(content):
            end = start + self.max_chunk_size
            chunk_text = content[start:end]
            # 在句子边界处断开
            if end < len(content):
                for sep in ["。", ".", "！", "？", "!", "?", "\n\n", "\n"]:
                    pos = chunk_text.rfind(sep)
                    if pos > self.max_chunk_size * 0.3:
                        chunk_text = chunk_text[:pos + len(sep)]
                        break
            chunks.append({"id": str(uuid.uuid4()), "content": chunk_text.strip(), "index": idx, "doc_id": doc_id})
            advance = max(len(chunk_text) - self.chunk_overlap, 1)
            start += advance
            idx += 1
        return chunks
