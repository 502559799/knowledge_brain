"""收集器测试"""
import os, tempfile, pytest
from kb.collectors.file_collector import FileCollector
from kb.collectors.note_collector import NoteCollector

def test_note_collector():
    collector = NoteCollector()
    result = collector.collect("这是一条测试笔记", tags=["test"], title="测试笔记")
    assert result.success
    assert result.word_count > 0

def test_note_empty():
    collector = NoteCollector()
    result = collector.collect("")
    assert not result.success

def test_file_collector_not_found():
    collector = FileCollector()
    result = collector.collect("/nonexistent/file.pdf")
    assert not result.success

def test_file_collector_txt():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("这是一个测试文件的内容\n第二行内容")
        path = f.name
    try:
        collector = FileCollector()
        result = collector.collect(path, tags=["test"])
        assert result.success
        assert result.word_count > 0
    finally:
        os.unlink(path)
