"""搜索路由"""
from typing import Optional, List
from fastapi import APIRouter, Query
from pydantic import BaseModel
from kb.web.dependencies import get_pipeline, get_config
router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    tags: Optional[List[str]] = None
    top_k: int = 5
    session_id: Optional[str] = None

@router.get("/search/keyword")
def keyword_search(q: str, limit: int = 20):
    from kb.query.keyword_search import KeywordSearch
    ks = KeywordSearch(data_dir=str(get_config().data_dir))
    results = ks.search(q, limit)
    return [{"id": r.id, "content": r.content, "score": r.score} for r in results]

@router.post("/search/semantic")
def semantic_search(req: SearchRequest):
    from kb.query.semantic_search import SemanticSearch
    ss = SemanticSearch(get_config())
    results = ss.search(req.query, req.tags, req.top_k)
    return [{"id": r.id, "content": r.content, "score": r.score, "metadata": r.metadata} for r in results]

@router.post("/search/rag")
def rag_search(req: SearchRequest):
    from kb.query.rag import RAGQuery
    rag = RAGQuery(get_config())
    result = rag.query(req.query, req.tags, req.top_k)
    return {"answer": result.answer, "sources": [{"id": s.id, "content": s.content, "score": s.score} for s in result.sources], "confidence": result.confidence}

@router.post("/search/pipeline")
def pipeline_search(req: SearchRequest):
    pipeline = get_pipeline()
    result = pipeline.run(req.query, session_id=req.session_id, tags=req.tags, top_k=req.top_k)
    return {"answer": result.answer, "sources": [{"id": s.id, "content": s.content, "score": s.score} for s in result.sources], "confidence": result.confidence, "strategy": result.retrieval_strategy}
