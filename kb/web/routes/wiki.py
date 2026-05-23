"""Wiki路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_sqlite
router = APIRouter()

@router.get("/wiki/categories")
def wiki_categories(topic_id: int = None):
    c = get_sqlite().conn.cursor()
    if topic_id:
        c.execute("SELECT * FROM wiki_categories WHERE topic_id = ? ORDER BY created_at DESC", (topic_id,))
    else:
        c.execute("SELECT * FROM wiki_categories ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    c.close()
    return rows

@router.get("/wiki/articles/{topic_id}")
def wiki_articles(topic_id: int):
    c = get_sqlite().conn.cursor()
    c.execute("SELECT * FROM wiki_articles WHERE topic_id = ?", (topic_id,))
    rows = [dict(r) for r in c.fetchall()]
    c.close()
    return rows
