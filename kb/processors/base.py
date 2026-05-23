"""处理器基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class ProcessResult:
    """处理结果"""
    success: bool
    data: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

class BaseProcessor(ABC):
    """处理器抽象基类"""
    def __init__(self, **kwargs: Any) -> None:
        self.config = kwargs

    @abstractmethod
    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        pass
