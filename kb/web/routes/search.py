"""搜索路由"""
from typing import Optional, List
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from kb.web.dependencies import (get_pipeline, get_config, get_semantic_search,
                                  get_keyword_search, get_conversation)

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    tags: Optional[List[str]] = None
    top_k: int = Field(default=5, ge=1, le=100)
    session_id: Optional[str] = None

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("查询不能为空")
        return value


@router.get("/search/keyword")
def keyword_search(q: str = Query(min_length=1), limit: int = Query(default=20, ge=1, le=100)):
    ks = get_keyword_search()
    results = ks.search(q, limit)
    return [{"id": r.id, "content": r.content, "score": r.score, "metadata": r.metadata} for r in results]


@router.post("/search/semantic")
def semantic_search(req: SearchRequest):
    ss = get_semantic_search()
    results = ss.search(req.query, req.tags, req.top_k)
    return [{"id": r.id, "content": r.content, "score": r.score, "metadata": r.metadata} for r in results]


@router.post("/search/rag")
def rag_search(req: SearchRequest):
    from kb.query.rag import RAGQuery
    config = get_config()
    conv = get_conversation()
    session_id = conv.get_or_create_session(req.session_id)
    rag = RAGQuery(config=config, semantic_search=get_semantic_search(), keyword_search=get_keyword_search(), conversation_manager=conv)
    result = rag.query(req.query, req.tags, req.top_k, session_id=session_id)
    return {
        "answer": result.answer,
        "sources": [{"id": s.id, "content": s.content, "score": s.score, "metadata": s.metadata} for s in result.sources],
        "confidence": result.confidence,
        "session_id": result.session_id or session_id,
    }


@router.post("/search/pipeline")
def pipeline_search(req: SearchRequest):
    pipeline = get_pipeline()
    conv = get_conversation()
    session_id = conv.get_or_create_session(req.session_id)
    result = pipeline.run(req.query, session_id=session_id, tags=req.tags, top_k=req.top_k)
    return {
        "answer": result.answer,
        "sources": [{"id": s.id, "content": s.content, "score": s.score, "metadata": s.metadata} for s in result.sources],
        "confidence": result.confidence,
        "strategy": result.retrieval_strategy,
        "session_id": session_id,
    }
