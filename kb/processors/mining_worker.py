"""异步知识挖掘Worker - 后台线程执行"""
import logging, threading
from typing import Optional
from kb.config import Config
logger = logging.getLogger(__name__)
_mining_lock = threading.Lock()

def mine_document_async(knowledge_id: str, title: str, content: str, db_path: str, config_file: Optional[str] = None) -> None:
    """异步挖掘单文档: 实体抽取→嵌入→关系发现"""
    thread = threading.Thread(target=_mine_document, args=(knowledge_id, title, content, db_path, config_file), daemon=True, name=f"mine-{knowledge_id[:8]}")
    thread.start()

def _mine_document(knowledge_id: str, title: str, content: str, db_path: str, config_file: Optional[str] = None) -> None:
    with _mining_lock:
        try:
            config = Config(config_file) if config_file else Config()
            # Step 1: 实体抽取
            try:
                from kb.processors.entity_extractor import EntityExtractor
                extractor = EntityExtractor(config=config)
                result = extractor.process(content, title=title)
                if result.success and result.data:
                    extractor.save_to_db(result.data, knowledge_id, db_path)
                    logger.info(f"[mine] 实体抽取完成: {knowledge_id[:8]}")
            except Exception as e:
                logger.error(f"[mine] 实体抽取错误: {e}")

            # Step 2: 文档嵌入
            try:
                from kb.processors.embedder import Embedder
                import sqlite3, json
                embedder = Embedder(config=config)
                summary = content[:500] if content else ""
                emb = embedder.embed_single(f"{title} {summary}")
                if emb:
                    conn = sqlite3.connect(db_path)
                    emb_blob = json.dumps(emb).encode("utf-8")
                    conn.execute("INSERT OR REPLACE INTO document_embeddings (knowledge_id, embedding) VALUES (?, ?)", (knowledge_id, json.dumps(emb)))
                    conn.commit()
                    conn.close()
                    logger.info(f"[mine] 嵌入生成完成: {knowledge_id[:8]}")
            except Exception as e:
                logger.error(f"[mine] 嵌入错误: {e}")

            # Step 3: 文档关系
            try:
                from kb.processors.doc_relation_builder import DocRelationBuilder
                builder = DocRelationBuilder(config=config)
                builder.build_all(db_path)
            except Exception as e:
                logger.error(f"[mine] 关系构建错误: {e}")

            logger.info(f"[mine] 异步挖掘完成: {knowledge_id[:8]}")
        except Exception as e:
            logger.error(f"[mine] 挖掘异常: {e}")
