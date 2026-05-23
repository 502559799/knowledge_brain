"""知识挖掘路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_sqlite, get_config
router = APIRouter()

@router.post("/mine/run")
def run_mining():
    config = get_config()
    storage = get_sqlite()
    results = {}
    try:
        from kb.processors.topic_clusterer import TopicClusterer
        tc = TopicClusterer(config=config)
        results["topics"] = tc.cluster_all()
    except Exception as e:
        results["topics_error"] = str(e)
    try:
        from kb.processors.doc_relation_builder import DocRelationBuilder
        dr = DocRelationBuilder(config=config)
        results["relations"] = dr.build_all()
    except Exception as e:
        results["relations_error"] = str(e)
    return results
