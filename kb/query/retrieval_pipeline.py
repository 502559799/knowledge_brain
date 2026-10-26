"""Hybrid retrieval pipeline sharing evidence and generation with RAGQuery."""
from kb.config import Config
from kb.query.rag import RAGQuery
from kb.query.models import EnhancedRAGResult, RankedChunk
from kb.query.hybrid import reciprocal_rank_fusion


class RetrievalPipeline:
    def __init__(self, config=None, **kwargs):
        self.config = config or Config()
        cfg = self.config.get("query.pipeline", {})
        self.default_top_k = cfg.get("top_k", 10)
        self.rerank_top_k = cfg.get("rerank_top_k", 5)
        self.context_budget = cfg.get("context_budget", 4000)
        self.rag = RAGQuery(self.config, kwargs.get("semantic_search"), kwargs.get("keyword_search"),
                            kwargs.get("conversation_manager"))
        self.rag.context_budget = self.context_budget
        self.rag.source_limit = self.rerank_top_k

    def run(self, question, session_id=None, tags=None, top_k=None):
        k = self.default_top_k if top_k is None else top_k
        result = self.rag.query(question, tags=tags, top_k=k, session_id=session_id)
        strategy = "no_results" if not result.sources else ("pipeline" if result.confidence else "retrieval_only")
        return EnhancedRAGResult(answer=result.answer, question=question, sources=result.sources,
                                 context=result.context, confidence=result.confidence,
                                 retrieval_strategy=strategy, session_id=session_id)

    def _rrf_rerank(self, results, k=60):
        rankings = results if results and isinstance(results[0], list) else [results]
        return [RankedChunk(content=r.content, source=r.id, metadata=r.metadata, final_score=r.score)
                for r in reciprocal_rank_fusion(rankings, k)]
