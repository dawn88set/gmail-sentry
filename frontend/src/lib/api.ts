/**
 * API Client for Gmail Sentry.
 *
 * Mirrors backend/routes/app.py — keep paths/methods/shapes in sync.
 */

import axios from 'axios';

/**
 * Where API requests go depends on HOW the app is served (preview proxy vs
 * deployed edge). Resolved once and cached in sessionStorage. (Unchanged from
 * the seed — platform contract.)
 */
export function resolveProxyApiBase(pathname: string): string | null {
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
    return value;
  }
}

const proxyApiBase = persisted(
  'claritty_api_base',
  resolveProxyApiBase(window.location.pathname),
);

const edgeToken = persisted(
  'claritty_token',
  new URLSearchParams(window.location.search).get('claritty_token'),
);

const API_BASE_URL = proxyApiBase ?? (import.meta.env.VITE_API_URL || '');

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  if (proxyApiBase) return config;
  if (edgeToken) {
    config.headers.Authorization = `Bearer ${edgeToken}`;
    return config;
  }
  const userId = localStorage.getItem('user_id');
  if (userId) config.headers['X-User-ID'] = userId;
  const token =
    localStorage.getItem('auth_token') || (import.meta.env.DEV ? 'test-user' : null);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Error helpers ───────────────────────────────────────────────────────────
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

// ── Domain types ────────────────────────────────────────────────────────────
export type Tier = 'urgent' | 'needs_reply' | 'fyi';
export type RuleKind = 'nl' | 'vip_sender' | 'keyword';
export type LabelMatchType = 'sender' | 'domain' | 'subject_keyword';

export interface Alert {
  id: string;
  gmail_message_id: string;
  thread_id?: string | null;
  sender?: string | null;
  subject?: string | null;
  snippet?: string | null;
  tier: Tier;
  reason?: string | null;
  deep_link?: string | null;
  slack_sent: boolean;
  status: 'new' | 'seen' | 'dismissed';
  reply_draft?: string | null;
  reply_status?: 'none' | 'drafted' | 'sent' | 'failed';
  reply_sent_at?: string | null;
  created_at?: string | null;
}

export interface TriageRule {
  id: string;
  name: string;
  kind: RuleKind;
  value: string;
  tier: Tier;
  active: boolean;
  created_at?: string | null;
}

export interface LabelRule {
  id: string;
  name: string;
  match_type: LabelMatchType;
  match_value: string;
  target_label: string;
  archive_after: boolean;
  active: boolean;
  created_at?: string | null;
}

export type NotifyChannel = 'slack' | 'telegram' | 'discord' | 'whatsapp';

export interface SentryConfig {
  slack_channel: string;
  notify_tier: 'urgent' | 'needs_reply';
  // Per-channel urgency override; a channel absent here follows notify_tier.
  channel_tiers: Partial<Record<NotifyChannel, 'urgent' | 'needs_reply'>>;
  telegram_chat_id: string;
  discord_channel_id: string;
  teams_chat_id: string;
  whatsapp_to: string;
  auto_draft: boolean;
}

export interface CleanupCounts {
  promotions: number;
  social: number;
  spam: number;
  last_scan: string;
  last_scan_error?: string | null; // set when the last scan couldn't run (e.g. Gmail disconnected)
}

export interface ScanRunItem {
  at: string | null;
  ago: string;
  scanned: number;
  flagged: number;
  notified: number;
  error?: string | null;
}
/** Recent scan runs (newest first) — lets the user SEE the actual cadence, since
 *  the interval is owned by the platform. */
export const getRecentScans = async (): Promise<{ runs: ScanRunItem[] }> =>
  (await api.get('/api/scans/recent')).data;

export interface ScanSummary {
  /** Mail newly JUDGED this run. Settled mail is never re-examined, so 0 is the
   *  normal steady state and means "up to date" — not "nothing happened". */
  scanned: number;
  /** Messages newly added to the thread ledger this run (inbound + outbound). */
  indexed?: number;
  flagged: number;
  labeled: number;
  notified: number;
  slack_configured: boolean;
  promo_count: number;
  social_count: number;
  spam_count: number;
}

// Shape returned by GET /api/widget (see backend/routes/app.py).
export interface WidgetAlert {
  id: string;
  subject: string;
  sender: string;
  tier: Tier;
  reason: string;
  deep_link: string;
  reply_ready?: boolean;
}

export interface WidgetData {
  urgent_count: number;
  needs_reply_count: number;
  /** Now also requires the open loops to be closed — "nothing needs you" while
   *  a customer has waited nine days would be a lie. */
  all_clear: boolean;
  /** Thread-level open loops. Same field the app's hero number uses, so the
   *  widget and the app can never disagree. */
  open_loops?: number;
  owed_count?: number;
  waiting_count?: number;
  cold_count?: number;
  last_scan: string;
  top_alerts: WidgetAlert[];
  cleanup: { promo: number; social: number; spam: number };
  slack_configured: boolean;
}

// ── Integrations setup (connection status) ──────────────────────────────────
export interface RequiredIntegration {
  id: string;
  name: string;
  connected: boolean;
}
export interface IntegrationsStatus {
  integrations: RequiredIntegration[];
  all_connected: boolean;
  app_id?: string | null;
}

// ── API methods ─────────────────────────────────────────────────────────────
export const healthCheck = async () => (await api.get('/health')).data;

export const getWidgetData = async (
  size: 'small' | 'medium' | 'large' = 'medium',
): Promise<WidgetData> => (await api.get(`/api/widget?size=${size}`)).data;

// Alerts
export type AlertStatusFilter = 'active' | 'snoozed' | 'done' | 'all';

export const getAlerts = async (
  status: AlertStatusFilter = 'active',
  tier?: Tier,
): Promise<Alert[]> => {
  const q = new URLSearchParams({ status });
  if (tier) q.set('tier', tier);
  return (await api.get(`/api/alerts?${q.toString()}`)).data.alerts;
};

export const dismissAlert = async (id: string): Promise<void> => {
  await api.post(`/api/alerts/${id}/dismiss`);
};

export const doneAlert = async (id: string): Promise<void> => {
  await api.post(`/api/alerts/${id}/done`);
};

export const snoozeAlert = async (id: string, hours: number): Promise<void> => {
  await api.post(`/api/alerts/${id}/snooze`, { hours });
};

export const muteAlert = async (id: string): Promise<{ muted: string }> =>
  (await api.post(`/api/alerts/${id}/mute`)).data;

// Draft a reply. Pass `intent` — a rough, scrappy note of what you want to say —
// and it's expanded into a polished email in your voice. Omit for an auto-draft.
export const draftReplyAlert = async (
  id: string,
  intent?: string,
): Promise<{ draft: string; compose_url: string; voice_matched: boolean }> =>
  (await api.post(`/api/alerts/${id}/draft-reply`, intent ? { intent } : {})).data;

// Approve & SEND the drafted reply through Gmail (threaded). 409 → connect Gmail;
// 5xx → real send failure (the alert keeps its draft for retry). Only a real
// message id flips it to sent.
export const sendReply = async (
  id: string,
  body?: string,
): Promise<{ success: boolean; reply_status: 'sent'; message_id: string }> =>
  (await api.post(`/api/alerts/${id}/reply/send`, { body })).data;

export const createRuleFromAlert = async (id: string, tier: Tier = 'urgent'): Promise<TriageRule> =>
  (await api.post(`/api/alerts/${id}/create-rule`, { tier })).data;

// Category messages (paginated, for the "see what will be cleared" list)
export interface CategoryMessage {
  id: string;
  sender: string;
  subject: string;
  snippet: string;
}
export const getCategoryMessages = async (
  category: 'promotions' | 'social' | 'spam',
  pageToken = '',
): Promise<{ messages: CategoryMessage[]; next_page_token: string | null }> =>
  (await api.get(`/api/cleanup/${category}/messages?page_token=${encodeURIComponent(pageToken)}`)).data;

// Triage rules
export const getRules = async (): Promise<TriageRule[]> =>
  (await api.get('/api/rules')).data.rules;

export const createRule = async (input: {
  name: string;
  kind: RuleKind;
  value: string;
  tier: Tier;
}): Promise<TriageRule> => (await api.post('/api/rules', input)).data;

export const toggleRule = async (id: string): Promise<TriageRule> =>
  (await api.post(`/api/rules/${id}/toggle`)).data;

export const deleteRule = async (id: string): Promise<void> => {
  await api.delete(`/api/rules/${id}`);
};

// Label (filing) rules
export const getLabelRules = async (): Promise<LabelRule[]> =>
  (await api.get('/api/label-rules')).data.label_rules;

export const createLabelRule = async (input: {
  name: string;
  match_type: LabelMatchType;
  match_value: string;
  target_label: string;
  archive_after: boolean;
}): Promise<LabelRule> => (await api.post('/api/label-rules', input)).data;

export const toggleLabelRule = async (id: string): Promise<LabelRule> =>
  (await api.post(`/api/label-rules/${id}/toggle`)).data;

export const deleteLabelRule = async (id: string): Promise<void> => {
  await api.delete(`/api/label-rules/${id}`);
};

// Settings
export const getConfig = async (): Promise<SentryConfig> =>
  (await api.get('/api/config')).data;

export const updateConfig = async (input: Partial<SentryConfig>): Promise<SentryConfig> =>
  (await api.put('/api/config', input)).data;

export interface NotifyResult {
  channel: string;
  ok: boolean;
  error: string;
  configured?: boolean;
}

/** Send a test alert to a channel (or all configured) — returns each channel's
 *  exact success/error so the user can verify delivery. */
export const testNotify = async (channel?: string): Promise<{ results: NotifyResult[] }> =>
  (await api.post('/api/notify/test', { channel })).data;

export interface SlackChannel {
  id: string;
  name: string;
}
/** Channels the connected Slack bot can post to — the user picks one instead of
 *  typing a name (free-text names cause `channel_not_found`). */
export const getSlackChannels = async (): Promise<{
  connected: boolean;
  workspace?: string; // the connected Slack workspace/team name (to spot a mismatch)
  channels: SlackChannel[];
  error?: string;
}> => (await api.get('/api/integrations/slack/channels')).data;

// Cleanup
export const getCleanup = async (): Promise<CleanupCounts> =>
  (await api.get('/api/cleanup')).data;

export interface ClearResult {
  cleared: number;
  remaining: number;
  done: boolean;
  category: string;
  action: string;
}

/** One batched, paginated pass (clears up to a few thousand). Loop while
 *  `!done` for a full mass-clear — see clearCategoryAll. */
export const clearCategory = async (
  category: 'promotions' | 'social' | 'spam',
  action: 'archive' | 'trash' = 'trash',
): Promise<ClearResult> =>
  (await api.post('/api/cleanup/clear', { category, action })).data;

/** Mass-clear a whole category regardless of size: repeat the batched pass
 *  until the server says `done`. `onProgress` gets the running total after each
 *  pass so the UI can show live progress. Bounded so a runaway can't loop. */
export const clearCategoryAll = async (
  category: 'promotions' | 'social' | 'spam',
  action: 'archive' | 'trash' = 'trash',
  onProgress?: (total: number, remaining: number) => void,
): Promise<ClearResult> => {
  let total = 0;
  let prevRemaining = Infinity;
  let last: ClearResult = { cleared: 0, remaining: 0, done: true, category, action };
  for (let pass = 0; pass < 100; pass++) {
    last = await clearCategory(category, action);
    total += last.cleared;
    onProgress?.(total, last.remaining);
    if (last.done) break;
    // Safety: stop if a pass cleared nothing, or the remaining count isn't
    // dropping — otherwise a batch that can't be removed would loop 100×.
    if (last.cleared === 0 || last.remaining >= prevRemaining) break;
    prevRemaining = last.remaining;
  }
  return { ...last, cleared: total };
};

// Scan now
export const runScan = async (): Promise<ScanSummary> =>
  (await api.post('/api/scan/run')).data;

// Connection status (platform-provided)
export const getRequiredIntegrations = async (): Promise<IntegrationsStatus> =>
  (await api.get('/api/integrations/required')).data;

// ── Smart onboarding ────────────────────────────────────────────────────────
export interface DraftTriageRule {
  name: string;
  kind: RuleKind;
  value: string;
  tier: Tier;
  reason?: string;
}
export interface DraftLabelRule {
  name: string;
  match_type: LabelMatchType;
  match_value: string;
  target_label: string;
  archive_after: boolean;
  reason?: string;
}
export interface OnboardingDraft {
  triage_rules: DraftTriageRule[];
  label_rules: DraftLabelRule[];
  notify_tier: 'urgent' | 'needs_reply';
  scan_minutes: number;
  summary: string;
  source?: string;
}
export interface SuggestResponse {
  draft: OnboardingDraft;
  grounded: boolean;
  signals_summary?: {
    senders: number;
    promo_domains: string[];
    counts: Record<string, number>;
  } | null;
}
export interface OnboardingStatus {
  onboarded: boolean;
  intent: string;
  role: string;
}

export const getOnboardingStatus = async (): Promise<OnboardingStatus> =>
  (await api.get('/api/onboarding/status')).data;

export const suggestOnboarding = async (body: {
  description?: string;
  role?: string;
  noise?: string;
  current_draft?: OnboardingDraft | null;
}): Promise<SuggestResponse> => (await api.post('/api/onboarding/suggest', body)).data;

export const applyOnboarding = async (body: {
  triage_rules: DraftTriageRule[];
  label_rules: DraftLabelRule[];
  notify_tier?: 'urgent' | 'needs_reply';
  intent?: string;
  role?: string;
}): Promise<{ created_rules: number; created_label_rules: number; onboarded: boolean }> =>
  (await api.post('/api/onboarding/apply', body)).data;

// ── Communication-pattern profile ("what I've learned about you") ────────────
export interface CommVip {
  email: string;
  name?: string;
  count?: number;
}
export interface CommProfile {
  vip_senders: CommVip[];
  response_habits: { frequent_contacts?: string[] } & Record<string, unknown>;
  tone: string;
  style_exemplars: string[];
  signature: string;
  refreshed_at: string | null;
}

export const getProfile = async (): Promise<CommProfile> =>
  (await api.get('/api/profile')).data;

// Re-learn the user's communication patterns from their real sent + inbox mail.
export const learnProfile = async (): Promise<CommProfile> =>
  (await api.post('/api/profile/learn')).data;

export default api;

// ── Follow-ups: thread-level open loops ─────────────────────────────────────
// An Alert is one MESSAGE that needs your eyes now. A FollowUp is one THREAD
// with an unresolved loop — it outlives the alert, which is why sending a reply
// moves it to `awaiting_them` rather than ending it.
export type FollowUpState =
  | 'awaiting_you'
  | 'awaiting_them'
  | 'going_cold'
  | 'snoozed'
  | 'done'
  | 'ignored';

export interface FollowUp {
  id: string;
  thread_id: string;
  counterparty_email: string;
  counterparty_name: string;
  subject: string;
  state: FollowUpState;
  ball: 'you' | 'them';
  /** One line saying what's actually being asked — the payload of a row. */
  ask_summary: string;
  due_at: string | null;
  due_source: string;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  last_activity_at: string | null;
  /** How long silence is normal for THIS person, from their own reply habits. */
  stale_after_hours: number;
  importance: number;
  risk: number;
  nudge_count: number;
  snoozed_until: string | null;
  closed_reason: string;
}

export interface FollowUpCounts {
  owed: number;
  waiting: number;
  cold: number;
  open_loops: number;
}

export type FollowUpFilter = 'open' | 'owed' | 'waiting' | 'cold' | 'snoozed' | 'done' | 'all';

export const getFollowUps = async (
  state: FollowUpFilter = 'open',
): Promise<{ followups: FollowUp[]; counts: FollowUpCounts }> =>
  (await api.get('/api/followups', { params: { state } })).data;

export const snoozeFollowUp = async (id: string, hours: number) =>
  (await api.post(`/api/followups/${id}/snooze`, { hours })).data;

export const doneFollowUp = async (id: string) =>
  (await api.post(`/api/followups/${id}/done`)).data;

export const ignoreFollowUp = async (id: string) =>
  (await api.post(`/api/followups/${id}/ignore`)).data;

export const syncFollowUps = async (): Promise<{ counts: FollowUpCounts }> =>
  (await api.post('/api/followups/sync')).data;

// ── Smart filing: folders ───────────────────────────────────────────────────
// Threads are filed by who they're with, both directions, so a conversation
// lives in one place instead of the user's replies being orphaned in Sent.
// Nothing is labelled with a folder in `proposed` — approval is the gate that
// keeps this from sprawling through a real mailbox.
export interface MailFolder {
  id: string;
  name: string;
  kind: 'counterparty' | 'topical';
  source: 'derived' | 'ai_proposed' | 'user';
  status: 'proposed' | 'active' | 'rejected';
  counterparty_email: string;
  thread_count: number;
  created_at?: string | null;
}

export const getFolders = async (): Promise<{
  folders: MailFolder[];
  filing_enabled: boolean;
  pending: number;
}> => (await api.get('/api/folders')).data;

export const approveFolder = async (id: string, name?: string) =>
  (await api.post(`/api/folders/${id}/approve`, name ? { name } : {})).data;

export const rejectFolder = async (id: string) =>
  (await api.post(`/api/folders/${id}/reject`)).data;

export const setFilingEnabled = async (enabled: boolean): Promise<{ filing_enabled: boolean }> =>
  (await api.put('/api/folders/settings', { enabled })).data;

export const getBacklogPreview = async (
  days = 30,
): Promise<{ preview: { folder: string; threads: number; exists: boolean }[] }> =>
  (await api.get('/api/folders/backlog-preview', { params: { days } })).data;
