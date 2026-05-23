"""SQLite元数据存储 - 结构化存储+FTS5全文搜索+知识图谱"""
import json, os, sqlite3
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
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Cursor, None, None]:
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
            # FTS5
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'")
            if c.fetchone() is None:
                c.execute("CREATE VIRTUAL TABLE knowledge_fts USING fts5(title, summary, content='knowledge', content_rowid='rowid')")
                c.execute("CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN INSERT INTO knowledge_fts(rowid, title, summary) VALUES (NEW.rowid, NEW.title, NEW.summary); END")
                c.execute("CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN INSERT INTO knowledge_fts(knowledge_fts, rowid, title, summary) VALUES ('delete', OLD.rowid, OLD.title, OLD.summary); END")
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
            c.execute("""CREATE TABLE IF NOT EXISTS document_embeddings (knowledge_id TEXT PRIMARY KEY, embedding BLOB NOT NULL,
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
            # 索引
            for idx in ["idx_k_content_type ON knowledge(content_type)", "idx_k_collected_at ON knowledge(collected_at)",
                         "idx_k_source ON knowledge(source, content_type)", "idx_k_content_hash ON knowledge(content_hash)",
                         "idx_chunks_kid ON chunks(knowledge_id)", "idx_tags_name ON tags(name)",
                         "idx_entities_type ON entities(type)", "idx_entities_name ON entities(name)",
                         "idx_em_kid ON entity_mentions(knowledge_id)", "idx_em_eid ON entity_mentions(entity_id)",
                         "idx_er_source ON entity_relations(source_entity_id)", "idx_er_target ON entity_relations(target_entity_id)",
                         "idx_dr_source ON document_relations(source_knowledge_id)"]:
                c.execute(f"CREATE INDEX IF NOT EXISTS {idx}")

    # --- Knowledge CRUD ---
    def add_knowledge(self, id: str, title: str, content_type: str, source: str, collected_at: str = "", summary: str = "", word_count: int = 0, file_path: str = "", content_hash: str = "") -> bool:
        if not collected_at: collected_at = datetime.now().isoformat()
        try:
            with self._transaction() as c:
                c.execute("INSERT OR IGNORE INTO knowledge (id, title, content_type, source, collected_at, summary, word_count, file_path, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (id, title, content_type, source, collected_at, summary, word_count, file_path, content_hash))
            return True
        except Exception: return False

    def get_knowledge(self, id: str) -> Optional[Dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM knowledge WHERE id = ?", (id,))
        row = c.fetchone()
        c.close()
        return dict(row) if row else None

    def list_knowledge(self, content_type: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        c = self.conn.cursor()
        if content_type:
            c.execute("SELECT * FROM knowledge WHERE content_type = ? ORDER BY collected_at DESC LIMIT ? OFFSET ?", (content_type, limit, offset))
        else:
            c.execute("SELECT * FROM knowledge ORDER BY collected_at DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    def delete_knowledge(self, id: str) -> bool:
        try:
            with self._transaction() as c:
                c.execute("DELETE FROM knowledge WHERE id = ?", (id,))
            return True
        except Exception: return False

    def get_stats(self) -> Dict[str, Any]:
        c = self.conn.cursor()
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
        c.close()
        return {"total_items": total, "by_type": by_type, "tag_count": tag_count, "entity_count": entity_count, "relation_count": relation_count, "topic_count": topic_count}

    def source_exists(self, source: str, content_type: str = None) -> Optional[Dict]:
        c = self.conn.cursor()
        if content_type:
            c.execute("SELECT id, title FROM knowledge WHERE source = ? AND content_type = ?", (source, content_type))
        else:
            c.execute("SELECT id, title FROM knowledge WHERE source = ?", (source,))
        row = c.fetchone()
        c.close()
        return dict(row) if row else None

    def hash_exists(self, content_hash: str, content_type: str = None) -> Optional[Dict]:
        c = self.conn.cursor()
        if content_type:
            c.execute("SELECT id, title FROM knowledge WHERE content_hash = ? AND content_type = ?", (content_hash, content_type))
        else:
            c.execute("SELECT id, title FROM knowledge WHERE content_hash = ?", (content_hash,))
        row = c.fetchone()
        c.close()
        return dict(row) if row else None

    # --- Tags ---
    def add_tag(self, name: str) -> int:
        with self._transaction() as c:
            c.execute("INSERT OR IGNORE INTO tags (name, count) VALUES (?, 0)", (name,))
            c.execute("SELECT id FROM tags WHERE name = ?", (name,))
            return c.fetchone()[0]

    def link_tag(self, knowledge_id: str, tag_name: str) -> None:
        tag_id = self.add_tag(tag_name)
        with self._transaction() as c:
            c.execute("INSERT OR IGNORE INTO knowledge_tags (knowledge_id, tag_id) VALUES (?, ?)", (knowledge_id, tag_id))
            c.execute("UPDATE tags SET count = count + 1 WHERE id = ?", (tag_id,))

    def get_tags(self) -> List[Dict]:
        c = self.conn.cursor()
        c.execute("SELECT id, name, count FROM tags ORDER BY count DESC")
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    def get_items_by_tag(self, tag_name: str) -> List[Dict]:
        c = self.conn.cursor()
        c.execute("SELECT k.* FROM knowledge k JOIN knowledge_tags kt ON k.id = kt.knowledge_id JOIN tags t ON kt.tag_id = t.id WHERE t.name = ?", (tag_name,))
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    # --- Chunks ---
    def add_chunk(self, id: str, knowledge_id: str, chunk_index: int, content: str) -> bool:
        try:
            with self._transaction() as c:
                c.execute("INSERT OR IGNORE INTO chunks (id, knowledge_id, chunk_index, content) VALUES (?, ?, ?, ?)", (id, knowledge_id, chunk_index, content))
            return True
        except Exception: return False

    def get_chunks(self, knowledge_id: str) -> List[Dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM chunks WHERE knowledge_id = ? ORDER BY chunk_index", (knowledge_id,))
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    # --- FTS Search ---
    def fts_search(self, query: str, limit: int = 20) -> List[Dict]:
        c = self.conn.cursor()
        try:
            # 尝试FTS5 MATCH搜索
            c.execute("SELECT k.* FROM knowledge_fts f JOIN knowledge k ON k.rowid = f.rowid WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?", (query, limit))
            rows = [dict(r) for r in c.fetchall()]
            if rows:
                c.close()
                return rows
        except Exception:
            pass
        # 降级到LIKE搜索(对中文更友好)
        c.execute("SELECT * FROM knowledge WHERE title LIKE ? OR summary LIKE ? ORDER BY collected_at DESC LIMIT ?", (f'%{query}%', f'%{query}%', limit))
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    # --- Dashboard ---
    def get_timeline(self, days: int = 30) -> List[Dict]:
        c = self.conn.cursor()
        c.execute("SELECT date(collected_at) as date, COUNT(*) as count FROM knowledge WHERE collected_at >= date('now', ?) GROUP BY date(collected_at) ORDER BY date", (f"-{days} days",))
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    def get_recent(self, limit: int = 10) -> List[Dict]:
        c = self.conn.cursor()
        c.execute("SELECT id, title, content_type, collected_at FROM knowledge ORDER BY collected_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
        c.close()
        return rows

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
