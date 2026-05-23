"""管理命令"""
import click
from kb.storage.sqlite_storage import SQLiteStorage
from kb.config import Config

def stats_cmd():
    config = Config()
    storage = SQLiteStorage(str(config.data_dir / "db" / "metadata.db"))
    stats = storage.get_stats()
    click.echo("📊 知识库统计:")
    click.echo(f"  总数: {stats['total_items']}")
    for ct, count in stats.get("by_type", {}).items():
        click.echo(f"  {ct}: {count}")
    click.echo(f"  标签: {stats['tag_count']}")
    click.echo(f"  实体: {stats['entity_count']}")
    click.echo(f"  关系: {stats['relation_count']}")
    click.echo(f"  主题: {stats['topic_count']}")
    storage.close()
