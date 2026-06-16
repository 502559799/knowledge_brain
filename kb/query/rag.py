"""RAG查询 - 检索增强生成"""
import logging
from typing import Any, Dict, List, Optional
from kb.config import Config
from kb.query.models import RAGResult, SearchResult

logger = logging.getLogger(__name__)


class RAGQuery:
    """RAG查询: 语义搜索→关键词回退→上下文构建（含对话历史）→LLM生成"""

    def __init__(self, config: Optional[Config] = None, semantic_search=None, keyword_search=None, conversation_manager=None):
        self.config = config or Config()
        rag_cfg = self.config.get("query.rag", {})
        self.top_k = rag_cfg.get("top_k", 5)
        self.temperature = rag_cfg.get("temperature", 0.3)
        self.max_tokens = min(rag_cfg.get("max_tokens", 1000), 8192)
        self.context_budget = rag_cfg.get("context_budget", 4000)
        self.semantic_search = semantic_search
        self.keyword_search = keyword_search
        self.conversation_manager = conversation_manager

        # Initialize search backends if not injected
        if self.semantic_search is None:
            try:
                from kb.query.semantic_search import SemanticSearch
                self.semantic_search = SemanticSearch(self.config)
            except Exception as e:
                logger.warning(f"语义搜索初始化失败: {e}")
        if self.keyword_search is None:
            try:
                from kb.query.keyword_search import KeywordSearch
                self.keyword_search = KeywordSearch(data_dir=str(self.config.data_dir))
            except Exception as e:
                logger.warning(f"关键词搜索初始化失败: {e}")

        self.llm_available = False
        self._init_llm()

    def _init_llm(self):
        api_key = self.config.get("llm.api_key", "")
        if not api_key:
            return
        try:
            import litellm
            self.api_key = api_key
            provider = self.config.get("llm.provider", "dashscope")
            model = self.config.get("llm.model", "qwen-plus")
            if provider == "dashscope" and "/" not in model:
                model = f"dashscope/{model}"
            elif provider == "openai_compatible":
                model = f"openai/{model}" if "/" not in model else model
                self.api_base = self.config.get("llm.base_url", "")
            self.model = model
            self.llm_available = True
        except Exception:
            pass

    def query(self, question: str, tags: Optional[List[str]] = None,
              top_k: Optional[int] = None, session_id: Optional[str] = None) -> RAGResult:
        if not question.strip():
            raise ValueError("问题不能为空")
        k = top_k or self.top_k
        search_results: List[SearchResult] = []

        # Try semantic search first
        if self.semantic_search:
            try:
                search_results = self.semantic_search.search(question, tags, k)
            except Exception as e:
                logger.warning(f"语义搜索失败: {e}")

        # Fallback to keyword search if semantic returns nothing
        if not search_results and self.keyword_search:
            try:
                search_results = self.keyword_search.search(question, k)
            except Exception as e:
                logger.warning(f"关键词搜索失败: {e}")

        if not search_results:
            return RAGResult(answer="未找到相关信息", question=question, session_id=session_id)

        context = self._build_context(search_results)

        # Save to conversation history if manager provided
        if self.conversation_manager and session_id:
            self.conversation_manager.add_turn(session_id, "user", question)

        if self.llm_available:
            try:
                import litellm
                messages = [
                    {"role": "system",
                     "content": "你是一个知识助理。基于提供的上下文回答用户问题。只使用上下文信息，如果上下文不足以回答，请明确说明。回答使用中文。"},
                ]
                # Add conversation history
                if self.conversation_manager and session_id:
                    history = self.conversation_manager.get_history(session_id)
                    for turn in history[-6:]:  # Last 6 turns (3 Q&A pairs)
                        messages.append({"role": turn["role"], "content": turn["content"]})
                messages.append({"role": "user", "content": f"参考资料:\n{context}\n\n问题: {question}"})

                kwargs: Dict[str, Any] = {
                    "model": self.model, "messages": messages,
                    "temperature": self.temperature, "max_tokens": self.max_tokens,
                    "api_key": self.api_key,
                }
                if hasattr(self, 'api_base') and self.api_base:
                    kwargs["api_base"] = self.api_base
                resp = litellm.completion(**kwargs)
                answer = resp.choices[0].message.content

                if self.conversation_manager and session_id:
                    self.conversation_manager.add_turn(session_id, "assistant", answer)

                return RAGResult(
                    answer=answer, sources=search_results, context=context,
                    question=question, confidence=0.8, session_id=session_id,
                )
            except Exception as e:
                logger.warning(f"LLM生成失败: {e}")

        return RAGResult(
            answer=f"找到{len(search_results)}个相关文档(LLM不可用)",
            sources=search_results, context=context, question=question, session_id=session_id,
        )

    def _build_context(self, results: List[SearchResult]) -> str:
        parts = []
        total_len = 0
        for i, r in enumerate(results, 1):
            title = r.metadata.get("title", "") if r.metadata else ""
            src = r.metadata.get("source", r.id) if r.metadata else r.id
            header = f"[文档{i}] {title or src}"
            entry = f"{header}\n{r.content}\n"
            if total_len + len(entry) > self.context_budget:
                break
            parts.append(entry)
            total_len += len(entry)
        return "\n".join(parts)
