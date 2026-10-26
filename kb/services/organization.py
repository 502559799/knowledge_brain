"""Build usable topic collections, with explicit offline and semantic paths."""
from collections import defaultdict
from kb.storage.sqlite_storage import SQLiteStorage
from kb.services.reading import read_item


def organize(config, strategy='tags', enhance=False, report=lambda **kw:None):
    path=str(config.data_dir/'db/metadata.db')
    with SQLiteStorage(path) as storage:
        if strategy=='tags':
            report(stage='按已有标签整理主题')
            with storage._lock:
                pairs=storage.conn.execute('SELECT t.name,kt.knowledge_id FROM tags t JOIN knowledge_tags kt ON t.id=kt.tag_id JOIN knowledge k ON k.id=kt.knowledge_id ORDER BY t.name,kt.knowledge_id').fetchall()
            groups=defaultdict(list)
            for name,id in pairs:
                groups[name].append(id)
            if not groups:
                raise ValueError('尚无可用标签。请先在知识库为资料添加标签，再开始整理。')
            with storage._transaction() as cursor:
                cursor.execute('DELETE FROM wiki_articles')
                cursor.execute('DELETE FROM wiki_categories')
                cursor.execute('DELETE FROM knowledge_topics')
                cursor.execute('DELETE FROM topic_clusters')
                for name,ids in groups.items():
                    cursor.execute('INSERT INTO topic_clusters(label,description,document_count) VALUES (?,?,?)',(name,'按标签整理的主题；同一文档可以属于多个主题。',len(ids)))
                    topic_id=cursor.lastrowid
                    cursor.executemany('INSERT INTO knowledge_topics VALUES (?,?,1)',[(id,topic_id) for id in ids])
            result={'clusters':len(groups),'classified':len({id for ids in groups.values() for id in ids})}
        elif strategy=='semantic':
            from kb.processors.embedder import Embedder
            from kb.processors.topic_clusterer import TopicClusterer
            if not config.validate_services()['embedding_available']:
                raise ValueError('语义分类需要可用的嵌入服务，请在设置中配置；也可使用按标签整理。')
            docs=storage.list_knowledge(limit=100000)
            missing=[doc for doc in docs if storage.get_document_embedding(doc['id']) is None]
            report(stage='补充缺失的文档向量',total=len(missing),processed=0)
            embedder=Embedder(config=config)
            for i,doc in enumerate(missing):
                body=read_item(storage,config,doc)['content']
                embedding=embedder.embed_single((doc['title'] or '')+'\n'+body[:2000])
                if not embedding or not storage.set_document_embedding(doc['id'],embedding):
                    raise ValueError('文档向量生成失败，请检查嵌入服务配置')
                report(processed=i+1)
            report(stage='根据内容相似度自动分类')
            result=TopicClusterer(config=config).cluster_all(path)
            if not result['clusters']:
                raise ValueError('暂未发现稳定的语义主题。需要至少 3 篇有效向量文档且内容足够相近，可先使用按标签整理。已有主题已保留。')
        else:
            raise ValueError('未知主题整理方式')
    report(stage='生成主题资料概览'+('与 AI 摘要' if enhance else '（无需模型）'))
    from kb.processors.wiki_generator import WikiGenerator
    generator=WikiGenerator(config=config,enhance_with_llm=enhance)
    articles=generator.generate_for_all_topics(path)
    return {**result,'articles':articles,'strategy':strategy,'warnings':generator.enhancement_errors}
