"""备份调度器"""
import schedule, time, threading, logging
logger = logging.getLogger(__name__)
_scheduler_thread = None

def init_scheduler(config):
    global _scheduler_thread
    backup_cfg = config.get("backup", {})
    if not backup_cfg.get("enabled"): return
    cron_expr = backup_cfg.get("schedule", "0 2 * * *")
    logger.info(f"备份调度已启用: {cron_expr}")
    # 简单实现: 每天执行
    schedule.every().day.at("02:00").do(_run_backup, config=config)
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()

def _run_backup(config):
    try:
        from kb.web.routes.backup import create_backup
        result = create_backup()
        logger.info(f"自动备份: {result}")
    except Exception as e:
        logger.error(f"自动备份失败: {e}")

def _scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(60)

def stop_scheduler():
    schedule.clear()
