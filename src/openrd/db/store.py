from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from openrd.paths import db_path, secrets_path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return uuid.uuid4().hex[:16]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # --- secrets (API keys) ---
    def _secrets(self) -> dict[str, Any]:
        p = secrets_path()
        if not p.exists():
            return {"providers": {}}
        return json.loads(p.read_text(encoding="utf-8"))

    def _write_secrets(self, data: dict[str, Any]) -> None:
        p = secrets_path()
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            p.chmod(0o600)
        except OSError:
            pass

    def set_provider_key(self, provider_id: str, api_key: str) -> None:
        data = self._secrets()
        data.setdefault("providers", {})[provider_id] = api_key
        self._write_secrets(data)

    def get_provider_key(self, provider_id: str) -> str | None:
        return self._secrets().get("providers", {}).get(provider_id)

    # --- providers ---
    def create_provider(
        self,
        name: str,
        base_url: str,
        api_key: str | None,
        roles: dict[str, str],
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        pid = provider_id or _uid()
        self.execute(
            "INSERT INTO providers(id, name, base_url, created_at) VALUES (?,?,?,?)",
            (pid, name, base_url.rstrip("/"), _now()),
        )
        for role, model in roles.items():
            self.execute(
                "INSERT INTO provider_roles(provider_id, role, model) VALUES (?,?,?)",
                (pid, role, model),
            )
        if api_key:
            self.set_provider_key(pid, api_key)
        return self.get_provider(pid)  # type: ignore[return-value]

    def update_provider(
        self,
        provider_id: str,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        roles: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        row = self.get_provider(provider_id)
        if not row:
            return None
        if name:
            self.execute("UPDATE providers SET name=? WHERE id=?", (name, provider_id))
        if base_url:
            self.execute(
                "UPDATE providers SET base_url=? WHERE id=?",
                (base_url.rstrip("/"), provider_id),
            )
        if api_key:
            self.set_provider_key(provider_id, api_key)
        if roles is not None:
            self.execute("DELETE FROM provider_roles WHERE provider_id=?", (provider_id,))
            for role, model in roles.items():
                self.execute(
                    "INSERT INTO provider_roles(provider_id, role, model) VALUES (?,?,?)",
                    (provider_id, role, model),
                )
        return self.get_provider(provider_id)

    def list_providers(self) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM providers ORDER BY created_at")
        return [self._hydrate_provider(r) for r in rows]

    def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM providers WHERE id=?", (provider_id,))
        return self._hydrate_provider(row) if row else None

    def delete_provider(self, provider_id: str) -> None:
        self.execute("DELETE FROM provider_roles WHERE provider_id=?", (provider_id,))
        self.execute("DELETE FROM providers WHERE id=?", (provider_id,))
        data = self._secrets()
        data.get("providers", {}).pop(provider_id, None)
        self._write_secrets(data)

    def _hydrate_provider(self, row: dict[str, Any]) -> dict[str, Any]:
        roles = self.query(
            "SELECT role, model FROM provider_roles WHERE provider_id=?",
            (row["id"],),
        )
        key = self.get_provider_key(row["id"])
        return {
            **row,
            "roles": {r["role"]: r["model"] for r in roles},
            "has_key": bool(key),
        }

    # --- projects ---
    def create_project(self, data: dict[str, Any]) -> dict[str, Any]:
        pid = data.get("id") or _uid()
        now = _now()
        self.execute(
            """INSERT INTO projects(
                id, name, goal, description, kpi_json, profile, think_slots, exec_slots,
                status, workspace_path, provider_id, rigor, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                data["name"],
                data["goal"],
                data.get("description") or "",
                _json(data.get("kpi") or {}),
                data.get("profile") or "default",
                int(data.get("think_slots") or 4),
                int(data.get("exec_slots") or 1),
                "idle",
                data["workspace_path"],
                data.get("provider_id"),
                data.get("rigor") or "high",
                now,
                now,
            ),
        )
        self.init_memory_blocks(pid, data)
        return self.get_project(pid)  # type: ignore[return-value]

    def init_memory_blocks(self, project_id: str, data: dict[str, Any]) -> None:
        defaults = {
            "goal": data.get("goal") or "",
            "champion": "(none yet)",
            "open_questions": "",
            "bans": "",
            "budget": "early=novelty; do not run naive baselines if a stronger champion exists",
            "kpi": _json(data.get("kpi") or {}),
        }
        for key, content in defaults.items():
            self.patch_memory(project_id, key, content)

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM projects ORDER BY updated_at DESC")
        return [self._hydrate_project(r) for r in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
        return self._hydrate_project(row) if row else None

    def _hydrate_project(self, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        out["kpi"] = _parse(row.get("kpi_json"), {})
        return out

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_project(project_id)
        allowed = {
            "name",
            "goal",
            "description",
            "status",
            "champion_node_id",
            "think_slots",
            "exec_slots",
            "provider_id",
            "profile",
            "rigor",
            "last_event_seq",
        }
        sets = []
        params: list[Any] = []
        for k, v in fields.items():
            if k == "kpi":
                sets.append("kpi_json=?")
                params.append(_json(v))
            elif k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        sets.append("updated_at=?")
        params.append(_now())
        params.append(project_id)
        self.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", tuple(params))
        return self.get_project(project_id)

    # --- events / journal ---
    def append_event(
        self,
        project_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
        node_id: str | None = None,
        ts: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT last_event_seq FROM projects WHERE id=?",
                (project_id,),
            ).fetchone()
            seq = int(row["last_event_seq"] if row else 0) + 1
            event = {
                "project_id": project_id,
                "seq": seq,
                "ts": ts or _now(),
                "type": event_type,
                "agent_id": agent_id,
                "node_id": node_id,
                "payload": payload or {},
            }
            self._conn.execute(
                """INSERT INTO events(project_id, seq, ts, type, agent_id, node_id, payload_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    project_id,
                    seq,
                    event["ts"],
                    event_type,
                    agent_id,
                    node_id,
                    _json(payload or {}),
                ),
            )
            self._conn.execute(
                "UPDATE projects SET last_event_seq=?, updated_at=? WHERE id=?",
                (seq, event["ts"], project_id),
            )
            self._conn.commit()
            event["id"] = seq
            return event

    def list_events(
        self, project_id: str, after_seq: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]:
        rows = self.query(
            """SELECT * FROM events WHERE project_id=? AND seq>? ORDER BY seq LIMIT ?""",
            (project_id, after_seq, limit),
        )
        out = []
        for r in rows:
            item = dict(r)
            item["payload"] = _parse(r["payload_json"], {})
            out.append(item)
        return out

    def last_seq(self, project_id: str) -> int:
        row = self.query_one("SELECT last_event_seq FROM projects WHERE id=?", (project_id,))
        return int(row["last_event_seq"]) if row else 0

    # --- memory ---
    def patch_memory(self, project_id: str, key: str, content: str) -> None:
        self.execute(
            """INSERT INTO memory_blocks(project_id, key, content, updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(project_id, key) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at""",
            (project_id, key, content, _now()),
        )

    def get_memory(self, project_id: str) -> dict[str, str]:
        rows = self.query(
            "SELECT key, content FROM memory_blocks WHERE project_id=?",
            (project_id,),
        )
        return {r["key"]: r["content"] for r in rows}

    # --- archive ---
    def add_archive(self, doc: dict[str, Any]) -> dict[str, Any]:
        did = doc.get("id") or _uid()
        self.execute(
            """INSERT INTO archive_docs(
                id, project_id, kind, title, body, url, url_canon, query_canon,
                embedding, meta_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                did,
                doc["project_id"],
                doc["kind"],
                doc.get("title") or "",
                doc.get("body") or "",
                doc.get("url"),
                doc.get("url_canon"),
                doc.get("query_canon"),
                doc.get("embedding"),
                _json(doc.get("meta") or {}),
                _now(),
            ),
        )
        return self.query_one("SELECT * FROM archive_docs WHERE id=?", (did,))  # type: ignore

    def find_archive_url(self, project_id: str, url_canon: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM archive_docs WHERE project_id=? AND url_canon=?",
            (project_id, url_canon),
        )

    def find_archive_query(self, project_id: str, query_canon: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM archive_docs WHERE project_id=? AND query_canon=?",
            (project_id, query_canon),
        )

    def list_archive(self, project_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        if kind:
            return self.query(
                "SELECT * FROM archive_docs WHERE project_id=? AND kind=? ORDER BY created_at DESC",
                (project_id, kind),
            )
        return self.query(
            "SELECT * FROM archive_docs WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        )

    def iter_archive_with_embeddings(self, project_id: str) -> Iterator[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM archive_docs WHERE project_id=? AND embedding IS NOT NULL",
            (project_id,),
        )
        yield from rows

    # --- tree ---
    def add_tree_node(self, node: dict[str, Any]) -> dict[str, Any]:
        nid = node.get("id") or _uid()
        self.execute(
            """INSERT INTO tree_nodes(
                id, project_id, parent_id, kind, title, status, summary,
                metrics_json, cost_json, payload_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                nid,
                node["project_id"],
                node.get("parent_id"),
                node["kind"],
                node["title"],
                node.get("status") or "open",
                node.get("summary") or "",
                _json(node.get("metrics") or {}),
                _json(node.get("cost") or {}),
                _json(node.get("payload") or {}),
                _now(),
            ),
        )
        return self.get_tree_node(nid)  # type: ignore

    def get_tree_node(self, node_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM tree_nodes WHERE id=?", (node_id,))
        return self._hydrate_tree(row) if row else None

    def update_tree_node(self, node_id: str, **fields: Any) -> dict[str, Any] | None:
        mapping = {
            "status": "status",
            "summary": "summary",
            "title": "title",
            "parent_id": "parent_id",
        }
        sets = []
        params: list[Any] = []
        for k, v in fields.items():
            if k in ("metrics", "cost", "payload"):
                sets.append(f"{k}_json=?")
                params.append(_json(v))
            elif k in mapping:
                sets.append(f"{mapping[k]}=?")
                params.append(v)
        if not sets:
            return self.get_tree_node(node_id)
        params.append(node_id)
        self.execute(f"UPDATE tree_nodes SET {', '.join(sets)} WHERE id=?", tuple(params))
        return self.get_tree_node(node_id)

    def list_tree(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM tree_nodes WHERE project_id=? ORDER BY created_at",
            (project_id,),
        )
        return [self._hydrate_tree(r) for r in rows]

    def _hydrate_tree(self, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["metrics"] = _parse(row.get("metrics_json"), {})
        item["cost"] = _parse(row.get("cost_json"), {})
        item["payload"] = _parse(row.get("payload_json"), {})
        return item

    # --- hypotheses ---
    def add_hypothesis(self, hyp: dict[str, Any]) -> dict[str, Any]:
        hid = hyp.get("id") or _uid()
        self.execute(
            """INSERT INTO hypotheses(
                id, project_id, line_id, type, mechanism, fingerprint, text,
                status, virtual_score, parent_hyp_id, node_id, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                hid,
                hyp["project_id"],
                hyp.get("line_id") or hid,
                hyp.get("type") or "explore",
                hyp["mechanism"],
                hyp.get("fingerprint") or "",
                hyp["text"],
                hyp.get("status") or "queued",
                hyp.get("virtual_score"),
                hyp.get("parent_hyp_id"),
                hyp.get("node_id"),
                _now(),
            ),
        )
        return self.get_hypothesis(hid)  # type: ignore

    def get_hypothesis(self, hyp_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM hypotheses WHERE id=?", (hyp_id,))

    def list_hypotheses(self, project_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM hypotheses WHERE project_id=? ORDER BY created_at",
            (project_id,),
        )

    def update_hypothesis(self, hyp_id: str, **fields: Any) -> None:
        if not fields:
            return
        sets = []
        params: list[Any] = []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            params.append(v)
        params.append(hyp_id)
        self.execute(f"UPDATE hypotheses SET {', '.join(sets)} WHERE id=?", tuple(params))

    def recent_hypothesis_types(self, project_id: str, n: int = 5) -> list[dict[str, Any]]:
        return self.query(
            """SELECT * FROM hypotheses WHERE project_id=? AND status IN ('tested','promoted','rejected','selected')
               ORDER BY created_at DESC LIMIT ?""",
            (project_id, n),
        )

    # --- cemetery ---
    def add_cemetery(self, item: dict[str, Any]) -> dict[str, Any]:
        cid = item.get("id") or _uid()
        self.execute(
            """INSERT INTO cemetery(id, project_id, mechanism_class, fingerprint, lesson, embedding, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                cid,
                item["project_id"],
                item["mechanism_class"],
                item.get("fingerprint") or "",
                item.get("lesson") or "",
                item.get("embedding"),
                _now(),
            ),
        )
        return self.query_one("SELECT * FROM cemetery WHERE id=?", (cid,))  # type: ignore

    def list_cemetery(self, project_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM cemetery WHERE project_id=? ORDER BY created_at",
            (project_id,),
        )

    # --- runs / metrics ---
    def add_run(self, run: dict[str, Any]) -> dict[str, Any]:
        rid = run.get("id") or _uid()
        self.execute(
            """INSERT INTO runs(id, project_id, hypothesis_id, node_id, phase, status, params_json, metrics_json, log_path, started_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                rid,
                run["project_id"],
                run.get("hypothesis_id"),
                run.get("node_id"),
                run.get("phase") or "screen",
                run.get("status") or "running",
                _json(run.get("params") or {}),
                _json(run.get("metrics") or {}),
                run.get("log_path"),
                _now(),
            ),
        )
        return self.get_run(rid)  # type: ignore

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM runs WHERE id=?", (run_id,))
        if not row:
            return None
        item = dict(row)
        item["params"] = _parse(row["params_json"], {})
        item["metrics"] = _parse(row["metrics_json"], {})
        return item

    def update_run(self, run_id: str, **fields: Any) -> None:
        sets = []
        params: list[Any] = []
        for k, v in fields.items():
            if k in ("params", "metrics"):
                sets.append(f"{k}_json=?")
                params.append(_json(v))
            else:
                sets.append(f"{k}=?")
                params.append(v)
        params.append(run_id)
        self.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id=?", tuple(params))

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM runs WHERE project_id=? ORDER BY started_at",
            (project_id,),
        )
        out = []
        for r in rows:
            item = dict(r)
            item["params"] = _parse(r["params_json"], {})
            item["metrics"] = _parse(r["metrics_json"], {})
            out.append(item)
        return out

    def add_metric_point(self, run_id: str, name: str, value: float, step: int = 0) -> None:
        self.execute(
            "INSERT INTO metric_points(run_id, name, step, value, ts) VALUES (?,?,?,?,?)",
            (run_id, name, step, value, _now()),
        )

    def metrics_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return self.query(
            """SELECT m.*, r.hypothesis_id, r.phase FROM metric_points m
               JOIN runs r ON r.id = m.run_id WHERE r.project_id=? ORDER BY m.ts""",
            (project_id,),
        )

    # --- cost ---
    def add_cost(self, row: dict[str, Any]) -> None:
        self.execute(
            """INSERT INTO cost_ledger(project_id, ts, model, role, prompt_tokens, completion_tokens, cost_rub, cost_usd, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                row["project_id"],
                _now(),
                row.get("model") or "",
                row.get("role") or "",
                int(row.get("prompt_tokens") or 0),
                int(row.get("completion_tokens") or 0),
                row.get("cost_rub"),
                row.get("cost_usd"),
                _json(row.get("meta") or {}),
            ),
        )

    def cost_summary(self, project_id: str) -> dict[str, Any]:
        row = self.query_one(
            """SELECT COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,
                      COALESCE(SUM(completion_tokens),0) AS completion_tokens,
                      COALESCE(SUM(cost_rub),0) AS cost_rub,
                      COALESCE(SUM(cost_usd),0) AS cost_usd,
                      COUNT(*) AS calls
               FROM cost_ledger WHERE project_id=?""",
            (project_id,),
        )
        by_model = self.query(
            """SELECT model, role, SUM(prompt_tokens) AS prompt_tokens,
                      SUM(completion_tokens) AS completion_tokens,
                      SUM(cost_rub) AS cost_rub, COUNT(*) AS calls
               FROM cost_ledger WHERE project_id=? GROUP BY model, role""",
            (project_id,),
        )
        return {**(row or {}), "by_model": by_model}

    # --- search cache ---
    def cache_search(self, item: dict[str, Any]) -> None:
        self.execute(
            """INSERT OR REPLACE INTO search_cache(id, project_id, query_canon, url_canon, source, result_json, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                item.get("id") or _uid(),
                item["project_id"],
                item.get("query_canon"),
                item.get("url_canon"),
                item["source"],
                _json(item.get("result") or {}),
                _now(),
            ),
        )

    def get_search_cache(
        self, project_id: str, query_canon: str | None = None, url_canon: str | None = None
    ) -> dict[str, Any] | None:
        if query_canon:
            row = self.query_one(
                "SELECT * FROM search_cache WHERE project_id=? AND query_canon=?",
                (project_id, query_canon),
            )
        elif url_canon:
            row = self.query_one(
                "SELECT * FROM search_cache WHERE project_id=? AND url_canon=?",
                (project_id, url_canon),
            )
        else:
            return None
        if not row:
            return None
        item = dict(row)
        item["result"] = _parse(row["result_json"], {})
        return item

    # --- blackboard ---
    def claim(self, project_id: str, claim_type: str, key: str, owner: str, meta: dict | None = None) -> bool:
        existing = self.query_one(
            "SELECT owner_agent FROM blackboard WHERE project_id=? AND claim_type=? AND claim_key=?",
            (project_id, claim_type, key),
        )
        if existing:
            return existing["owner_agent"] == owner
        self.execute(
            """INSERT INTO blackboard(project_id, claim_type, claim_key, owner_agent, meta_json, created_at)
               VALUES (?,?,?,?,?,?)""",
            (project_id, claim_type, key, owner, _json(meta or {}), _now()),
        )
        return True

    def release(self, project_id: str, claim_type: str, key: str) -> None:
        self.execute(
            "DELETE FROM blackboard WHERE project_id=? AND claim_type=? AND claim_key=?",
            (project_id, claim_type, key),
        )

    def list_claims(self, project_id: str) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM blackboard WHERE project_id=?", (project_id,))

    # --- artifacts ---
    def add_artifact(self, art: dict[str, Any]) -> dict[str, Any]:
        aid = art.get("id") or _uid()
        self.execute(
            """INSERT INTO artifacts(id, project_id, filename, path, mime, status, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                aid,
                art["project_id"],
                art["filename"],
                art["path"],
                art.get("mime"),
                art.get("status") or "pending",
                _now(),
            ),
        )
        return self.query_one("SELECT * FROM artifacts WHERE id=?", (aid,))  # type: ignore

    def list_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at",
            (project_id,),
        )

    def update_artifact(self, artifact_id: str, **fields: Any) -> None:
        sets = []
        params: list[Any] = []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            params.append(v)
        params.append(artifact_id)
        self.execute(f"UPDATE artifacts SET {', '.join(sets)} WHERE id=?", tuple(params))

    # --- human chat ---
    def add_human_message(self, project_id: str, role: str, content: str) -> dict[str, Any]:
        mid = _uid()
        ts = _now()
        self.execute(
            "INSERT INTO human_messages(id, project_id, role, content, ts) VALUES (?,?,?,?,?)",
            (mid, project_id, role, content, ts),
        )
        return {"id": mid, "project_id": project_id, "role": role, "content": content, "ts": ts}

    def list_human_messages(self, project_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM human_messages WHERE project_id=? ORDER BY ts",
            (project_id,),
        )

    # --- plugins enabled ---
    def set_plugin_enabled(self, project_id: str, plugin_id: str, enabled: bool, config: dict | None = None) -> None:
        self.execute(
            """INSERT INTO plugins_enabled(project_id, plugin_id, enabled, config_json)
               VALUES (?,?,?,?)
               ON CONFLICT(project_id, plugin_id) DO UPDATE SET enabled=excluded.enabled, config_json=excluded.config_json""",
            (project_id, plugin_id, 1 if enabled else 0, _json(config or {})),
        )

    def enabled_plugins(self, project_id: str) -> dict[str, dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM plugins_enabled WHERE project_id=?",
            (project_id,),
        )
        return {r["plugin_id"]: r for r in rows}

    # --- graph ---
    def add_graph_node(self, node: dict[str, Any]) -> None:
        self.execute(
            """INSERT OR REPLACE INTO graph_nodes(id, project_id, kind, label, data_json) VALUES (?,?,?,?,?)""",
            (
                node["id"],
                node["project_id"],
                node["kind"],
                node["label"],
                _json(node.get("data") or {}),
            ),
        )

    def add_graph_edge(self, project_id: str, src: str, dst: str, rel: str) -> None:
        self.execute(
            "INSERT INTO graph_edges(id, project_id, src, dst, rel) VALUES (?,?,?,?,?)",
            (_uid(), project_id, src, dst, rel),
        )

    def get_graph(self, project_id: str) -> dict[str, Any]:
        nodes = self.query("SELECT * FROM graph_nodes WHERE project_id=?", (project_id,))
        edges = self.query("SELECT * FROM graph_edges WHERE project_id=?", (project_id,))
        for n in nodes:
            n["data"] = _parse(n.get("data_json"), {})
        return {"nodes": nodes, "edges": edges}


_STORE: Store | None = None


def get_store() -> Store:
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE


def reset_store_for_tests(path: Path) -> Store:
    global _STORE
    _STORE = Store(path)
    return _STORE
