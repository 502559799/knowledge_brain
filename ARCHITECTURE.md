# Knowledge Brain 架构文档 v0.2.0

> 代号：doubao
> 个人知识大脑系统 — 代码架构与功能架构说明

---

## 1. 系统概览

Knowledge Brain（知识大脑）是一个本地化的个人知识管理系统，支持多源知识采集、智能处理、语义搜索、RAG问答、知识图谱、主题聚类和百科文章自动生成。

**核心能力：**
- 多渠道知识采集（笔记、网页、文件、书签）
- 文档分块与向量嵌入（ChromaDB）
- 全文+语义混合搜索（FTS5 + Embedding）
- RAG检索增强问答（多轮对话）
- 实体抽取与知识图谱（LLM + G6可视化）
- HDBSCAN主题聚类 + 百科文章自动生成
- 定时备份与Web管理界面

---

## 2. 技术栈

| 层次 | 技术选型 |
|------|---------|
| **后端语言** | Python 3.10+ |
| **Web框架** | FastAPI + Uvicorn |
| **结构化存储** | SQLite（FTS5全文搜索、WAL模式） |
| **向量数据库** | ChromaDB（文档级 + Chunk级双集合） |
| **嵌入模型** | DashScope text-embedding-v4（默认）/ OpenAI（可选） |
| **大语言模型** | DashScope qwen-plus（默认）/ OpenAI兼容（LiteLLM代理） |
| **NLP/ML** | HDBSCAN聚类、TF-IDF关键词提取、scikit-learn |
| **CLI框架** | Click |
| **前端** | React 18（CDN/UMD）+ Ant Design 5 + AntV G6 + ECharts 5 |
| **前端编译** | Babel Standalone（浏览器内JSX编译，无需构建工具） |

---

## 3. 项目目录结构

```
kb/
├── __init__.py
├── version.py              # 版本号 (0.2.0)
├── config.py               # 配置管理（YAML + 环境变量展开 + API Key脱敏）
├── cli.py                  # CLI入口（Click命令组）
│
├── collectors/             # 知识采集层（Strategy模式）
│   ├── base.py             #   BaseCollector + CollectResult
│   ├── note_collector.py   #   纯文本笔记采集
│   ├── webpage_collector.py#   网页采集（httpx + readability + markdownify）
│   ├── file_collector.py   #   文件采集
│   └── bookmark_collector.py # 书签采集
│
├── processors/             # 内容处理管线
│   ├── base.py             #   BaseProcessor + ProcessResult
│   ├── chunker.py          #   文本分块（支持中英文，可重叠）
│   ├── embedder.py         #   向量化（批处理，支持多Provider）
│   ├── entity_extractor.py #   实体/关系抽取（LLM驱动，JSON输出）
│   ├── tag_extractor.py    #   标签提取（三级回退：用户>LLM>TF-IDF）
│   ├── topic_clusterer.py  #   主题聚类（HDBSCAN，基于文档嵌入）
│   ├── doc_relation_builder.py # 文档关系构建（余弦相似度 + 共享实体）
│   ├── wiki_generator.py   #   百科文章生成（LLM增强，Markdown格式）
│   └── mining_worker.py    #   异步挖掘调度（串联所有处理步骤）
│
├── storage/                # 存储层
│   ├── sqlite_storage.py   #   SQLite元数据存储（线程安全，WAL，FTS5）
│   └── chroma_storage.py   #   ChromaDB向量存储（文档集+Chunk集双集合）
│
├── query/                  # 查询层
│   ├── models.py           #   数据模型（SearchResult, RAGResult等dataclass）
│   ├── keyword_search.py   #   FTS5关键词搜索
│   ├── semantic_search.py  #   语义搜索（Chunk优先，文档级回退）
│   ├── rag.py              #   RAG问答（会话历史，关键词回退）
│   ├── retrieval_pipeline.py # 检索管线（混合检索+RRF重排+LLM生成）
│   ├── graph_query.py      #   图谱查询（子图展开，关联文档）
│   ├── topic_query.py      #   主题查询
│   ├── recommendation.py   #   推荐引擎（基于文档关系）
│   └── conversation.py     #   多轮会话管理（线程安全，超时清理）
│
├── scheduler/              # 后台调度
│   └── backup_scheduler.py #   定时备份（cron解析，保留策略，优雅关闭）
│
├── commands/               # CLI命令实现
│   ├── init.py             #   初始化
│   ├── collect.py          #   采集命令
│   ├── search.py           #   搜索命令
│   ├── mine.py             #   挖掘命令
│   ├── backup.py           #   备份命令
│   └── manage.py           #   管理命令
│
└── web/                    # Web应用层
    ├── app.py              #   FastAPI应用（lifespan管理，全局异常处理）
    ├── dependencies.py     #   依赖注入（单例模式：存储/搜索/管线/会话）
    ├── static/
    │   └── index.html      #   单页前端（React + Ant Design）
    └── routes/             # API路由
        ├── dashboard.py    #   /stats, /recent, /timeline
        ├── items.py        #   知识项CRUD + chunks + related
        ├── search.py       #   keyword, semantic, rag, pipeline
        ├── collect.py      #   note, webpage采集API
        ├── tags.py         #   标签列表 + 按标签查文档
        ├── graph.py        #   知识图谱 + 实体详情
        ├── topics.py       #   主题列表 + 主题文档 + 重建
        ├── mining.py       #   触发全量挖掘
        ├── wiki.py         #   百科分类与文章
        ├── recommendations.py # 推荐
        ├── backup.py       #   创建/列表/下载/删除/恢复
        └── settings.py     #   配置读写 + 服务状态
```

---

## 4. 功能架构

### 4.1 数据流向图

```
                         ┌─────────────────────┐
                         │   知识输入渠道       │
                         │ 笔记/网页/文件/书签  │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   Collectors 采集层  │
                         │ BaseCollector        │
                         │ (提取内容→存Markdown) │
                         └──────────┬──────────┘
                                    │ CollectResult
                         ┌──────────▼──────────┐
                         │  SQLite 元数据入库   │
                         │  knowledge / tags    │
                         └──────────┬──────────┘
                                    │ doc_id
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
    ┌─────────▼─────────┐  ┌───────▼───────┐  ┌─────────▼─────────┐
    │  Chunker 分块      │  │ EntityExtractor│  │ TagExtractor      │
    │  (重叠窗口分块)    │  │ (LLM实体/关系) │  │ (LLM/TF-IDF标签)  │
    └─────────┬─────────┘  └───────┬───────┘  └─────────┬─────────┘
              │                     │                     │
    ┌─────────▼─────────┐  ┌───────▼───────┐            │
    │  Embedder 向量化  │  │ SQLite        │            │
    │  (batch embedding)│  │ entities/rels │            │
    └─────────┬─────────┘  └───────────────┘            │
              │                                          │
    ┌─────────▼──────────────────────────────────────────▼─┐
    │              ChromaDB 向量存储                        │
    │  documents collection   │   chunks collection         │
    │  (文档级嵌入)            │   (细粒度Chunk嵌入)         │
    └─────────┬────────────────────────────────────────────┘
              │
    ┌─────────▼──────────┐    ┌──────────────────────┐
    │ TopicClusterer     │    │ DocRelationBuilder   │
    │ (HDBSCAN聚类)      │    │ (文档相似度+共现实体) │
    └─────────┬──────────┘    └──────────┬───────────┘
              │                          │
    ┌─────────▼──────────┐    ┌──────────▼───────────┐
    │ WikiGenerator      │    │ document_relations   │
    │ (LLM百科文章生成)  │    │ (双向图存储)         │
    └────────────────────┘    └──────────────────────┘
```

### 4.2 查询流向图

```
                         ┌─────────────────────┐
                         │   用户查询入口       │
                         │ Web UI / CLI        │
                         └──────────┬──────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               │                    │                    │
    ┌──────────▼──────┐  ┌─────────▼────────┐ ┌────────▼───────┐
    │ KeywordSearch   │  │ SemanticSearch   │ │ GraphQuery     │
    │ (FTS5全文搜索)  │  │ (ChromaDB向量)   │ │ (实体关系子图) │
    └──────────┬──────┘  └─────────┬────────┘ └────────────────┘
               │                   │
               └───────┬───────────┘
                       │
            ┌──────────▼───────────┐
            │ RetrievalPipeline    │
            │ RRF重排序 → Context  │
            └──────────┬───────────┘
                       │
            ┌──────────▼───────────┐     ┌────────────────────┐
            │ RAG问答              │◄────┤ ConversationManager│
            │ (上下文+历史→LLM)    │     │ (多轮会话+超时清理) │
            └──────────┬───────────┘     └────────────────────┘
                       │
            ┌──────────▼───────────┐
            │ EnhancedRAGResult    │
            │ answer+sources+conf  │
            └──────────────────────┘
```

---

## 5. 核心模块设计

### 5.1 配置管理 (`config.py`)

**设计原则：** 默认配置 + YAML覆盖 + 环境变量展开 + 运行时可修改

```python
# 默认配置结构（嵌套dict）
DEFAULT_CONFIG = {
    "data_dir": "~/.knowledge-brain",
    "embedding": {"provider": "dashscope", "model": "text-embedding-v4", "api_key": ""},
    "llm": {"provider": "dashscope", "model": "qwen-plus", "api_key": "", "temperature": 0.7},
    "chunking": {"max_chunk_size": 1000, "overlap": 100},
    "storage": {"type": "chroma"},
    "query": {
        "rag": {"top_k": 5, "temperature": 0.7, "context_budget": 4000},
        "pipeline": {"top_k": 10, "rerank_top_k": 5, "context_budget": 4000},
        "conversation": {"max_turns": 20, "timeout_minutes": 30, "history_turns": 5}
    },
    "backup": {"enabled": False, "cron": "0 2 * * *", "retention_days": 30},
    # ...
}
```

**关键特性：**
- `Config.get("llm.api_key")` — 点路径访问
- `Config.set("llm.api_key", "sk-xxx")` — 运行时修改
- `Config.to_safe_dict()` — API Key脱敏后返回（Web界面安全展示）
- `${DASHSCOPE_API_KEY}` — 环境变量自动展开

### 5.2 采集层 (`collectors/`)

**Strategy模式**：`BaseCollector` 定义统一接口，各Collector实现特定来源的内容提取。

```python
@dataclass
class CollectResult:
    success: bool
    file_path: Optional[Path]   # Markdown存储路径
    title: Optional[str]
    word_count: int
    tags: List[str]
    metadata: Dict[str, Any]    # content_type, source, 时间戳等
    content_hash: Optional[str] # SHA-256去重
    summary: Optional[str]
    error: Optional[str]
```

**采集流程：**
1. `_extract_content(source)` — 来源特定内容提取（网页→readability, 笔记→原始文本）
2. `_save_to_file()` — 统一保存为带YAML front matter的Markdown文件
3. 返回标准化 `CollectResult`

### 5.3 处理管线 (`processors/`)

所有处理器继承 `BaseProcessor`，实现 `process(data, **kwargs) -> ProcessResult`。

**`MiningWorker.mine_document()` 异步处理步骤：**

| 步骤 | 处理器 | 输入 | 输出存储 |
|------|--------|------|---------|
| 1 | Chunker | 原文 → 重叠窗口分块 | SQLite chunks表 |
| 2 | Embedder | 文档全文 | SQLite document_embeddings |
| 3 | Embedder | 各Chunk | ChromaDB chunks collection |
| 4 | Embedder | 文档嵌入 | ChromaDB documents collection |
| 5 | EntityExtractor | 标题+内容 | SQLite entities/entity_mentions/entity_relations |
| 6 | TagExtractor | 标题+内容 | SQLite tags/knowledge_tags |
| 7 | DocRelationBuilder | 新文档+已存文档 | SQLite document_relations |

**关键设计决策：**
- 分块嵌入 + 文档嵌入双存储：Chunk搜索更精准，文档级搜索提供全局覆盖
- 增量关系构建：新文档只与已有文档计算相似度（O(n)而非O(n²)）
- 标签三级回退：用户指定 > LLM智能提取 > TF-IDF关键词兜底
- 关系双向存储：`doc_relations` 同时存 (A→B) 和 (B→A)，查询无需UNION

### 5.4 存储层

#### SQLite (`sqlite_storage.py`)

**核心表设计：**

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `knowledge` | 知识项主表 | id(PK), title, content_type, source, summary, user_notes, word_count, collected_at |
| `knowledge_fts` | FTS5全文搜索虚拟表 | content (title + summary + source)，配合au触发器自动更新 |
| `tags` / `knowledge_tags` | 标签系统 | name(PK), count / knowledge_id+tag_name联合唯一 |
| `chunks` | 文档分块 | id(PK), knowledge_id(FK), chunk_index, content, embedding_id |
| `document_embeddings` | 文档级嵌入 | knowledge_id(PK), embedding(JSON文本), model |
| `entities` | 实体 | id(PK), name(唯一), entity_type, description |
| `entity_mentions` | 实体提及 | entity_id+knowledge_id联合主键 |
| `entity_relations` | 实体关系 | source_id+target_id+relation_type联合主键 |
| `document_relations` | 文档关系 | source_id+target_id+relation_type联合主键, score |
| `topic_clusters` / `knowledge_topics` | 主题聚类 | id(PK), label, description, centroid / knowledge_id+cluster_id |
| `wiki_categories` / `wiki_articles` | 百科内容 | id(PK), topic_id, name, content(Markdown) |

**线程安全设计：**
- `threading.Lock` 保护所有写操作
- WAL模式启用（读写不互斥）
- `check_same_thread=False` + 单连接复用
- `@contextmanager _transaction()` 统一提交/回滚/关闭游标

#### ChromaDB (`chroma_storage.py`)

**双集合设计：**

| 集合名 | 存储内容 | 元数据 |
|--------|---------|--------|
| `knowledge_docs` (默认) | 文档级嵌入向量 | knowledge_id, title, content_type |
| `knowledge_chunks` | Chunk级嵌入向量 | knowledge_id, chunk_index, chunk_id |

**关键方法：** `upsert()`处理重复、`add_chunks()`批量分块、`query_chunks()`细粒度检索、`delete_knowledge()`双向清理。

### 5.5 查询层

#### 语义搜索 (`semantic_search.py`)

**Chunk优先策略：**
1. 先在 `knowledge_chunks` 集合检索最相似的chunks
2. 按knowledge_id去重，保留最高分chunk
3. 结果不足时回退到 `knowledge_docs` 文档级检索
4. 返回 `SearchResult(id=knowledge_id, content=chunk_content, metadata={title, content_type}, score)`

#### 检索管线 (`retrieval_pipeline.py`)

**六阶段流程：**
1. **并行检索** — SemanticSearch + KeywordSearch同时执行
2. **去重合并** — 按ID合并两路结果
3. **RRF重排序** — `score = 1/(k+rank+1) + retrieval_score * 0.5`（k=60）
4. **上下文构建** — 取Top-N结果拼接成Context（受context_budget限制）
5. **LLM生成** — 带对话历史的Prompt发送给LLM
6. **结果封装** — 返回 `EnhancedRAGResult`（含answer, sources, confidence, strategy, entities/topics）

#### RAG问答 (`rag.py`)

- 接受注入的 `semantic_search`, `keyword_search`, `conversation_manager`
- 语义搜索无结果时自动回退到关键词搜索
- 对话历史注入LLM上下文（取最近N轮）
- 回答后记录Q&A到会话管理器

#### 会话管理 (`conversation.py`)

**线程安全的内存会话：**
- UUID session_id，最多max_turns轮
- 超时自动过期（默认30分钟无活动）
- 后台定期清理（每5分钟）
- `get_or_create_session()` 支持传入已有session_id续接

### 5.6 Web层

#### 依赖注入 (`dependencies.py`)

**单例模式，避免重复初始化：**

```python
_sqlite_instance = None
_chroma_instance = None
_embedder_instance = None
_semantic_search_instance = None
_keyword_search_instance = None
_pipeline_instance = None
_conversation_instance = None

def get_sqlite() -> SQLiteStorage: ...
def get_chroma() -> ChromaStorage: ...
def get_embedder() -> Embedder: ...
def get_semantic_search() -> SemanticSearch: ...  # 注入chroma + embedder
def get_keyword_search() -> KeywordSearch: ...
def get_pipeline() -> RetrievalPipeline: ...      # 注入两个search后端
def get_conversation() -> ConversationManager: ... # 从config读取参数
def get_config() -> Config: ...
```

#### 应用生命周期 (`app.py`)

```
Startup:
  1. 初始化配置
  2. 启动备份调度器线程（background thread）
  3. 挂载静态文件

Shutdown:
  1. 停止备份调度器（threading.Event信号）
  2. 关闭SQLite连接
  3. 关闭ChromaDB连接
```

#### API路由总览

| 路由组 | 前缀 | 主要端点 |
|--------|------|---------|
| Dashboard | `/api` | GET /stats, /recent, /timeline |
| Items | `/api` | GET/POST/PATCH/DELETE /items, /items/{id}/chunks, /related |
| Search | `/api` | GET /search/keyword, POST /search/semantic, /search/rag, /search/pipeline |
| Collect | `/api` | POST /collect/note, /collect/webpage |
| Tags | `/api` | GET /tags, /tags/{name}/items |
| Graph | `/api` | GET /graph, /graph/entity/{id} |
| Topics | `/api` | GET /topics, /topics/{id}/documents, POST /topics/rebuild |
| Wiki | `/api` | GET /wiki/categories, /wiki/articles/{topic_id} |
| Backup | `/api` | POST /backup/create, GET /backup/list, GET /backup/download/{f}, DELETE /backup/{f} |
| Settings | `/api` | GET/POST /settings, GET /settings/services |
| Health | `/` | GET /health, GET / |

### 5.7 前端架构 (`web/static/index.html`)

**单页应用，零构建工具：**
- React 18 + Babel Standalone（浏览器内JSX转译）
- Ant Design 5 组件库（CDN）
- AntV G6 知识图谱可视化
- ECharts 5 图表（时间线、统计、主题地图）

**页面结构（分组导航）：**

```
概览组:
  📊 仪表盘  — 统计卡片、最近知识、时间线图表、标签云
  🔍 搜索    — 关键词/语义/RAG/管线四种搜索模式，多轮对话

知识组:
  ➕ 添加知识 — 笔记表单 + 网页URL采集表单
  📚 知识库  — 知识列表、详情弹窗（Chunk查看、关联文档、删除）
  📅 时间线  — 按时间顺序展示所有知识

分析组:
  🕸️ 知识图谱 — G6力导向图，节点点击展开实体详情
  📂 主题地图 — ECharts矩形树图，点击查看主题下文档
  📖 百科     — 主题列表，AI生成的百科文章

系统组:
  💾 备份    — 创建备份、列表、下载、删除
  ⚙️ 设置    — API Key配置、Embedding/LLM Provider选择、备份开关
```

**状态指示：** 顶部显示Embedding和LLM服务可用状态（绿点/红点）。

### 5.8 备份调度 (`scheduler/backup_scheduler.py`)

- 独立后台线程，cron表达式指定每日运行时间
- `threading.Event` 实现优雅关闭（等待当前备份完成）
- 自动清理超过 `retention_days` 的旧备份
- 备份内容：`db/` 目录、`1_collect/` 目录、`config.yaml`

---

## 6. 修复和优化记录 (v0.1.0 → v0.2.0)

### 阻断性Bug修复（6项）

| Bug | 影响 | 修复 |
|-----|------|------|
| ChromaDB从未写入数据 | 语义搜索完全不可用 | mining_worker增加chunk/doc双写入 |
| RetrievalPipeline未注入搜索后端 | 管线搜索永远返回空 | dependencies.py正确注入semantic+keyword |
| Config浅拷贝污染DEFAULT_CONFIG | 多实例配置互相干扰 | 改用copy.deepcopy() |
| FTS5缺少UPDATE触发器 | 更新文档后搜索不到 | 新增knowledge_au触发器 |
| Wiki文章从未生成 | 百科页面永远为空 | 新建WikiGenerator，topics重建后触发 |
| 备份调度器从未启动 | 自动备份不运行 | app.py lifespan中调用init_scheduler |

### 中等Bug修复（8项）

- `link_tag()` 重复链接也递增count → 改为仅首次插入时递增
- `chunker.py` 重复的 `"！"` 分隔符 → 删除重复
- `embedder.py` 未知provider抛AttributeError → 改为明确的ValueError
- 会话管理用created_at判断过期 → 改为last_activity，增加线程安全锁
- 推荐查询只查单向关系 → UNION双向查询
- 搜索API不返回metadata → 所有搜索结果统一返回metadata（前端展示标题）
- 设置API返回明文API Key → to_safe_dict()脱敏
- Items API不返回404 → 正确HTTPException(status_code=404)

### 新增功能

- **知识项CRUD API**：PATCH更新、DELETE删除、chunks查询、related查询
- **笔记/网页采集API**：Web端直接添加知识，含去重检测
- **备份管理API**：下载、删除、恢复端点
- **设置更新API**：Web端修改配置并持久化
- **百科生成器**：从主题聚类自动生成Markdown格式百科文章
- **增量关系构建**：新文档只计算与已有文档的关系
- **双集合向量存储**：文档级+Chunk级分离，搜索更精准

### 前端重构

- 全新紫靛粉渐变主题 (#4f46e5 → #7c3aed → #ec4899)
- 分组侧边栏导航（概览/知识/分析/系统）
- 新增页面：添加知识、设置、知识详情弹窗、Chunk查看器
- 修复RAG搜索结果标题显示（metadata）
- 主题图从错误的Sunburst改为Treemap
- 图谱节点点击展开实体详情
- 服务状态实时指示器
- apiFetch统一错误处理

---

## 7. 优化优先级与建议（Roadmap）

### P0 - 核心可靠性
- [ ] 单元测试覆盖核心模块（storage, query, processors）
- [ ] 集成测试（API端点+数据库）
- [ ] 添加日志结构化输出（JSON格式）

### P1 - 性能
- [ ] SQLite连接池（多线程高并发场景）
- [ ] ChromaDB批量嵌入的进度反馈（WebSocket/SSE）
- [ ] 大文档分块的并行嵌入
- [ ] 查询结果缓存（相同query缓存5分钟）

### P2 - 功能增强
- [ ] PDF/EPUB文件采集器
- [ ] 浏览器书签HTML导入
- [ ] Markdown文件直接导入
- [ ] 知识项手动标签编辑界面
- [ ] 全文内容显示与编辑
- [ ] 导出为Markdown/Zip
- [ ] 多用户支持（API Key鉴权）

### P3 - 体验优化
- [ ] 离线/本地嵌入模型（无需API Key即可使用）
- [ ] Dark Mode
- [ ] 知识图谱节点拖动画布
- [ ] 搜索高亮与上下文片段
- [ ] 移动端响应式布局优化
- [ ] 操作快捷键

### P4 - 生态
- [ ] 云备份（OSS/S3）
- [ ] Webhook通知（备份完成、挖掘完成）
- [ ] REST API认证（JWT）
- [ ] Docker一键部署

---

## 8. Mac端安装与验证指南

### 环境要求
- macOS 12+ (Intel/Apple Silicon均支持)
- Python 3.10+（推荐Homebrew安装：`brew install python@3.11`）

### 安装步骤

```bash
# 1. 克隆/进入项目目录
cd /path/to/kb

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -e .

# 可选：安装网页采集依赖
pip install httpx readability-lxml markdownify beautifulsoup4

# 可选：安装HDBSCAN聚类依赖
pip install scikit-learn numpy

# 4. 初始化知识库
kbrain init

# 5. 配置API Key（可选，不配置则部分功能不可用）
# 编辑 ~/.knowledge-brain/config.yaml
# 设置 embedding.api_key 和 llm.api_key

# 6. 启动Web界面
kbrain web
# 打开浏览器访问 http://localhost:8765
```

### 常用CLI命令

```bash
# 添加笔记
kbrain collect note "今天学习了FastAPI的依赖注入系统" --tags 编程 Python

# 采集网页
kbrain collect webpage https://docs.python.org/3/library/asyncio.html

# 搜索
kbrain search keyword "依赖注入"
kbrain search semantic "Python异步编程"
kbrain search rag "FastAPI如何管理数据库连接？"

# 运行全量挖掘（实体抽取、聚类、图谱）
kbrain mine

# 备份
kbrain backup create
kbrain backup list

# 查看统计
kbrain stats
```

### 功能验证清单

| 功能 | 验证方式 | 预期结果 |
|------|---------|---------|
| 服务启动 | `kbrain web` | http://localhost:8765 可访问，仪表盘正常加载 |
| 健康检查 | GET /health | 返回 `{"status":"ok",...}` |
| 添加笔记 | Web界面"添加知识"→输入笔记 | 提示采集成功，知识库列表可见 |
| 关键词搜索 | 搜索页→关键词模式 | 返回匹配结果及标题 |
| 语义搜索 | 配置API Key后用语义模式 | 返回语义相关结果 |
| RAG问答 | 配置API Key后用RAG模式 | 生成AI回答附带来源 |
| 知识图谱 | 图谱页面 | 节点和边正确渲染，点击可展开 |
| 主题聚类 | 分析页→重建主题 | 主题列表显示，百科可查看 |
| 备份 | 系统→备份→创建 | 备份列表出现，可下载 |
| 设置 | 系统→设置→保存 | 配置持久化到config.yaml |
