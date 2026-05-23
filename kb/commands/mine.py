"""挖掘命令"""
import click
from kb.config import Config

def mine_cmd():
    config = Config()
    click.echo("⛏️ 开始知识挖掘...")
    try:
        from kb.processors.topic_clusterer import TopicClusterer
        tc = TopicClusterer(config=config)
        result = tc.cluster_all()
        click.echo(f"  主题聚类: {result['clusters']} 个聚类, {result['classified']} 篇分类, {result['noise']} 噪声")
    except Exception as e:
        click.echo(f"  主题聚类失败: {e}")
    try:
        from kb.processors.doc_relation_builder import DocRelationBuilder
        dr = DocRelationBuilder(config=config)
        result = dr.build_all()
        click.echo(f"  文档关系: {result['embedding_similarity']} 相似, {result['shared_entity']} 共享实体")
    except Exception as e:
        click.echo(f"  关系构建失败: {e}")
    click.echo("✅ 挖掘完成")
