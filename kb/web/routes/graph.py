"""知识图谱路由"""
from typing import Optional
from fastapi import APIRouter, Query
from kb.web.dependencies import get_sqlite
from kb.query.graph_query import GraphQuery
router = APIRouter()

@router.get("/graph")
def get_graph(entity_type: Optional[str] = None, depth: int = Query(default=2, ge=0, le=5), limit: int = Query(default=100, ge=1, le=500), entity_id: Optional[int] = None):
    gq = GraphQuery(get_sqlite())
    return gq.get_graph(entity_type, depth, limit, entity_id)

@router.get("/graph/entity/{entity_id}")
def get_entity(entity_id: int):
    gq = GraphQuery(get_sqlite())
    return gq.get_entity(entity_id)


@router.get('/graph/documents')
def document_graph(limit: int = Query(100, ge=1, le=300)):
    """Show real document/tag membership without requiring model extraction."""
    from pathlib import Path
    storage = get_sqlite()
    docs = storage.list_knowledge(limit=limit)
    nodes, edges, tags = [], [], set()
    with storage._lock:
        for doc in docs:
            nodes.append({'id': 'doc:'+doc['id'], 'knowledge_id': doc['id'], 'type':'document',
                          'display_name':doc['title'] or Path(doc['source'] or '').stem or '未命名知识'})
            rows = storage.conn.execute('SELECT t.name FROM tags t JOIN knowledge_tags kt ON kt.tag_id=t.id WHERE kt.knowledge_id=?',(doc['id'],)).fetchall()
            for row in rows:
                tag=row[0]; tags.add(tag)
                edges.append({'source_entity_id':'doc:'+doc['id'], 'target_entity_id':'tag:'+tag, 'relation_type':'标签'})
        nodes.extend({'id':'tag:'+tag,'type':'tag','display_name':tag} for tag in sorted(tags))
    return {'nodes':nodes, 'edges':edges, 'mode':'documents', 'stats':{'total_entities':len(nodes),'total_relations':len(edges)}}
