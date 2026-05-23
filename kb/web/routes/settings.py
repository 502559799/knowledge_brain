"""设置路由"""
from fastapi import APIRouter
from kb.web.dependencies import get_config
router = APIRouter()

@router.get("/settings")
def get_settings():
    config = get_config()
    return config.to_dict()

@router.get("/settings/services")
def check_services():
    config = get_config()
    return config.validate_services()
