"""初始化命令"""
import click
from pathlib import Path
from kb.config import Config

def init_cmd(setup: bool = False):
    config = Config()
    data_dir = config.data_dir
    for sub in ["1_collect/files", "1_collect/webpages", "1_collect/bookmarks", "1_collect/notes", "db", "backups"]:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    config.save()
    click.echo(f"✅ 知识库已初始化: {data_dir}")
    if setup:
        click.echo("配置文件: " + str(config._config_path))
