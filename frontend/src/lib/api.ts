/**
 * API Client for Clarity Agentic App Backend
 *
 * Communicates with FastAPI backend on port 8000
 */

import axios from 'axios';

/**
 * Where API requests go depends on HOW the app is being served:
 *
 *  - PREVIEW (during/just-after generation): the platform serves this app
 *    through the clarity-api proxy at `…/api/proxy/app/<userId>/<appId>/`. The
 *    proxy authenticates the platform user and WRAPS every forwarded request
 *    with the trusted identity (X-User-Id + X-Claritty-Auth). So our requests
 *    MUST go through the proxy's backend path `…/api/proxy/api/<userId>/<appId>`
 *    — a root-relative `/api/...` would escape to the platform root and 401.
 *
 *  - DEPLOYED (CloudFront + Lambda@Edge): served same-origin on
 *    `<appId>.apps.claritty.ai` with `?claritty_token=<jwt>`; the edge wraps the
 *    request after verifying that token. Base is same-origin; we attach the token.
 *
 * Resolved ONCE and cached in sessionStorage so client-side routing / a refresh
 * on a sub-route (which can drop the URL prefix or the `?claritty_token`) never
 * loses the wrapping context.
 */
export function resolveProxyApiBase(pathname: string): string | null {
  // `…/api/proxy/app/<userId>/<appId>` → `…/api/proxy/api/<userId>/<appId>`
  const m = pathname.match(/^(.*\/api\/proxy)\/app\/([^/]+)\/([^/]+)(?=\/|$)/);
  return m ? `${m[1]}/api/${m[2]}/${m[3]}` : null;
}

function persisted(key: string, value: string | null): string | null {
  try {
    if (value) {
      sessionStorage.setItem(key, value);
      return value;
    }
    return sessionStorage.getItem(key);
  } catch {
    return value; // sessionStorage unavailable (rare) — fall back to the live value
  }
}

// Preview proxy base (if served through the proxy) — sticky across routing.
const proxyApiBase = persisted(
  'claritty_api_base',
  resolveProxyApiBase(window.location.pathname),
);

// Deployed edge token — sticky across routing (was previously a one-shot read
// of window.location.search, lost the moment routing dropped the query param).
const edgeToken = persisted(
  'claritty_token',
  new URLSearchParams(window.location.search).get('claritty_token'),
);

const API_BASE_URL =
  proxyApiBase ?? (import.meta.env.VITE_API_URL || ''); // proxy path, or same-origin

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add authentication to requests.
api.interceptors.request.use((config) => {
  // PREVIEW: the proxy wraps the request with the trusted identity server-side,
  // so we attach NO token — sending one would be ignored, and the proxy is the
  // source of truth for "the right user".
  if (proxyApiBase) {
    return config;
  }

  // DEPLOYED: present the platform edge token; the edge verifies + injects the
  // identity. Never fall back to a default when it's present.
  if (edgeToken) {
    config.headers.Authorization = `Bearer ${edgeToken}`;
    return config;
  }

  // Marketplace / host-set identity fallback.
  const userId = localStorage.getItem('user_id');
  if (userId) {
    config.headers['X-User-ID'] = userId;
  }

  // A stored auth token, or — ONLY in local dev — the `test-user` convenience
  // identity so `docker compose up` works without the platform. In production we
  // send NO default Authorization: a real 401 is correct and safe, where
  // `test-user` would silently merge every user's data.
  const token =
    localStorage.getItem('auth_token') ||
    (import.meta.env.DEV ? 'test-user' : null);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

// ── Error helpers ─────────────────────────────────────────────────────────────
/**
 * A typed view of an API error: HTTP status + the backend's machine `error` code
 * + a human message. ALWAYS run a caught error through this and show the message
 * in a toast — never swallow it (see "Surface every error" in CLAUDE.md). On a
 * 409 the backend signals NOT_CONNECTED ("connect <service>"); special-case it.
 */
export interface ApiError {
  status?: number;
  code?: string;
  message: string;
}

export function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    const data = err.response?.data as
      | { error?: string; detail?: string; message?: string }
      | undefined;
    return {
      status,
      code: data?.error,
      message: data?.detail || data?.message || err.message,
    };
  }
  return { message: err instanceof Error ? err.message : 'Something went wrong' };
}

// Types
export interface Agent {
  id: string;
  name: string;
  description: string;
  category: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  integrations: Array<{
    service: string;
    required: boolean;
    auth_type: string;
  }>;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  execution_mode: string;
  steps: Array<{
    agent_id: string;
    output_key?: string;
  }>;
  agent_steps?: Array<{
    agent_id: string;
    output_key?: string;
  }>;
}

export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

export interface Task {
  id: string;
  title: string;
  notes?: string | null;
  priority: TaskPriority;
  suggested_action?: string | null;
  done: boolean;
  created_at?: string | null;
}

export interface WidgetTask {
  id: string;
  title: string;
  priority: TaskPriority;
  done: boolean;
  suggested_action?: string | null;
}

// Agent/workflow/trigger graph — the v1 contract served at GET /api/graph
// (see claritty_sdk/graph.py → build_graph). Node ids are prefixed `agent:` /
// `trigger:`; edges connect those ids.
export interface GraphNode {
  id: string;
  type: 'agent' | 'trigger';
  name: string;
  data?: {
    agentId?: string;
    triggerId?: string;
    category?: string;
    description?: string;
    templateType?: string;
    workflowId?: string;
    inputs?: Record<string, unknown>;
    outputs?: Record<string, unknown>;
  };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  data?: { workflowId?: string; trigger?: boolean };
}

export interface GraphWorkflow {
  id: string;
  name: string;
  executionMode?: string;
  steps?: Array<{ agentId: string; outputKey?: string; inputFrom?: string }>;
}

export interface GraphData {
  version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  workflows: GraphWorkflow[];
  source?: string;
}

// Shape returned by GET /api/widget (see backend/routes/app.py).
export interface WidgetData {
  open_count: number;
  done_today?: number;
  top_priority?: TaskPriority | null;
  top_task?: string | null;
  top_task_id?: string | null;
  tasks?: WidgetTask[];
  last_updated: string;
}

// API Methods

export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

export const getWidgetData = async (
  size: 'small' | 'medium' | 'large' = 'medium',
): Promise<WidgetData> => {
  const response = await api.get(`/api/widget?size=${size}`);
  return response.data;
};

// Tasks CRUD — mirrors backend/routes/app.py.
export const getTasks = async (): Promise<Task[]> => {
  const response = await api.get('/api/tasks');
  return response.data.tasks;
};

export const createTask = async (title: string, notes?: string): Promise<Task> => {
  const response = await api.post('/api/tasks', { title, notes });
  return response.data;
};

export const toggleTask = async (taskId: string): Promise<Task> => {
  const response = await api.post(`/api/tasks/${taskId}/toggle`);
  return response.data;
};

export const deleteTask = async (taskId: string): Promise<void> => {
  await api.delete(`/api/tasks/${taskId}`);
};

// The full agent/workflow/trigger graph (one round-trip), for the template
// showcase. See claritty_sdk/graph.py for the contract.
export const getGraph = async (): Promise<GraphData> => {
  const response = await api.get('/api/graph');
  return response.data;
};

export const listAgents = async (): Promise<Agent[]> => {
  const response = await api.get('/api/agents');
  return response.data.agents;
};

export const getAgent = async (agentId: string): Promise<Agent> => {
  const response = await api.get(`/api/agents/${agentId}`);
  return response.data;
};

export const executeAgent = async (agentId: string, inputData: Record<string, unknown>) => {
  const response = await api.post(`/api/agents/${agentId}/execute`, inputData);
  return response.data;
};

export const listWorkflows = async (): Promise<Workflow[]> => {
  const response = await api.get('/api/workflows');
  return response.data.workflows;
};

export const executeWorkflow = async (workflowId: string, inputData?: Record<string, unknown>) => {
  const response = await api.post(`/api/workflows/${workflowId}/execute`, inputData);
  return response.data;
};

export const getWorkflowExecution = async (executionId: string) => {
  const response = await api.get(`/api/workflows/executions/${executionId}`);
  return response.data;
};

// Trigger management lives on the Claritty platform now (not in-app).

// ── Integrations setup (first-run checklist) ───────────────────────────────
export interface RequiredIntegration {
  id: string;
  name: string;
  connected: boolean;
}
export interface IntegrationsStatus {
  integrations: RequiredIntegration[];
  all_connected: boolean;
  /** This app's id — used to scope the connect flow to this app. */
  app_id?: string | null;
}

/** The app's required integrations + per-user connection status. Powers the
 * setup checklist + Integrations page. Returns no required integrations for a
 * self-contained app. */
export const getRequiredIntegrations = async (): Promise<IntegrationsStatus> => {
  const response = await api.get('/api/integrations/required');
  return response.data;
};

// Helper functions / aliases for convenience (wrapped format for Dashboard compatibility)
export const getAgents = async () => ({ agents: await listAgents() });
export const getWorkflows = async () => ({ workflows: await listWorkflows() });

export default api;
