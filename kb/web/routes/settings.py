"""设置路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from kb.web.dependencies import get_config

router = APIRouter()


class UpdateSettingsRequest(BaseModel):
    embedding_api_key: str = None
    embedding_provider: str = None
    embedding_model: str = None
    llm_api_key: str = None
    llm_provider: str = None
    llm_model: str = None
    backup_enabled: bool = None
    backup_schedule: str = None


@router.get("/settings")
def get_settings():
    """Return masked config (API keys hidden)"""
    config = get_config()
    return config.to_safe_dict()


@router.post("/settings")
def update_settings(req: UpdateSettingsRequest):
    """Update config settings and persist to disk"""
    config = get_config()
    updates = req.model_dump(exclude_none=True)
    if "embedding_api_key" in updates:
        config.set("embedding.api_key", updates["embedding_api_key"])
    if "embedding_provider" in updates:
        config.set("embedding.provider", updates["embedding_provider"])
    if "embedding_model" in updates:
        config.set("embedding.model", updates["embedding_model"])
    if "llm_api_key" in updates:
        config.set("llm.api_key", updates["llm_api_key"])
    if "llm_provider" in updates:
        config.set("llm.provider", updates["llm_provider"])
    if "llm_model" in updates:
        config.set("llm.model", updates["llm_model"])
    if "backup_enabled" in updates:
        config.set("backup.enabled", updates["backup_enabled"])
    if "backup_schedule" in updates:
        config.set("backup.schedule", updates["backup_schedule"])
    config.save()
    return {"success": True, "config": config.to_safe_dict()}


@router.get("/settings/services")
def check_services():
    config = get_config()
    return config.validate_services()
