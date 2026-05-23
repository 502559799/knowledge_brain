"""主题聚类路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_sqlite
from kb.query.topic_query import TopicQuery
router = APIRouter()

@router.get("/topics")
def list_topics():
    tq = TopicQuery(get_sqlite())
    return tq.get_topics()

@router.get("/topics/{cluster_id}/documents")
def topic_docs(cluster_id: int, limit: int = 20):
    tq = TopicQuery(get_sqlite())
    return tq.get_topic_documents(cluster_id, limit)

@router.post("/topics/rebuild")
def rebuild_topics():
    from kb.processors.topic_clusterer import TopicClusterer
    tc = TopicClusterer()
    result = tc.cluster_all()
    return result
