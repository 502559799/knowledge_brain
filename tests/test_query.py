"""查询测试"""
import pytest
from kb.query.models import SearchResult, RAGResult
from kb.query.conversation import ConversationManager

def test_search_result():
    r = SearchResult(id="test", content="hello", score=0.9)
    assert r.id == "test"
    assert r.score == 0.9

def test_rag_result():
    r = RAGResult(answer="test answer", question="q")
    assert r.answer == "test answer"

def test_conversation_manager():
    cm = ConversationManager()
    sid = cm.create_session()
    cm.add_turn(sid, "user", "hello")
    cm.add_turn(sid, "assistant", "hi")
    history = cm.get_history(sid)
    assert len(history) == 2
