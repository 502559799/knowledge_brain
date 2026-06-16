"""知识项CRUD路由"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from kb.web.dependencies import get_sqlite

router = APIRouter()


class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    user_notes: Optional[str] = None


@router.get("/items")
def list_items(content_type: Optional[str] = None, limit: int = 50, offset: int = 0):
    return get_sqlite().list_knowledge(content_type, limit, offset)


@router.get("/items/{item_id}")
def get_item(item_id: str):
    item = get_sqlite().get_knowledge(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item["tags"] = get_sqlite().get_knowledge_tags(item_id)
    return item


@router.patch("/items/{item_id}")
def update_item(item_id: str, req: UpdateItemRequest):
    storage = get_sqlite()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if not storage.update_knowledge(item_id, **updates):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True}


@router.delete("/items/{item_id}")
def delete_item(item_id: str):
    storage = get_sqlite()
    if not storage.delete_knowledge(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True}


@router.get("/items/{item_id}/chunks")
def get_chunks(item_id: str):
    return get_sqlite().get_chunks(item_id)


@router.get("/items/{item_id}/related")
def get_related(item_id: str, limit: int = 10):
    from kb.query.graph_query import GraphQuery
    gq = GraphQuery(get_sqlite())
    return gq.get_related_documents(item_id, limit)
