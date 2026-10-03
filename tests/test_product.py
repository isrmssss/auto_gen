from pathlib import Path

from fastapi.testclient import TestClient

from openrd.core.context import Context
from openrd.db.store import reset_store_for_tests
from openrd.engine.bus import reset_bus
from openrd.engine.worker import ProjectRuntime, reset_runtimes
from openrd.plugins.embed_local import EmbedService
from openrd.plugins.memory_archive import ArchiveService
from openrd.plugins.memory_compiler import Compiler
from openrd.plugins.memory_core import CoreMemory
from openrd.plugins.rnd_funnel import Funnel
from openrd.server.app import app


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRD_HOME", str(tmp_path))
    monkeypatch.setenv("OPENRD_WORKSPACES", str(tmp_path / "ws"))
    store = reset_store_for_tests(tmp_path / "db.sqlite")
    reset_bus(store)
    reset_runtimes()
    return TestClient(app), store


def test_create_prompt_differs_from_goal_and_file_roles(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    proj = client.post(
        "/api/projects",
        json={
            "name": "hack",
            "prompt": "Kaggle tabular contest with noisy labels",
            "goal": "beat RMSLE 0.12",
            "kpi": {"primary": "rmsle", "higher_is_better": False},
            "think_slots": 1,
        },
    ).json()
    assert proj["prompt"] == "Kaggle tabular contest with noisy labels"
    assert proj["goal"] == "beat RMSLE 0.12"
    assert proj["prompt"] != proj["goal"]
    assert proj["kpi"]["primary"] == "rmsle"
    assert proj["kpi"]["higher_is_better"] is False

    pid = proj["id"]
    inp = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("train.csv", b"a,b\n1,2\n", "text/csv")},
        data={"role": "input"},
    ).json()
    out = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("ckpt.bin", b"CKPT", "application/octet-stream")},
        data={"role": "output"},
    ).json()
    extra = client.post(
        f"/api/projects/{pid}/artifacts",
        files={"file": ("paper.md", b"# Wasserstein\nUse OT instead of L2.\n", "text/markdown")},
        data={"role": "extra", "prompt": "check this idea"},
    ).json()
    assert inp["role"] == "input"
    assert out["role"] == "output"
    assert extra["role"] == "extra"
    assert extra.get("hypothesis_id")
    hyps = client.get(f"/api/projects/{pid}/hypotheses").json()
    queued = [h for h in hyps if h["id"] == extra["hypothesis_id"]]
    assert queued and queued[0]["status"] == "queued"
    assert "check this idea" in queued[0]["text"]
    tree = client.get(f"/api/projects/{pid}/tree").json()
    hyp_nodes = [n for n in tree if n["kind"] == "hypothesis"]
    assert hyp_nodes and hyp_nodes[0]["status"] == "queued"
    assert "check this idea" in (hyp_nodes[0].get("title") or "")
    listed = client.get(f"/api/projects/{pid}/artifacts").json()
    roles = {a["filename"]: a["role"] for a in listed}
    assert roles["train.csv"] == "input"
    assert roles["ckpt.bin"] == "output"
    assert roles["paper.md"] == "extra"
    ws = Path(proj["workspace_path"])
    assert (ws / "inputs" / "train.csv").is_file()
    assert (ws / "outputs" / "ckpt.bin").is_file()
    assert (ws / "extras" / "paper.md").is_file()


def test_secrets_api_hides_value_and_redacts_brief(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    proj = client.post(
        "/api/projects",
        json={"name": "sec", "goal": "keep tokens small", "prompt": "research OT"},
    ).json()
    pid = proj["id"]
    secret_val = "SUPER_SECRET_TOKEN_9f3a"
    put = client.post(
        f"/api/projects/{pid}/secrets",
        json={"name": "kaggle_key", "value": secret_val, "note": "kaggle api"},
    ).json()
    assert put["name"] == "kaggle_key"
    assert put["has_value"] is True
    assert "value" not in put
    listed = client.get(f"/api/projects/{pid}/secrets").json()
    assert listed[0]["name"] == "kaggle_key"
    assert "SUPER_SECRET" not in str(listed)
    assert listed[0].get("value") is None

    store.patch_memory(pid, "open_questions", f"user pasted {secret_val} by mistake")
    archive = ArchiveService()
    archive.bind(pid, EmbedService())
    core = CoreMemory()
    core.bind(pid)
    ctx = Context()
    ctx.provide("memory_core", core)
    ctx.provide("archive", archive)
    ctx.extras["manifests"] = {}
    compiler = Compiler()
    compiler.bind(ctx, pid)
    brief = compiler.brief("ideate", f"also {secret_val}")
    assert secret_val not in brief
    assert "[secret:kaggle_key]" in brief


def test_asks_block_only_dependents(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    proj = store.create_project(
        {"name": "j", "goal": "g", "prompt": "p", "workspace_path": str(tmp_path / "w")}
    )
    pid = proj["id"]
    j1 = store.add_job({"project_id": pid, "kind": "search", "title": "lit"})
    j2 = store.add_job({"project_id": pid, "kind": "denoise", "title": "noise"})
    ask = store.add_ask(
        {
            "project_id": pid,
            "kind": "access",
            "question": "need dataset password",
            "blocked_job_ids": [j2["id"]],
        }
    )
    store.update_job(j2["id"], blocked_by=ask["id"], status="blocked")
    runnable = store.list_runnable_jobs(pid)
    ids = {j["id"] for j in runnable}
    assert j1["id"] in ids
    assert j2["id"] not in ids
    store.answer_ask(ask["id"], "granted")
    runnable2 = store.list_runnable_jobs(pid)
    assert j2["id"] in {j["id"] for j in runnable2}
    j3 = store.add_job({"project_id": pid, "kind": "fetch", "title": "pdf"})
    ask2 = store.add_ask(
        {"project_id": pid, "kind": "secret", "question": "api?", "blocked_job_ids": [j3["id"]]}
    )
    store.update_job(j3["id"], blocked_by=ask2["id"], status="blocked")
    store.decline_ask(ask2["id"])
    assert store.get_job(j3["id"])["status"] == "cancelled"
    still = {j["id"] for j in store.list_runnable_jobs(pid)}
    assert j3["id"] not in still


def test_funnel_short_path_vs_research_and_noise_job(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    letter = store.create_project(
        {
            "name": "letter",
            "prompt": "древнее письмо, на вход фото",
            "goal": "получить расшифрованный текст на русском",
            "workspace_path": str(tmp_path / "letter"),
        }
    )
    store.add_artifact(
        {
            "project_id": letter["id"],
            "filename": "letter.jpg",
            "path": str(tmp_path / "letter.jpg"),
            "role": "input",
            "status": "stored",
        }
    )
    funnel = Funnel()
    funnel.bind(Context(), letter["id"])
    formal = funnel.formalize(store.get_project(letter["id"]))
    assert formal["skip_math"] is True
    assert formal["short_path"] is True
    assert funnel.score_domains(store.get_project(letter["id"])) == []

    tab = store.create_project(
        {
            "name": "tab",
            "prompt": "noisy tabular kaggle dataset RMSLE baseline",
            "goal": "beat rmsle 0.1",
            "kpi": {"primary": "rmsle", "higher_is_better": False},
            "workspace_path": str(tmp_path / "tab"),
        }
    )
    funnel2 = Funnel()
    funnel2.bind(Context(), tab["id"])
    formal2 = funnel2.formalize(store.get_project(tab["id"]))
    assert formal2["skip_math"] is False
    domains = funnel2.score_domains(store.get_project(tab["id"]))
    assert domains and "id" in domains[0]
    assert "total" in domains[0]
    job = funnel2.maybe_noise_job(store.get_project(tab["id"]))
    assert job is not None
    assert job["kind"] == "denoise"
    assert job["metric"] == "noise_level"


def test_http_asks_secrets_and_funnel_plugin_listed(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    plugins = client.get("/api/plugins").json()
    assert any(p["id"] == "rnd.funnel" for p in plugins)
    proj = client.post(
        "/api/projects",
        json={"name": "q", "goal": "g", "prompt": "p"},
    ).json()
    pid = proj["id"]
    created = client.post(
        f"/api/projects/{pid}/asks",
        json={"kind": "clarify", "question": "which split?"},
    )
    assert created.status_code == 200
    ask = created.json()
    assert ask["status"] == "open"
    reply = client.post(
        f"/api/projects/{pid}/asks/{ask['id']}/reply",
        json={"answer": "use official split"},
    ).json()
    assert reply["status"] == "answered"
    assert reply["answer"] == "use official split"
    start = client.post(f"/api/projects/{pid}/start")
    assert start.status_code == 200
    got = client.get(f"/api/projects/{pid}").json()
    assert got["id"] == pid
    events = client.get(f"/api/projects/{pid}/events").json()
    types = [e["type"] for e in events]
    assert "provider.missing" in types
    missing = next(e for e in events if e["type"] == "provider.missing")
    assert missing["payload"]["reason"] == "no_provider"


def test_worker_advances_unblocked_denoise_job(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    proj = store.create_project(
        {
            "name": "w",
            "goal": "g",
            "prompt": "noisy data",
            "workspace_path": str(tmp_path / "w"),
        }
    )
    pid = proj["id"]
    blocked = store.add_job({"project_id": pid, "kind": "train", "title": "need creds"})
    ask = store.add_ask(
        {
            "project_id": pid,
            "kind": "secret",
            "question": "api key?",
            "blocked_job_ids": [blocked["id"]],
        }
    )
    store.update_job(blocked["id"], blocked_by=ask["id"], status="blocked")
    denoise = store.add_job(
        {"project_id": pid, "kind": "denoise", "title": "noise", "metric": "noise_level"}
    )
    rt = ProjectRuntime(pid, store=store)
    import asyncio

    asyncio.run(rt._advance_jobs())
    assert store.get_job(denoise["id"])["status"] == "done"
    assert store.get_job(blocked["id"])["status"] == "blocked"
    hyps = store.list_hypotheses(pid)
    assert any(h["line_id"] == "denoise" for h in hyps)
