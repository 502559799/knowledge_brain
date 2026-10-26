"""Topic organization with prerequisites and observable completion."""
import threading
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from kb.web.dependencies import get_sqlite, get_config
from kb.query.topic_query import TopicQuery

router=APIRouter()
_lock=threading.Lock()
_job={'state':'idle','stage':'','processed':0,'total':0,'error':'','result':None}


@router.get('/topics')
def list_topics():
    return TopicQuery(get_sqlite()).get_topics()


@router.get('/topics/status')
def organization_status():
    storage=get_sqlite()
    with storage._lock:
        counts={table:storage.conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ['knowledge','document_embeddings','topic_clusters','wiki_articles']}
    with _lock:
        return {**_job,'counts':counts,'services':get_config().validate_services()}


@router.get('/topics/{cluster_id}/documents')
def topic_docs(cluster_id:int,limit:int=20):
    return TopicQuery(get_sqlite()).get_topic_documents(cluster_id,limit)


class RebuildRequest(BaseModel):
    strategy:Literal['tags','semantic']='tags'
    enhance:bool=False


def _run_rebuild(config,strategy='tags',enhance=False):
    from kb.services.organization import organize
    def report(**values):
        with _lock:
            _job.update(values)
    try:
        result=organize(config,strategy,enhance,report)
        report(state='completed',stage='整理完成',result=result)
    except Exception as exc:
        report(state='failed',error=str(exc),stage='整理未完成')


@router.post('/topics/rebuild')
def rebuild_topics(background_tasks:BackgroundTasks,req:RebuildRequest=RebuildRequest()):
    config=get_config()
    if req.strategy=='semantic' and not config.validate_services()['embedding_available']:
        raise HTTPException(400,'请先配置嵌入服务，或选择“按标签整理”')
    if req.enhance and not config.validate_services()['llm_available']:
        raise HTTPException(400,'生成 AI 摘要需要先配置 LLM')
    with _lock:
        if _job['state']=='running':
            return {'state':'running'}
        _job.update(state='running',stage='准备整理',processed=0,total=0,error='',result=None)
    background_tasks.add_task(_run_rebuild,config,req.strategy,req.enhance)
    return {'success':True,'state':'running'}
