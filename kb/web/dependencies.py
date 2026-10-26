"""Web层依赖注入 - 单例管理"""
import logging
import threading
from functools import wraps
from typing import Optional
from kb.config import Config
from kb.storage.sqlite_storage import SQLiteStorage
from kb.storage.chroma_storage import ChromaStorage

logger = logging.getLogger(__name__)

_config_instance: Optional[Config] = None
_sqlite_instance: Optional[SQLiteStorage] = None
_chroma_instance: Optional[ChromaStorage] = None
_pipeline_instance = None
_conversation_instance = None
_semantic_search_instance = None
_keyword_search_instance = None
_embedder_instance = None


_instance_lock = threading.RLock()


def synchronized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _instance_lock:
            return function(*args, **kwargs)
    return wrapped


@synchronized
def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


@synchronized
def get_sqlite() -> SQLiteStorage:
    global _sqlite_instance
    if _sqlite_instance is None:
        config = get_config()
        _sqlite_instance = SQLiteStorage(str(config.data_dir / "db" / "metadata.db"))
    return _sqlite_instance


@synchronized
def get_chroma() -> Optional[ChromaStorage]:
    global _chroma_instance
    if _chroma_instance is None:
        try:
            config = get_config()
            persist_dir = config.get("storage.persist_directory", str(config.data_dir / "db" / "chroma"))
            _chroma_instance = ChromaStorage(path=persist_dir)
        except Exception as e:
            logger.warning(f"ChromaDB初始化失败（语义搜索不可用）: {e}")
            _chroma_instance = None
    if _chroma_instance is not None:
        from kb.services.deletion import flush_vector_deletions
        flush_vector_deletions(get_sqlite(), _chroma_instance)
    return _chroma_instance


@synchronized
def get_embedder():
    """Singleton embedder instance"""
    global _embedder_instance
    if '_embedder_instance' not in globals() or _embedder_instance is None:
        from kb.processors.embedder import Embedder
        _embedder_instance = Embedder(config=get_config())
    return _embedder_instance


@synchronized
def get_semantic_search():
    global _semantic_search_instance
    if _semantic_search_instance is None:
        from kb.query.semantic_search import SemanticSearch
        _semantic_search_instance = SemanticSearch(
            config=get_config(),
            chroma_storage=get_chroma(),
            embedder=get_embedder(),
            storage=get_sqlite(),
        )
    return _semantic_search_instance


@synchronized
def get_keyword_search():
    global _keyword_search_instance
    if _keyword_search_instance is None:
        from kb.query.keyword_search import KeywordSearch
        _keyword_search_instance = KeywordSearch(data_dir=str(get_config().data_dir))
    return _keyword_search_instance


@synchronized
def get_pipeline():
    global _pipeline_instance
    if _pipeline_instance is None:
        from kb.query.retrieval_pipeline import RetrievalPipeline
        config = get_config()
        ss = get_semantic_search()
        ks = get_keyword_search()
        _pipeline_instance = RetrievalPipeline(config=config, semantic_search=ss, keyword_search=ks, conversation_manager=get_conversation())
    return _pipeline_instance


@synchronized
def get_conversation():
    global _conversation_instance
    if _conversation_instance is None:
        from kb.query.conversation import ConversationManager
        config = get_config()
        conv_cfg = config.get("query.rag.conversation", {})
        _conversation_instance = ConversationManager(
            max_turns=conv_cfg.get("max_turns", 20),
            timeout_minutes=conv_cfg.get("session_timeout_minutes", 30),
            history_turns=conv_cfg.get("history_turns_in_context", 5),
        )
    return _conversation_instance


@synchronized
def reset_query_services():
    global _pipeline_instance, _semantic_search_instance, _embedder_instance
    _pipeline_instance = _semantic_search_instance = _embedder_instance = None
