import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Project, Provider } from "../api";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [ideas, setIdeas] = useState("");
  const [provider, setProvider] = useState("");
  const [agents, setAgents] = useState(5);
  const [exec, setExec] = useState(1);
  const [rigor, setRigor] = useState("high");
  const [err, setErr] = useState("");

  async function load() {
    const [ps, pr] = await Promise.all([api<Project[]>("/api/projects"), api<Provider[]>("/api/providers")]);
    setProjects(ps);
    setProviders(pr);
    if (!provider && pr[0]) setProvider(pr[0].id);
  }
  useEffect(() => {
    load().catch((e) => setErr(String(e)));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const created = await api<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({
        name,
        goal,
        user_ideas: ideas,
        provider_id: provider || null,
        think_slots: agents,
        exec_slots: exec,
        rigor,
        kpi: { primary: "primary", higher_is_better: false },
      }),
    });
    window.location.href = `/projects/${created.id}`;
  }

  return (
    <>
      <h1>Projects</h1>
      <p className="muted">Each project gets an isolated workspace. The orchestrator cannot see other projects.</p>
      {err && <p className="pill bad">{err}</p>}
      <form className="form card" onSubmit={onSubmit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Goal
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Hackathon task, product KPI, or a research question. Be specific about the metric and the bar (e.g. top-1)."
            required
          />
        </label>
        <label>
          Your ideas / constraints (optional)
          <textarea value={ideas} onChange={(e) => setIdeas(e.target.value)} />
        </label>
        <label>
          Provider
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">(none yet)</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Agents (1 sequential · 5 = 1 orchestrator + 4 think)
          <select value={agents} onChange={(e) => setAgents(Number(e.target.value))}>
            {[1, 5, 10, 15].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Exec slots (code runs; hardware-gated)
          <input type="number" min={1} max={4} value={exec} onChange={(e) => setExec(Number(e.target.value))} />
        </label>
        <label>
          Rigor
          <select value={rigor} onChange={(e) => setRigor(e.target.value)}>
            <option value="low">low</option>
            <option value="high">high (reject naive baselines)</option>
            <option value="extreme">extreme</option>
          </select>
        </label>
        <button className="primary" type="submit">
          Create isolated project
        </button>
      </form>
      <h2>Existing</h2>
      <div className="cards">
        {projects.map((p) => (
          <Link className="card" key={p.id} to={`/projects/${p.id}`}>
            <strong>{p.name}</strong>
            <div>
              <span className={`pill ${p.status === "running" ? "run" : ""}`}>{p.status}</span>
            </div>
            <p className="muted">{p.goal.slice(0, 180)}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
