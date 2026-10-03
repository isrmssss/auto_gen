import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
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
import {
  api,
  Artifact,
  Ask,
  Job,
  PluginInfo,
  Project,
  SecretMeta,
  TreeNode,
  uploadArtifact,
} from "../api";

type EventRow = {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  ts: string;
  agent_id?: string;
};

const COLUMNS: { id: string; title: string; kinds: string[] }[] = [
  { id: "formalize", title: "Формализация", kinds: ["goal", "formalize"] },
  { id: "structures", title: "Структуры", kinds: ["structure"] },
  { id: "domains", title: "Области", kinds: ["domain"] },
  { id: "methods", title: "Методы", kinds: ["method"] },
  { id: "papers", title: "Статьи", kinds: ["paper"] },
  { id: "hypotheses", title: "Гипотезы", kinds: ["hypothesis"] },
  { id: "experiments", title: "Эксперименты", kinds: ["run"] },
  { id: "selection", title: "Отбор", kinds: ["cemetery"] },
];

const LINE_COLORS = ["#d4a054", "#7eb8d4", "#6fbf8b", "#d36b6b", "#c9a0dc"];

function humanEvent(e: EventRow): string {
  const p = e.payload || {};
  switch (e.type) {
    case "search.query":
      return `Ищу статьи: ${p.query || p.q || ""}`;
    case "search.hit":
      return `Нашёл: ${p.title || p.url || ""}`;
    case "search.skipped":
      return `Пропуск: ${p.reason || "уже пробовали"}`;
    case "paper.ingested":
      return `Прочитал статью «${p.title || p.paper_key || ""}», в модель ушла карточка`;
    case "hypothesis.proposed":
      return `Гипотеза: ${p.mechanism || p.title || ""}`;
    case "hypothesis.rejected":
      return `Гипотеза отброшена: ${p.reason || p.reject_reason || p.mechanism || ""}`;
    case "hypothesis.selected":
      return `Выбрана гипотеза: ${p.mechanism || ""}`;
    case "run.started":
      return `Запуск ${p.phase || "прогона"}`;
    case "run.finished":
      return `Прогон готов`;
    case "run.failed":
      return `Прогон не удался: ${p.error || ""}`;
    case "funnel.step":
      return p.skip_math
        ? "Короткий путь: расшифровка/разбор входа, математическая гребёнка пропущена"
        : `Воронка, уровень ${p.level ?? ""}`;
    case "human.question":
      return `Модель спрашивает (${p.kind || "уточнение"})`;
    case "human.ask.answered":
      return p.declined ? "Отказ на вопрос модели" : "Ответ на вопрос модели получен";
    case "job.ready":
      return `Работа ${p.kind || ""} идёт параллельно`;
    case "agent.thought":
      return String(p.text || "").slice(0, 180);
    case "phase.enter":
      return `Фаза: ${p.phase}`;
    case "phase.exit":
      return "";
    case "safety.block":
      return "Сработало правило безопасности";
    case "project.created":
      return "Проект создан";
    case "project.started":
      return "Исследование запущено";
    case "provider.missing":
      return "Нет провайдера модели: формализация идёт, LLM-шаги пропущены";
    default:
      return e.type;
  }
}

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
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [asks, setAsks] = useState<Ask[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [secrets, setSecrets] = useState<SecretMeta[]>([]);
  const [secretName, setSecretName] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [secretNote, setSecretNote] = useState("");
  const [askDraft, setAskDraft] = useState<Record<string, string>>({});
  const [rawLog, setRawLog] = useState(false);
  const [editPrompt, setEditPrompt] = useState("");
  const [editGoal, setEditGoal] = useState("");
  const fileRefs = {
    input: useRef<HTMLInputElement>(null),
    output: useRef<HTMLInputElement>(null),
    extra: useRef<HTMLInputElement>(null),
  };
  const [extraPrompt, setExtraPrompt] = useState("");

  async function refresh() {
    if (!id) return;
    const [p, t, e, m, pl, c, arts, as, js, sc] = await Promise.all([
      api<Project>(`/api/projects/${id}`),
      api<TreeNode[]>(`/api/projects/${id}/tree`),
      api<EventRow[]>(`/api/projects/${id}/events`),
      api<{ name: string; value: number; step: number }[]>(`/api/projects/${id}/metrics`),
      api<PluginInfo[]>(`/api/projects/${id}/plugins`),
      api<Record<string, unknown>>(`/api/projects/${id}/cost`),
      api<Artifact[]>(`/api/projects/${id}/artifacts`),
      api<Ask[]>(`/api/projects/${id}/asks`),
      api<Job[]>(`/api/projects/${id}/jobs`),
      api<SecretMeta[]>(`/api/projects/${id}/secrets`),
    ]);
    setProject(p);
    setTree(t);
    setEvents(e);
    setMetrics(m);
    setPlugins(pl);
    setCost(c);
    setArtifacts(arts);
    setAsks(as);
    setJobs(js);
    setSecrets(sc);
    setEditPrompt(p.prompt || p.memory?.prompt || "");
    setEditGoal(p.goal);
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

  const byKind = useMemo(() => {
    const m = new Map<string, TreeNode[]>();
    for (const n of tree) {
      m.set(n.kind, [...(m.get(n.kind) || []), n]);
    }
    return m;
  }, [tree]);

  const metricNames = useMemo(() => Array.from(new Set(metrics.map((x) => x.name))), [metrics]);
  const chartRows = useMemo(() => {
    const byStep = new Map<number, Record<string, number | string>>();
    metrics.forEach((pt, i) => {
      const step = pt.step || i;
      const row = byStep.get(step) || { step };
      row[pt.name] = pt.value;
      byStep.set(step, row);
    });
    return Array.from(byStep.values());
  }, [metrics]);

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

  async function saveBrief() {
    await api(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ prompt: editPrompt, goal: editGoal }),
    });
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

  async function upload(role: string, f: File) {
    await uploadArtifact(id!, f, role, role === "extra" ? extraPrompt : "");
    await refresh();
  }

  async function replyAsk(ask: Ask, decline = false) {
    const body: Record<string, unknown> = { decline };
    if (ask.kind === "secret") body.secret_value = askDraft[ask.id] || "";
    else body.answer = askDraft[ask.id] || "";
    await api(`/api/projects/${id}/asks/${ask.id}/reply`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setAskDraft((d) => ({ ...d, [ask.id]: "" }));
    await refresh();
  }

  async function saveSecret(e: FormEvent) {
    e.preventDefault();
    await api(`/api/projects/${id}/secrets`, {
      method: "POST",
      body: JSON.stringify({ name: secretName, value: secretValue, note: secretNote }),
    });
    setSecretName("");
    setSecretValue("");
    setSecretNote("");
    await refresh();
  }

  async function deleteSecret(name: string) {
    await api(`/api/projects/${id}/secrets/${encodeURIComponent(name)}`, { method: "DELETE" });
    await refresh();
  }

  if (!project) return <p className="muted">Загрузка…</p>;

  const openSecretAsk = asks.find((a) => a.status === "open" && a.kind === "secret");
  const files = (role: string) => artifacts.filter((a) => (a.role || "extra") === role);

  return (
    <div className="project-grid">
      <header className="project-head">
        <div className="row">
          <h1 style={{ margin: 0 }}>{project.name}</h1>
          <span className={`pill ${project.status === "running" ? "run" : ""}`}>{project.status}</span>
        </div>
        <div className="row">
          <button className="primary" onClick={() => action("start")}>
            Старт
          </button>
          <button onClick={() => action("pause")}>Пауза</button>
          <button onClick={() => action("resume")}>Продолжить</button>
          <button onClick={() => action("stop")}>Стоп</button>
          <button onClick={rollback} disabled={!selected}>
            Откат к карточке
          </button>
          <span className="muted">
            думать {project.think_slots} · запуск {project.exec_slots}
          </span>
        </div>
      </header>

      <section className="split-brief">
        <div className="card">
          <h2>Промпт</h2>
          <textarea value={editPrompt} onChange={(e) => setEditPrompt(e.target.value)} />
        </div>
        <div className="card">
          <h2>Цель</h2>
          <textarea value={editGoal} onChange={(e) => setEditGoal(e.target.value)} />
          <button onClick={saveBrief} style={{ marginTop: "0.5rem" }}>
            Сохранить
          </button>
        </div>
        <div className="card">
          <div className="muted">Стоимость</div>
          <strong>
            {Number(cost.cost_rub || 0).toFixed(4)} ₽ · {Number(cost.cost_usd || 0).toFixed(4)} $
          </strong>
          <div className="muted">{project.memory?.champion || "чемпиона ещё нет"}</div>
        </div>
      </section>

      <section>
        <h2>Файлы</h2>
        <div className="file-cols">
          {(["input", "output", "extra"] as const).map((role) => (
            <div className="drop" key={role}>
              <strong>{role === "input" ? "Вход" : role === "output" ? "Выход" : "Дополнительно"}</strong>
              <p className="hint">
                {role === "input"
                  ? "Датасет и исходники эксперимента."
                  : role === "output"
                    ? "Чекпоинты и эталон."
                    : "Статья + промпт → очередь гипотез."}
              </p>
              {files(role).length === 0 && <p className="muted">пусто</p>}
              <ul>
                {files(role).map((a) => (
                  <li key={a.id}>
                    {a.filename} <span className="muted">{a.status}</span>
                  </li>
                ))}
              </ul>
              {role === "extra" && (
                <input
                  placeholder="промпт к файлу"
                  value={extraPrompt}
                  onChange={(e) => setExtraPrompt(e.target.value)}
                />
              )}
              <button onClick={() => fileRefs[role].current?.click()}>Добавить</button>
              <input
                ref={fileRefs[role]}
                type="file"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload(role, f);
                  e.target.value = "";
                }}
              />
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2>Пайплайн</h2>
        <div className="board">
          {COLUMNS.map((col) => {
            const nodes = col.kinds.flatMap((k) => byKind.get(k) || []);
            return (
              <div className="board-col" key={col.id}>
                <div className="board-col-title">{col.title}</div>
                {nodes.length === 0 && <p className="muted">пока пусто</p>}
                {nodes.map((n) => (
                  <button
                    type="button"
                    key={n.id}
                    className={`board-card ${selected?.id === n.id ? "selected" : ""} status-${n.status}`}
                    onClick={() => setSelected(n)}
                  >
                    <div>{n.title}</div>
                    <span className="pill">{n.status}</span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
        {selected && (
          <div className="card" style={{ marginTop: "0.8rem" }}>
            <strong>{selected.title}</strong>
            <p>{selected.summary}</p>
            {selected.metrics && Object.keys(selected.metrics).length > 0 && (
              <p className="muted">
                {Object.entries(selected.metrics)
                  .map(([k, v]) => `${k}=${v}`)
                  .join(" · ")}
              </p>
            )}
          </div>
        )}
      </section>

      <section className="split">
        <div>
          <h2>Вопросы модели</h2>
          {asks.filter((a) => a.status === "open").length === 0 && (
            <p className="muted">Открытых вопросов нет. Независимые работы идут дальше.</p>
          )}
          {asks
            .filter((a) => a.status === "open")
            .map((a) => (
              <div className="card" key={a.id} style={{ marginBottom: "0.6rem" }}>
                <span className="pill">{a.kind}</span>
                <p>{a.question}</p>
                {a.kind === "secret" ? (
                  <input
                    type="password"
                    placeholder="значение секрета не попадёт в чат"
                    value={askDraft[a.id] || ""}
                    onChange={(e) => setAskDraft((d) => ({ ...d, [a.id]: e.target.value }))}
                  />
                ) : (
                  <textarea
                    value={askDraft[a.id] || ""}
                    onChange={(e) => setAskDraft((d) => ({ ...d, [a.id]: e.target.value }))}
                  />
                )}
                <div className="row" style={{ marginTop: "0.4rem" }}>
                  <button className="primary" onClick={() => replyAsk(a)}>
                    {a.kind === "secret" ? "Сохранить секрет" : "Ответить"}
                  </button>
                  <button onClick={() => replyAsk(a, true)}>Отказать</button>
                </div>
              </div>
            ))}
          <h2>Работы</h2>
          {jobs.length === 0 && <p className="muted">Очередь пуста</p>}
          {jobs.map((j) => (
            <div key={j.id} className="muted">
              {j.kind} · {j.title} · {j.status}
              {j.blocked_by ? " (ждёт ответа)" : ""}
              {j.metric ? ` · метрика ${j.metric}` : ""}
            </div>
          ))}
        </div>
        <div>
          <h2>Направление</h2>
          <form onSubmit={steer} className="form">
            <textarea
              value={chat}
              onChange={(e) => setChat(e.target.value)}
              placeholder="Уточнение или ограничение. Исследование не останавливается."
            />
            <button className="primary" type="submit">
              Отправить
            </button>
          </form>
          <h2>Журнал</h2>
          <label className="row" style={{ fontSize: "0.8rem" }}>
            <input type="checkbox" checked={rawLog} onChange={(e) => setRawLog(e.target.checked)} />
            сырой JSON
          </label>
          <div className="log">
            {events
              .slice(-80)
              .map((e) =>
                rawLog
                  ? `#${e.seq} ${e.type} ${JSON.stringify(e.payload).slice(0, 220)}`
                  : `${humanEvent(e)}`,
              )
              .filter((line) => line.trim())
              .join("\n")}
          </div>
        </div>
      </section>

      {openSecretAsk && (
        <div className="modal">
          <div className="card">
            <h2>Вставьте секрет</h2>
            <p>{openSecretAsk.question}</p>
            <p className="hint">Значение сохранится в хранилище и не уйдёт в переписку с моделью.</p>
            <input
              type="password"
              value={askDraft[openSecretAsk.id] || ""}
              onChange={(e) => setAskDraft((d) => ({ ...d, [openSecretAsk.id]: e.target.value }))}
            />
            <div className="row" style={{ marginTop: "0.6rem" }}>
              <button className="primary" onClick={() => replyAsk(openSecretAsk)}>
                Сохранить
              </button>
              <button onClick={() => replyAsk(openSecretAsk, true)}>Отказать</button>
            </div>
          </div>
        </div>
      )}

      <section>
        <h2>Секреты проекта</h2>
        <p className="hint">Имена видны модели, значения — нет.</p>
        <ul>
          {secrets.map((s) => (
            <li key={s.name}>
              {s.name} {s.note ? `— ${s.note}` : ""} {s.has_value ? "" : "(пусто)"}
              <button onClick={() => deleteSecret(s.name)} style={{ marginLeft: "0.5rem" }}>
                удалить
              </button>
            </li>
          ))}
        </ul>
        <form className="form" onSubmit={saveSecret}>
          <input placeholder="имя" value={secretName} onChange={(e) => setSecretName(e.target.value)} required />
          <input
            type="password"
            placeholder="значение"
            value={secretValue}
            onChange={(e) => setSecretValue(e.target.value)}
            required
          />
          <input placeholder="заметка" value={secretNote} onChange={(e) => setSecretNote(e.target.value)} />
          <button className="primary" type="submit">
            Сохранить секрет
          </button>
        </form>
      </section>

      <h2>Метрики</h2>
      <div className="card" style={{ height: 280 }}>
        {metrics.length === 0 ? (
          <p className="muted">Точек ещё нет.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartRows}>
              <CartesianGrid stroke="#2a3340" />
              <XAxis dataKey="step" stroke="#8b98a8" />
              <YAxis stroke="#8b98a8" />
              <Tooltip />
              <Legend />
              {metricNames.map((name, i) => (
                <Line
                  key={name}
                  type="monotone"
                  dataKey={name}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <h2>Плагины</h2>
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
    </div>
  );
}
