"""处理器测试"""
import pytest
from kb.processors.chunker import Chunker
from kb.processors.tag_extractor import TagExtractor

def test_chunker_short():
    chunker = Chunker(max_chunk_size=1000)
    result = chunker.process("短文本内容")
    assert result.success
    assert len(result.data) == 1

def test_chunker_long():
    chunker = Chunker(max_chunk_size=100, chunk_overlap=20)
    long_text = "这是一个测试。" * 50
    result = chunker.process(long_text)
    assert result.success
    assert len(result.data) > 1

def test_chunker_empty():
    chunker = Chunker()
    result = chunker.process("")
    assert not result.success

def test_tag_extractor_user_provided():
    extractor = TagExtractor()
    result = extractor.process("内容", tags=["user_tag"])
    assert result.success
    assert "user_tag" in result.data["tags"]

def test_tag_extractor_tfidf():
    extractor = TagExtractor()
    result = extractor.process("Python机器学习是人工智能的重要分支。深度学习和自然语言处理是机器学习的子领域。", title="Python机器学习")
    assert result.success
    assert len(result.data["tags"]) > 0
