"""异步知识挖掘Worker - 后台线程执行: 分块→嵌入→ChromaDB→实体抽取→关系发现"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional

from kb.config import Config

logger = logging.getLogger(__name__)
_mining_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kb-mining")


def mine_document_async(knowledge_id: str, title: str, content: str, db_path: str,
                        chroma_path: Optional[str] = None,
                        config_file: Optional[str] = None) -> Future:
    """异步挖掘单文档: 分块→嵌入→ChromaDB存储→实体抽取→关系发现"""
    return _executor.submit(_mine_document, knowledge_id, title, content, db_path, chroma_path, config_file)



def _mine_document(knowledge_id: str, title: str, content: str, db_path: str,
                   chroma_path: Optional[str] = None,
                   config_file: Optional[str] = None) -> None:
    with _mining_lock:
        try:
            config = Config(config_file) if config_file else Config()
            if not chroma_path:
                chroma_path = config.get("storage.persist_directory", str(config.data_dir / "db" / "chroma"))

            # Step 1: 文本分块
            chunks_info = []
            try:
                from kb.processors.chunker import Chunker
                chunker = Chunker(
                    max_chunk_size=config.get("chunking.max_chunk_size", 1000),
                    chunk_overlap=config.get("chunking.chunk_overlap", 100),
                )
                from kb.storage.sqlite_storage import SQLiteStorage
                storage = SQLiteStorage(db_path)
                if not storage.get_knowledge(knowledge_id):
                    storage.close()
                    return
                existing_chunks = storage.get_chunks(knowledge_id)
                if existing_chunks:
                    chunks_info = [{"id": c["id"], "index": c["chunk_index"], "content": c["content"]} for c in existing_chunks]
                else:
                    chunk_result = chunker.process(content or title or "")
                    if chunk_result.success:
                        for ck in chunk_result.data:
                            storage.add_chunk(ck["id"], knowledge_id, ck["index"], ck["content"])
                            chunks_info.append(ck)
                storage.close()
            except Exception as e:
                logger.error(f"[mine] 分块错误: {e}")

            # Step 2: 文档级嵌入 + 存储到SQLite
            doc_embedding = None
            try:
                from kb.processors.embedder import Embedder
                import sqlite3, json
                embedder = Embedder(config=config)
                summary = content[:500] if content else (title or "")
                emb = embedder.embed_single(f"{title} {summary}")
                if emb:
                    doc_embedding = emb
                    conn = sqlite3.connect(db_path)
                    conn.execute("INSERT OR REPLACE INTO document_embeddings (knowledge_id, embedding) VALUES (?, ?)",
                                 (knowledge_id, json.dumps(emb)))
                    conn.commit()
                    conn.close()
                    logger.info(f"[mine] 文档嵌入完成: {knowledge_id[:8]}")
            except Exception as e:
                logger.error(f"[mine] 文档嵌入错误: {e}")

            # Step 3: 文档级向量存入ChromaDB
            if doc_embedding:
                try:
                    from kb.storage.chroma_storage import ChromaStorage
                    chroma = ChromaStorage(path=chroma_path)
                    tags = []
                    try:
                        from kb.storage.sqlite_storage import SQLiteStorage
                        s = SQLiteStorage(db_path)
                        tags = s.get_knowledge_tags(knowledge_id)
                        s.close()
                    except Exception:
                        pass
                    chroma.add_documents(
                        ids=[knowledge_id],
                        embeddings=[doc_embedding],
                        metadatas=[{"title": title or "", "tags": ",".join(tags) if tags else "", "knowledge_id": knowledge_id}],
                        documents=[(content or title or "")[:1000]],
                    )
                    logger.info(f"[mine] ChromaDB文档向量存储完成: {knowledge_id[:8]}")
                except Exception as e:
                    logger.error(f"[mine] ChromaDB存储错误: {e}")

            # Step 4: Chunk级嵌入并存入ChromaDB
            if chunks_info:
                try:
                    from kb.processors.embedder import Embedder
                    from kb.storage.chroma_storage import ChromaStorage
                    embedder = Embedder(config=config)
                    chroma = ChromaStorage(path=chroma_path)
                    batch_size = 10
                    for i in range(0, len(chunks_info), batch_size):
                        batch = chunks_info[i:i + batch_size]
                        texts = [ck["content"] for ck in batch]
                        try:
                            embs = embedder.embed([f"{title}\n{text}" for text in texts])
                            if embs and len(embs) == len(batch):
                                chroma.add_chunks(
                                    ids=[ck["id"] for ck in batch],
                                    embeddings=embs,
                                    metadatas=[{"knowledge_id": knowledge_id, "title": title or "",
                                                "chunk_index": ck["index"]} for ck in batch],
                                    documents=texts,
                                )
                        except Exception as be:
                            logger.error(f"[mine] Chunk batch嵌入错误: {be}")
                    logger.info(f"[mine] Chunk向量存储完成: {knowledge_id[:8]}, {len(chunks_info)} chunks")
                except Exception as e:
                    logger.error(f"[mine] Chunk向量存储错误: {e}")

            # Step 5: 实体抽取
            try:
                from kb.processors.entity_extractor import EntityExtractor
                extractor = EntityExtractor(config=config)
                result = extractor.process(content or title or "", title=title)
                if result.success and result.data:
                    extractor.save_to_db(result.data, knowledge_id, db_path)
                    logger.info(f"[mine] 实体抽取完成: {knowledge_id[:8]}")
            except Exception as e:
                logger.error(f"[mine] 实体抽取错误: {e}")

            # Step 6: 增量关系构建（只对新文档计算相似度，不全量O(n^2)）
            try:
                from kb.processors.doc_relation_builder import DocRelationBuilder
                builder = DocRelationBuilder(config=config)
                builder.build_incremental(knowledge_id, db_path)
                logger.info(f"[mine] 增量关系构建完成: {knowledge_id[:8]}")
            except Exception as e:
                logger.error(f"[mine] 关系构建错误: {e}")

            logger.info(f"[mine] 异步挖掘完成: {knowledge_id[:8]}")
        except Exception as e:
            logger.error(f"[mine] 挖掘异常: {e}", exc_info=True)
