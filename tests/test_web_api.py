"""Web API测试"""
import pytest
from fastapi.testclient import TestClient
from kb.web.app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_stats(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
