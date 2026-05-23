"""推荐路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_sqlite
from kb.query.recommendation import RecommendationEngine
router = APIRouter()

@router.get("/recommendations/{knowledge_id}")
def recommend(knowledge_id: str, limit: int = 10):
    re = RecommendationEngine(get_sqlite())
    return re.get_recommendations(knowledge_id, limit)

@router.get("/recommendations/explore")
def explore(limit: int = 10):
    re = RecommendationEngine(get_sqlite())
    return re.get_recent_unexplored(limit)
