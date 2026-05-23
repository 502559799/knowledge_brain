"""存储层测试"""
import os, tempfile, pytest
from kb.storage.sqlite_storage import SQLiteStorage

@pytest.fixture
def storage():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = SQLiteStorage(db_path=db_path)
    yield s
    s.close()
    os.unlink(db_path)

def test_add_and_get_knowledge(storage):
    assert storage.add_knowledge(id="doc1", title="Test Doc", content_type="file", source="/test.pdf")
    item = storage.get_knowledge("doc1")
    assert item is not None
    assert item["title"] == "Test Doc"

def test_list_knowledge(storage):
    storage.add_knowledge(id="d1", title="Doc1", content_type="file", source="/1.pdf")
    storage.add_knowledge(id="d2", title="Doc2", content_type="webpage", source="http://example.com")
    items = storage.list_knowledge()
    assert len(items) == 2

def test_delete_knowledge(storage):
    storage.add_knowledge(id="doc1", title="Test", content_type="file", source="/test.pdf")
    assert storage.delete_knowledge("doc1")
    assert storage.get_knowledge("doc1") is None

def test_tags(storage):
    storage.add_knowledge(id="d1", title="Test", content_type="file", source="/test.pdf")
    storage.link_tag("d1", "python")
    storage.link_tag("d1", "ml")
    tags = storage.get_tags()
    assert len(tags) >= 2

def test_stats(storage):
    storage.add_knowledge(id="d1", title="T1", content_type="file", source="/1.pdf")
    stats = storage.get_stats()
    assert stats["total_items"] == 1

def test_source_exists(storage):
    storage.add_knowledge(id="d1", title="T1", content_type="file", source="/unique.pdf")
    result = storage.source_exists("/unique.pdf", "file")
    assert result is not None

def test_fts_search(storage):
    storage.add_knowledge(id="d1", title="Python机器学习入门", content_type="file", source="/ml.pdf", summary="关于Python和机器学习的基础教程")
    results = storage.fts_search("Python", limit=5)
    assert len(results) >= 1
