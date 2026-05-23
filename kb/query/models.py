"""查询数据模型"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class SearchResult:
    """搜索结果"""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

@dataclass
class RAGResult:
    """RAG查询结果"""
    answer: str
    sources: List[SearchResult] = field(default_factory=list)
    context: str = ""
    question: str = ""
    confidence: float = 0.0
    session_id: Optional[str] = None

@dataclass
class RankedChunk:
    """排序后的分块"""
    content: str
    source: str
    retrieval_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RetrievalContext:
    """检索上下文"""
    chunks: List[RankedChunk] = field(default_factory=list)
    entities: List[Dict] = field(default_factory=list)
    topics: List[Dict] = field(default_factory=list)
    total_tokens: int = 0

@dataclass
class EnhancedRAGResult:
    """增强RAG结果"""
    answer: str
    question: str
    sources: List[SearchResult] = field(default_factory=list)
    context: str = ""
    confidence: float = 0.0
    retrieval_strategy: str = ""
    session_id: Optional[str] = None
    entities: List[Dict] = field(default_factory=list)
    topics: List[Dict] = field(default_factory=list)

@dataclass
class EntityContext:
    """实体上下文"""
    entity_id: int
    name: str
    entity_type: str
    description: str = ""
    relations: List[Dict] = field(default_factory=list)
