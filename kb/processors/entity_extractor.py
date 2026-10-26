"""实体抽取处理器 - LLM结构化抽取构建知识图谱"""
import json, logging, re, sqlite3
from typing import Any, Dict, List, Optional
from kb.processors.base import BaseProcessor, ProcessResult
from kb.config import Config
logger = logging.getLogger(__name__)

class EntityExtractor(BaseProcessor):
    """实体关系抽取器"""
    ENTITY_TYPES = {"person", "concept", "tool", "project", "organization"}
    RELATION_TYPES = {"uses", "belongs_to", "related_to", "depends_on", "created_by"}

    EXTRACTION_PROMPT = """分析以下文档，抽取实体和关系。
标题: {title}
内容: {content}

实体类型: person, concept, tool, project, organization
关系类型: uses, belongs_to, related_to, depends_on, created_by

只返回JSON: {{"entities": [{{"name": "", "type": "", "description": ""}}], "relations": [{{"source": "", "target": "", "type": "", "context": ""}}]}}"""

    def __init__(self, config: Optional[Config] = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or Config()

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        title = kwargs.get("title", "")
        content = str(data) if not isinstance(data, str) else data
        if not content.strip():
            return ProcessResult(success=False, error="内容为空")

        api_key = self.config.get("llm.api_key", "")
        if not api_key:
            return ProcessResult(success=False, error="LLM未配置")

        try:
            import litellm
            model = self.config.get("llm.model", "qwen-plus")
            provider = self.config.get("llm.provider", "dashscope")
            if provider == "dashscope" and "/" not in model:
                model = f"dashscope/{model}"
            prompt = self.EXTRACTION_PROMPT.format(title=title[:500], content=content[:3000])
            resp = litellm.completion(model=model, messages=[{"role": "user", "content": prompt}],
                                       temperature=0.1, max_tokens=500, api_key=api_key)
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", re.sub(r"\s*```$", "", text))
            result = json.loads(text)
            # 过滤
            result["entities"] = [e for e in result.get("entities", []) if e.get("type", "").lower() in self.ENTITY_TYPES]
            result["relations"] = [r for r in result.get("relations", []) if r.get("type", "").lower() in self.RELATION_TYPES]
            return ProcessResult(success=True, data=result,
                                  metadata={"entity_count": len(result["entities"]), "relation_count": len(result["relations"])})
        except Exception as e:
            logger.error(f"实体抽取失败: {e}")
            return ProcessResult(success=False, error=str(e))

    def save_to_db(self, extracted: Dict, knowledge_id: str, db_path: str) -> Dict[str, int]:
        """保存抽取结果到SQLite"""
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            cursor = conn.cursor()
            entity_name_to_id = {}
            entities_saved = 0
            relations_saved = 0
            for entity in extracted.get("entities", []):
                name = entity.get("name", "").strip()
                etype = entity.get("type", "").strip().lower()
                desc = entity.get("description", "").strip()
                if not name or etype not in self.ENTITY_TYPES:
                    continue
                norm_name = name.strip().lower()
                cursor.execute("INSERT INTO entities (name, display_name, type, description) VALUES (?, ?, ?, ?) "
                               "ON CONFLICT(name, type) DO UPDATE SET updated_at = CURRENT_TIMESTAMP",
                               (norm_name, name, etype, desc))
                cursor.execute("SELECT id FROM entities WHERE name = ? AND type = ?", (norm_name, etype))
                row = cursor.fetchone()
                if row:
                    eid = row[0]
                    entity_name_to_id[norm_name] = eid
                    cursor.execute("INSERT OR IGNORE INTO entity_mentions (entity_id, knowledge_id, context) VALUES (?, ?, ?)",
                                   (eid, knowledge_id, desc[:200]))
                    cursor.execute("UPDATE entities SET mention_count=(SELECT COUNT(*) FROM entity_mentions WHERE entity_id=?) WHERE id=?", (eid, eid))
                    entities_saved += 1

            for rel in extracted.get("relations", []):
                src = rel.get("source", "").strip().lower()
                tgt = rel.get("target", "").strip().lower()
                rtype = rel.get("type", "").strip().lower()
                ctx = rel.get("context", "").strip()
                if rtype not in self.RELATION_TYPES:
                    continue
                src_id = entity_name_to_id.get(src)
                tgt_id = entity_name_to_id.get(tgt)
                if not src_id or not tgt_id:
                    continue
                cursor.execute("INSERT INTO entity_relations (source_entity_id, target_entity_id, relation_type) VALUES (?, ?, ?) "
                               "ON CONFLICT(source_entity_id, target_entity_id, relation_type) DO NOTHING",
                               (src_id, tgt_id, rtype))
                cursor.execute("SELECT id FROM entity_relations WHERE source_entity_id=? AND target_entity_id=? AND relation_type=?",
                               (src_id, tgt_id, rtype))
                rrow = cursor.fetchone()
                if rrow:
                    cursor.execute("INSERT OR IGNORE INTO entity_relation_sources (relation_id, knowledge_id, context) VALUES (?, ?, ?)",
                                   (rrow[0], knowledge_id, ctx[:200]))
                    cursor.execute("UPDATE entity_relations SET weight=(SELECT COUNT(*) FROM entity_relation_sources WHERE relation_id=?) WHERE id=?", (rrow[0], rrow[0]))
                    relations_saved += 1
            conn.commit()
            return {"entities_saved": entities_saved, "relations_saved": relations_saved}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
