"""Wiki百科文章生成器 - 基于主题聚类和LLM生成知识百科"""
import json
import logging
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from kb.config import Config
from kb.processors.base import BaseProcessor, ProcessResult

logger = logging.getLogger(__name__)


class WikiGenerator(BaseProcessor):
    """基于主题聚类和LLM生成Wiki百科文章"""

    def __init__(self, config: Optional[Config] = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or Config()
        self.wiki_cfg = self.config.get("wiki", {})
        self.enabled = self.wiki_cfg.get("enabled", True)

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        try:
            count = self.generate_for_all_topics(kwargs.get("db_path"))
            return ProcessResult(success=True, data={"articles_generated": count})
        except Exception as e:
            return ProcessResult(success=False, error=str(e))

    def generate_for_all_topics(self, db_path: Optional[str] = None) -> int:
        """为所有主题生成百科文章"""
        if not self.enabled:
            logger.info("Wiki generation disabled in config")
            return 0
        if db_path is None:
            db_path = str(self.config.data_dir / "db" / "metadata.db")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, label, description, document_count FROM topic_clusters ORDER BY document_count DESC")
            topics = [dict(r) for r in cursor.fetchall()]
            count = 0
            for topic in topics:
                try:
                    self._generate_for_topic(cursor, conn, topic)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to generate wiki for topic {topic['id']}: {e}")
            return count
        finally:
            conn.close()

    def _generate_for_topic(self, cursor, conn, topic: Dict) -> None:
        topic_id = topic["id"]
        topic_label = topic["label"]

        # Get documents in this topic
        cursor.execute("""SELECT k.id, k.title, k.summary, k.content_type
                          FROM knowledge_topics kt
                          JOIN knowledge k ON kt.knowledge_id = k.id
                          WHERE kt.cluster_id = ?
                          ORDER BY kt.confidence DESC LIMIT 20""", (topic_id,))
        docs = [dict(r) for r in cursor.fetchall()]
        if not docs:
            return

        # Get entities mentioned in these documents
        doc_ids = [d["id"] for d in docs]
        placeholders = ",".join("?" for _ in doc_ids)
        cursor.execute(f"""SELECT DISTINCT e.name, e.display_name, e.type, e.description, COUNT(em.id) as mentions
                           FROM entities e
                           JOIN entity_mentions em ON e.id = em.entity_id
                           WHERE em.knowledge_id IN ({placeholders})
                           GROUP BY e.id
                           ORDER BY mentions DESC LIMIT 15""", doc_ids)
        entities = [dict(r) for r in cursor.fetchall()]

        # Generate category
        category_id = f"cat-{topic_id}"
        category_name = topic_label[:50]
        category_desc = f"包含{len(docs)}篇相关文档的主题分类"

        cursor.execute("INSERT OR REPLACE INTO wiki_categories (category_id, topic_id, name, description, doc_ids, article_count) VALUES (?, ?, ?, ?, ?, 0)",
                       (category_id, topic_id, category_name, category_desc, json.dumps(doc_ids)))

        # Generate main article
        article_id = f"art-{topic_id}-{uuid.uuid4().hex[:8]}"
        article_title = f"{topic_label} - 主题概览"
        article_content = self._build_article_content(topic_label, docs, entities)

        entity_summary = ", ".join(f"{e['display_name']}({e['type']})" for e in entities[:10]) if entities else ""

        cursor.execute("""INSERT OR REPLACE INTO wiki_articles (article_id, topic_id, category_id, title, content, entity_summary, compiled_at)
                          VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                       (article_id, topic_id, category_id, article_title, article_content, entity_summary))

        # Update category article count
        cursor.execute("UPDATE wiki_categories SET article_count = (SELECT COUNT(*) FROM wiki_articles WHERE category_id = ?) WHERE category_id = ?",
                       (category_id, category_id))
        conn.commit()

        # Try to enhance with LLM if available
        self._try_llm_enhance(cursor, conn, topic_id, category_id, docs, entities)

    def _build_article_content(self, topic_label: str, docs: List[Dict], entities: List[Dict]) -> str:
        """Build basic article content without LLM"""
        lines = [f"# {topic_label}\n"]
        lines.append(f"本主题包含 **{len(docs)}** 篇相关文档。\n")

        if entities:
            lines.append("## 核心实体\n")
            type_labels = {"person": "人物", "concept": "概念", "tool": "工具", "project": "项目", "organization": "组织"}
            for ent in entities[:10]:
                tlabel = type_labels.get(ent["type"], ent["type"])
                desc = f" - {ent['description']}" if ent.get("description") else ""
                lines.append(f"- **[[{ent['display_name']}]]** ({tlabel}){desc}")
            lines.append("")

        lines.append("## 相关文档\n")
        for doc in docs[:20]:
            title = doc.get("title", "Untitled")
            summary = doc.get("summary", "")
            dtype = doc.get("content_type", "")
            icon = {"file": "📄", "webpage": "🌐", "bookmark": "🔖", "note": "📝"}.get(dtype, "📄")
            if summary:
                lines.append(f"- {icon} **{title}**\n  {summary[:200]}")
            else:
                lines.append(f"- {icon} **{title}**")
        lines.append("")
        return "\n".join(lines)

    def _try_llm_enhance(self, cursor, conn, topic_id: int, category_id: str, docs: List[Dict], entities: List[Dict]) -> None:
        """Try to enhance wiki article with LLM-generated summary"""
        api_key = self.config.get("llm.api_key", "")
        if not api_key or api_key.startswith("${"):
            return
        try:
            import litellm
            provider = self.config.get("llm.provider", "dashscope")
            model = self.config.get("llm.model", "qwen-plus")
            if provider == "dashscope" and "/" not in model:
                model = f"dashscope/{model}"

            doc_text = "\n".join(f"- {d.get('title', 'Untitled')}: {d.get('summary', '')[:100]}" for d in docs[:10])
            ent_text = ", ".join(e["display_name"] for e in entities[:8]) if entities else "无"

            prompt = f"""请为以下知识主题生成一段200-400字的中文摘要概述，说明该主题的核心内容和关键实体之间的关系。

主题名称: {cursor.execute("SELECT label FROM topic_clusters WHERE id=?", (topic_id,)).fetchone()[0]}
相关文档:
{doc_text}
关键实体: {ent_text}

请直接输出摘要正文，不要包含标题或前缀。"""

            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.wiki_cfg.get("temperature", 0.3),
                max_tokens=600,
                api_key=api_key,
            )
            llm_summary = resp.choices[0].message.content.strip()
            if llm_summary:
                article_id = f"art-{topic_id}-llm-{uuid.uuid4().hex[:8]}"
                cursor.execute("""INSERT OR REPLACE INTO wiki_articles (article_id, topic_id, category_id, title, content, entity_summary, compiled_at)
                                  VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                               (article_id, topic_id, category_id, "AI 主题摘要", llm_summary, ent_text))
                cursor.execute("UPDATE wiki_categories SET article_count = (SELECT COUNT(*) FROM wiki_articles WHERE category_id = ?) WHERE category_id = ?",
                               (category_id, category_id))
                conn.commit()
        except Exception as e:
            logger.debug(f"LLM wiki enhancement skipped: {e}")
