"""Shared retrieval and evidence packing for CLI, RAG and Web pipeline."""
import logging
from dataclasses import replace
from kb.query.models import SearchResult

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(rankings, k=60):
    scores, evidence = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, result in enumerate(ranking, 1):
            if result.id in seen:
                continue
            seen.add(result.id)
            scores[result.id] = scores.get(result.id, 0.0) + 1 / (k + rank)
            evidence.setdefault(result.id, result)
    return [replace(evidence[key], score=scores[key])
            for key in sorted(scores, key=lambda key: (-scores[key], key))]


def retrieve(question, semantic, keyword, tags, top_k):
    if top_k <= 0:
        raise ValueError("top_k 必须大于 0")
    rankings = []
    if semantic is not None:
        try:
            rankings.append(semantic.search(question, tags, top_k))
        except Exception:
            logger.warning("语义检索不可用，继续关键词检索", exc_info=True)
    if keyword is not None:
        try:
            rankings.append(keyword.search(question, top_k, tags=tags) if tags else keyword.search(question, top_k))
        except Exception:
            logger.warning("关键词检索不可用", exc_info=True)
    return reciprocal_rank_fusion(rankings)[:top_k]


def pack_context(results, budget):
    """Budget is in characters, including headers and separators; sources match evidence."""
    parts, sources, used = [], [], 0
    for result in results:
        if not result.content.strip():
            continue
        header = f"[文档{len(sources) + 1}] {result.metadata.get('title') or result.id}\n"
        available = budget - used - len(header) - (1 if parts else 0)
        if available <= 0:
            break
        content = result.content[:available]
        part = header + content
        used += len(part) + (1 if parts else 0)
        parts.append(part)
        sources.append(replace(result, content=content))
    return "\n".join(parts), sources
