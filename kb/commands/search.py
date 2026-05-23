"""搜索命令"""
import click, json
from kb.config import Config

def search_semantic_cmd(query):
    from kb.query.semantic_search import SemanticSearch
    ss = SemanticSearch(Config())
    results = ss.search(query)
    for r in results:
        click.echo(f" [{r.score:.2f}] {r.id[:8]}: {r.metadata.get('title', 'N/A')}")

def search_keyword_cmd(query):
    from kb.query.keyword_search import KeywordSearch
    ks = KeywordSearch(data_dir=str(Config().data_dir))
    results = ks.search(query)
    for r in results:
        click.echo(f" {r.id[:8]}: {r.metadata.get('title', 'N/A')}")

def search_rag_cmd(question):
    from kb.query.rag import RAGQuery
    rag = RAGQuery(Config())
    result = rag.query(question)
    click.echo(f"\n📖 回答:\n{result.answer}\n")
    if result.sources:
        click.echo(f"📚 来源: {len(result.sources)} 个文档")
