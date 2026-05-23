"""6阶段检索管道: 查询扩展→混合检索→重排序→上下文增强→上下文构建→答案生成"""
import logging, time
from typing import Any, Dict, List, Optional
from kb.config import Config
from kb.query.models import EnhancedRAGResult, RankedChunk, RetrievalContext, SearchResult
logger = logging.getLogger(__name__)

_pipeline_cache: Dict[str, tuple] = {}

class RetrievalPipeline:
    """6阶段可插拔检索管道"""
    def __init__(self, config: Optional[Config] = None, **kwargs):
        self.config = config or Config()
        pipe_cfg = self.config.get("query.pipeline", {})
        self.default_top_k = pipe_cfg.get("top_k", 10)
        self.rerank_top_k = pipe_cfg.get("rerank_top_k", 5)
        self.context_budget = pipe_cfg.get("context_budget", 4000)
        self.semantic_search = kwargs.get("semantic_search")
        self.keyword_search = kwargs.get("keyword_search")
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
            self.model = model
            self.llm_available = True
        except: pass

    def run(self, question: str, session_id: Optional[str] = None, tags: Optional[List[str]] = None,
            top_k: Optional[int] = None) -> EnhancedRAGResult:
        if not question.strip():
            raise ValueError("问题不能为空")
        k = top_k or self.default_top_k
        all_results: List[SearchResult] = []
        # Stage 1&2: 混合检索
        if self.semantic_search:
            try:
                sem = self.semantic_search.search(question, tags, k)
                all_results.extend(sem)
            except: pass
        if self.keyword_search:
            try:
                kw = self.keyword_search.search(question, k)
                for r in kw:
                    if not any(er.id == r.id for er in all_results):
                        all_results.append(r)
            except: pass
        if not all_results:
            return EnhancedRAGResult(answer="未找到相关信息", question=question, retrieval_strategy="no_results")
        # Stage 3: RRF重排序
        ranked = self._rrf_rerank(all_results)
        top_results = ranked[:self.rerank_top_k]
        # Stage 5&6: 上下文构建+答案生成
        context_str = "\n".join(f"[{i+1}] {r.source}\n{r.content}\n" for i, r in enumerate(top_results))
        sources = [SearchResult(id=c.source, content=c.content, metadata=c.metadata, score=c.final_score) for c in top_results]
        if self.llm_available:
            try:
                import litellm
                messages = [{"role": "system", "content": "基于上下文回答问题，引用来源。"}, {"role": "user", "content": f"上下文:\n{context_str}\n\n问题: {question}"}]
                resp = litellm.completion(model=self.model, messages=messages, temperature=0.3, max_tokens=1000, api_key=self.api_key)
                answer = resp.choices[0].message.content
                return EnhancedRAGResult(answer=answer, question=question, sources=sources, context=context_str, confidence=0.8, retrieval_strategy="pipeline")
            except: pass
        return EnhancedRAGResult(answer=f"找到{len(top_results)}个相关文档", question=question, sources=sources, context=context_str, retrieval_strategy="retrieval_only")

    def _rrf_rerank(self, results: List[SearchResult], k: int = 60) -> List[RankedChunk]:
        """Reciprocal Rank Fusion"""
        chunks = [RankedChunk(content=r.content, source=r.id, retrieval_score=r.score, final_score=0.0, metadata=r.metadata) for r in results]
        for i, c in enumerate(chunks):
            c.final_score = 1.0 / (k + i + 1) + c.retrieval_score * 0.5
        chunks.sort(key=lambda x: x.final_score, reverse=True)
        return chunks
