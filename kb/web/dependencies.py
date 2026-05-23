"""Web层依赖注入"""
from typing import Optional
from kb.storage.sqlite_storage import SQLiteStorage
from kb.storage.chroma_storage import ChromaStorage
from kb.query.retrieval_pipeline import RetrievalPipeline
from kb.query.conversation import ConversationManager
from kb.config import Config

_sqlite_instance: Optional[SQLiteStorage] = None
_chroma_instance: Optional[ChromaStorage] = None
_pipeline_instance: Optional[RetrievalPipeline] = None
_conversation_instance: Optional[ConversationManager] = None

def get_config() -> Config:
    return Config()

def get_sqlite() -> SQLiteStorage:
    global _sqlite_instance
    if _sqlite_instance is None:
        config = get_config()
        _sqlite_instance = SQLiteStorage(str(config.data_dir / "db" / "metadata.db"))
    return _sqlite_instance

def get_chroma() -> Optional[ChromaStorage]:
    global _chroma_instance
    if _chroma_instance is None:
        try:
            config = get_config()
            _chroma_instance = ChromaStorage(config.get("storage.persist_directory", str(config.data_dir / "db" / "chroma")))
        except: pass
    return _chroma_instance

def get_pipeline() -> RetrievalPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        config = get_config()
        _pipeline_instance = RetrievalPipeline(config=config)
    return _pipeline_instance

def get_conversation() -> ConversationManager:
    global _conversation_instance
    if _conversation_instance is None:
        _conversation_instance = ConversationManager()
    return _conversation_instance
