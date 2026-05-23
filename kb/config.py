"""配置管理模块 - YAML配置 + 环境变量替换"""
import logging, os, re
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "data_dir": "~/.knowledge-brain",
    "embedding": {"provider": "dashscope", "model": "text-embedding-v4"},
    "llm": {"provider": "dashscope", "model": "qwen-plus"},
    "chunking": {"max_chunk_size": 1000, "chunk_overlap": 100},
    "storage": {"type": "chroma", "persist_directory": "~/.knowledge-brain/db/chroma"},
    "query": {
        "rag": {"top_k": 5, "temperature": 0.3, "max_tokens": 1000, "context_budget": 4000,
                "reranking": {"enabled": True, "top_n_candidates": 20, "weight_retrieval": 0.4, "weight_rerank": 0.6},
                "conversation": {"max_turns": 20, "session_timeout_minutes": 30, "history_turns_in_context": 5}},
        "pipeline": {"top_k": 10, "rerank_top_k": 5, "context_budget": 4000},
    },
    "logging": {"level": "INFO", "max_bytes": 10485760, "backup_count": 5},
    "extraction": {"summary_max_length": 512},
    "wiki": {"enabled": True, "max_source_tokens_per_topic": 8000, "entity_card_threshold": 3, "temperature": 0.3},
    "backup": {"enabled": False, "schedule": "0 2 * * *", "retention_days": 30, "backup_dir": "~/.knowledge-brain/backups",
               "compression": True, "cloud_provider": "oss",
               "oss": {"endpoint": "oss-cn-hangzhou.aliyuncs.com", "access_key_id": "", "access_key_secret": "", "bucket": "kb-backups"},
               "s3": {"region": "us-west-2", "access_key_id": "", "secret_access_key": "", "bucket": "kb-backups"}},
}

def _expand_env_vars(value: str) -> str:
    return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), value)

def _expand_env_vars_in_config(config: Any) -> Any:
    if isinstance(config, dict):
        return {k: _expand_env_vars_in_config(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_expand_env_vars_in_config(item) for item in config]
    elif isinstance(config, str):
        return _expand_env_vars(config)
    return config

class Config:
    """配置管理器"""
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path.home() / ".knowledge-brain" / "config.yaml"
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        self._config = DEFAULT_CONFIG.copy()
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    self._deep_merge(self._config, file_config)
        self._config = _expand_env_vars_in_config(self._config)

    def _deep_merge(self, base: Dict, override: Dict) -> None:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def data_dir(self) -> Path:
        return Path(os.path.expanduser(self.get("data_dir", DEFAULT_CONFIG["data_dir"])))

    def save(self, path: Optional[Path] = None) -> None:
        save_path = path or self._config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

    def to_dict(self) -> Dict[str, Any]:
        return self._config.copy()

    def validate_services(self) -> dict:
        status = {"embedding_available": False, "llm_available": False}
        emb_key = self.get("embedding.dashscope.api_key", "") or self.get("embedding.api_key", "")
        if emb_key and not emb_key.startswith("${"):
            status["embedding_available"] = True
        llm_key = self.get("llm.api_key", "")
        if llm_key and not llm_key.startswith("${"):
            status["llm_available"] = True
        return status
