"""收集器基类 - 策略模式 + 模板方法"""
import hashlib, re, unicodedata, uuid
import yaml
from kb.config import Config
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class CollectResult:
    """收集结果数据类"""
    success: bool
    file_path: Optional[Path] = None
    title: Optional[str] = None
    word_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    content_hash: Optional[str] = None
    summary: Optional[str] = None

class BaseCollector(ABC):
    """收集器抽象基类"""
    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or (Config().data_dir / "1_collect")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def collect(self, source: Any, **kwargs: Any) -> CollectResult:
        pass

    @abstractmethod
    def _extract_content(self, source: Any) -> str:
        pass

    @abstractmethod
    def _generate_metadata(self, title: str, content: str, source: Any, **kwargs: Any) -> Dict[str, Any]:
        pass

    def _save_to_file(self, content: str, metadata: Dict[str, Any], filename: str, sub_dir: str) -> Path:
        target_dir = self.output_dir / sub_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        yaml_header = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip()
        full_content = f"---\n{yaml_header}\n---\n\n{content}"
        file_path = target_dir / filename
        file_path.write_text(full_content, encoding="utf-8")
        return file_path

    @staticmethod
    def _generate_content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _count_words(content: str) -> int:
        chinese = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
        english_text = "".join(" " if "\u4e00" <= c <= "\u9fff" else c for c in content)
        return chinese + len(english_text.split())

    @staticmethod
    def _safe_filename(prefix: str, title: Optional[str] = None) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]
        if title:
            slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii").lower())[:50].strip("-")
            return f"{timestamp}_{slug or prefix}.md"
        return f"{timestamp}_{prefix}.md"
