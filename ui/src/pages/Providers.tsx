import { FormEvent, useEffect, useState } from "react";
import { api, Provider } from "../api";

const PRESET: Record<string, string> = {
  orchestrator: "openai/gpt-4.1",
  researcher: "openai/gpt-4o-mini",
  critic: "openai/gpt-4.1",
  coder: "openai/gpt-4.1",
};

export function ProvidersPage() {
  const [items, setItems] = useState<Provider[]>([]);
  const [name, setName] = useState("Polza");
  const [base, setBase] = useState("https://polza.ai/api/v1");
  const [key, setKey] = useState("");
  const [roles, setRoles] = useState({ ...PRESET });
  const [models, setModels] = useState<string[]>([]);
  const [err, setErr] = useState("");

  async function load() {
    setItems(await api("/api/providers"));
  }
  useEffect(() => {
    load().catch((e) => setErr(String(e)));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr("");
    await api("/api/providers", {
      method: "POST",
      body: JSON.stringify({ name, base_url: base, api_key: key, roles }),
    });
    setKey("");
    await load();
  }

  async function fetchModels(id: string) {
    const data = await api<{ models: { id: string }[] }>(`/api/providers/${id}/models`);
    setModels((data.models || []).map((m) => m.id).slice(0, 40));
  }

  return (
    <>
      <h1>LLM providers</h1>
      <p className="muted">
        OpenAI-compatible base URL. Polza default: <code>https://polza.ai/api/v1</code>. Keys stay in{" "}
        <code>data/secrets.json</code> (mode 600).
      </p>
      {err && <p className="pill bad">{err}</p>}
      <form className="form card" onSubmit={onSubmit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Base URL
          <input value={base} onChange={(e) => setBase(e.target.value)} />
        </label>
        <label>
          API key
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        {Object.keys(roles).map((role) => (
          <label key={role}>
            Model · {role}
            <input
              value={roles[role as keyof typeof roles]}
              onChange={(e) => setRoles({ ...roles, [role]: e.target.value })}
            />
          </label>
        ))}
        <button className="primary" type="submit">
          Save provider
        </button>
      </form>
      <h2>Saved</h2>
      <div className="cards">
        {items.map((p) => (
          <div className="card" key={p.id}>
            <strong>{p.name}</strong>
            <div className="muted">{p.base_url}</div>
            <div className="pill">{p.has_key ? "key stored" : "no key"}</div>
            <pre className="muted" style={{ whiteSpace: "pre-wrap" }}>
              {JSON.stringify(p.roles, null, 2)}
            </pre>
            <button onClick={() => fetchModels(p.id)}>List remote models</button>
          </div>
        ))}
      </div>
      {models.length > 0 && (
        <div className="card">
          <h2>Remote catalog (first 40)</h2>
          <div className="muted">{models.join(" · ")}</div>
        </div>
      )}
    </>
  );
}
