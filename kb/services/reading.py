"""Read saved source text, falling back to recoverable indexed passages."""
from pathlib import Path


def read_item(storage, config, item):
    with storage._lock:
        edited = storage.conn.execute('SELECT content,revision FROM knowledge_content WHERE knowledge_id=?', (item['id'],)).fetchone()
    if edited:
        return {'content': edited['content'], 'content_origin': 'edited', 'complete': True, 'revision': edited['revision']}
    path = Path(item['file_path']).expanduser() if item.get('file_path') else None
    if path and path.resolve().is_relative_to(config.data_dir.resolve()):
        try:
            text = path.read_text(encoding='utf-8')
            if text.startswith('---\n') and '\n---\n' in text:
                text = text.split('\n---\n', 1)[1].lstrip('\n')
            return {'content': text, 'content_origin': 'saved_file', 'complete': True}
        except (OSError, UnicodeError):
            pass
    chunks = storage.get_chunks(item['id'])
    if chunks:
        # Preserve evidence as separate passages: legacy chunk overlap is not necessarily known.
        return {'content': '\n\n'.join(c['content'] for c in chunks),
                'content_origin': 'indexed_passages', 'complete': False}
    return {'content': item.get('summary') or '', 'content_origin': 'summary', 'complete': False}
