"""CLI入口 - Click框架"""
import click
from kb import __version__

@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="kbrain")
@click.pass_context
def cli(ctx):
    """Knowledge Brain - 个人知识大脑系统"""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command()
@click.option("--setup", is_flag=True, help="完整初始化")
def init(setup):
    """初始化知识库"""
    from kb.commands.init import init_cmd
    init_cmd(setup=setup)

@cli.group()
def collect():
    """知识采集"""
    pass

@collect.command("file")
@click.argument("path")
@click.option("--tags", "-t", multiple=True)
@click.option("--title", default=None)
def collect_file(path, tags, title):
    from kb.commands.collect import collect_file_cmd
    collect_file_cmd(path, tags, title)

@collect.command("webpage")
@click.argument("url")
@click.option("--tags", "-t", multiple=True)
def collect_webpage(url, tags):
    from kb.commands.collect import collect_webpage_cmd
    collect_webpage_cmd(url, tags)

@collect.command("bookmark")
@click.argument("url")
@click.option("--tags", "-t", multiple=True)
@click.option("--title", default=None)
def collect_bookmark(url, tags, title):
    from kb.commands.collect import collect_bookmark_cmd
    collect_bookmark_cmd(url, tags, title)

@collect.command("note")
@click.argument("text")
@click.option("--tags", "-t", multiple=True)
@click.option("--title", default=None)
def collect_note(text, tags, title):
    from kb.commands.collect import collect_note_cmd
    collect_note_cmd(text, tags, title)

@cli.group()
def search():
    """搜索知识"""
    pass

@search.command("semantic")
@click.argument("query")
def search_semantic(query):
    from kb.commands.search import search_semantic_cmd
    search_semantic_cmd(query)

@search.command("keyword")
@click.argument("query")
def search_keyword(query):
    from kb.commands.search import search_keyword_cmd
    search_keyword_cmd(query)

@search.command("rag")
@click.argument("question")
def search_rag(question):
    from kb.commands.search import search_rag_cmd
    search_rag_cmd(question)

@cli.command()
def stats():
    """知识库统计"""
    from kb.commands.manage import stats_cmd
    stats_cmd()

@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, type=click.IntRange(1, 65535), show_default=True)
def web(host, port):
    """启动Web界面"""
    import uvicorn
    uvicorn.run("kb.web.app:app", host=host, port=port, reload=False)

@cli.command()
def mine():
    """运行知识挖掘"""
    from kb.commands.mine import mine_cmd
    mine_cmd()

@cli.group()
def backup():
    """备份管理"""
    pass

@backup.command("create")
def backup_create():
    from kb.commands.backup import backup_create_cmd
    backup_create_cmd()

@backup.command("list")
def backup_list():
    from kb.commands.backup import backup_list_cmd
    backup_list_cmd()

if __name__ == "__main__":
    cli()
