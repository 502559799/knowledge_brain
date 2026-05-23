# 🧠 Knowledge Brain — 个人知识大脑系统

> 采集、处理、查询与可视化的全栈个人知识管理平台

## ✨ 特性

- **多源采集**: 文件(PDF/MD/TXT)、网页、书签、笔记
- **智能处理**: 文本分块、向量嵌入、3层降级标签提取、实体关系抽取
- **知识图谱**: 实体关系构建、N-hop遍历、AntV G6力导向图可视化
- **智能检索**: 语义搜索 + 关键词搜索 + RAG问答、6阶段检索管道
- **主题聚类**: HDBSCAN无监督聚类 + LLM标签生成 + 旭日图可视化
- **知识百科**: LLM自动合成百科文章，支持[[wiki-link]]跳转
- **可视化**: 仪表盘统计、图谱力导向图、主题旭日图、知识时间线
- **备份恢复**: 本地备份 + 云存储(OSS/S3)
- **双界面**: CLI (`kbrain`) + Web API (FastAPI)

## 🚀 快速开始

```bash
# 安装
pip install -e .

# 初始化
kbrain init

# 采集知识
kbrain collect file add ~/doc.pdf
kbrain collect webpage add https://example.com
kbrain collect note add "重要笔记内容" --tags "ml,ai"

# 搜索
kbrain search rag "什么是机器学习?"
kbrain search keyword "python"

# 知识挖掘
kbrain mine

# 启动Web界面
kbrain web
# 浏览器打开 http://localhost:8765
```

## 📊 可视化功能

| 页面 | 功能 | 技术 |
|------|------|------|
| 仪表盘 | 统计卡片、类型饼图、增长趋势图、标签词云 | ECharts |
| 知识图谱 | 力导向图、拖拽缩放、N-hop展开、类型着色 | AntV G6 |
| 主题地图 | 旭日图展示聚类层级关系 | ECharts |
| 时间线 | 按时间展示知识增长 | React |
| 搜索 | RAG/语义/关键词三模式搜索 | React |
| 百科 | 主题百科浏览、wiki-link跳转 | React |

## 🏗️ 架构

```
Interface (CLI + Web API)
    ↓
Command Layer (init/collect/search/mine/backup)
    ↓
Core Modules
├── Collectors (File/Webpage/Bookmark/Note)
├── Processors (Chunker/Embedder/TagExtractor/EntityExtractor/TopicClusterer)
├── Query (SemanticSearch/KeywordSearch/RAG/RetrievalPipeline/GraphQuery)
    ↓
Storage Layer (SQLite + FTS5 | ChromaDB)
```

## ⚙️ 配置

编辑 `~/.knowledge-brain/config.yaml`:

```yaml
embedding:
  provider: dashscope
  model: text-embedding-v4
  api_key: ${DASHSCOPE_API_KEY}

llm:
  provider: dashscope
  model: qwen-plus
  api_key: ${DASHSCOPE_API_KEY}
```

## 📜 License

MIT
