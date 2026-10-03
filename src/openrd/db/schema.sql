-- OpenRD local store (SQLite WAL)

CREATE TABLE IF NOT EXISTS providers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_roles (
  provider_id TEXT NOT NULL,
  role TEXT NOT NULL,
  model TEXT NOT NULL,
  PRIMARY KEY (provider_id, role),
  FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  goal TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  kpi_json TEXT NOT NULL DEFAULT '{}',
  profile TEXT NOT NULL DEFAULT 'default',
  think_slots INTEGER NOT NULL DEFAULT 4,
  exec_slots INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'idle',
  champion_node_id TEXT,
  workspace_path TEXT NOT NULL,
  provider_id TEXT,
  rigor TEXT NOT NULL DEFAULT 'high',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_event_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  agent_id TEXT,
  node_id TEXT,
  payload_json TEXT NOT NULL,
  UNIQUE (project_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_events_project_type ON events(project_id, type);

CREATE TABLE IF NOT EXISTS memory_blocks (
  project_id TEXT NOT NULL,
  key TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (project_id, key)
);

CREATE TABLE IF NOT EXISTS archive_docs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  url TEXT,
  url_canon TEXT,
  query_canon TEXT,
  embedding BLOB,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_archive_project_kind ON archive_docs(project_id, kind);
CREATE INDEX IF NOT EXISTS idx_archive_url ON archive_docs(project_id, url_canon);
CREATE INDEX IF NOT EXISTS idx_archive_query ON archive_docs(project_id, query_canon);

CREATE TABLE IF NOT EXISTS recall_keys (
  project_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  PRIMARY KEY (project_id, kind, key)
);

CREATE INDEX IF NOT EXISTS idx_recall_project_kind ON recall_keys(project_id, kind);

CREATE TABLE IF NOT EXISTS graph_nodes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS graph_edges (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  rel TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tree_nodes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  parent_id TEXT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  summary TEXT NOT NULL DEFAULT '',
  metrics_json TEXT NOT NULL DEFAULT '{}',
  cost_json TEXT NOT NULL DEFAULT '{}',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tree_project ON tree_nodes(project_id);

CREATE TABLE IF NOT EXISTS hypotheses (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  line_id TEXT NOT NULL,
  type TEXT NOT NULL,
  mechanism TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  virtual_score REAL,
  parent_hyp_id TEXT,
  node_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cemetery (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  mechanism_class TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  lesson TEXT NOT NULL,
  embedding BLOB,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  hypothesis_id TEXT,
  node_id TEXT,
  phase TEXT NOT NULL DEFAULT 'screen',
  status TEXT NOT NULL DEFAULT 'pending',
  params_json TEXT NOT NULL DEFAULT '{}',
  metrics_json TEXT NOT NULL DEFAULT '{}',
  log_path TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS metric_points (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  name TEXT NOT NULL,
  step INTEGER NOT NULL DEFAULT 0,
  value REAL NOT NULL,
  ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  model TEXT NOT NULL,
  role TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_rub REAL,
  cost_usd REAL,
  meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS search_cache (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  query_canon TEXT,
  url_canon TEXT,
  source TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blackboard (
  project_id TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  claim_key TEXT NOT NULL,
  owner_agent TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  PRIMARY KEY (project_id, claim_type, claim_key)
);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  mime TEXT,
  role TEXT NOT NULL DEFAULT 'extra',
  prompt TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  blocked_by TEXT,
  metric TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, status);

CREATE TABLE IF NOT EXISTS asks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  question TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  answer TEXT NOT NULL DEFAULT '',
  secret_name TEXT,
  blocked_job_ids TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asks_project ON asks(project_id, status);

CREATE TABLE IF NOT EXISTS plugins_enabled (
  project_id TEXT NOT NULL,
  plugin_id TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  config_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (project_id, plugin_id)
);

CREATE TABLE IF NOT EXISTS human_messages (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TEXT NOT NULL
);
