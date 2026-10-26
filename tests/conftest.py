"""All tests use an isolated home; never read credentials or mutate personal data."""
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    import os.path
    original_expand = os.path.expanduser
    monkeypatch.setattr(os.path, "expanduser", lambda path: str(tmp_path) + str(path)[1:] if str(path).startswith("~") else original_expand(path))
    from kb.web import dependencies as deps
    for name in list(vars(deps)):
        if name.endswith('_instance'):
            monkeypatch.setattr(deps, name, None)
    yield
    if deps._sqlite_instance:
        deps._sqlite_instance.close()
    if deps._keyword_search_instance and deps._keyword_search_instance._storage:
        deps._keyword_search_instance._storage.close()
