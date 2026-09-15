"""Long-horizon R&D loop. Phases are a DAG on a blackboard, not a chat chain."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openrd.core.context import Context
from openrd.core.events import (
    CEMETERY_ADD,
    HYPOTHESIS_PROPOSED,
    HYPOTHESIS_REJECTED,
    HYPOTHESIS_SELECTED,
    PAPER_INGESTED,
    PHASE_ENTER,
    PHASE_EXIT,
    PROJECT_SOLVED,
    ROLLBACK,
    RUN_FAILED,
    RUN_FINISHED,
    RUN_STARTED,
    SAFETY_BLOCK,
    SEARCH_HIT,
    SEARCH_QUERY,
    SEARCH_SKIPPED,
    THOUGHT,
    TREE_NODE,
)
from openrd.core.loader import load_into
from openrd.core.profile import load_profile, profiles_dir
from openrd.db.store import Store, get_store
from openrd.engine.knowledge import export_knowledge
from openrd.paths import project_workspace
from openrd.settings import settings
from openrd.util.canon import canon_query, fingerprint_text, mechanism_key
from openrd.util.embed import hashing_embed


PHASES = [
    "understand",
    "research",
    "ideate",
    "critique",
    "select",
    "implement",
    "screen",
    "fulleval",
    "analyze",
    "update_memory",
]


class ProjectRuntime:
    def __init__(self, project_id: str, store: Store | None = None) -> None:
        self.project_id = project_id
        self.store = store or get_store()
        self.ctx = Context()
        self.ctx.project_id = project_id
        self.task: asyncio.Task | None = None
        self.cycle = 0
        self.current_phase = "idle"
        self.current_hyps: list[dict[str, Any]] = []
        self.selected: dict[str, Any] | None = None
        self.last_code: str = ""
        self.last_run: dict[str, Any] | None = None
        self.root_id: str | None = None

    def _project(self) -> dict[str, Any]:
        p = self.store.get_project(self.project_id)
        if not p:
            raise RuntimeError("project missing")
        return p

    def load_plugins(self) -> None:
        profile_name = self._project().get("profile") or "default"
        path = profiles_dir() / f"{profile_name}.yaml"
        if not path.exists():
            path = profiles_dir() / "default.yaml"
        load_into(self.ctx, load_profile(path))
        self._bind()

    def _bind(self) -> None:
        p = self._project()
        ws = Path(p["workspace_path"])
        if self.ctx.has("llm") and p.get("provider_id"):
            self.ctx.require("llm").bind(p["provider_id"], self.project_id)
        if self.ctx.has("journal"):
            self.ctx.require("journal").bind(self.project_id)
        if self.ctx.has("memory_core"):
            self.ctx.require("memory_core").bind(self.project_id)
        if self.ctx.has("archive"):
            self.ctx.require("archive").bind(self.project_id, self.ctx.get("embed"))
        if self.ctx.has("graph"):
            self.ctx.require("graph").bind(self.project_id)
        if self.ctx.has("compiler"):
            self.ctx.require("compiler").bind(self.ctx, self.project_id)
        if self.ctx.has("tracker"):
            self.ctx.require("tracker").bind(self.project_id)
        if self.ctx.has("human"):
            self.ctx.require("human").bind(self.project_id)
        if self.ctx.has("search_policy"):
            self.ctx.require("search_policy").bind(self.project_id)
        if self.ctx.has("quality_bar"):
            self.ctx.require("quality_bar").bind(self.ctx, p.get("rigor") or "high")
        if self.ctx.has("sandbox"):
            self.ctx.require("sandbox").bind(ws / "work", memory_mb=2048, timeout_s=180)
        if self.ctx.has("scheduler"):
            think = int(p.get("think_slots") or 4)
            exec_slots = int(p.get("exec_slots") or 1)
            self.ctx.require("scheduler").configure(think, exec_slots)
        if self.ctx.has("scientist"):
            self.ctx.require("scientist").bind(self.ctx)
        if self.ctx.has("debate"):
            self.ctx.require("debate").bind(self.ctx)
        if self.ctx.has("virtual_eval"):
            self.ctx.require("virtual_eval").bind(self.ctx)
        if self.ctx.has("coder"):
            self.ctx.require("coder").bind(self.ctx)
        if self.ctx.has("analyst"):
            self.ctx.require("analyst").bind(self.ctx)
        if self.ctx.has("search_planner"):
            self.ctx.require("search_planner").bind(self.ctx)
        if self.ctx.has("artifacts"):
            self.ctx.require("artifacts").bind(self.ctx, self.project_id)

    async def emit(self, typ: str, payload: dict[str, Any] | None = None, node_id: str | None = None, agent: str = "orchestrator") -> dict[str, Any]:
        return await self.ctx.require("journal").write(typ, payload, agent_id=agent, node_id=node_id)

    def tree(self, **kwargs: Any) -> dict[str, Any]:
        node = self.store.add_tree_node({"project_id": self.project_id, **kwargs})
        return node

    async def start(self) -> None:
        if self.task and not self.task.done():
            return
        self.load_plugins()
        p = self._project()
        if not self.root_id:
            existing = [n for n in self.store.list_tree(self.project_id) if n["kind"] == "goal"]
            if existing:
                self.root_id = existing[0]["id"]
            else:
                root = self.tree(kind="goal", title=p["name"], summary=p["goal"], status="running")
                self.root_id = root["id"]
                if self.ctx.has("graph"):
                    gid = self.ctx.require("graph").node("goal", p["name"], {"goal": p["goal"]}, node_id=self.root_id)
                    self.ctx.require("graph").edge(gid, gid, "self")
        self.store.update_project(self.project_id, status="running")
        await self.emit("project.started", {"cycle": self.cycle})
        self.task = asyncio.create_task(self._loop(), name=f"openrd-{self.project_id}")

    async def stop(self) -> None:
        if self.ctx.has("human"):
            self.ctx.require("human").stop = True
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
        self.store.update_project(self.project_id, status="stopped")
        await self.emit("project.stopped", {})

    async def pause(self) -> None:
        if self.ctx.has("human"):
            self.ctx.require("human").pause = True
        self.store.update_project(self.project_id, status="paused")
        await self.emit("project.paused", {})

    async def resume(self) -> None:
        if self.ctx.has("human"):
            self.ctx.require("human").pause = False
            self.ctx.require("human").stop = False
        status = self._project()["status"]
        self.store.update_project(self.project_id, status="running")
        await self.emit("project.resumed", {"from": status})
        if not self.task or self.task.done():
            self.load_plugins()
            self.task = asyncio.create_task(self._loop(), name=f"openrd-{self.project_id}")

    async def rollback(self, node_id: str) -> None:
        node = self.store.get_tree_node(node_id)
        if not node:
            return
        self.store.update_tree_node(node_id, status="rolled_back_to")
        self.selected = None
        self.current_hyps = []
        await self.emit(ROLLBACK, {"node_id": node_id}, node_id=node_id)
        if self.ctx.has("memory_core"):
            self.ctx.require("memory_core").patch(
                "open_questions",
                f"Rolled back to {node.get('title')}: {node.get('summary')}",
            )

    async def _loop(self) -> None:
        try:
            while True:
                human = self.ctx.get("human")
                if human and human.stop:
                    break
                while human and human.pause:
                    await asyncio.sleep(0.4)
                    await self._consume_human()
                    if human.stop:
                        return
                await self._consume_human()
                self.cycle += 1
                for phase in PHASES:
                    self.current_phase = phase
                    await self.emit(PHASE_ENTER, {"phase": phase, "cycle": self.cycle})
                    await getattr(self, f"phase_{phase}")()
                    await self.emit(PHASE_EXIT, {"phase": phase, "cycle": self.cycle})
                    if self._project()["status"] in {"stopped", "solved"}:
                        return
                    human = self.ctx.get("human")
                    if human and human.stop:
                        return
                export_knowledge(self.store, self.project_id, Path(self._project()["workspace_path"]) / "knowledge")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.emit("run.failed", {"error": str(e), "phase": self.current_phase})
            self.store.update_project(self.project_id, status="error")

    async def _consume_human(self) -> None:
        human = self.ctx.get("human")
        if not human:
            return
        for msg in human.drain():
            await self.emit("human.steer", msg)
            kind = msg.get("kind")
            if kind == "rollback" and msg.get("node_id"):
                await self.rollback(msg["node_id"])
            if kind in {"question", "steer", "note"}:
                if self.ctx.has("memory_core"):
                    prev = self.ctx.require("memory_core").get().get("open_questions") or ""
                    self.ctx.require("memory_core").patch(
                        "open_questions", prev + f"\n- human: {msg.get('content')}"
                    )
                self.store.add_human_message(self.project_id, "user", msg.get("content") or "")
            if kind == "artifact":
                await self.emit(PAPER_INGESTED, msg)

    async def phase_understand(self) -> None:
        p = self._project()
        await self.emit(THOUGHT, {"text": f"Goal: {p['goal'][:500]}"})
        if self.ctx.has("compiler"):
            brief = self.ctx.require("compiler").brief("understand", p["goal"])
            await self.emit(THOUGHT, {"text": brief[:1500], "kind": "brief"})

    async def phase_research(self) -> None:
        p = self._project()
        planner = self.ctx.get("search_planner")
        ranker = self.ctx.get("search_ranker")
        archive = self.ctx.get("archive")
        if not planner:
            return
        queries = await planner.plan(p["goal"], extra=(self.ctx.require("memory_core").get().get("open_questions") if self.ctx.has("memory_core") else "") or "")
        sources = [
            ("search_arxiv", self.ctx.get("search_arxiv")),
            ("search_s2", self.ctx.get("search_s2")),
            ("search_openalex", self.ctx.get("search_openalex")),
            ("search_github", self.ctx.get("search_github")),
            ("search_web", self.ctx.get("search_web")),
        ]
        hits: list[dict[str, Any]] = []

        async def run_one(q: dict[str, Any]) -> None:
            query = q["q"]
            if archive and archive.seen_query(query):
                await self.emit(SEARCH_SKIPPED, {"query": query, "reason": "duplicate_query"})
                return
            await self.emit(SEARCH_QUERY, {"query": query, "intent": q.get("intent")})
            if archive:
                archive.add("search", query, query, query=query)
            for name, svc in sources:
                if svc is None:
                    continue
                try:
                    batch = await svc.search(query, count=5)
                except Exception as e:
                    await self.emit(THOUGHT, {"text": f"{name} failed: {e}"})
                    continue
                for h in batch:
                    url = h.get("url") or ""
                    if archive and url and archive.seen_url(url):
                        await self.emit(SEARCH_SKIPPED, {"url": url, "reason": "duplicate_url"})
                        continue
                    if not self.store.claim(self.project_id, "url", h.get("url_canon") or url, "research"):
                        continue
                    hits.append(h)
                    if archive and url:
                        archive.add("paper", h.get("title") or url, h.get("snippet") or "", url=url, query=query)
                    await self.emit(SEARCH_HIT, h)

        sched = self.ctx.get("scheduler")
        if sched:
            await asyncio.gather(*[sched.run_think(lambda qq=q: run_one(qq)) for q in queries[:8]])
        else:
            for q in queries[:8]:
                await run_one(q)
        if ranker:
            ranked = ranker.rank(hits)
            await self.emit(THOUGHT, {"text": f"ranked {len(ranked)} unique hits", "top": ranked[:5]})

    async def phase_ideate(self) -> None:
        scientist = self.ctx.get("scientist")
        policy = self.ctx.get("search_policy")
        if not scientist:
            return
        raw = await scientist.propose(f"cycle={self.cycle}")
        if policy:
            raw = policy.filter_portfolio(raw)
        self.current_hyps = raw
        for h in raw:
            node = self.tree(
                parent_id=self.root_id,
                kind="hypothesis",
                title=h.get("mechanism") or "hypothesis",
                summary=h.get("text") or "",
                payload=h,
                status="proposed",
            )
            h["node_id"] = node["id"]
            h["fingerprint"] = fingerprint_text(h.get("mechanism") or "", h.get("text") or "")
            rec = self.store.add_hypothesis(
                {
                    "project_id": self.project_id,
                    "line_id": mechanism_key(h.get("line") or h.get("mechanism") or ""),
                    "type": h.get("type") or "explore",
                    "mechanism": h.get("mechanism") or "",
                    "fingerprint": h["fingerprint"],
                    "text": h.get("text") or "",
                    "node_id": node["id"],
                    "status": "proposed",
                }
            )
            h["id"] = rec["id"]
            await self.emit(HYPOTHESIS_PROPOSED, h, node_id=node["id"])
            await self.emit(TREE_NODE, node, node_id=node["id"])

    async def phase_critique(self) -> None:
        quality = self.ctx.get("quality_bar")
        debate = self.ctx.get("debate")
        archive = self.ctx.get("archive")
        safety = self.ctx.get("safety")
        kept: list[dict[str, Any]] = []
        p = self._project()
        champion = (self.ctx.require("memory_core").get().get("champion") if self.ctx.has("memory_core") else "") or ""
        n_think = max(1, int(p.get("think_slots") or 4))
        for h in self.current_hyps:
            mech = h.get("mechanism") or ""
            if not self.store.claim(self.project_id, "mechanism", mechanism_key(mech), "critique"):
                h["reject_reason"] = "mechanism already claimed"
                await self.emit(HYPOTHESIS_REJECTED, h, node_id=h.get("node_id"))
                continue
            if safety:
                verdict = safety.check_hypothesis(f"{mech}\n{h.get('text')}")
                if not verdict.ok:
                    await self.emit(SAFETY_BLOCK, {"reasons": verdict.reasons, "hyp": mech})
                    self.store.update_hypothesis(h["id"], status="blocked")
                    continue
            if archive:
                sim = archive.similar_mechanism(mech + "\n" + (h.get("text") or ""), settings.novelty_cosine_block)
                if sim:
                    h["reject_reason"] = f"too similar to {sim.get('title')}"
                    await self.emit(HYPOTHESIS_REJECTED, h, node_id=h.get("node_id"))
                    self.store.update_hypothesis(h["id"], status="rejected")
                    continue
            cem = self.store.list_cemetery(self.project_id)
            if any(c["mechanism_class"] == mechanism_key(mech) for c in cem):
                h["reject_reason"] = "cemetery class"
                await self.emit(HYPOTHESIS_REJECTED, h, node_id=h.get("node_id"))
                self.store.update_hypothesis(h["id"], status="rejected")
                continue
            if quality:
                q = await quality.judge(p["goal"], mech, h.get("text") or "", champion)
                if not q.get("ok"):
                    h["reject_reason"] = q.get("reasons")
                    await self.emit(HYPOTHESIS_REJECTED, h, node_id=h.get("node_id"))
                    self.store.update_hypothesis(h["id"], status="rejected")
                    continue
            if debate:
                d = await debate.run(h, n_think=min(3, n_think))
                h["debate"] = d
                if d.get("veto"):
                    h["reject_reason"] = "debate veto"
                    await self.emit(HYPOTHESIS_REJECTED, h, node_id=h.get("node_id"))
                    self.store.update_hypothesis(h["id"], status="rejected")
                    continue
            kept.append(h)
        self.current_hyps = kept

    async def phase_select(self) -> None:
        ve = self.ctx.get("virtual_eval")
        if not self.current_hyps:
            self.selected = None
            await self.emit(THOUGHT, {"text": "no hypotheses survived critique"})
            return
        if ve:
            picked = await ve.pick(self.current_hyps[: settings.virtual_eval_k])
            self.selected = picked["winner"]
        else:
            self.selected = self.current_hyps[0]
        assert self.selected
        self.store.update_hypothesis(
            self.selected["id"],
            status="selected",
            virtual_score=self.selected.get("virtual_score"),
        )
        if self.selected.get("node_id"):
            self.store.update_tree_node(self.selected["node_id"], status="selected")
        await self.emit(HYPOTHESIS_SELECTED, self.selected, node_id=self.selected.get("node_id"))

    async def _run_code(self, code: str, phase: str) -> dict[str, Any]:
        safety = self.ctx.require("safety")
        verdict = safety.check_code(code)
        if not verdict.ok:
            await self.emit(SAFETY_BLOCK, {"reasons": verdict.reasons, "phase": phase})
            return {"ok": False, "reasons": verdict.reasons}
        sandbox = self.ctx.require("sandbox")
        env = {"OPENRD_SAMPLE": "1" if phase == "screen" else "0"}
        result = sandbox.run_python(code, filename="treatment.py", env=env)
        return {
            "ok": result.returncode == 0 and not result.timed_out,
            "result": result,
        }

    async def phase_implement(self) -> None:
        if not self.selected:
            return
        coder = self.ctx.get("coder")
        if not coder:
            return
        code = await coder.write(self.selected, sample=True)
        self.last_code = code
        await self.emit(THOUGHT, {"text": "wrote treatment.py", "chars": len(code)}, node_id=self.selected.get("node_id"))

    async def phase_screen(self) -> None:
        if not self.selected or not self.last_code:
            return
        coder = self.ctx.require("coder")
        code = self.last_code
        node = self.tree(
            parent_id=self.selected.get("node_id"),
            kind="run",
            title="screen",
            status="running",
        )
        tracker = self.ctx.require("tracker")
        run = tracker.start_run(
            hypothesis_id=self.selected["id"],
            node_id=node["id"],
            phase="screen",
            params={"sample": True, "mechanism": self.selected.get("mechanism")},
        )
        await self.emit(RUN_STARTED, {"run_id": run["id"], "phase": "screen"}, node_id=node["id"])
        depth = 0
        while depth <= settings.max_debug_depth:
            try:
                out = await self.ctx.require("scheduler").run_exec(lambda c=code: self._run_code(c, "screen"))
            except Exception as e:
                await self.emit(RUN_FAILED, {"error": str(e)})
                tracker.finish(run["id"], "failed")
                return
            if out.get("ok"):
                res = out["result"]
                tracker.log_metrics(run["id"], res.metrics)
                tracker.finish(run["id"], "ok", res.metrics)
                self.last_run = {"run": run, "result": res, "metrics": res.metrics, "node_id": node["id"]}
                self.store.update_tree_node(node["id"], status="ok", metrics=res.metrics, summary="screen ok")
                await self.emit(RUN_FINISHED, {"run_id": run["id"], "metrics": res.metrics}, node_id=node["id"])
                self.last_code = code
                return
            res = out.get("result")
            stderr = getattr(res, "stderr", None) or str(out.get("reasons"))
            depth += 1
            await self.emit(THOUGHT, {"text": f"debug {depth}: {str(stderr)[:400]}"})
            code = await coder.repair(code, str(stderr))
            safety = self.ctx.require("safety")
            if not safety.check_code(code).ok:
                break
        tracker.finish(run["id"], "failed")
        self.store.update_tree_node(node["id"], status="failed", summary=str(stderr)[:400])
        await self.emit(RUN_FAILED, {"run_id": run["id"]})
        self.last_run = None

    async def phase_fulleval(self) -> None:
        if not self.last_run or not self.selected:
            return
        node = self.tree(parent_id=self.selected.get("node_id"), kind="run", title="full", status="running")
        tracker = self.ctx.require("tracker")
        run = tracker.start_run(
            hypothesis_id=self.selected["id"],
            node_id=node["id"],
            phase="full",
            params={"sample": False},
        )
        await self.emit(RUN_STARTED, {"run_id": run["id"], "phase": "full"}, node_id=node["id"])
        try:
            out = await self.ctx.require("scheduler").run_exec(lambda: self._run_code(self.last_code, "full"))
        except Exception as e:
            tracker.finish(run["id"], "failed")
            await self.emit(RUN_FAILED, {"error": str(e)})
            return
        if not out.get("ok"):
            tracker.finish(run["id"], "failed")
            self.store.update_tree_node(node["id"], status="failed")
            await self.emit(RUN_FAILED, {"run_id": run["id"]})
            self.last_run = None
            return
        res = out["result"]
        tracker.log_metrics(run["id"], res.metrics)
        tracker.finish(run["id"], "ok", res.metrics)
        self.last_run = {"run": run, "result": res, "metrics": res.metrics, "node_id": node["id"]}
        self.store.update_tree_node(node["id"], status="ok", metrics=res.metrics)
        await self.emit(RUN_FINISHED, {"run_id": run["id"], "metrics": res.metrics}, node_id=node["id"])

    async def phase_analyze(self) -> None:
        if not self.last_run or not self.selected:
            return
        analyst = self.ctx.get("analyst")
        champion_id = self._project().get("champion_node_id")
        champion = self.store.get_tree_node(champion_id) if champion_id else None
        report = {"lesson": "no analyst", "promote": bool(self.last_run.get("metrics"))}
        if analyst:
            report = await analyst.analyze(
                {"hyp": self.selected, "metrics": self.last_run.get("metrics")},
                champion,
                getattr(self.last_run["result"], "stdout", "")
                + getattr(self.last_run["result"], "stderr", ""),
            )
        metrics = self.last_run.get("metrics") or {}
        primary = metrics.get("primary")
        champ_metrics = (champion or {}).get("metrics") or {}
        champ_primary = champ_metrics.get("primary")
        promote = bool(report.get("promote"))
        if primary is not None and champ_primary is not None:
            gate = self.ctx.require("tracker").noise_gate([primary, champ_primary], float(primary) - float(champ_primary))
            report["noise_gate"] = gate
            if gate.get("tie"):
                promote = False
        if promote:
            self.store.update_project(self.project_id, champion_node_id=self.last_run["node_id"])
            self.store.update_hypothesis(self.selected["id"], status="promoted")
            if self.ctx.has("memory_core"):
                self.ctx.require("memory_core").patch(
                    "champion",
                    f"{self.selected.get('mechanism')} metrics={metrics}",
                )
        else:
            self.store.update_hypothesis(self.selected["id"], status="tested")
            klass = report.get("cemetery_class") or mechanism_key(self.selected.get("mechanism") or "")
            if report.get("cemetery_class") or not promote:
                self.store.add_cemetery(
                    {
                        "project_id": self.project_id,
                        "mechanism_class": klass,
                        "fingerprint": self.selected.get("fingerprint") or "",
                        "lesson": report.get("lesson") or "did not beat champion",
                        "embedding": hashing_embed(self.selected.get("mechanism") or ""),
                    }
                )
                if self.ctx.has("archive"):
                    self.ctx.require("archive").add(
                        "cemetery",
                        klass,
                        report.get("lesson") or "",
                    )
                await self.emit(CEMETERY_ADD, {"class": klass, "lesson": report.get("lesson")})
        await self.emit(THOUGHT, {"text": "analysis", "report": report})

    async def phase_update_memory(self) -> None:
        if self.ctx.has("memory_core"):
            core = self.ctx.require("memory_core")
            bans = "\n".join(
                f"- {c['mechanism_class']}: {c['lesson']}" for c in self.store.list_cemetery(self.project_id)[-8:]
            )
            core.patch("bans", bans)
        export_knowledge(self.store, self.project_id, Path(self._project()["workspace_path"]) / "knowledge")
        # cheap "solved" if user KPI target met
        kpi = self._project().get("kpi") or {}
        target = kpi.get("target")
        champ = self._project().get("champion_node_id")
        if target is not None and champ:
            node = self.store.get_tree_node(champ)
            primary = (node or {}).get("metrics", {}).get("primary")
            direction = kpi.get("higher_is_better", True)
            if primary is not None:
                done = primary >= float(target) if direction else primary <= float(target)
                if done:
                    self.store.update_project(self.project_id, status="solved")
                    await self.emit(PROJECT_SOLVED, {"primary": primary, "target": target})


_RUNTIMES: dict[str, ProjectRuntime] = {}


def get_runtime(project_id: str) -> ProjectRuntime:
    rt = _RUNTIMES.get(project_id)
    if rt is None:
        rt = ProjectRuntime(project_id)
        _RUNTIMES[project_id] = rt
    return rt


def reset_runtimes() -> None:
    _RUNTIMES.clear()
