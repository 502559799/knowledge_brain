"""主题聚类路由"""
import logging
from fastapi import APIRouter, BackgroundTasks
from kb.web.dependencies import get_sqlite, get_config
from kb.query.topic_query import TopicQuery

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/topics")
def list_topics():
    tq = TopicQuery(get_sqlite())
    return tq.get_topics()


@router.get("/topics/{cluster_id}/documents")
def topic_docs(cluster_id: int, limit: int = 20):
    tq = TopicQuery(get_sqlite())
    return tq.get_topic_documents(cluster_id, limit)


def _run_rebuild(config):
    """Background task: rebuild topics and generate wiki articles"""
    try:
        from kb.processors.topic_clusterer import TopicClusterer
        tc = TopicClusterer(config=config)
        result = tc.cluster_all()
        logger.info(f"Topic rebuild complete: {result}")
        try:
            from kb.processors.wiki_generator import WikiGenerator
            wg = WikiGenerator(config=config)
            wg.generate_for_all_topics()
            logger.info("Wiki generation complete")
        except Exception as we:
            logger.warning(f"Wiki generation skipped: {we}")
        return result
    except Exception as e:
        logger.error(f"Topic rebuild failed: {e}")
        return {"error": str(e)}


@router.post("/topics/rebuild")
def rebuild_topics(background_tasks: BackgroundTasks):
    """Trigger topic rebuild in background"""
    config = get_config()
    background_tasks.add_task(_run_rebuild, config)
    return {"success": True, "message": "主题重建已在后台启动，请稍后刷新页面查看结果"}
