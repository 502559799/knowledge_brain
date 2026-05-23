"""备份路由"""
import os, tarfile, tempfile
from datetime import datetime
from fastapi import APIRouter
from kb.web.dependencies import get_config, get_sqlite
router = APIRouter()

@router.post("/backup/create")
def create_backup():
    config = get_config()
    backup_dir = config.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"kb-backup-{timestamp}.tar.gz"
    filepath = backup_dir / filename
    db_path = config.data_dir / "db"
    with tarfile.open(str(filepath), "w:gz") as tar:
        tar.add(str(db_path), arcname="db")
    return {"success": True, "filename": filename, "path": str(filepath)}

@router.get("/backup/list")
def list_backups():
    config = get_config()
    backup_dir = config.data_dir / "backups"
    if not backup_dir.exists(): return []
    files = sorted(backup_dir.glob("*.tar.gz"), reverse=True)
    return [{"name": f.name, "size": f.stat().st_size, "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()} for f in files]
