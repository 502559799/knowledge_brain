"""标签提取处理器 - 3层降级策略"""
import logging, re
from collections import Counter
from typing import Any, Dict, List, Optional
from kb.processors.base import BaseProcessor, ProcessResult
from kb.config import Config
logger = logging.getLogger(__name__)

class TagExtractor(BaseProcessor):
    """标签提取: 用户→LLM→TF-IDF 3层降级"""
    def __init__(self, config: Optional[Config] = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or Config()
        self.llm_available = bool(self.config.get("llm.api_key", ""))

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        """提取标签和摘要, 3层降级"""
        content = str(data) if not isinstance(data, str) else data
        title = kwargs.get("title", "")

        # Tier 1: 用户手动提供
        if kwargs.get("tags"):
            return ProcessResult(success=True, data={"tags": kwargs["tags"], "summary": kwargs.get("summary", "")})

        # Tier 2: LLM 提取
        if self.llm_available:
            try:
                result = self._llm_extract(title, content)
                if result.get("tags"):
                    return ProcessResult(success=True, data=result)
            except Exception as e:
                logger.warning(f"LLM标签提取失败: {e}")

        # Tier 3: TF-IDF 内置
        tags = self._tfidf_extract(title, content)
        summary = content[:200] + "..." if len(content) > 200 else content
        return ProcessResult(success=True, data={"tags": tags, "summary": summary})

    def _llm_extract(self, title: str, content: str) -> Dict[str, Any]:
        """LLM 提取标签和摘要"""
        import json
        import litellm
        api_key = self.config.get("llm.api_key", "")
        provider = self.config.get("llm.provider", "dashscope")
        model = self.config.get("llm.model", "qwen-plus")
        if provider == "dashscope":
            model = f"dashscope/{model}" if "/" not in model else model
        elif provider == "openai_compatible":
            model = f"openai/{model}" if "/" not in model else model
        prompt = f"""分析以下文档，提取3-5个标签和1-2句摘要。只返回JSON: {{"tags": [...], "summary": "..."}}

标题: {title}
内容: {content[:2000]}"""

        resp = litellm.completion(model=model, messages=[{"role": "user", "content": prompt}],
                                   temperature=0.1, max_tokens=200, api_key=api_key)
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", re.sub(r"\s*```$", "", text))
        return json.loads(text)

    def _tfidf_extract(self, title: str, content: str, top_k: int = 5) -> List[str]:
        """TF-IDF 关键词提取(标题加权)"""
        # 简单实现: 词频统计
        text = f"{title} {title} {title} {content}"  # 标题3倍权重
        # 中英文分词
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', text.lower())
        # 停用词
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "have", "has", "had",
                     "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
                     "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
                     "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "怎么", "如何"}
        filtered = [w for w in words if w not in stopwords and len(w) >= 2]
        counter = Counter(filtered)
        return [word for word, _ in counter.most_common(top_k)]
