import sqlite3
from unittest.mock import Mock

import pytest
import yaml
from fastapi.testclient import TestClient
from kb.config import Config
from kb.collectors.note_collector import NoteCollector
from kb.processors.chunker import Chunker
from kb.query.hybrid import reciprocal_rank_fusion, pack_context
from kb.query.models import SearchResult
from kb.query.rag import RAGQuery
from kb.query.semantic_search import SemanticSearch
from kb.services.ingestion import ingest, read_content
from kb.storage.sqlite_storage import SQLiteStorage
from kb.web.app import app


@pytest.fixture
def db(tmp_path):
    with SQLiteStorage(str(tmp_path / 'data.db')) as storage:
        yield storage


def add(db, id, text='body'):
    db.add_knowledge(id, id, 'note', 'note')
    db.add_chunk(id + '-chunk', id, 0, text)


def test_two_distinct_notes_and_duplicate(db):
    collector = NoteCollector()
    first = collector.collect('第一篇正文', title='中文标题')
    second = collector.collect('第二篇正文', title='中文标题')
    assert first.file_path != second.file_path
    one, dup = ingest(db, Config(), first, read_content(first))
    two, dup2 = ingest(db, Config(), second, read_content(second))
    assert one != two and not dup and not dup2
    assert ingest(db, Config(), first, read_content(first)) == (one, True)
    assert len(db.get_chunks(one)) == 1


def test_frontmatter_is_valid():
    result = NoteCollector().collect('正文', title='标题: [复杂]\n多行', tags=['a:b', '中文'])
    data = yaml.safe_load(result.file_path.read_text().split('---')[1])
    assert data['title'] == '标题: [复杂]\n多行'
    assert read_content(result) == '正文'


def test_fulltext_and_tag_filters(db):
    add(db, 'one', 'unique_body_keyword 数据检索架构优化')
    add(db, 'two', 'unique_body_keyword')
    db.link_tag('two', 'chosen')
    assert len(db.fts_search('unique_body_keyword')) == 2
    assert [r['id'] for r in db.fts_search('unique_body_keyword', tags=['chosen'])] == ['two']
    assert db.fts_search('检索架构')[0]['id'] == 'one'
    assert db.fts_search('"') == []
    assert db.fts_search('unique_body_keyword', limit=0) == []


def test_chunk_fts_update_delete_and_reopen(db):
    add(db, 'one', 'originaltoken')
    with db._transaction() as c:
        c.execute("UPDATE chunks SET content='replacementtoken' WHERE knowledge_id='one'")
    assert not db.fts_search('originaltoken')
    assert db.fts_search('replacementtoken')
    path = str(db.db_path)
    db.close()
    with SQLiteStorage(path) as reopened:
        assert reopened.fts_search('replacementtoken')
        reopened.delete_knowledge('one')
        assert not reopened.fts_search('replacementtoken')


def test_delete_related_data_and_tag_counts(db):
    add(db, 'one'); add(db, 'two')
    db.link_tag('one', 'tag'); db.link_tag('two', 'tag')
    db.unlink_tag('one', 'tag')
    assert db.get_tags()[0]['count'] == 1
    db.link_tag('one', 'tag')
    entity = db.upsert_entity('e', 'e', 'concept')
    db.add_entity_mention(entity, 'one')
    db.add_document_relation('one', 'two', 'related', 1)
    db.add_topic_cluster('topic', '', ['one', 'two'])
    assert db.delete_knowledge('one')
    assert db.get_tags()[0]['count'] == 1
    for table in ['entity_mentions', 'document_relations']:
        assert db.conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert db.conn.execute('SELECT document_count FROM topic_clusters').fetchone()[0] == 1


def test_rrf_uses_independent_ranks_not_score_scales():
    a, b, c = [SearchResult(x, x, score=s) for x, s in [('a', 999), ('b', -900), ('c', 20)]]
    fused = reciprocal_rank_fusion([[a, b, b], [b, c]])
    assert fused[0].id == 'b'
    assert fused[0].score == pytest.approx(1/62 + 1/61)
    assert len(fused) == 3 and b.score == -900


def test_context_long_first_document_is_truncated():
    context, sources = pack_context([SearchResult('doc', 'x'*10000)], 100)
    assert len(context) == 100
    assert sources and sources[0].content in context


def test_rag_hybrid_fallback_and_no_empty_context():
    sem = Mock(); sem.search.side_effect = RuntimeError('offline')
    kw = Mock(); kw.search.return_value = [SearchResult('d', 'x'*10000)]
    rag = RAGQuery(Config(), sem, kw)
    result = rag.query('question')
    assert result.sources and len(result.context) <= 4000
    assert result.confidence == 0


def test_semantic_filters_stale_vectors_and_tags(db):
    add(db, 'live'); add(db, 'other')
    db.link_tag('live', 'wanted')
    chroma = Mock()
    chroma.query_chunks.return_value = {'ids': ['c0', 'c1', 'c2'], 'documents': ['stale', 'good', 'other'],
        'metadatas': [{'knowledge_id': 'deleted'}, {'knowledge_id': 'live'}, {'knowledge_id': 'other'}], 'distances': [0, .1, .2]}
    chroma.query.return_value = {'ids': []}
    embedder = Mock(); embedder.embed_single.return_value = [1, 0]
    search = SemanticSearch(Config(), chroma, embedder, storage=db)
    assert [r.id for r in search.search('q', ['wanted'])] == ['live']


def test_chunker_no_tail_explosion():
    chunks = Chunker(100, 20).chunk('x'*200)
    assert len(chunks) == 3
    with pytest.raises(ValueError):
        Chunker(100, 100)


def test_api_collect_and_search_immediately(monkeypatch):
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async', lambda *a, **kw: None)
    with TestClient(app) as client:
        one = client.post('/api/collect/note', json={'text': 'first uniqueterm', 'tags': ['test']}).json()
        two = client.post('/api/collect/note', json={'text': 'second note'}).json()
        duplicate = client.post('/api/collect/note', json={'text': 'first uniqueterm'}).json()
        assert not one['duplicate'] and not two['duplicate'] and duplicate['duplicate']
        results = client.get('/api/search/keyword', params={'q': 'uniqueterm'}).json()
        assert results[0]['id'] == one['id']
        assert 'uniqueterm' in results[0]['content']
        assert client.get('/api/items/' + one['id']).json()['file_path']


@pytest.mark.parametrize('query,k', [('', 5), ('  ', 5), ('q', 0), ('q', -1), ('q', 101)])
def test_invalid_search_request(query, k):
    with TestClient(app) as client:
        assert client.post('/api/search/rag', json={'query': query, 'top_k': k}).status_code == 422


def test_backup_captures_committed_wal(tmp_path):
    from kb.web.dependencies import get_sqlite, get_config
    from kb.web.routes.backup import create_backup, _get_backup_dir
    import tarfile
    storage = get_sqlite()
    add(storage, 'wal-doc', 'persisted')
    created = create_backup()
    with tarfile.open(_get_backup_dir() / created['filename']) as archive:
        archive.extract('db/metadata.db', tmp_path / 'restored', filter='data')
    with sqlite3.connect(tmp_path / 'restored/db/metadata.db') as conn:
        assert conn.execute("SELECT id FROM knowledge").fetchone()[0] == 'wal-doc'


def test_backup_rejects_traversal_and_links(tmp_path):
    import io
    import tarfile
    from fastapi import HTTPException
    from kb.web.routes.backup import _resolve_backup, _get_backup_dir, restore_backup
    with pytest.raises(HTTPException):
        _resolve_backup(tmp_path, '../evil.tar.gz')
    path = _get_backup_dir() / 'unsafe.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        info = tarfile.TarInfo('../escape')
        info.size = 4
        archive.addfile(info, io.BytesIO(b'evil'))
    with pytest.raises(HTTPException):
        restore_backup(path.name)


def test_legacy_chunk_index_backfill(tmp_path):
    path = str(tmp_path / 'legacy.db')
    with SQLiteStorage(path) as storage:
        add(storage, 'legacy', 'legacytoken')
        storage.conn.executescript('DROP TRIGGER chunks_ai; DROP TRIGGER chunks_ad; DROP TRIGGER chunks_au; DROP TABLE chunks_fts;')
    with SQLiteStorage(path) as storage:
        assert storage.fts_search('legacytoken')[0]['id'] == 'legacy'


def test_ingest_rolls_back_all_writes_on_failure(db):
    result = NoteCollector().collect('rollback content')
    with pytest.raises(sqlite3.ProgrammingError):
        ingest(db, Config(), result, 'rollback content', tags=[object()])
    assert db.get_stats()['total_items'] == 0
    assert db.get_stats()['chunk_count'] == 0


def test_chroma_delete_uses_parent_id():
    from kb.storage.chroma_storage import ChromaStorage
    storage = ChromaStorage.__new__(ChromaStorage)
    storage.collection = Mock()
    chunks = Mock()
    storage._get_chunks_collection = Mock(return_value=chunks)
    storage.delete(['doc'])
    chunks.delete.assert_called_once_with(where={'knowledge_id': {'$in': ['doc']}})


def test_vector_deletion_outbox_survives_failure(db):
    from kb.services.deletion import flush_vector_deletions
    add(db, 'doc')
    db.delete_knowledge('doc')
    chroma = Mock(); chroma.delete.side_effect = RuntimeError('offline')
    flush_vector_deletions(db, chroma)
    assert db.conn.execute('SELECT COUNT(*) FROM vector_deletions').fetchone()[0] == 1
    chroma.delete.side_effect = None
    flush_vector_deletions(db, chroma)
    assert db.conn.execute('SELECT COUNT(*) FROM vector_deletions').fetchone()[0] == 0


def test_actual_chroma_roundtrip_and_document_delete(tmp_path):
    from kb.storage.chroma_storage import ChromaStorage
    storage = ChromaStorage(str(tmp_path / 'vectors'))
    storage.add_documents(['d'], [[1., 0.]], [{'title': 'doc'}], ['document'])
    storage.add_chunks(['c'], [[1., 0.]], [{'knowledge_id': 'd'}], ['passage'])
    assert storage.query_chunks([1., 0.], 1)['ids'] == ['c']
    storage.delete(['d'])
    assert storage.count() == 0
    assert storage.count_chunks() == 0
    storage.close()


def test_wiki_rebuild_does_not_duplicate_articles(db):
    from kb.processors.wiki_generator import WikiGenerator
    add(db, 'one')
    db.add_topic_cluster('topic', '', ['one'])
    generator = WikiGenerator(Config())
    generator.generate_for_all_topics(str(db.db_path))
    generator.generate_for_all_topics(str(db.db_path))
    assert db.conn.execute('SELECT COUNT(*) FROM wiki_articles').fetchone()[0] == 1


def test_cli_note_without_title(monkeypatch):
    from click.testing import CliRunner
    from kb.cli import cli
    monkeypatch.setattr('kb.commands.collect.mine_document_async', lambda *a, **kw: None)
    runner = CliRunner()
    assert runner.invoke(cli, ['collect', 'note', 'cli uniquenote']).exit_code == 0
    result = runner.invoke(cli, ['search', 'keyword', 'uniquenote'])
    assert result.exit_code == 0
    assert 'cli uniquenote' in result.output


def test_graph_shared_entities_without_embeddings(db):
    from kb.processors.doc_relation_builder import DocRelationBuilder
    add(db, 'one'); add(db, 'two')
    entity = db.upsert_entity('shared', 'shared', 'concept')
    db.add_entity_mention(entity, 'one'); db.add_entity_mention(entity, 'two')
    builder = DocRelationBuilder(Config())
    assert builder.build_all(str(db.db_path))['shared_entity'] == 1
    db.clear_document_relations()
    assert builder.build_incremental('one', str(db.db_path))['shared_entity'] == 1


def test_entity_extraction_save_is_idempotent(db):
    from kb.processors.entity_extractor import EntityExtractor
    add(db, 'one')
    data = {'entities': [{'name': 'a', 'type': 'concept'}, {'name': 'b', 'type': 'concept'}],
            'relations': [{'source': 'a', 'target': 'b', 'type': 'related_to'}]}
    extractor = EntityExtractor(Config())
    extractor.save_to_db(data, 'one', str(db.db_path))
    extractor.save_to_db(data, 'one', str(db.db_path))
    assert db.conn.execute('SELECT MAX(mention_count) FROM entities').fetchone()[0] == 1
    assert db.conn.execute('SELECT weight FROM entity_relations').fetchone()[0] == 1


def test_rag_history_not_duplicated(monkeypatch):
    import sys
    from types import SimpleNamespace
    from kb.query.conversation import ConversationManager
    completion = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='answer [文档1]'))]))
    monkeypatch.setitem(sys.modules, 'litellm', SimpleNamespace(completion=completion))
    config = Config(); config.set('llm.api_key', 'test-key')
    sem = Mock(); sem.search.return_value = [SearchResult('one', 'evidence')]
    kw = Mock(); kw.search.return_value = []
    conversation = ConversationManager()
    sid = conversation.create_session()
    conversation.add_turn(sid, 'user', 'previous')
    rag = RAGQuery(config, sem, kw, conversation)
    assert rag.query('current', session_id=sid).answer == 'answer [文档1]'
    messages = completion.call_args.kwargs['messages']
    assert [m['content'] for m in messages].count('current') == 0
    assert sum('current' in m['content'] for m in messages) == 1
    assert len(conversation.get_history(sid)) == 3


def test_reader_saved_source_and_download(monkeypatch):
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async', lambda *a, **kw: None)
    with TestClient(app) as client:
        text = '完整正文\n' + '长文内容' * 1000
        doc = client.post('/api/collect/note', json={'text': text, 'title': '阅读测试'}).json()['id']
        result = client.get(f'/api/items/{doc}/content').json()
        assert result['content'] == text and result['complete']
        assert client.get(f'/api/items/{doc}/download').text == text
        assert client.get('/api/items', params={'q': '长文内容'}).json()[0]['id'] == doc
        assert client.get('/api/items/missing/content').status_code == 404


def test_reader_does_not_expose_arbitrary_files(db, tmp_path):
    from kb.services.reading import read_item
    secret = tmp_path / 'private.txt'; secret.write_text('private')
    add(db, 'one', 'recoverable passage')
    result = read_item(db, Config(), {'id': 'one', 'file_path': str(secret), 'summary': 'fallback'})
    assert result['content'] == 'recoverable passage'
    assert not result['complete']


def test_reader_summary_only(db):
    from kb.services.reading import read_item
    result = read_item(db, Config(), {'id': 'legacy', 'summary': 'only summary'})
    assert result['content_origin'] == 'summary' and not result['complete']


def test_edit_content_revision_and_search(monkeypatch):
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async',lambda *a,**kw:None)
    with TestClient(app) as client:
        id=client.post('/api/collect/note',json={'text':'oldtoken','title':'before'}).json()['id']
        result=client.patch('/api/items/'+id,json={'title':'after','content':'newtoken','user_notes':'my note','revision':0})
        assert result.status_code==200
        content=client.get('/api/items/'+id+'/content').json()
        assert content['content']=='newtoken' and content['revision']==1
        assert content['user_notes']=='my note'
        assert client.get('/api/search/keyword',params={'q':'newtoken'}).json()
        assert not client.get('/api/search/keyword',params={'q':'oldtoken'}).json()
        assert client.patch('/api/items/'+id,json={'content':'stale','revision':0}).status_code==409


def test_pdf_original_endpoint(tmp_path):
    from kb.web.dependencies import get_sqlite
    pdf=tmp_path/'source.pdf';pdf.write_bytes(b'%PDF-1.4\n%%EOF')
    storage=get_sqlite();storage.add_knowledge('pdf','pdf','file',str(pdf))
    with TestClient(app) as client:
        assert client.get('/api/items/pdf/content').json()['pdf_available']
        result=client.get('/api/items/pdf/pdf')
        assert result.content.startswith(b'%PDF-')
        assert result.headers['content-type']=='application/pdf'
        pdf.unlink()
        assert client.get('/api/items/pdf/pdf').status_code==404


def test_document_graph_without_model():
    from kb.web.dependencies import get_sqlite
    storage=get_sqlite();add(storage,'doc');storage.link_tag('doc','topic')
    with TestClient(app) as client:
        data=client.get('/api/graph/documents').json()
        assert len(data['nodes'])==2 and len(data['edges'])==1
        assert data['edges'][0]['relation_type']=='标签'
        assert client.post('/api/mine/entities').status_code==400


def test_pdf_page_renders_layout(tmp_path):
    import shutil
    if not shutil.which('pdftoppm'):
        pytest.skip('Poppler unavailable')
    from PyPDF2 import PdfWriter
    from kb.web.dependencies import get_sqlite
    path=tmp_path/'layout.pdf'
    writer=PdfWriter();writer.add_blank_page(width=200,height=300)
    with path.open('wb') as f:
        writer.write(f)
    get_sqlite().add_knowledge('pdfpage','PDF','file',str(path))
    with TestClient(app) as client:
        assert client.get('/api/items/pdfpage/pdf/info').json()['pages']==1
        response=client.get('/api/items/pdfpage/pdf/page/1')
        assert response.status_code==200 and response.content.startswith(b'\x89PNG')
        assert client.get('/api/items/pdfpage/pdf/page/2').status_code==404


def test_entity_backfill_reports_progress(monkeypatch):
    from kb.web.dependencies import get_sqlite,get_config
    from kb.processors.base import ProcessResult
    from kb.web.routes import mining
    add(get_sqlite(),'source','concept')
    get_config().set('llm.api_key','test-key')
    monkeypatch.setattr('kb.processors.entity_extractor.EntityExtractor.process', lambda *a,**kw:ProcessResult(success=True,data={'entities':[{'name':'concept','type':'concept'}],'relations':[]}))
    with TestClient(app) as client:
        assert client.post('/api/mine/entities').status_code==200
        state=client.get('/api/mine/entities/status').json()
        assert state['state']=='completed' and state['processed']==1
        assert client.get('/api/graph').json()['nodes']


def test_edit_tags_add_remove_clear_and_counts(monkeypatch):
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async',lambda *a,**kw:None)
    with TestClient(app) as client:
        id=client.post('/api/collect/note',json={'text':'tagged note','tags':['old','keep']}).json()['id']
        assert client.patch('/api/items/'+id,json={'tags':[' new ','keep','new'],'revision':0}).status_code==200
        assert set(client.get('/api/items/'+id).json()['tags'])=={'new','keep'}
        counts={r['name']:r['count'] for r in client.get('/api/tags').json()}
        assert counts['old']==0 and counts['new']==1 and counts['keep']==1
        assert client.patch('/api/items/'+id,json={'tags':[],'revision':1}).status_code==200
        assert client.get('/api/items/'+id).json()['tags']==[]
        assert not client.get('/api/items',params={'tag':'keep'}).json()


def test_web_upload_text_and_duplicate(monkeypatch):
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async',lambda *a,**kw:None)
    with TestClient(app) as client:
        response=client.post('/api/collect/file',files={'file':('知识.txt','正文包含上传文件'.encode(),'text/plain')},data={'tags':'上传，测试','title':'我的文档'})
        assert response.status_code==200
        id=response.json()['id']
        doc=client.get('/api/items/'+id+'/content').json()
        assert doc['content']=='正文包含上传文件' and doc['title']=='我的文档'
        assert set(doc['tags'])=={'上传','测试'}
        assert client.post('/api/collect/file',files={'file':('知识.txt','正文包含上传文件'.encode(),'text/plain')}).json()['duplicate']
        assert client.post('/api/collect/file',files={'file':('program.exe',b'data')}).status_code==400


def test_webpage_capture_preview_and_bookmark(monkeypatch):
    import httpx
    from kb.collectors.webpage_collector import WebpageCollector
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async',lambda *a,**kw:None)
    monkeypatch.setattr(WebpageCollector,'_download',lambda self,url,**kw:httpx.Response(200,text='<html><title>网页标题</title><article><h1>知识文章</h1><p>这段正文可以在知识库预览。</p></article></html>',request=httpx.Request('GET',url)))
    with TestClient(app) as client:
        response=client.post('/api/collect/webpage',json={'url':'https://example.org/article'})
        assert response.status_code==200
        doc=client.get('/api/items/'+response.json()['id']+'/content').json()
        assert doc['title']=='网页标题' and '正文可以在知识库预览' in doc['content']
        bookmark=client.post('/api/collect/bookmark',json={'url':'https://example.org/','title':'收藏的网站','tags':['收藏']}).json()
        item=client.get('/api/items/'+bookmark['id']).json()
        assert item['content_type']=='bookmark' and item['tags']==['收藏']
        assert client.post('/api/collect/webpage',json={'url':'file:///tmp/private'}).status_code==422


def test_tag_only_edit_preserves_index(monkeypatch):
    from kb.web.dependencies import get_sqlite
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async',lambda *a,**kw:None)
    with TestClient(app) as client:
        id=client.post('/api/collect/note',json={'text':'keep vectors'}).json()['id']
        db=get_sqlite();db.set_document_embedding(id,[1.,0.])
        ids=[r['id'] for r in db.get_chunks(id)]
        assert client.patch('/api/items/'+id,json={'tags':['new'],'revision':0}).status_code==200
        assert [r['id'] for r in db.get_chunks(id)]==ids
        assert db.get_document_embedding(id)==[1.,0.]
        assert id in db.search_metadata([id],['new'])


@pytest.fixture
def multitag_client():
    from kb.web.dependencies import get_sqlite
    storage=get_sqlite()
    for id,kind,text,tags in [('both','note','sharedkeyword',['AI','视频生成']),('ai','file','sharedkeyword',['AI']),('video','note','sharedkeyword',['视频生成']),('none','note','sharedkeyword',[]),('other','note','otherkeyword',['AI','视频生成'])]:
        storage.add_knowledge(id,id,kind,'note',collected_at='2026-10-23T10:00:00')
        storage.add_chunk(id+'-chunk',id,0,text)
        for tag in tags:
            storage.link_tag(id,tag)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize('params,expected',[
    ([('tags','AI'),('tags','视频生成')],{'both','other'}),
    ([('tags','AI'),('tags','视频生成'),('tag_mode','or')],{'both','other','ai','video'}),
    ([('tags','AI'),('tags','视频生成'),('q','sharedkeyword')],{'both'}),
    ([('tags','AI'),('tags','视频生成'),('q','sharedkeyword'),('tag_mode','or'),('content_type','file')],{'ai'}),
    ([('tags','AI'),('tags','AI')],{'both','other','ai'}),
    ([('tags','AI'),('tags','missing')],set()),
    ([('tags','AI'),('tags','missing'),('tag_mode','or')],{'both','other','ai'}),
    ([('tag','AI')],{'both','other','ai'}),
    ([('tag','AI'),('tags','视频生成')],{'both','other'}),
    ([('tags','')],{'both','other','ai','video','none'}),
])
def test_multitag_filter_combinations(multitag_client,params,expected):
    result=multitag_client.get('/api/items',params=params)
    assert result.status_code==200
    assert {row['id'] for row in result.json()}==expected


def test_multitag_pagination_and_validation(multitag_client):
    params=[('tags','AI'),('tags','视频生成'),('tag_mode','or')]
    full=multitag_client.get('/api/items',params=params).json()
    page=multitag_client.get('/api/items',params=[*params,('limit','1'),('offset','1')]).json()
    assert [r['id'] for r in page]==[full[1]['id']]
    assert multitag_client.get('/api/items',params={'tag_mode':'invalid'}).status_code==422


def test_multitag_literal_comma_label(multitag_client):
    from kb.web.dependencies import get_sqlite
    get_sqlite().link_tag('both','图形算法，渲染算法')
    rows=multitag_client.get('/api/items',params=[('tags','图形算法，渲染算法'),('tags','AI')]).json()
    assert [row['id'] for row in rows]==['both']


@pytest.mark.parametrize('mime',['application/pdf','application/octet-stream'])
def test_pdf_url_auto_detect_and_preview(tmp_path,monkeypatch,mime):
    import io,httpx
    from PyPDF2 import PdfWriter
    from kb.collectors.webpage_collector import WebpageCollector
    from kb.web.dependencies import get_sqlite
    writer=PdfWriter();writer.add_blank_page(width=200,height=300)
    data=io.BytesIO();writer.write(data);pdf=data.getvalue()
    url='https://arxiv.org/pdf/2609.28466'
    monkeypatch.setattr(WebpageCollector,'_download',lambda self,source:httpx.Response(200,content=pdf,headers={'content-type':mime},request=httpx.Request('GET',url)))
    monkeypatch.setattr(WebpageCollector,'_parse_html',lambda *a:pytest.fail('PDF must not enter the HTML parser'))
    monkeypatch.setattr('kb.web.routes.collect.mine_document_async',lambda *a,**kw:None)
    with TestClient(app) as client:
        response=client.post('/api/collect/webpage',json={'url':url,'title':'自回归视频生成','tags':['AI','视频生成']})
        assert response.status_code==200,response.text
        id=response.json()['id']
        item=client.get('/api/items/'+id+'/content').json()
        assert item['content_type']=='file' and item['title']=='自回归视频生成'
        assert set(item['tags'])=={'AI','视频生成'} and item['source']==url
        assert item['pdf_available']
        assert client.get('/api/items/'+id+'/pdf').content==pdf
        assert client.post('/api/collect/webpage',json={'url':url}).json()['duplicate']


def test_bad_pdf_response_gives_readable_error(monkeypatch):
    import httpx
    from kb.collectors.webpage_collector import WebpageCollector
    monkeypatch.setattr(WebpageCollector,'_download',lambda self,url:httpx.Response(200,text='<html>Login required</html>',headers={'content-type':'application/pdf'},request=httpx.Request('GET',url)))
    with TestClient(app) as client:
        result=client.post('/api/collect/webpage',json={'url':'https://example.org/pdf'})
        assert result.status_code==400
        assert '未返回有效 PDF' in result.json()['detail']


def test_html_control_characters_removed(monkeypatch):
    import httpx
    from kb.collectors.webpage_collector import WebpageCollector
    monkeypatch.setattr(WebpageCollector,'_download',lambda self,url:httpx.Response(200,text='<html><title>标题</title><article><p>合法正文\x00\x08仍然可读</p></article></html>',headers={'content-type':'text/html'},request=httpx.Request('GET',url)))
    collector=WebpageCollector()
    result=collector.collect('https://example.org/')
    assert result.success,result.error
    from kb.services.ingestion import read_content
    content=read_content(result)
    assert '合法正文' in content and '\x00' not in content and '\x08' not in content


def test_stream_download_size_bound(monkeypatch):
    import httpx
    from kb.collectors.webpage_collector import WebpageCollector
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'x'*100,request=req))) as client:
        monkeypatch.setattr(httpx,'stream',lambda method,url,**kw:client.stream(method,url,**kw))
        collector=WebpageCollector();collector.MAX_DOWNLOAD_BYTES=10
        result=collector.collect('https://example.org/')
        assert not result.success and '30 MB' in result.error


def test_organize_tags_builds_real_topics_and_wiki_without_models(monkeypatch):
    from kb.web.dependencies import get_config,get_sqlite
    from kb.services.organization import organize
    from kb.processors.wiki_generator import WikiGenerator
    storage=get_sqlite();add(storage,'one','Full evidence for the overview');add(storage,'two','Other source')
    storage.link_tag('one','视频生成');storage.link_tag('one','AI');storage.link_tag('two','AI')
    monkeypatch.setattr(WikiGenerator,'_try_llm_enhance',lambda *a:pytest.fail('Offline organization must not call LLM'))
    result=organize(get_config(),'tags',False)
    assert result['clusters']==2 and result['articles']==2 and result['classified']==2
    assert storage.conn.execute('SELECT COUNT(*) FROM document_embeddings').fetchone()[0]==0
    assert any('Full evidence' in row[0] for row in storage.conn.execute('SELECT content FROM wiki_articles'))
    result=organize(get_config(),'tags',False)
    assert storage.conn.execute('SELECT COUNT(*) FROM wiki_articles').fetchone()[0]==2
    assert storage.conn.execute('SELECT document_count FROM topic_clusters WHERE label=?',('AI',)).fetchone()[0]==2


def test_organization_empty_tags_preserves_existing_topics():
    from kb.web.dependencies import get_config,get_sqlite
    from kb.services.organization import organize
    storage=get_sqlite();add(storage,'one');storage.add_topic_cluster('existing','', ['one'])
    with pytest.raises(ValueError,match='标签'):
        organize(get_config(),'tags')
    assert storage.conn.execute('SELECT label FROM topic_clusters').fetchone()[0]=='existing'


def test_topic_generation_endpoint_reports_completion(monkeypatch):
    from kb.web.dependencies import get_sqlite
    from kb.web.routes import topics
    monkeypatch.setattr(topics,'_job',{'state':'idle','stage':'','processed':0,'total':0,'error':'','result':None})
    storage=get_sqlite();add(storage,'one');storage.link_tag('one','topic')
    with TestClient(app) as client:
        assert client.post('/api/topics/rebuild',json={'strategy':'tags','enhance':False}).status_code==200
        status=client.get('/api/topics/status').json()
        assert status['state']=='completed' and status['result']['articles']==1
        topic=client.get('/api/topics').json()[0]
        assert client.get('/api/topics/'+str(topic['id'])+'/documents').json()[0]['id']=='one'
        assert client.get('/api/wiki/articles/'+str(topic['id'])).json()
        assert client.post('/api/topics/rebuild',json={'strategy':'semantic'}).status_code==400


def test_no_semantic_clusters_does_not_clear_existing_topics(monkeypatch):
    import numpy as np
    from kb.web.dependencies import get_sqlite,get_config
    from kb.processors.topic_clusterer import TopicClusterer
    storage=get_sqlite()
    for i in range(3):
        add(storage,str(i));storage.set_document_embedding(str(i),[float(i),1.])
    storage.add_topic_cluster('existing','',['0'])
    class Noise:
        def __init__(self,**kw):pass
        def fit_predict(self,values):return np.array([-1,-1,-1])
    monkeypatch.setattr('kb.processors.topic_clusterer.HDBSCAN',Noise)
    assert TopicClusterer(get_config()).cluster_all(str(storage.db_path))['clusters']==0
    assert storage.conn.execute('SELECT label FROM topic_clusters').fetchone()[0]=='existing'


def test_semantic_organization_backfills_missing_embeddings(monkeypatch):
    from kb.web.dependencies import get_sqlite,get_config
    from kb.services.organization import organize
    storage=get_sqlite();add(storage,'one','text')
    get_config().set('embedding.api_key','test-key')
    called=[]
    monkeypatch.setattr('kb.processors.embedder.Embedder.embed_single',lambda self,text:called.append(text) or [1.,0.])
    monkeypatch.setattr('kb.processors.topic_clusterer.TopicClusterer.cluster_all',lambda *a:{'clusters':0})
    with pytest.raises(ValueError,match='稳定'):
        organize(get_config(),'semantic')
    assert called and storage.get_document_embedding('one')==[1.,0.]
