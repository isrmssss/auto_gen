import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Project, Provider, uploadArtifact } from "../api";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [goal, setGoal] = useState("");
  const [ideas, setIdeas] = useState("");
  const [provider, setProvider] = useState("");
  const [agents, setAgents] = useState(5);
  const [exec, setExec] = useState(1);
  const [rigor, setRigor] = useState("high");
  const [kpiName, setKpiName] = useState("primary");
  const [higher, setHigher] = useState(true);
  const [inputs, setInputs] = useState<File[]>([]);
  const [outputs, setOutputs] = useState<File[]>([]);
  const [extras, setExtras] = useState<File[]>([]);
  const [extraPrompt, setExtraPrompt] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

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
    setBusy(true);
    setErr("");
    try {
      const created = await api<Project>("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          name,
          goal,
          prompt,
          user_ideas: ideas,
          provider_id: provider || null,
          think_slots: agents,
          exec_slots: exec,
          rigor,
          kpi: { primary: kpiName || "primary", higher_is_better: higher },
        }),
      });
      for (const f of inputs) await uploadArtifact(created.id, f, "input");
      for (const f of outputs) await uploadArtifact(created.id, f, "output");
      for (const f of extras) await uploadArtifact(created.id, f, "extra", extraPrompt);
      window.location.href = `/projects/${created.id}`;
    } catch (ex) {
      setErr(String(ex));
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Проекты</h1>
      <p className="muted">
        Каждый проект — изолированная рабочая папка. Оркестратор не видит соседние проекты.
      </p>
      {err && <p className="pill bad">{err}</p>}
      <form className="form card form-wide" onSubmit={onSubmit}>
        <label>
          Имя
          <span className="hint">Как найти проект в списке.</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Промпт
          <span className="hint">
            Постановка: условие хакатона, «расшифруй письмо», ограничения, что уже пробовали.
          </span>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Например: хакатон по табличным данным, вот описание и ограничения…"
          />
        </label>
        <label>
          Цель
          <span className="hint">Критерий готовности. Отдельно от постановки.</span>
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Расшифрованный текст на русском / метрика лучше baseline"
            required
          />
        </label>
        <div className="row">
          <label style={{ flex: 1 }}>
            Метрика
            <span className="hint">Имя числа, по которому сравнивают прогоны.</span>
            <input value={kpiName} onChange={(e) => setKpiName(e.target.value)} />
          </label>
          <label>
            Направление
            <span className="hint">Больше — лучше или меньше.</span>
            <select value={higher ? "up" : "down"} onChange={(e) => setHigher(e.target.value === "up")}>
              <option value="up">больше лучше</option>
              <option value="down">меньше лучше</option>
            </select>
          </label>
        </div>
        <label>
          Идеи и ограничения (необязательно)
          <span className="hint">Попадёт в открытые вопросы, не заменяет промпт и цель.</span>
          <textarea value={ideas} onChange={(e) => setIdeas(e.target.value)} />
        </label>
        <div className="file-cols">
          <label className="drop">
            Вход
            <span className="hint">Как на Kaggle: датасет, фото письма — то, что видит эксперимент.</span>
            <input type="file" multiple onChange={(e) => setInputs(Array.from(e.target.files || []))} />
            <span className="muted">{inputs.length ? inputs.map((f) => f.name).join(", ") : "пусто"}</span>
          </label>
          <label className="drop">
            Выход
            <span className="hint">Чекпоинты, эталон, результаты прогонов.</span>
            <input type="file" multiple onChange={(e) => setOutputs(Array.from(e.target.files || []))} />
            <span className="muted">{outputs.length ? outputs.map((f) => f.name).join(", ") : "пусто"}</span>
          </label>
          <label className="drop">
            Дополнительно
            <span className="hint">Статья или заметка. С промптом ниже сразу встанет в очередь гипотез.</span>
            <input type="file" multiple onChange={(e) => setExtras(Array.from(e.target.files || []))} />
            <span className="muted">{extras.length ? extras.map((f) => f.name).join(", ") : "пусто"}</span>
            <input
              placeholder='Промпт к файлу, например «проверь эту идею»'
              value={extraPrompt}
              onChange={(e) => setExtraPrompt(e.target.value)}
            />
          </label>
        </div>
        <label>
          Провайдер
          <span className="hint">Чья модель думает. Без ключа проект создаётся, старт объяснит, чего не хватает.</span>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">(пока нет)</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.has_key ? "" : " — нет ключа"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Агенты
          <span className="hint">Сколько параллельных думающих слотов. 1 — всё по очереди.</span>
          <select value={agents} onChange={(e) => setAgents(Number(e.target.value))}>
            {[1, 5, 10, 15].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Слоты запуска
          <span className="hint">Сколько экспериментов одновременно. Железо может урезать.</span>
          <input type="number" min={1} max={4} value={exec} onChange={(e) => setExec(Number(e.target.value))} />
        </label>
        <label>
          Строгость
          <span className="hint">Насколько жёстко отсекаются наивные идеи.</span>
          <select value={rigor} onChange={(e) => setRigor(e.target.value)}>
            <option value="low">низкая</option>
            <option value="high">высокая (без наивных baseline)</option>
            <option value="extreme">крайняя</option>
          </select>
        </label>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Создаю…" : "Создать изолированный проект"}
        </button>
      </form>
      <h2>Существующие</h2>
      <div className="cards">
        {projects.map((p) => (
          <Link className="card" key={p.id} to={`/projects/${p.id}`}>
            <strong>{p.name}</strong>
            <div>
              <span className={`pill ${p.status === "running" ? "run" : ""}`}>{p.status}</span>
            </div>
            <p className="muted">{(p.goal || "").slice(0, 180)}</p>
          </Link>
        ))}
      </div>
    </>
  );
}
