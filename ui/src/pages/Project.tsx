import { FormEvent, type ReactElement, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, PluginInfo, Project, TreeNode } from "../api";

type EventRow = {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  ts: string;
  agent_id?: string;
};

export function ProjectPage() {
  const { id } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [selected, setSelected] = useState<TreeNode | null>(null);
  const [chat, setChat] = useState("");
  const [metrics, setMetrics] = useState<{ name: string; value: number; step: number }[]>([]);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [cost, setCost] = useState<Record<string, unknown>>({});
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    if (!id) return;
    const [p, t, e, m, pl, c] = await Promise.all([
      api<Project>(`/api/projects/${id}`),
      api<TreeNode[]>(`/api/projects/${id}/tree`),
      api<EventRow[]>(`/api/projects/${id}/events`),
      api<{ name: string; value: number; step: number }[]>(`/api/projects/${id}/metrics`),
      api<PluginInfo[]>(`/api/projects/${id}/plugins`),
      api<Record<string, unknown>>(`/api/projects/${id}/cost`),
    ]);
    setProject(p);
    setTree(t);
    setEvents(e);
    setMetrics(m);
    setPlugins(pl);
    setCost(c);
  }

  useEffect(() => {
    refresh().catch(console.error);
  }, [id]);

  useEffect(() => {
    if (!id) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/projects/${id}/stream`);
    ws.onmessage = (ev) => {
      try {
        const row = JSON.parse(ev.data);
        if (row.seq) {
          setEvents((prev) => {
            if (prev.some((x) => x.seq === row.seq)) return prev;
            return [...prev, row].slice(-400);
          });
        }
      } catch {
        /* ignore */
      }
    };
    const t = setInterval(() => refresh().catch(() => undefined), 4000);
    return () => {
      ws.close();
      clearInterval(t);
    };
  }, [id]);

  const byParent = useMemo(() => {
    const m = new Map<string | null, TreeNode[]>();
    for (const n of tree) {
      const k = n.parent_id || null;
      m.set(k, [...(m.get(k) || []), n]);
    }
    return m;
  }, [tree]);

  function renderNodes(parent: string | null, depth: number): ReactElement[] {
    return (byParent.get(parent) || []).flatMap((n) => [
      <div
        key={n.id}
        className={`node ${selected?.id === n.id ? "selected" : ""}`}
        style={{ ["--d" as string]: depth }}
        onClick={() => setSelected(n)}
      >
        <span className="pill">{n.kind}</span> {n.title} <span className="muted">{n.status}</span>
        {n.metrics && Object.keys(n.metrics).length > 0 && (
          <span className="muted"> · {JSON.stringify(n.metrics)}</span>
        )}
      </div>,
      ...renderNodes(n.id, depth + 1),
    ]);
  }

  async function action(path: string) {
    await api(`/api/projects/${id}/${path}`, { method: "POST", body: "{}" });
    await refresh();
  }

  async function steer(e: FormEvent) {
    e.preventDefault();
    await api(`/api/projects/${id}/steer`, {
      method: "POST",
      body: JSON.stringify({ kind: "steer", content: chat }),
    });
    setChat("");
    await refresh();
  }

  async function rollback() {
    if (!selected) return;
    await api(`/api/projects/${id}/rollback`, {
      method: "POST",
      body: JSON.stringify({ kind: "rollback", node_id: selected.id, content: selected.id }),
    });
    await refresh();
  }

  async function upload(f: File) {
    const fd = new FormData();
    fd.append("file", f);
    await fetch(`/api/projects/${id}/artifacts`, { method: "POST", body: fd });
    await refresh();
  }

  const chartData = metrics.map((m, i) => ({ i, [m.name]: m.value, name: m.name }));

  if (!project) return <p className="muted">Loading…</p>;

  return (
    <>
      <div className="row">
        <h1 style={{ margin: 0 }}>{project.name}</h1>
        <span className={`pill ${project.status === "running" ? "run" : ""}`}>{project.status}</span>
      </div>
      <p>{project.goal}</p>
      <div className="row">
        <button className="primary" onClick={() => action("start")}>
          Start
        </button>
        <button onClick={() => action("pause")}>Pause</button>
        <button onClick={() => action("resume")}>Resume</button>
        <button onClick={() => action("stop")}>Stop</button>
        <button onClick={rollback} disabled={!selected}>
          Rollback to node
        </button>
        <span className="muted">
          think {project.think_slots} · exec {project.exec_slots}
        </span>
      </div>

      <div className="cards" style={{ marginTop: "1rem" }}>
        <div className="card">
          <div className="muted">Cost</div>
          <strong>
            {Number(cost.cost_rub || 0).toFixed(4)} ₽ · {Number(cost.cost_usd || 0).toFixed(4)} $
          </strong>
          <div className="muted">
            tokens {(cost.prompt_tokens as number) || 0} + {(cost.completion_tokens as number) || 0} · calls{" "}
            {(cost.calls as number) || 0}
          </div>
        </div>
        <div className="card">
          <div className="muted">Champion</div>
          <div>{project.memory?.champion || "(none)"}</div>
        </div>
        <div className="card">
          <div className="muted">Hardware</div>
          <pre className="muted" style={{ whiteSpace: "pre-wrap" }}>
            {JSON.stringify(project.hw, null, 2)?.slice(0, 400)}
          </pre>
        </div>
      </div>

      <div className="split" style={{ marginTop: "1rem" }}>
        <div>
          <h2>Search / hypothesis tree</h2>
          <div className="tree">{renderNodes(null, 0)}</div>
          {selected && (
            <div className="card" style={{ marginTop: "0.8rem" }}>
              <strong>{selected.title}</strong>
              <p>{selected.summary}</p>
              <pre className="log">{JSON.stringify(selected.payload, null, 2)}</pre>
            </div>
          )}
        </div>
        <div>
          <h2>Steer</h2>
          <form onSubmit={steer} className="form">
            <textarea
              value={chat}
              onChange={(e) => setChat(e.target.value)}
              placeholder="Ask, redirect, inject a constraint. Research continues."
            />
            <button className="primary" type="submit">
              Send
            </button>
          </form>
          <div className="row" style={{ marginTop: "0.6rem" }}>
            <button onClick={() => fileRef.current?.click()}>Drop PDF / notes</button>
            <input
              ref={fileRef}
              type="file"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload(f);
              }}
            />
          </div>
          <h2>Live journal</h2>
          <div className="log">
            {events
              .slice(-80)
              .map((e) => `#${e.seq} ${e.type} ${JSON.stringify(e.payload).slice(0, 220)}`)
              .join("\n")}
          </div>
        </div>
      </div>

      <h2>Metrics</h2>
      <div className="card" style={{ height: 280 }}>
        {metrics.length === 0 ? (
          <p className="muted">No metric points yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={metrics.map((m, i) => ({ i, value: m.value, name: m.name }))}>
              <CartesianGrid stroke="#2a3340" />
              <XAxis dataKey="i" stroke="#8b98a8" />
              <YAxis stroke="#8b98a8" />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="value" stroke="#d4a054" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <h2>Core memory</h2>
      <pre className="log">{JSON.stringify(project.memory, null, 2)}</pre>

      <h2>Plugins for this project</h2>
      <table>
        <thead>
          <tr>
            <th>id</th>
            <th>on</th>
            <th>when</th>
          </tr>
        </thead>
        <tbody>
          {plugins.map((p) => (
            <tr key={p.id}>
              <td>{p.id}</td>
              <td>{p.enabled === false ? "off" : "on"}</td>
              <td className="muted">{p.when_to_use}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
