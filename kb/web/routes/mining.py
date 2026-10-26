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

# Explicit entity backfill: unlike clustering, this creates the graph's source data.
import threading
_entity_lock = threading.Lock()
_entity_status = {'state':'idle', 'processed':0, 'total':0, 'errors':[], 'entities':0}


def _extract_existing(config):
    from kb.web.dependencies import get_sqlite
    from kb.services.reading import read_item
    from kb.processors.entity_extractor import EntityExtractor
    storage = get_sqlite()
    try:
        docs = storage.list_knowledge(limit=100000)
        with _entity_lock:
            _entity_status['total']=len(docs)
        extractor=EntityExtractor(config)
        for doc in docs:
            content=read_item(storage,config,doc)['content']
            result=extractor.process(content,title=doc['title'] or '')
            with _entity_lock:
                _entity_status['processed']+=1
            if result.success and result.data:
                saved=extractor.save_to_db(result.data,doc['id'],str(storage.db_path))
                with _entity_lock:
                    _entity_status['entities']+=saved['entities_saved']
            else:
                with _entity_lock:
                    _entity_status['errors'].append({'id':doc['id'],'error':result.error or '未提取到实体'})
        with _entity_lock:
            _entity_status['state']='completed' if not _entity_status['errors'] else 'completed_with_errors'
    except Exception as exc:
        with _entity_lock:
            _entity_status['state']='failed'
            _entity_status['errors'].append({'error':str(exc)})


@router.get('/mine/entities/status')
def entity_status():
    with _entity_lock:
        return {**_entity_status, 'errors':list(_entity_status['errors'])}


@router.post('/mine/entities')
def extract_entities(background_tasks: BackgroundTasks):
    from fastapi import HTTPException
    config=get_config()
    if not config.validate_services()['llm_available']:
        raise HTTPException(400,'请先配置 LLM，实体提取需要调用配置的模型服务')
    with _entity_lock:
        if _entity_status['state']=='running':
            return {'state':'running'}
        _entity_status.update(state='running',processed=0,total=0,errors=[],entities=0)
    background_tasks.add_task(_extract_existing,config)
    return {'state':'running'}
