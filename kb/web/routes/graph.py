"""知识图谱路由"""
from typing import Optional
from fastapi import APIRouter, Query
from kb.web.dependencies import get_sqlite
from kb.query.graph_query import GraphQuery
router = APIRouter()

@router.get("/graph")
def get_graph(entity_type: Optional[str] = None, depth: int = 2, limit: int = 100, entity_id: Optional[int] = None):
    gq = GraphQuery(get_sqlite())
    return gq.get_graph(entity_type, depth, limit, entity_id)

@router.get("/graph/entity/{entity_id}")
def get_entity(entity_id: int):
    gq = GraphQuery(get_sqlite())
    return gq.get_entity(entity_id)
