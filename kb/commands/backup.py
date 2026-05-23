"""备份命令"""
import click
from kb.web.routes.backup import create_backup, list_backups

def backup_create_cmd():
    result = create_backup()
    if result.get("success"):
        click.echo(f"✅ 备份创建: {result['filename']}")
    else:
        click.echo("❌ 备份失败")

def backup_list_cmd():
    backups = list_backups()
    for b in backups:
        click.echo(f"  {b['name']} ({b['size']//1024}KB) {b['created']}")
    if not backups:
        click.echo("暂无备份")
