"""备份路由"""
import os
import tarfile
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from kb.web.dependencies import get_config

router = APIRouter()


def _get_backup_dir():
    config = get_config()
    backup_dir = Path(os.path.expanduser(config.get("backup.backup_dir", str(config.data_dir / "backups"))))
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


@router.post("/backup/create")
def create_backup():
    config = get_config()
    backup_dir = _get_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"kb-backup-{timestamp}.tar.gz"
    filepath = backup_dir / filename
    data_dir = config.data_dir
    with tarfile.open(str(filepath), "w:gz") as tar:
        # Backup database directory
        db_path = data_dir / "db"
        if db_path.exists():
            tar.add(str(db_path), arcname="db")
        # Backup collected files
        collect_dir = data_dir / "1_collect"
        if collect_dir.exists():
            tar.add(str(collect_dir), arcname="1_collect")
        # Backup config
        config_path = data_dir / "config.yaml"
        if config_path.exists():
            tar.add(str(config_path), arcname="config.yaml")
    return {"success": True, "filename": filename, "size": filepath.stat().st_size}


@router.get("/backup/list")
def list_backups():
    backup_dir = _get_backup_dir()
    if not backup_dir.exists():
        return []
    files = sorted(backup_dir.glob("*.tar.gz"), reverse=True)
    return [{
        "name": f.name,
        "size": f.stat().st_size,
        "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
    } for f in files]


@router.get("/backup/download/{filename}")
def download_backup(filename: str):
    backup_dir = _get_backup_dir()
    filepath = backup_dir / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(str(filepath), filename=filename, media_type="application/gzip")


@router.delete("/backup/{filename}")
def delete_backup(filename: str):
    backup_dir = _get_backup_dir()
    filepath = backup_dir / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    filepath.unlink()
    return {"success": True}


@router.post("/backup/restore/{filename}")
def restore_backup(filename: str):
    """Restore from a backup file. WARNING: This overwrites current data."""
    config = get_config()
    backup_dir = _get_backup_dir()
    filepath = backup_dir / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    data_dir = config.data_dir
    try:
        with tarfile.open(str(filepath), "r:gz") as tar:
            # Extract to data directory (overwriting existing files)
            tar.extractall(str(data_dir))
        return {"success": True, "message": "Backup restored. Please restart the server."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")
