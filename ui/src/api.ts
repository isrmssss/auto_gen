const base = "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export type Provider = {
  id: string;
  name: string;
  base_url: string;
  roles: Record<string, string>;
  has_key: boolean;
};

export type Project = {
  id: string;
  name: string;
  goal: string;
  status: string;
  think_slots: number;
  exec_slots: number;
  provider_id?: string;
  kpi: Record<string, unknown>;
  memory?: Record<string, string>;
  cost?: { cost_rub?: number; prompt_tokens?: number; completion_tokens?: number; calls?: number; by_model?: unknown[] };
  hw?: Record<string, unknown>;
};

export type TreeNode = {
  id: string;
  parent_id?: string | null;
  kind: string;
  title: string;
  status: string;
  summary: string;
  metrics: Record<string, number>;
  payload: Record<string, unknown>;
  created_at: string;
};

export type PluginInfo = {
  id: string;
  title: string;
  description: string;
  bundle: string;
  when_to_use: string;
  enabled?: boolean;
};
