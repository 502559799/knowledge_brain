"""管道集成测试"""
import pytest
from kb.query.retrieval_pipeline import RetrievalPipeline
from kb.config import Config

def test_pipeline_init():
    pipeline = RetrievalPipeline(config=Config())
    assert pipeline is not None

def test_pipeline_empty_query():
    pipeline = RetrievalPipeline(config=Config())
    with pytest.raises(ValueError):
        pipeline.run("")
