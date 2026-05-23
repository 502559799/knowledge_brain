"""RAG查询 - 检索增强生成"""
import logging
from typing import Any, Dict, List, Optional
from kb.config import Config
from kb.query.models import RAGResult, SearchResult
from kb.query.semantic_search import SemanticSearch
logger = logging.getLogger(__name__)

class RAGQuery:
    """RAG查询: 语义搜索→上下文构建→LLM生成"""
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        rag_cfg = self.config.get("query.rag", {})
        self.top_k = rag_cfg.get("top_k", 5)
        self.temperature = rag_cfg.get("temperature", 0.3)
        self.max_tokens = min(rag_cfg.get("max_tokens", 1000), 8192)
        self.semantic_search = None
        try:
            self.semantic_search = SemanticSearch(self.config)
        except Exception as e:
            logger.warning(f"语义搜索初始化失败: {e}")
        self.llm_available = False
        self._init_llm()

    def _init_llm(self):
        api_key = self.config.get("llm.api_key", "")
        if not api_key: return
        try:
            import litellm
            self.api_key = api_key
            provider = self.config.get("llm.provider", "dashscope")
            model = self.config.get("llm.model", "qwen-plus")
            if provider == "dashscope" and "/" not in model: model = f"dashscope/{model}"
            elif provider == "openai_compatible":
                model = f"openai/{model}" if "/" not in model else model
                self.api_base = self.config.get("llm.base_url", "")
            self.model = model
            self.llm_available = True
        except Exception: pass

    def query(self, question: str, tags: Optional[List[str]] = None, top_k: Optional[int] = None) -> RAGResult:
        if not question.strip():
            raise ValueError("问题不能为空")
        k = top_k or self.top_k
        # 语义搜索
        search_results = []
        if self.semantic_search:
            try:
                search_results = self.semantic_search.search(question, tags, k)
            except Exception as e:
                logger.warning(f"语义搜索失败: {e}")
        if not search_results:
            return RAGResult(answer="未找到相关信息", question=question)
        # 构建上下文
        context = self._build_context(search_results)
        # LLM生成
        if self.llm_available:
            try:
                import litellm
                messages = [
                    {"role": "system", "content": "基于提供的上下文回答问题。只使用上下文信息，不足时明确说明。"},
                    {"role": "user", "content": f"上下文:\n{context}\n\n问题: {question}"}
                ]
                kwargs = {"model": self.model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens, "api_key": self.api_key}
                if hasattr(self, 'api_base') and self.api_base: kwargs["api_base"] = self.api_base
                resp = litellm.completion(**kwargs)
                answer = resp.choices[0].message.content
                return RAGResult(answer=answer, sources=search_results, context=context, question=question, confidence=0.8)
            except Exception as e:
                logger.warning(f"LLM生成失败: {e}")
        # 降级: 返回搜索结果
        return RAGResult(answer=f"找到{len(search_results)}个相关文档(LLM不可用)", sources=search_results, context=context, question=question)

    def _build_context(self, results: List[SearchResult]) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            src = r.metadata.get("source", r.id)
            parts.append(f"[来源{i}] {src}\n{r.content}\n")
        return "\n".join(parts)
