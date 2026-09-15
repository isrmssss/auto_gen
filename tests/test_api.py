from fastapi.testclient import TestClient

from openrd.db.store import reset_store_for_tests
from openrd.engine.bus import reset_bus
from openrd.engine.worker import reset_runtimes
from openrd.server.app import app


def test_api_provider_and_project(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRD_HOME", str(tmp_path))
    monkeypatch.setenv("OPENRD_WORKSPACES", str(tmp_path / "ws"))
    store = reset_store_for_tests(tmp_path / "db.sqlite")
    reset_bus(store)
    reset_runtimes()
    client = TestClient(app)
    assert client.get("/api/health").json()["ok"] is True
    hw = client.get("/api/hw").json()
    assert "ram_available_mb" in hw
    plugins = client.get("/api/plugins").json()
    assert any(p["id"] == "rnd.orchestrator" for p in plugins)
    prov = client.post(
        "/api/providers",
        json={
            "name": "Polza",
            "base_url": "https://polza.ai/api/v1",
            "api_key": "sk-test",
            "roles": {"orchestrator": "openai/gpt-4.1", "coder": "openai/gpt-4.1"},
        },
    ).json()
    assert prov["has_key"] is True
    proj = client.post(
        "/api/projects",
        json={
            "name": "demo",
            "goal": "Beat the naive mean on a toy RMSLE task with a compound method.",
            "provider_id": prov["id"],
            "think_slots": 5,
            "exec_slots": 1,
        },
    ).json()
    assert proj["status"] == "idle"
    assert proj["think_slots"] == 4
    got = client.get(f"/api/projects/{proj['id']}").json()
    assert "goal" in got["memory"]
    tree = client.get(f"/api/projects/{proj['id']}/tree").json()
    assert tree == []
    client.post(
        f"/api/projects/{proj['id']}/steer",
        json={"kind": "steer", "content": "Focus on mid-band error, skip λ-tuning."},
    )
    chat = client.get(f"/api/projects/{proj['id']}/chat").json()
    assert chat
