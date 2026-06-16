"""知识挖掘路由"""
import logging
from fastapi import APIRouter, BackgroundTasks
from kb.web.dependencies import get_config

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_full_mining(config):
    """Background: run full mining pipeline"""
    db_path = str(config.data_dir / "db" / "metadata.db")
    results = {}
    try:
        from kb.processors.topic_clusterer import TopicClusterer
        tc = TopicClusterer(config=config)
        results["topics"] = tc.cluster_all(db_path)
        logger.info(f"Topic clustering: {results['topics']}")
    except Exception as e:
        results["topics_error"] = str(e)
        logger.error(f"Topic clustering failed: {e}")
    try:
        from kb.processors.doc_relation_builder import DocRelationBuilder
        dr = DocRelationBuilder(config=config)
        results["relations"] = dr.build_all(db_path)
        logger.info(f"Relation building: {results['relations']}")
    except Exception as e:
        results["relations_error"] = str(e)
        logger.error(f"Relation building failed: {e}")
    try:
        from kb.processors.wiki_generator import WikiGenerator
        wg = WikiGenerator(config=config)
        results["wiki"] = wg.generate_for_all_topics(db_path)
        logger.info(f"Wiki generation: {results['wiki']} articles")
    except Exception as e:
        results["wiki_error"] = str(e)
        logger.warning(f"Wiki generation failed: {e}")
    return results


@router.post("/mine/run")
def run_mining(background_tasks: BackgroundTasks):
    config = get_config()
    background_tasks.add_task(_run_full_mining, config)
    return {"success": True, "message": "知识挖掘已在后台启动（主题聚类 + 关系构建 + 百科生成）"}
