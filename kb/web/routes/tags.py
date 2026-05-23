"""标签路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_sqlite
router = APIRouter()

@router.get("/tags")
def list_tags():
    return get_sqlite().get_tags()

@router.get("/tags/{tag_name}/items")
def tag_items(tag_name: str):
    return get_sqlite().get_items_by_tag(tag_name)
