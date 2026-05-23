"""仪表盘路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_sqlite
router = APIRouter()

@router.get("/stats")
def stats():
    return get_sqlite().get_stats()

@router.get("/recent")
def recent(limit: int = 10):
    return get_sqlite().get_recent(limit)

@router.get("/timeline")
def timeline(days: int = 30):
    return get_sqlite().get_timeline(days)
