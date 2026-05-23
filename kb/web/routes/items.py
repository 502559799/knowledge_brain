"""知识项CRUD路由"""
from typing import Optional
from fastapi import APIRouter, Query
from kb.web.dependencies import get_sqlite
router = APIRouter()

@router.get("/items")
def list_items(content_type: Optional[str] = None, limit: int = 50, offset: int = 0):
    return get_sqlite().list_knowledge(content_type, limit, offset)

@router.get("/items/{item_id}")
def get_item(item_id: str):
    item = get_sqlite().get_knowledge(item_id)
    if not item: return {"error": "not found"}
    return item

@router.delete("/items/{item_id}")
def delete_item(item_id: str):
    return {"success": get_sqlite().delete_knowledge(item_id)}

@router.get("/items/{item_id}/chunks")
def get_chunks(item_id: str):
    return get_sqlite().get_chunks(item_id)

@router.get("/items/{item_id}/related")
def get_related(item_id: str, limit: int = 10):
    from kb.query.graph_query import GraphQuery
    gq = GraphQuery(get_sqlite())
    return gq.get_related_documents(item_id, limit)
