"""向量嵌入处理器"""
import logging
from typing import Any, List, Optional

from kb.config import Config
from kb.processors.base import BaseProcessor, ProcessResult

logger = logging.getLogger(__name__)


class Embedder(BaseProcessor):
    """文档向量嵌入处理器，支持 DashScope / OpenAI / OpenAI兼容接口"""

    def __init__(self, config: Optional[Config] = None, **kwargs):
        super().__init__(**kwargs)
        self.config = config or Config()
        self.provider = self.config.get("embedding.provider", "dashscope")
        self.model = self.config.get("embedding.model", "text-embedding-v4")
        self.api_key = (self.config.get("embedding.api_key", "")
                        or self.config.get("embedding.dashscope.api_key", ""))
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise ValueError("嵌入服务未配置API Key，请在config.yaml中设置embedding.api_key")
        if self.provider == "dashscope":
            import dashscope
            dashscope.api_key = self.api_key
            self._client = "dashscope"
        elif self.provider in ("openai", "openai_compatible"):
            from openai import OpenAI
            base_url = self.config.get("embedding.openai_compatible.base_url", "")
            self._client = OpenAI(api_key=self.api_key, base_url=base_url or None)
        else:
            raise ValueError(f"不支持的嵌入提供商: {self.provider}，支持: dashscope, openai, openai_compatible")
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        """生成文本向量，自动分批处理"""
        if not texts:
            return []
        client = self._get_client()
        # Batch processing to avoid API limits
        batch_size = 20 if self.provider == "dashscope" else 100
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            if client == "dashscope":
                import dashscope
                from dashscope import TextEmbedding
                resp = TextEmbedding.call(model=self.model, input=batch)
                if resp.status_code == 200:
                    all_embeddings.extend(item["embedding"] for item in resp.output["embeddings"])
                else:
                    raise Exception(f"DashScope嵌入失败: {resp.message}")
            else:
                resp = client.embeddings.create(model=self.model, input=batch)
                all_embeddings.extend(item.embedding for item in resp.data)
        return all_embeddings

    def embed_single(self, text: str) -> List[float]:
        result = self.embed([text])
        return result[0] if result else []

    def process(self, data: Any, **kwargs: Any) -> ProcessResult:
        texts = data if isinstance(data, list) else [str(data)]
        try:
            embeddings = self.embed(texts)
            return ProcessResult(success=True, data=embeddings, metadata={"count": len(embeddings)})
        except Exception as e:
            logger.error(f"嵌入处理失败: {e}")
            return ProcessResult(success=False, error=str(e))
