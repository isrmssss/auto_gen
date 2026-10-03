from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from openrd import __version__
from openrd.core.loader import catalog
from openrd.db.store import get_store
from openrd.engine.bus import get_bus
from openrd.engine.hw import probe_dict
from openrd.engine.ingest import ingest_upload
from openrd.engine.worker import get_runtime
from openrd.paths import project_workspace
from openrd.server.schemas import (
    AskIn,
    AskReply,
    PluginToggle,
    ProjectIn,
    ProjectPatch,
    ProviderIn,
    ProviderUpdate,
    SecretIn,
    SteerIn,
)
from openrd.settings import settings

app = FastAPI(title="OpenRD", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/hw")
def hw():
    return probe_dict(settings.default_exec_memory_frac, 1)


@app.get("/api/plugins")
def plugins():
    return [
        {
            "id": m.id,
            "title": m.title,
            "description": m.description,
            "bundle": m.bundle,
            "provides": m.provides,
            "requires": m.requires,
            "when_to_use": m.when_to_use,
            "tools": m.tools,
            "optional": m.optional,
        }
        for m in catalog().values()
    ]


@app.get("/api/providers")
def list_providers():
    return get_store().list_providers()


@app.post("/api/providers")
def create_provider(body: ProviderIn):
    return get_store().create_provider(body.name, body.base_url, body.api_key, body.roles)


@app.get("/api/providers/{provider_id}")
def get_provider(provider_id: str):
    row = get_store().get_provider(provider_id)
    if not row:
        raise HTTPException(404, "provider not found")
    return row


@app.patch("/api/providers/{provider_id}")
def patch_provider(provider_id: str, body: ProviderUpdate):
    row = get_store().update_provider(
        provider_id,
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        roles=body.roles,
    )
    if not row:
        raise HTTPException(404, "provider not found")
    return row


@app.delete("/api/providers/{provider_id}")
def delete_provider(provider_id: str):
    get_store().delete_provider(provider_id)
    return {"ok": True}


@app.get("/api/providers/{provider_id}/models")
async def provider_models(provider_id: str):
    from openrd.plugins.llm_openai import LLMService

    svc = LLMService(get_store())
    svc.bind(provider_id)
    try:
        models = await svc.list_remote_models()
    except Exception as e:
        raise HTTPException(502, str(e)) from e
    return {"models": models}


@app.get("/api/projects")
def list_projects():
    return get_store().list_projects()


@app.post("/api/projects")
def create_project(body: ProjectIn):
    store = get_store()
    # think_slots: UI sends N agents; 1 => sequential (1 think), else N-1 think + 1 orch
    n = body.think_slots
    if n <= 1:
        think, exec_slots = 1, 1
    else:
        think, exec_slots = n - 1, body.exec_slots
    ws = project_workspace("pending")
    # create with real id first
    row = store.create_project(
        {
            "name": body.name,
            "goal": body.goal,
            "prompt": body.prompt or body.description or "",
            "description": body.description,
            "kpi": body.kpi or {"primary": "primary", "higher_is_better": True},
            "provider_id": body.provider_id,
            "think_slots": think,
            "exec_slots": exec_slots,
            "profile": body.profile,
            "rigor": body.rigor,
            "workspace_path": str(ws),
        }
    )
    real_ws = project_workspace(row["id"])
    store.update_project(row["id"], **{})  # touch
    # rewrite workspace path
    store.execute(
        "UPDATE projects SET workspace_path=? WHERE id=?",
        (str(real_ws), row["id"]),
    )
    if body.user_ideas:
        store.patch_memory(row["id"], "open_questions", "User ideas:\n" + body.user_ideas)
        (real_ws / "artifacts" / "user_ideas.md").write_text(body.user_ideas, encoding="utf-8")
    store.append_event(row["id"], "project.created", {"name": body.name})
    return store.get_project(row["id"])


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch):
    store = get_store()
    if not store.get_project(project_id):
        raise HTTPException(404, "project not found")
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.goal is not None:
        fields["goal"] = body.goal
        store.patch_memory(project_id, "goal", body.goal)
    if body.prompt is not None:
        fields["prompt"] = body.prompt
        store.patch_memory(project_id, "prompt", body.prompt)
    if body.kpi is not None:
        fields["kpi"] = body.kpi
        store.patch_memory(project_id, "kpi", str(body.kpi))
    return store.update_project(project_id, **fields)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    row = get_store().get_project(project_id)
    if not row:
        raise HTTPException(404, "project not found")
    store = get_store()
    return {
        **row,
        "memory": store.get_memory(project_id),
        "cost": store.cost_summary(project_id),
        "hw": probe_dict(settings.default_exec_memory_frac, row.get("exec_slots") or 1),
        "claims": store.list_claims(project_id),
    }


@app.post("/api/projects/{project_id}/start")
async def start_project(project_id: str):
    if not get_store().get_project(project_id):
        raise HTTPException(404, "project not found")
    rt = get_runtime(project_id)
    await rt.start()
    return {"ok": True, "status": "running"}


@app.post("/api/projects/{project_id}/pause")
async def pause_project(project_id: str):
    await get_runtime(project_id).pause()
    return {"ok": True}


@app.post("/api/projects/{project_id}/resume")
async def resume_project(project_id: str):
    await get_runtime(project_id).resume()
    return {"ok": True}


@app.post("/api/projects/{project_id}/stop")
async def stop_project(project_id: str):
    await get_runtime(project_id).stop()
    return {"ok": True}


@app.post("/api/projects/{project_id}/steer")
async def steer_project(project_id: str, body: SteerIn):
    rt = get_runtime(project_id)
    if not rt.ctx.has("human"):
        rt.load_plugins()
    extra = {"node_id": body.node_id} if body.node_id else {}
    rt.ctx.require("human").push(body.kind, body.content, extra)
    if body.kind == "rollback" and body.node_id:
        await rt.rollback(body.node_id)
    get_store().add_human_message(project_id, "assistant", "queued: " + body.kind)
    return {"ok": True}


@app.post("/api/projects/{project_id}/rollback")
async def rollback_project(project_id: str, body: SteerIn):
    if not body.node_id:
        raise HTTPException(400, "node_id required")
    await get_runtime(project_id).rollback(body.node_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/tree")
def project_tree(project_id: str):
    return get_store().list_tree(project_id)


@app.get("/api/projects/{project_id}/events")
def project_events(project_id: str, after: int = 0):
    return get_store().list_events(project_id, after_seq=after, limit=1000)


@app.get("/api/projects/{project_id}/hypotheses")
def project_hyps(project_id: str):
    return get_store().list_hypotheses(project_id)


@app.get("/api/projects/{project_id}/runs")
def project_runs(project_id: str):
    return get_store().list_runs(project_id)


@app.get("/api/projects/{project_id}/metrics")
def project_metrics(project_id: str):
    return get_store().metrics_for_project(project_id)


@app.get("/api/projects/{project_id}/cost")
def project_cost(project_id: str):
    return get_store().cost_summary(project_id)


@app.get("/api/projects/{project_id}/cemetery")
def project_cemetery(project_id: str):
    return get_store().list_cemetery(project_id)


@app.get("/api/projects/{project_id}/graph")
def project_graph(project_id: str):
    return get_store().get_graph(project_id)


@app.get("/api/projects/{project_id}/chat")
def project_chat(project_id: str):
    return get_store().list_human_messages(project_id)


@app.get("/api/projects/{project_id}/artifacts")
def project_artifacts(project_id: str):
    return get_store().list_artifacts(project_id)


@app.post("/api/projects/{project_id}/artifacts")
async def upload_artifact(
    project_id: str,
    file: UploadFile = File(...),
    role: str = Form("extra"),
    prompt: str = Form(""),
):
    store = get_store()
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(404, "project not found")
    data = await file.read()
    rt = get_runtime(project_id)
    ingest = None
    archive = None
    try:
        if not rt.ctx.has("ingest"):
            rt.load_plugins()
        ingest = rt.ctx.get("ingest")
        archive = rt.ctx.get("archive")
        if archive and not getattr(archive, "project_id", None):
            archive.bind(project_id, rt.ctx.get("embed"))
    except Exception:
        ingest = None
        archive = None
    rec = ingest_upload(
        store,
        project_id=project_id,
        workspace=Path(project["workspace_path"]),
        filename=file.filename or "upload.bin",
        data=data,
        mime=file.content_type,
        role=role,
        prompt=prompt,
        ingest_svc=ingest,
        archive=archive,
    )
    if rt.ctx.has("human"):
        rt.ctx.require("human").push(
            "artifact", rec["filename"], {"path": rec["path"], "role": role}
        )
    return rec


@app.get("/api/projects/{project_id}/jobs")
def project_jobs(project_id: str):
    return get_store().list_jobs(project_id)


@app.get("/api/projects/{project_id}/asks")
def project_asks(project_id: str):
    return get_store().list_asks(project_id)


@app.post("/api/projects/{project_id}/asks")
def create_ask(project_id: str, body: AskIn):
    store = get_store()
    if not store.get_project(project_id):
        raise HTTPException(404, "project not found")
    rec = store.add_ask(
        {
            "project_id": project_id,
            "kind": body.kind,
            "question": body.question,
            "secret_name": body.secret_name,
            "blocked_job_ids": body.blocked_job_ids,
        }
    )
    for jid in body.blocked_job_ids:
        store.update_job(jid, blocked_by=rec["id"], status="blocked")
    store.append_event(project_id, "human.question", {"id": rec["id"], "kind": body.kind})
    return rec


@app.post("/api/projects/{project_id}/asks/{ask_id}/reply")
def reply_ask(project_id: str, ask_id: str, body: AskReply):
    store = get_store()
    ask = store.get_ask(ask_id)
    if not ask or ask.get("project_id") != project_id:
        raise HTTPException(404, "ask not found")
    if body.decline:
        rec = store.decline_ask(ask_id)
        store.append_event(project_id, "human.ask.answered", {"id": ask_id, "declined": True})
        store.add_human_message(project_id, "user", f"declined ask {ask_id}")
        return rec
    if ask.get("kind") == "secret" and body.secret_value:
        name = ask.get("secret_name") or "unnamed"
        store.set_project_secret(
            project_id, name, body.secret_value, note=ask.get("question") or ""
        )
        rec = store.answer_ask(ask_id, f"saved secret {name}")
        store.add_human_message(project_id, "user", f"saved secret {name}")
    else:
        rec = store.answer_ask(ask_id, body.answer)
        store.add_human_message(project_id, "user", body.answer[:500])
    store.append_event(project_id, "human.ask.answered", {"id": ask_id, "declined": False})
    return rec


@app.get("/api/projects/{project_id}/secrets")
def list_secrets(project_id: str):
    return get_store().list_project_secrets(project_id)


@app.post("/api/projects/{project_id}/secrets")
def put_secret(project_id: str, body: SecretIn):
    if not get_store().get_project(project_id):
        raise HTTPException(404, "project not found")
    rec = get_store().set_project_secret(project_id, body.name, body.value, body.note)
    get_store().add_human_message(project_id, "user", f"saved secret {body.name}")
    return rec


@app.patch("/api/projects/{project_id}/secrets/{name}")
def patch_secret(project_id: str, name: str, body: SecretIn):
    rec = get_store().set_project_secret(project_id, name, body.value, body.note)
    return rec


@app.delete("/api/projects/{project_id}/secrets/{name}")
def delete_secret(project_id: str, name: str):
    get_store().delete_project_secret(project_id, name)
    return {"ok": True}


@app.get("/api/projects/{project_id}/plugins")
def project_plugins(project_id: str):
    enabled = get_store().enabled_plugins(project_id)
    out = []
    for m in catalog().values():
        row = enabled.get(m.id)
        out.append(
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "bundle": m.bundle,
                "enabled": True if row is None else bool(row["enabled"]),
                "when_to_use": m.when_to_use,
            }
        )
    return out


@app.post("/api/projects/{project_id}/plugins/{plugin_id}")
def toggle_plugin(project_id: str, plugin_id: str, body: PluginToggle):
    get_store().set_plugin_enabled(project_id, plugin_id, body.enabled, body.config)
    return {"ok": True}


@app.websocket("/api/projects/{project_id}/stream")
async def stream(project_id: str, ws: WebSocket):
    await ws.accept()
    bus = get_bus()
    # catch-up
    for ev in get_store().list_events(project_id, after_seq=0, limit=200):
        await ws.send_json(ev)
    try:
        async for event in bus.subscribe(project_id):
            await ws.send_json(event)
    except WebSocketDisconnect:
        return


def _ui_dist() -> Path | None:
    env = os.environ.get("OPENRD_UI_DIST")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "ui" / "dist",
        Path("/app/ui/dist"),
    ]
    try:
        candidates.append(here.parents[3] / "ui" / "dist")
    except IndexError:
        pass
    for c in candidates:
        if c.is_dir():
            return c
    return None


ui_dist = _ui_dist()
if ui_dist is not None:
    assets = ui_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        index = ui_dist / "index.html"
        candidate = ui_dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
