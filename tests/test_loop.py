import asyncio
import json

from openrd.core.context import Context
from openrd.engine.ingest import ingest_upload
from openrd.engine.worker import PHASES, ProjectRuntime, _source_status
from openrd.plugins.memory_archive import ArchiveService
from openrd.plugins.memory_compiler import Compiler
from openrd.plugins.memory_core import CoreMemory
from openrd.plugins.rnd_funnel import Funnel
from openrd.plugins.search_planner import SearchPlanner
from openrd.plugins.search_ranker import Ranker
from tests.test_product import _client


class _IdleRuntime(ProjectRuntime):
    async def phase_understand(self) -> None:
        return

    async def phase_research(self) -> None:
        return

    async def phase_ideate(self) -> None:
        return

    async def phase_critique(self) -> None:
        return

    async def phase_select(self) -> None:
        return

    async def phase_implement(self) -> None:
        return

    async def phase_screen(self) -> None:
        return

    async def phase_fulleval(self) -> None:
        return

    async def phase_analyze(self) -> None:
        return

    async def phase_update_memory(self) -> None:
        return


def test_phase_names_match_idle_runtime():
    for phase in PHASES:
        assert hasattr(_IdleRuntime, f"phase_{phase}")


def test_start_without_provider_does_not_loop(tmp_path, monkeypatch):
    client, _store = _client(tmp_path, monkeypatch)
    proj = client.post("/api/projects", json={"name": "q", "goal": "g", "prompt": "p"}).json()
    pid = proj["id"]
    assert client.post(f"/api/projects/{pid}/start").status_code == 200
    got = client.get(f"/api/projects/{pid}").json()
    assert got["status"] == "paused"
    events = client.get(f"/api/projects/{pid}/events").json()
    types = [e["type"] for e in events]
    assert "provider.missing" in types
    assert "cycle.summary" not in types
    stalled = next(e for e in events if e["type"] == "cycle.stalled")
    assert stalled["payload"]["reason"] == "no_provider"


def test_two_empty_cycles_pause(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    proj = store.create_project(
        {
            "name": "idle",
            "goal": "g",
            "prompt": "p",
            "provider_id": "prov",
            "workspace_path": str(tmp_path / "w"),
        }
    )
    rt = _IdleRuntime(proj["id"], store=store)
    asyncio.run(rt._loop())
    assert store.get_project(proj["id"])["status"] == "paused"
    assert rt.cycle == 2
    events = store.list_events(proj["id"], limit=20)
    assert len([e for e in events if e["type"] == "cycle.summary"]) == 2
    stalled = [e for e in events if e["type"] == "cycle.stalled"]
    assert len(stalled) == 1
    assert stalled[0]["payload"]["reason"] == "all_rejected"
    assert "phase.enter" not in {e["type"] for e in events}


def test_planner_error_does_not_query_the_raw_goal():
    class _Down:
        async def complete(self, *_args, **_kwargs):
            raise RuntimeError("planner down")

    ctx = Context()
    ctx.provide("llm", _Down())
    planner = SearchPlanner()
    planner.bind(ctx)
    queries = asyncio.run(planner.plan("beat RMSLE 0.12"))
    assert queries == []
    assert "beat RMSLE" not in planner.last_error
    assert planner.last_error


def test_ranker_drops_hits_that_miss_the_task():
    hits = [
        {
            "title": "Beating One Half for Online Bipartite Matching",
            "paper_key": "a",
            "source": "arxiv",
            "year": 2026,
        },
        {
            "title": "RMSLE tabular regression with LightGBM",
            "paper_key": "b",
            "source": "arxiv",
            "year": 2026,
        },
    ]
    ranked = Ranker().rank(hits, focus="beat RMSLE 0.12 tabular sales")
    titles = [h["title"] for h in ranked]
    assert titles == ["RMSLE tabular regression with LightGBM"]


def test_source_error_status_has_no_url():
    exc = RuntimeError(
        "Client error '403 Forbidden' for url 'https://api.example.test/secret-path'"
    )
    assert _source_status(exc) == "403"


def test_research_records_status_without_url(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    proj = store.create_project(
        {
            "name": "search",
            "goal": "tabular rmsle",
            "prompt": "sales table",
            "provider_id": "prov",
            "workspace_path": str(tmp_path / "w"),
        }
    )

    class _Planner:
        last_error = ""

        async def plan(self, _task, extra=""):
            del extra
            return [{"q": "tabular rmsle regression", "intent": "method"}]

    class _Bad:
        async def search(self, _query, count=5):
            del count
            raise RuntimeError(
                "Client error '403 Forbidden' for url 'https://api.example.test/secret-path'"
            )

    rt = ProjectRuntime(proj["id"], store=store)
    rt.ctx.provide("search_planner", _Planner())
    rt.ctx.provide("search_arxiv", _Bad())
    asyncio.run(rt.phase_research())
    blob = json.dumps(store.list_events(proj["id"], limit=20))
    assert "secret-path" not in blob
    assert rt._stats["source_errors"]["search_arxiv"] == "403"


def test_csv_ingest_writes_data_card(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    proj = store.create_project(
        {
            "name": "tab",
            "goal": "beat RMSLE 0.12",
            "prompt": "noisy labels",
            "kpi": {"primary": "rmsle", "higher_is_better": False},
            "workspace_path": str(tmp_path / "tab"),
        }
    )
    ingest_upload(
        store,
        project_id=proj["id"],
        workspace=tmp_path / "tab",
        filename="train.csv",
        data=b"a,b\n1,2\n",
        mime="text/csv",
        role="input",
    )
    card = store.get_memory(proj["id"])["data_card"]
    assert "columns=a,b" in card
    assert "target_candidate=b" in card
    assert "rmsle" in card
    core = CoreMemory()
    core.bind(proj["id"])
    archive = ArchiveService()
    archive.bind(proj["id"], None)
    ctx = Context()
    ctx.provide("memory_core", core)
    ctx.provide("archive", archive)
    ctx.extras["manifests"] = {}
    compiler = Compiler()
    compiler.bind(ctx, proj["id"])
    assert "columns=a,b" in compiler.brief("ideate", "")


def test_seed_is_baseline_not_catalog_template(tmp_path, monkeypatch):
    _c, store = _client(tmp_path, monkeypatch)
    proj = store.create_project(
        {
            "name": "tab",
            "goal": "beat rmsle",
            "prompt": "tabular dataset",
            "kpi": {"primary": "rmsle", "higher_is_better": False},
            "workspace_path": str(tmp_path / "tab"),
        }
    )
    store.patch_memory(proj["id"], "data_card", "train.csv: rows=1 columns=a,b. target_candidate=b. metric=rmsle.")
    funnel = Funnel()
    funnel.bind(Context(), proj["id"])
    project = store.get_project(proj["id"])
    seeded = funnel.seed_hypotheses(project, [{"id": "linear_algebra", "methods": ["PCA"]}])
    assert len(seeded) == 1
    assert seeded[0]["line_id"] == "baseline"
    assert "PCA" not in seeded[0]["mechanism"]
    assert funnel.seed_hypotheses(project, []) == []
    titles = [
        n["title"]
        for n in store.list_tree(proj["id"])
        if n["kind"] == "domain" and n["title"] == "cross-science analogies"
    ]
    store.add_tree_node(
        {
            "project_id": proj["id"],
            "kind": "domain",
            "title": "cross-science analogies",
            "status": "open",
        }
    )
    again = store.add_tree_node(
        {
            "project_id": proj["id"],
            "kind": "domain",
            "title": "cross-science analogies",
            "status": "open",
        }
    )
    nodes = [
        n
        for n in store.list_tree(proj["id"])
        if n["kind"] == "domain" and n["title"] == "cross-science analogies"
    ]
    assert len(nodes) == 1
    assert again["id"] == nodes[0]["id"]
    assert titles == []
