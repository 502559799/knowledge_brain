"""Offline reproducible FTS latency and chunk-count benchmark.
Run: PYTHONDONTWRITEBYTECODE=1 python3 -m benchmarks.retrieval
"""
import json
import statistics
import tempfile
import time
from pathlib import Path
from kb.processors.chunker import Chunker
from kb.storage.sqlite_storage import SQLiteStorage


def main():
    with tempfile.TemporaryDirectory() as root:
        with SQLiteStorage(str(Path(root) / 'benchmark.db')) as db:
            with db._transaction() as cursor:
                cursor.executemany('INSERT INTO knowledge(id,title,content_type,source,summary) VALUES (?,?,?,?,?)',
                    [(str(i), f'document {i}', 'note', 'note', '') for i in range(2000)])
                cursor.executemany('INSERT INTO chunks(id,knowledge_id,chunk_index,content) VALUES (?,?,?,?)',
                    [(str(i), str(i), 0, f'Knowledge retrieval benchmark topic{i} ' + 'context '*100) for i in range(2000)])
            times = []
            for i in range(100):
                start = time.perf_counter()
                results = db.fts_search(f'topic{i}', 5)
                times.append((time.perf_counter() - start)*1000)
                assert results[0]['id'] == str(i)
            print(json.dumps({'documents': 2000, 'queries': 100, 'exact_match_hits': 100,
                'fts_median_ms': round(statistics.median(times), 3),
                'fts_p95_ms': round(sorted(times)[94], 3),
                'chunks_for_200_chars_size100_overlap20': len(Chunker(100, 20).chunk('x'*200))}, indent=2))


if __name__ == '__main__':
    main()
