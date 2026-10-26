"""SQLite元数据存储 - 结构化存储+FTS5全文搜索+知识图谱"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional


class SQLiteStorage:
    """SQLite元数据存储类"""

    def __init__(self, db_path: str = None) -> None:
        if db_path is None:
            db_path = "~/.knowledge-brain/db/metadata.db"
        expanded = os.path.expanduser(db_path)
        self.db_path = Path(expanded)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        with self._lock:
            cursor = self.conn.cursor()
            try:
                yield cursor
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cursor.close()

    def _init_db(self) -> None:
        with self._transaction() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY, title TEXT, content_type TEXT, source TEXT,
                collected_at TIMESTAMP, summary TEXT, word_count INTEGER DEFAULT 0,
                file_path TEXT, content_hash TEXT, user_notes TEXT DEFAULT '')""")
            c.execute("""CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, count INTEGER DEFAULT 0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS knowledge_tags (knowledge_id TEXT, tag_id INTEGER,
                PRIMARY KEY (knowledge_id, tag_id), FOREIGN KEY (knowledge_id) REFERENCES knowledge(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE)""")
            c.execute("""CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, knowledge_id TEXT, chunk_index INTEGER,
                content TEXT, embedding_id TEXT, FOREIGN KEY (knowledge_id) REFERENCES knowledge(id) ON DELETE CASCADE)""")
            # FTS5 with INSERT, DELETE, UPDATE triggers
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'")
            if c.fetchone() is None:
                c.execute("CREATE VIRTUAL TABLE knowledge_fts USING fts5(title, summary, content='knowledge', content_rowid='rowid')")
                c.execute("CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN INSERT INTO knowledge_fts(rowid, title, summary) VALUES (NEW.rowid, NEW.title, NEW.summary); END")
                c.execute("CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary) VALUES ('delete', OLD.rowid, OLD.title, OLD.summary); END")
                c.execute("CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary) VALUES ('delete', OLD.rowid, OLD.title, OLD.summary); INSERT INTO knowledge_fts(rowid, title, summary) VALUES (NEW.rowid, NEW.title, NEW.summary); END")
                c.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES ('rebuild')")
            # Chunk full-text index, migrated and backfilled once for existing databases.
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone()
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, content='chunks', content_rowid='rowid')")
            c.execute("CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunks_fts(rowid, content) VALUES (NEW.rowid, NEW.content); END")
            c.execute("CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', OLD.rowid, OLD.content); END")
            c.execute("CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', OLD.rowid, OLD.content); INSERT INTO chunks_fts(rowid, content) VALUES (NEW.rowid, NEW.content); END")
            if not exists:
                c.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            # 知识图谱
            c.execute("""CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                display_name TEXT NOT NULL, type TEXT NOT NULL, description TEXT, mention_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(name, type))""")
            c.execute("""CREATE TABLE IF NOT EXISTS entity_mentions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL, knowledge_id TEXT NOT NULL, context TEXT,
                FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE, UNIQUE(entity_id, knowledge_id))""")
            c.execute("""CREATE TABLE IF NOT EXISTS entity_relations (id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_entity_id INTEGER NOT NULL, target_entity_id INTEGER NOT NULL, relation_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE CASCADE, UNIQUE(source_entity_id, target_entity_id, relation_type))""")
            c.execute("""CREATE TABLE IF NOT EXISTS entity_relation_sources (relation_id INTEGER NOT NULL, knowledge_id TEXT NOT NULL, context TEXT,
                PRIMARY KEY (relation_id, knowledge_id), FOREIGN KEY (relation_id) REFERENCES entity_relations(id) ON DELETE CASCADE)""")
            c.execute("""CREATE TABLE IF NOT EXISTS document_embeddings (knowledge_id TEXT PRIMARY KEY, embedding TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (knowledge_id) REFERENCES knowledge(id) ON DELETE CASCADE)""")
            c.execute("""CREATE TABLE IF NOT EXISTS document_relations (id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_knowledge_id TEXT NOT NULL, target_knowledge_id TEXT NOT NULL, relation_type TEXT NOT NULL,
                score REAL NOT NULL, shared_entities TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_knowledge_id, target_knowledge_id, relation_type))""")
            c.execute("""CREATE TABLE IF NOT EXISTS topic_clusters (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT, description TEXT,
                document_count INTEGER DEFAULT 0, centroid_embedding TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            c.execute("""CREATE TABLE IF NOT EXISTS knowledge_topics (knowledge_id TEXT, cluster_id INTEGER, confidence REAL DEFAULT 1.0,
                PRIMARY KEY (knowledge_id, cluster_id))""")
            c.execute("""CREATE TABLE IF NOT EXISTS wiki_categories (category_id TEXT PRIMARY KEY, topic_id INTEGER,
                name TEXT, description TEXT, doc_ids TEXT DEFAULT '[]', article_count INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            c.execute("""CREATE TABLE IF NOT EXISTS wiki_articles (article_id TEXT PRIMARY KEY, topic_id INTEGER,
                category_id TEXT, title TEXT, content TEXT, entity_summary TEXT, staleness_score REAL DEFAULT 0,
                compiled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            c.execute("CREATE TABLE IF NOT EXISTS vector_deletions (knowledge_id TEXT PRIMARY KEY)")
            c.execute("CREATE TABLE IF NOT EXISTS knowledge_content (knowledge_id TEXT PRIMARY KEY REFERENCES knowledge(id) ON DELETE CASCADE, content TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1)")
            c.execute("CREATE TABLE IF NOT EXISTS knowledge_originals (knowledge_id TEXT PRIMARY KEY REFERENCES knowledge(id) ON DELETE CASCADE, file_path TEXT NOT NULL)")
            # 索引
            for idx in ["idx_k_content_type ON knowledge(content_type)", "idx_k_collected_at ON knowledge(collected_at)",
                         "idx_k_source ON knowledge(source, content_type)", "idx_k_content_hash ON knowledge(content_hash)",
                         "idx_chunks_kid ON chunks(knowledge_id)", "idx_tags_name ON tags(name)",
                         "idx_entities_type ON entities(type)", "idx_entities_name ON entities(name)",
                         "idx_em_kid ON entity_mentions(knowledge_id)", "idx_em_eid ON entity_mentions(entity_id)",
                         "idx_er_source ON entity_relations(source_entity_id)", "idx_er_target ON entity_relations(target_entity_id)",
                         "idx_dr_source ON document_relations(source_knowledge_id)",
                         "idx_dr_target ON document_relations(target_knowledge_id)"]:
                c.execute(f"CREATE INDEX IF NOT EXISTS {idx}")

    # --- Knowledge CRUD ---
    def add_knowledge(self, id: str, title: str, content_type: str, source: str,
                      collected_at: str = "", summary: str = "", word_count: int = 0,
                      file_path: str = "", content_hash: str = "", user_notes: str = "") -> bool:
        if not collected_at:
            collected_at = datetime.now().isoformat()
        try:
            with self._transaction() as c:
                c.execute("INSERT OR IGNORE INTO knowledge (id, title, content_type, source, collected_at, summary, word_count, file_path, content_hash, user_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (id, title, content_type, source, collected_at, summary, word_count, file_path, content_hash, user_notes))
            return True
        except Exception:
            return False

    def get_knowledge(self, id: str) -> Optional[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT * FROM knowledge WHERE id = ?", (id,))
                row = c.fetchone()
                return dict(row) if row else None
            finally:
                c.close()

    def list_knowledge(self, content_type: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                if content_type:
                    c.execute("SELECT * FROM knowledge WHERE content_type = ? ORDER BY collected_at DESC LIMIT ? OFFSET ?", (content_type, limit, offset))
                else:
                    c.execute("SELECT * FROM knowledge ORDER BY collected_at DESC LIMIT ? OFFSET ?", (limit, offset))
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def update_knowledge(self, id: str, **kwargs) -> bool:
        """Update knowledge fields (e.g., user_notes, title, summary)"""
        allowed = {"title", "summary", "user_notes"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [id]
        try:
            with self._transaction() as c:
                c.execute(f"UPDATE knowledge SET {set_clause} WHERE id = ?", values)
                return c.rowcount > 0
        except Exception:
            return False

    def delete_knowledge(self, id: str) -> bool:
        try:
            with self._transaction() as c:
                if not c.execute("SELECT 1 FROM knowledge WHERE id=?", (id,)).fetchone():
                    return False
                c.execute("UPDATE tags SET count=MAX(count-1, 0) WHERE id IN (SELECT tag_id FROM knowledge_tags WHERE knowledge_id=?)", (id,))
                c.execute("UPDATE wiki_articles SET staleness_score=1 WHERE topic_id IN (SELECT cluster_id FROM knowledge_topics WHERE knowledge_id=?)", (id,))
                c.execute("DELETE FROM entity_mentions WHERE knowledge_id=?", (id,))
                c.execute("DELETE FROM entity_relation_sources WHERE knowledge_id=?", (id,))
                c.execute("DELETE FROM document_relations WHERE source_knowledge_id=? OR target_knowledge_id=?", (id, id))
                c.execute("DELETE FROM knowledge_topics WHERE knowledge_id=?", (id,))
                c.execute("UPDATE topic_clusters SET document_count=(SELECT COUNT(*) FROM knowledge_topics WHERE cluster_id=topic_clusters.id)")
                c.execute("UPDATE entities SET mention_count=(SELECT COUNT(*) FROM entity_mentions WHERE entity_id=entities.id)")
                c.execute("INSERT OR IGNORE INTO vector_deletions VALUES (?)", (id,))
                c.execute("DELETE FROM knowledge WHERE id = ?", (id,))
                deleted = c.rowcount > 0
            return deleted
        except Exception:
            return False

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT COUNT(*) FROM knowledge")
                total = c.fetchone()[0]
                c.execute("SELECT content_type, COUNT(*) FROM knowledge GROUP BY content_type")
                by_type = {r[0]: r[1] for r in c.fetchall()}
                c.execute("SELECT COUNT(*) FROM tags")
                tag_count = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM entities")
                entity_count = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM entity_relations")
                relation_count = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM topic_clusters")
                topic_count = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = c.fetchone()[0]
                return {"total_items": total, "by_type": by_type, "tag_count": tag_count,
                        "entity_count": entity_count, "relation_count": relation_count,
                        "topic_count": topic_count, "chunk_count": chunk_count}
            finally:
                c.close()

    def source_exists(self, source: str, content_type: str = None) -> Optional[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                if content_type:
                    c.execute("SELECT id, title FROM knowledge WHERE source = ? AND content_type = ?", (source, content_type))
                else:
                    c.execute("SELECT id, title FROM knowledge WHERE source = ?", (source,))
                row = c.fetchone()
                return dict(row) if row else None
            finally:
                c.close()

    def hash_exists(self, content_hash: str, content_type: str = None) -> Optional[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                if content_type:
                    c.execute("SELECT id, title FROM knowledge WHERE content_hash = ? AND content_type = ?", (content_hash, content_type))
                else:
                    c.execute("SELECT id, title FROM knowledge WHERE content_hash = ?", (content_hash,))
                row = c.fetchone()
                return dict(row) if row else None
            finally:
                c.close()

    # --- Tags ---
    def add_tag(self, name: str) -> int:
        with self._transaction() as c:
            c.execute("INSERT OR IGNORE INTO tags (name, count) VALUES (?, 0)", (name,))
            c.execute("SELECT id FROM tags WHERE name = ?", (name,))
            return c.fetchone()[0]

    def link_tag(self, knowledge_id: str, tag_name: str) -> None:
        tag_id = self.add_tag(tag_name)
        with self._transaction() as c:
            # Only increment count if this is a new link
            c.execute("INSERT OR IGNORE INTO knowledge_tags (knowledge_id, tag_id) VALUES (?, ?)", (knowledge_id, tag_id))
            if c.rowcount > 0:
                c.execute("UPDATE tags SET count = count + 1 WHERE id = ?", (tag_id,))

    def unlink_tag(self, knowledge_id: str, tag_name: str) -> None:
        with self._transaction() as c:
            c.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            row = c.fetchone()
            if not row:
                return
            tag_id = row[0]
            c.execute("DELETE FROM knowledge_tags WHERE knowledge_id = ? AND tag_id = ?", (knowledge_id, tag_id))
            if c.rowcount > 0:
                c.execute("UPDATE tags SET count = MAX(count - 1, 0) WHERE id = ?", (tag_id,))

    def get_tags(self) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT id, name, count FROM tags ORDER BY count DESC")
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def get_items_by_tag(self, tag_name: str) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT k.* FROM knowledge k JOIN knowledge_tags kt ON k.id = kt.knowledge_id JOIN tags t ON kt.tag_id = t.id WHERE t.name = ?", (tag_name,))
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def get_knowledge_tags(self, knowledge_id: str) -> List[str]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT t.name FROM tags t JOIN knowledge_tags kt ON t.id = kt.tag_id WHERE kt.knowledge_id = ?", (knowledge_id,))
                return [r[0] for r in c.fetchall()]
            finally:
                c.close()

    # --- Chunks ---
    def add_chunk(self, id: str, knowledge_id: str, chunk_index: int, content: str, embedding_id: str = "") -> bool:
        try:
            with self._transaction() as c:
                c.execute("INSERT OR IGNORE INTO chunks (id, knowledge_id, chunk_index, content, embedding_id) VALUES (?, ?, ?, ?, ?)",
                           (id, knowledge_id, chunk_index, content, embedding_id or None))
            return True
        except Exception:
            return False

    def update_chunk_embedding_id(self, chunk_id: str, embedding_id: str) -> bool:
        try:
            with self._transaction() as c:
                c.execute("UPDATE chunks SET embedding_id = ? WHERE id = ?", (embedding_id, chunk_id))
            return True
        except Exception:
            return False

    def get_chunks(self, knowledge_id: str) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT * FROM chunks WHERE knowledge_id = ? ORDER BY chunk_index", (knowledge_id,))
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def get_all_chunks_with_knowledge(self) -> List[Dict]:
        """Get all chunks joined with knowledge metadata"""
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("""SELECT c.id as chunk_id, c.knowledge_id, c.chunk_index, c.content, c.embedding_id,
                                    k.title, k.content_type, k.source
                             FROM chunks c JOIN knowledge k ON c.knowledge_id = k.id
                             ORDER BY c.knowledge_id, c.chunk_index""")
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def delete_chunks_by_knowledge(self, knowledge_id: str) -> None:
        with self._transaction() as c:
            c.execute("DELETE FROM chunks WHERE knowledge_id = ?", (knowledge_id,))

    # --- Document Embeddings ---
    def set_document_embedding(self, knowledge_id: str, embedding: List[float]) -> bool:
        try:
            with self._transaction() as c:
                c.execute("INSERT OR REPLACE INTO document_embeddings (knowledge_id, embedding) VALUES (?, ?)",
                           (knowledge_id, json.dumps(embedding)))
            return True
        except Exception:
            return False

    def get_document_embedding(self, knowledge_id: str) -> Optional[List[float]]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT embedding FROM document_embeddings WHERE knowledge_id = ?", (knowledge_id,))
                row = c.fetchone()
                return json.loads(row[0]) if row else None
            finally:
                c.close()

    def get_all_document_embeddings(self) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT de.knowledge_id, de.embedding, k.title FROM document_embeddings de JOIN knowledge k ON de.knowledge_id = k.id")
                return [{"knowledge_id": r[0], "embedding": json.loads(r[1]), "title": r[2]} for r in c.fetchall()]
            finally:
                c.close()

    # --- Entities ---
    def upsert_entity(self, name: str, display_name: str, entity_type: str, description: str = "") -> int:
        norm_name = name.strip().lower()
        with self._transaction() as c:
            c.execute("INSERT INTO entities (name, display_name, type, description) VALUES (?, ?, ?, ?) ON CONFLICT(name, type) DO UPDATE SET mention_count = mention_count + 1, updated_at = CURRENT_TIMESTAMP",
                       (norm_name, display_name or name, entity_type, description))
            c.execute("SELECT id FROM entities WHERE name = ? AND type = ?", (norm_name, entity_type))
            return c.fetchone()[0]

    def add_entity_mention(self, entity_id: int, knowledge_id: str, context: str = "") -> None:
        with self._transaction() as c:
            c.execute("INSERT OR IGNORE INTO entity_mentions (entity_id, knowledge_id, context) VALUES (?, ?, ?)",
                       (entity_id, knowledge_id, context))

    def add_entity_relation(self, source_id: int, target_id: int, relation_type: str, weight: float = 1.0, knowledge_id: str = "", context: str = "") -> None:
        with self._transaction() as c:
            c.execute("INSERT OR IGNORE INTO entity_relations (source_entity_id, target_entity_id, relation_type, weight) VALUES (?, ?, ?, ?)",
                       (source_id, target_id, relation_type, weight))
            if knowledge_id:
                c.execute("SELECT id FROM entity_relations WHERE source_entity_id = ? AND target_entity_id = ? AND relation_type = ?",
                           (source_id, target_id, relation_type))
                row = c.fetchone()
                if row:
                    c.execute("INSERT OR IGNORE INTO entity_relation_sources (relation_id, knowledge_id, context) VALUES (?, ?, ?)",
                               (row[0], knowledge_id, context))

    # --- Wiki ---
    def upsert_wiki_category(self, category_id: str, topic_id: int, name: str, description: str = "", doc_ids: Optional[List[str]] = None) -> None:
        with self._transaction() as c:
            c.execute("INSERT OR REPLACE INTO wiki_categories (category_id, topic_id, name, description, doc_ids, article_count) VALUES (?, ?, ?, ?, ?, ?)",
                       (category_id, topic_id, name, description, json.dumps(doc_ids or []), 0))

    def upsert_wiki_article(self, article_id: str, topic_id: int, category_id: str, title: str, content: str, entity_summary: str = "") -> None:
        with self._transaction() as c:
            c.execute("INSERT OR REPLACE INTO wiki_articles (article_id, topic_id, category_id, title, content, entity_summary, compiled_at) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                       (article_id, topic_id, category_id, title, content, entity_summary))
            c.execute("UPDATE wiki_categories SET article_count = (SELECT COUNT(*) FROM wiki_articles WHERE category_id = ?) WHERE category_id = ?",
                       (category_id, category_id))

    # --- Document Relations ---
    def clear_document_relations(self) -> None:
        with self._transaction() as c:
            c.execute("DELETE FROM document_relations")

    def add_document_relation(self, source_id: str, target_id: str, relation_type: str, score: float, shared_entities: Optional[List[str]] = None) -> None:
        with self._transaction() as c:
            c.execute("INSERT OR IGNORE INTO document_relations (source_knowledge_id, target_knowledge_id, relation_type, score, shared_entities) VALUES (?, ?, ?, ?, ?)",
                       (source_id, target_id, relation_type, score, json.dumps(shared_entities) if shared_entities else None))

    # --- Topic Clusters ---
    def clear_topics(self) -> None:
        with self._transaction() as c:
            c.execute("DELETE FROM knowledge_topics")
            c.execute("DELETE FROM topic_clusters")

    def add_topic_cluster(self, label: str, description: str, doc_ids: List[str], centroid_embedding: Optional[List[float]] = None) -> int:
        with self._transaction() as c:
            c.execute("INSERT INTO topic_clusters (label, description, document_count, centroid_embedding) VALUES (?, ?, ?, ?)",
                       (label, description, len(doc_ids), json.dumps(centroid_embedding) if centroid_embedding else None))
            cluster_id = c.lastrowid
            for did in doc_ids:
                c.execute("INSERT OR IGNORE INTO knowledge_topics (knowledge_id, cluster_id, confidence) VALUES (?, ?, 1.0)", (did, cluster_id))
            return cluster_id

    # --- FTS Search ---
    def search_metadata(self, ids: List[str], tags: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Batch authoritative metadata lookup; tag filters use AND semantics."""
        found = {}
        with self._lock:
            for start in range(0, len(ids), 400):
                batch = ids[start:start + 400]
                placeholders = ",".join("?" for _ in batch)
                if not batch:
                    continue
                sql = f"SELECT k.* FROM knowledge k WHERE k.id IN ({placeholders}) AND NOT EXISTS (SELECT 1 FROM vector_deletions vd WHERE vd.knowledge_id=k.id)"
                params = list(batch)
                for tag in tags or []:
                    sql += " AND EXISTS (SELECT 1 FROM knowledge_tags kt JOIN tags t ON t.id=kt.tag_id WHERE kt.knowledge_id=k.id AND t.name=?)"
                    params.append(tag)
                found.update({r["id"]: dict(r) for r in self.conn.execute(sql, params)})
        return found

    @staticmethod
    def tag_predicate(tags=None, tag_mode="and"):
        tags = list(dict.fromkeys(t.strip() for t in tags or [] if t.strip()))
        if not tags:
            return "", []
        if tag_mode not in ("and", "or"):
            raise ValueError("Invalid tag mode")
        exists = "EXISTS (SELECT 1 FROM knowledge_tags kt JOIN tags t ON t.id=kt.tag_id WHERE kt.knowledge_id=k.id AND t.name=?)"
        return " AND (" + (" AND " if tag_mode == "and" else " OR ").join([exists]*len(tags)) + ")", tags

    def list_filtered_knowledge(self, content_type=None, tags=None, tag_mode="and", limit=50, offset=0):
        clause, params = self.tag_predicate(tags, tag_mode)
        if content_type:
            clause += " AND k.content_type=?"
            params.append(content_type)
        with self._lock:
            rows = self.conn.execute("SELECT k.* FROM knowledge k WHERE 1=1" + clause +
                                     " ORDER BY k.collected_at DESC, k.id LIMIT ? OFFSET ?", [*params, limit, offset])
            return [dict(row) for row in rows]

    def fts_search(self, query: str, limit: int = 20, tags: Optional[List[str]] = None, tag_mode: str = "and", content_type: Optional[str] = None) -> List[Dict]:
        """Search both full passages and document metadata with literal user input."""
        if not query.strip() or limit <= 0:
            return []
        import re
        tokens = re.findall(r"\w+", query, re.UNICODE)
        if not tokens:
            return []
        match = " OR ".join('"' + token + '"' for token in tokens)
        filters, filter_params = self.tag_predicate(tags, tag_mode)
        if content_type:
            filters += " AND k.content_type=?"
            filter_params.append(content_type)
        with self._lock:
            rows = self.conn.execute(
                "SELECT k.*, c.id AS chunk_id, c.content AS matched_content, bm25(chunks_fts) AS rank "
                "FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid "
                "JOIN knowledge k ON k.id=c.knowledge_id WHERE chunks_fts MATCH ?" + filters +
                " ORDER BY rank LIMIT ?", [match, *filter_params, limit * 4]).fetchall()
            docs = self.conn.execute(
                "SELECT k.*, k.summary AS matched_content, bm25(knowledge_fts) AS rank "
                "FROM knowledge_fts JOIN knowledge k ON k.rowid=knowledge_fts.rowid "
                "WHERE knowledge_fts MATCH ?" + filters + " ORDER BY rank LIMIT ?",
                [match, *filter_params, limit]).fetchall()
            # Chinese substring fallback: unicode61 does not segment Chinese words.
            if not rows and not docs:
                pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                rows = self.conn.execute(
                    "SELECT k.*, c.id AS chunk_id, c.content AS matched_content FROM chunks c "
                    "JOIN knowledge k ON k.id=c.knowledge_id WHERE c.content LIKE ? ESCAPE '\\'" + filters + " LIMIT ?",
                    [pattern, *filter_params, limit * 4]).fetchall()
                docs = self.conn.execute(
                    "SELECT k.*, k.summary AS matched_content FROM knowledge k "
                    "WHERE (k.title LIKE ? ESCAPE '\\' OR k.summary LIKE ? ESCAPE '\\')" + filters + " LIMIT ?",
                    [pattern, pattern, *filter_params, limit]).fetchall()
            result, seen = [], set()
            for row in [*rows, *docs]:
                if row["id"] not in seen:
                    result.append(dict(row))
                    seen.add(row["id"])
                if len(result) >= limit:
                    break
            return result

    # --- Dashboard ---
    def get_timeline(self, days: int = 30) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT date(collected_at) as date, COUNT(*) as count FROM knowledge WHERE collected_at >= date('now', ?) GROUP BY date(collected_at) ORDER BY date",
                           (f"-{days} days",))
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def get_recent(self, limit: int = 10) -> List[Dict]:
        with self._lock:
            c = self.conn.cursor()
            try:
                c.execute("SELECT id, title, content_type, collected_at FROM knowledge ORDER BY collected_at DESC LIMIT ?", (limit,))
                return [dict(r) for r in c.fetchall()]
            finally:
                c.close()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
