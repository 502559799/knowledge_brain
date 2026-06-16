"""备份调度器 - 支持cron表达式"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
_scheduler_thread = None
_stop_event = threading.Event()


def init_scheduler(config):
    global _scheduler_thread
    backup_cfg = config.get("backup", {})
    if not backup_cfg.get("enabled"):
        logger.info("备份调度未启用")
        return

    cron_expr = backup_cfg.get("schedule", "0 2 * * *")
    retention_days = backup_cfg.get("retention_days", 30)
    logger.info(f"备份调度已启用: schedule={cron_expr}, retention={retention_days}天")

    # Parse hour:minute from "m H * * *" cron format
    parts = cron_expr.split()
    try:
        minute = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
        hour = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
    except (ValueError, IndexError):
        minute, hour = 0, 2

    import schedule
    schedule_time = f"{hour:02d}:{minute:02d}"
    schedule.every().day.at(schedule_time).do(_run_scheduled_backup, config=config, retention_days=retention_days)

    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="backup-scheduler")
    _scheduler_thread.start()


def _run_scheduled_backup(config, retention_days=30):
    try:
        from kb.web.routes.backup import create_backup
        result = create_backup()
        logger.info(f"自动备份完成: {result.get('filename', 'unknown')}")
        _cleanup_old_backups(config, retention_days)
    except Exception as e:
        logger.error(f"自动备份失败: {e}")


def _cleanup_old_backups(config, retention_days: int):
    """Delete backups older than retention_days"""
    backup_dir = Path(os.path.expanduser(
        config.get("backup.backup_dir", str(config.data_dir / "backups"))))
    if not backup_dir.exists():
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for f in backup_dir.glob("kb-backup-*.tar.gz"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                logger.info(f"已清理过期备份: {f.name}")
        except Exception as e:
            logger.warning(f"清理备份失败 {f.name}: {e}")


def _scheduler_loop():
    import schedule
    while not _stop_event.is_set():
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"调度器错误: {e}")
        _stop_event.wait(60)


def stop_scheduler():
    global _scheduler_thread
    _stop_event.set()
    try:
        import schedule
        schedule.clear()
    except Exception:
        pass
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=5)
    _scheduler_thread = None
