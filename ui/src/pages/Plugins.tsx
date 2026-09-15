import { useEffect, useState } from "react";
import { api, PluginInfo } from "../api";

export function PluginsPage() {
  const [items, setItems] = useState<PluginInfo[]>([]);
  useEffect(() => {
    api<PluginInfo[]>("/api/plugins").then(setItems);
  }, []);
  const bundles = [...new Set(items.map((p) => p.bundle))];
  return (
    <>
      <h1>Plugin catalog</h1>
      <p className="muted">
        Everything is a plugin. Add a folder under <code>src/openrd/plugins/&lt;name&gt;/plugin.yaml</code> and one line
        in the profile. The LLM sees this catalog, not hardcoded APIs.
      </p>
      {bundles.map((b) => (
        <section key={b}>
          <h2>{b}</h2>
          <div className="cards">
            {items
              .filter((p) => p.bundle === b)
              .map((p) => (
                <div className="card" key={p.id}>
                  <div className="pill">{p.id}</div>
                  <strong>{p.title}</strong>
                  <p>{p.description}</p>
                  <p className="muted">When: {p.when_to_use}</p>
                </div>
              ))}
          </div>
        </section>
      ))}
    </>
  );
}
