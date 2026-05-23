#!/usr/bin/env python3
"""生成测试数据 - 填充知识库以便可视化验证"""
import sys, os, uuid, tempfile
sys.path.insert(0, os.path.dirname(__file__))

from kb.config import Config
from kb.storage.sqlite_storage import SQLiteStorage
from kb.processors.mining_worker import mine_document_async
import json

def main():
    config = Config()
    data_dir = config.data_dir
    db_path = str(data_dir / "db" / "metadata.db")
    
    storage = SQLiteStorage(db_path=db_path)
    
    # 测试知识项
    test_items = [
        {"title": "Python机器学习入门指南", "content_type": "file", "source": "/docs/ml-guide.pdf", 
         "summary": "涵盖监督学习、无监督学习和强化学习的基础教程，使用Python和scikit-learn实现"},
        {"title": "深度学习与神经网络", "content_type": "webpage", "source": "https://deeplearning.ai/tutorial",
         "summary": "介绍CNN、RNN、Transformer等深度学习架构原理与实践"},
        {"title": "自然语言处理实战", "content_type": "file", "source": "/docs/nlp-practice.pdf",
         "summary": "从分词、词向量到大语言模型的NLP完整技术栈"},
        {"title": "数据结构与算法", "content_type": "note", "source": "note",
         "summary": "常见数据结构(链表/树/图)和算法(排序/搜索/动态规划)笔记"},
        {"title": "React前端开发", "content_type": "bookmark", "source": "https://react.dev",
         "summary": "React官方文档，组件化开发、Hooks、状态管理"},
        {"title": "Docker容器化部署", "content_type": "webpage", "source": "https://docs.docker.com",
         "summary": "Docker镜像构建、容器编排、Kubernetes集成"},
        {"title": "知识图谱构建方法", "content_type": "file", "source": "/docs/kg-methods.pdf",
         "summary": "实体识别、关系抽取、图谱存储与查询的完整方法论"},
        {"title": "RAG检索增强生成", "content_type": "note", "source": "note",
         "summary": "向量检索、重排序、上下文构建、LLM答案生成的管道设计"},
        {"title": "微服务架构设计", "content_type": "webpage", "source": "https://microservices.io",
         "summary": "服务拆分、API网关、服务发现、熔断降级等微服务核心模式"},
        {"title": "PostgreSQL高级查询", "content_type": "file", "source": "/docs/pg-advanced.pdf",
         "summary": "窗口函数、CTE递归、JSON查询、全文搜索等高级SQL技巧"},
        {"title": "Git版本控制最佳实践", "content_type": "bookmark", "source": "https://git-scm.com",
         "summary": "分支策略、rebase vs merge、冲突解决、CI/CD集成"},
        {"title": "计算机视觉应用", "content_type": "webpage", "source": "https://opencv.org",
         "summary": "图像分类、目标检测、语义分割、人脸识别等CV应用场景"},
        {"title": "系统设计面试指南", "content_type": "note", "source": "note",
         "summary": "分布式系统、缓存策略、负载均衡、数据库选型等系统设计要点"},
        {"title": "TypeScript类型体操", "content_type": "webpage", "source": "https://typescriptlang.org",
         "summary": "高级类型推导、条件类型、模板字面量类型等TypeScript进阶"},
        {"title": "Redis缓存策略", "content_type": "file", "source": "/docs/redis-cache.pdf",
         "summary": "缓存穿透/击穿/雪崩解决方案，LRU/LFU淘汰策略"},
        {"title": "GraphQL API设计", "content_type": "bookmark", "source": "https://graphql.org",
         "summary": "Schema设计、Resolver编写、N+1问题、Subscription实时推送"},
        {"title": "LLM大语言模型原理", "content_type": "file", "source": "/docs/llm-theory.pdf",
         "summary": "Transformer架构、预训练与微调、RLHF对齐、推理优化"},
        {"title": "Kubernetes运维手册", "content_type": "webpage", "source": "https://kubernetes.io",
         "summary": "Pod管理、Service暴露、HPA自动扩缩容、Helm包管理"},
        {"title": "向量数据库选型", "content_type": "note", "source": "note",
         "summary": "Milvus/Pinecone/Weaviate/Chroma等向量数据库对比分析"},
        {"title": "敏捷开发与Scrum", "content_type": "bookmark", "source": "https://scrum.org",
         "summary": "Sprint规划、每日站会、回顾会议、产品Backlog管理"},
    ]

    for item in test_items:
        doc_id = str(uuid.uuid4())
        storage.add_knowledge(
            id=doc_id,
            title=item["title"],
            content_type=item["content_type"],
            source=item["source"],
            summary=item["summary"],
            word_count=len(item["summary"]),
        )
        # 添加一些标签
        tags_map = {
            "Python": "python", "机器学习": "ml", "深度学习": "dl", "神经网络": "neural-network",
            "NLP": "nlp", "自然语言": "nlp", "算法": "algorithm", "React": "frontend",
            "Docker": "devops", "Kubernetes": "devops", "知识图谱": "kg", "RAG": "rag",
            "微服务": "architecture", "PostgreSQL": "database", "Git": "devops",
            "视觉": "cv", "系统设计": "architecture", "TypeScript": "frontend",
            "Redis": "database", "GraphQL": "api", "LLM": "ai", "向量数据库": "database",
            "敏捷": "management"
        }
        for keyword, tag in tags_map.items():
            if keyword in item["title"] or keyword in item["summary"]:
                storage.link_tag(doc_id, tag)

    # 添加一些实体和关系
    entities_data = [
        {"name": "python", "display_name": "Python", "type": "tool", "description": "流行的编程语言"},
        {"name": "machine learning", "display_name": "机器学习", "type": "concept", "description": "AI的子领域"},
        {"name": "deep learning", "display_name": "深度学习", "type": "concept", "description": "基于神经网络的ML"},
        {"name": "transformer", "display_name": "Transformer", "type": "concept", "description": "注意力机制架构"},
        {"name": "docker", "display_name": "Docker", "type": "tool", "description": "容器化平台"},
        {"name": "kubernetes", "display_name": "Kubernetes", "type": "tool", "description": "容器编排系统"},
        {"name": "react", "display_name": "React", "type": "tool", "description": "前端UI框架"},
        {"name": "rag", "display_name": "RAG", "type": "concept", "description": "检索增强生成"},
        {"name": "knowledge graph", "display_name": "知识图谱", "type": "concept", "description": "结构化知识表示"},
        {"name": "chromadb", "display_name": "ChromaDB", "type": "tool", "description": "向量数据库"},
        {"name": "fastapi", "display_name": "FastAPI", "type": "tool", "description": "Python Web框架"},
        {"name": "numpy", "display_name": "NumPy", "type": "tool", "description": "科学计算库"},
        {"name": "openai", "display_name": "OpenAI", "type": "organization", "description": "AI研究公司"},
        {"name": "hinton", "display_name": "Geoffrey Hinton", "type": "person", "description": "深度学习之父"},
    ]
    
    cursor = storage.conn.cursor()
    entity_ids = {}
    for e in entities_data:
        cursor.execute(
            "INSERT INTO entities (name, display_name, type, description) VALUES (?, ?, ?, ?) ON CONFLICT(name, type) DO UPDATE SET mention_count = mention_count + 1",
            (e["name"], e["display_name"], e["type"], e["description"])
        )
        cursor.execute("SELECT id FROM entities WHERE name = ? AND type = ?", (e["name"], e["type"]))
        row = cursor.fetchone()
        if row:
            entity_ids[e["name"]] = row[0]
    
    # 添加关系
    relations = [
        ("deep learning", "machine learning", "belongs_to"),
        ("machine learning", "python", "uses"),
        ("deep learning", "transformer", "uses"),
        ("rag", "transformer", "depends_on"),
        ("rag", "knowledge graph", "related_to"),
        ("docker", "kubernetes", "related_to"),
        ("kubernetes", "docker", "depends_on"),
        ("transformer", "openai", "created_by"),
        ("deep learning", "hinton", "created_by"),
        ("chromadb", "rag", "related_to"),
        ("machine learning", "numpy", "uses"),
        ("python", "fastapi", "created_by"),
        ("react", "fastapi", "related_to"),
    ]
    for src, tgt, rel_type in relations:
        src_id = entity_ids.get(src)
        tgt_id = entity_ids.get(tgt)
        if src_id and tgt_id:
            cursor.execute(
                "INSERT INTO entity_relations (source_entity_id, target_entity_id, relation_type) VALUES (?, ?, ?) ON CONFLICT(source_entity_id, target_entity_id, relation_type) DO UPDATE SET weight = weight + 1",
                (src_id, tgt_id, rel_type)
            )
    
    # 添加一个示例主题
    cursor.execute("INSERT INTO topic_clusters (label, description, document_count, centroid_embedding) VALUES (?, ?, ?, ?)",
                   ("AI与机器学习", "人工智能和机器学习相关文档", 5, json.dumps([0.1]*128)))
    topic_id = cursor.lastrowid
    cursor.execute("INSERT INTO topic_clusters (label, description, document_count, centroid_embedding) VALUES (?, ?, ?, ?)",
                   ("前端与DevOps", "前端开发和运维相关文档", 4, json.dumps([0.2]*128)))
    topic_id2 = cursor.lastrowid
    
    # 关联一些文档到主题
    items = storage.list_knowledge(limit=20)
    for i, item in enumerate(items):
        tid = topic_id if i < 5 else topic_id2
        cursor.execute("INSERT OR IGNORE INTO knowledge_topics (knowledge_id, cluster_id, confidence) VALUES (?, ?, ?)",
                       (item["id"], tid, 0.9 if i < 5 else 0.8))
    
    # 添加wiki文章
    cursor.execute("INSERT INTO wiki_articles (article_id, topic_id, title, content, compiled_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                   (str(uuid.uuid4()), topic_id, "人工智能与机器学习百科", "人工智能(AI)是计算机科学的重要分支。\n\n机器学习是AI的核心子领域，包括监督学习、无监督学习和强化学习。\n\n深度学习基于[[transformer]]架构，已成为NLP和CV的主流方法。\n\n[[python]]是实现机器学习最流行的语言，配合[[numpy]]等科学计算库。"))
    
    storage.conn.commit()
    storage.close()
    
    stats = SQLiteStorage(db_path=db_path).get_stats()
    print(f"✅ 测试数据生成完成!")
    print(f"   知识项: {stats['total_items']}")
    print(f"   标签: {stats['tag_count']}")
    print(f"   实体: {stats['entity_count']}")
    print(f"   关系: {stats['relation_count']}")
    print(f"   主题: {stats['topic_count']}")
    print()
    print("现在可以启动Web服务查看可视化效果:")
    print("  python3 -m uvicorn kb.web.app:app --port 8765")
    print("  浏览器打开: http://localhost:8765")

if __name__ == "__main__":
    main()
