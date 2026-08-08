/**
 * API Client for Gmail Sentry.
 *
 * Mirrors backend/routes/app.py — keep paths/methods/shapes in sync.
 */

import axios from 'axios';
import { isTokenExpiring, requestFreshSession, scheduleSessionRefresh } from './session';

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

/**
 * The host's identity token, re-read on every request rather than captured once.
 *
 * It is valid for 30 minutes. Reading it a single time at module load meant a
 * pane left open for half an hour kept sending a dead token, every call failed,
 * and the app looked like it had signed itself out — the "it makes me log in
 * again all the time" report. Re-reading costs nothing and picks up a fresh
 * token the moment the host provides one.
 */
const currentEdgeToken = (): string | null =>
  new URLSearchParams(window.location.search).get('claritty_token') ??
  persisted('claritty_token', null);

// Cache the first one we see, so a client-side route change (which drops the
// query string) doesn't lose the token.
persisted('claritty_token', new URLSearchParams(window.location.search).get('claritty_token'));

const API_BASE_URL = proxyApiBase ?? (import.meta.env.VITE_API_URL || '');

// Renew before the token lapses rather than after something breaks. The
// platform edge rejects an expired token with 403 before it reaches this app,
// so renewing in time is the only avenue an embedded app has.
scheduleSessionRefresh(currentEdgeToken());

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  if (proxyApiBase) return config;
  const edgeToken = currentEdgeToken();
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

/**
 * Judge a response by its content, not by a header an intermediary can rewrite.
 *
 * This app is served from the same origin as its API, so an infrastructure
 * response — a proxy page while the container restarts, a login redirect —
 * arrives as HTML with a 200. Left alone, `response.data` is a STRING, every
 * `data.someField` in this file is `undefined`, and that undefined travels into
 * component state and throws far away at render, naming neither the endpoint
 * nor the cause. That is the mechanism that blanked the deployed app.
 *
 * The first version of this check keyed on the content-type header, and that was
 * wrong in a way production demonstrated immediately: the header is set by
 * whatever last touched the response, so a perfectly good JSON body delivered
 * without `application/json` got rejected, and a working endpoint showed
 * "unexpected response from the server". A header is a claim about the payload;
 * the payload is the fact.
 *
 * So: if the body is a string that parses as JSON, use it. Only a body that is
 * NOT JSON is a real infrastructure response, and only then does this fail —
 * turning it into an ordinary API error the caller can catch and toast, rather
 * than an undefined that detonates somewhere else.
 */
api.interceptors.response.use((response) => {
  if (typeof response.data !== 'string') return response;

  const body = response.data.trim();
  if (body === '') {
    return Promise.reject(
      Object.assign(new Error('The server returned an empty response.'), {
        isAxiosError: true,
        response: {
          status: response.status,
          data: { detail: `The server sent ${response.status} with an empty body.` },
        },
      }),
    );
  }

  try {
    // A correct body that merely lost its content-type on the way here.
    return { ...response, data: JSON.parse(body) };
  } catch {
    // Lead with what it MEANS, then the evidence.
    //
    // The first version of this put the raw body first, and it did its job — it
    // is how the stale-server problem was finally identified. But once the cause
    // is known, greeting someone with "<!doctype html> <html lang=..." is
    // developer noise in a user's face: it reads as a crash, it is unactionable,
    // and it buries the one sentence that tells them what to do. The excerpt
    // stays, shortened and at the end, because the next unexplained response
    // will need it too.
    const evidence = body
      .replace(/[A-Za-z0-9_-]{40,}/g, '…')
      .replace(/\s+/g, ' ')
      .slice(0, 60);
    // The app is served from the same origin as its API, so a page where data
    // should be almost always means the server is mid-deploy or running a build
    // that predates this endpoint.
    const meaning = /<!doctype html|<html/i.test(body)
      ? 'The server sent a web page instead of data — it may be restarting, or running an older version of this app.'
      : `The server sent ${response.status} but not data.`;
    return Promise.reject(
      Object.assign(new Error('The server returned a page instead of data — it may be restarting.'), {
        isAxiosError: true,
        response: {
          status: response.status,
          data: { detail: `${meaning} (${evidence}…)` },
        },
      }),
    );
  }
}, (error) => {
  // The host's token lives 30 minutes. When it dies, every call fails at once
  // and the app looks like it signed itself out — but there is nothing here to
  // log into, so a login prompt would send people hunting for a password that
  // does not exist. Only the host can mint a new token, and the deep-link
  // message it already listens for makes it reopen the pane with a fresh one.
  const status = error?.response?.status;
  if (status === 401 || status === 403) {
    if (isTokenExpiring(currentEdgeToken())) {
      const asked = requestFreshSession(undefined, currentEdgeToken());
      error.sessionExpired = true;
      error.sessionRefreshRequested = asked;
      if (error.response?.data) {
        error.response.data.detail = asked
          ? 'Your session timed out — reopening the app.'
          : 'Your session timed out. Refresh the page to continue.';
      }
    }
  }
  return Promise.reject(error);
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
  /** How often the inbox is read, in minutes. 5 is the floor — the platform's
   *  scan trigger fires on that cadence and the app only runs when it does, so
   *  this can slow scanning down but never speed it up. */
  scan_interval_minutes?: number;
  /** What the cadence ACTUALLY turned out to be. The setting above is a request;
   *  Claritty's trigger decides how often the app gets to run, so the two can
   *  disagree and nothing else in the product would reveal it. */
  /** Whether reading the mail is producing anything. The quote check is strict
   *  by design, and the failure mode of strictness is silence — an app with
   *  nothing to say looks the same as a quiet inbox. Speaks only when wrong. */
  reading_health?: {
    read: number;
    with_findings: number;
    dropped: number;
    verdict: 'ok' | 'none' | 'all_dropped' | 'nothing_found' | 'failing';
    message: string;
  };
  scan_health?: {
    configured_minutes: number;
    typical_minutes: number | null;
    last_scan_at: string | null;
    verdict: 'ok' | 'never' | 'stalled' | 'slower';
    message: string;
  };
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
  /** Messages labelled — by a filing rule or by smart filing. Written on every
   *  run since filing shipped, but dropped by the API until now, so the work
   *  the app does most of never reached the screen. */
  labeled: number;
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
  /** What this mail is actually asking for, when the thread has been read —
   *  falls back to the subject. Same helper as the worklist, so the widget and
   *  the app never describe the same mail differently. */
  headline?: string;
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
  /** The account slipping furthest, when there is one. A named company reads as
   *  a decision where a bare count reads as a statistic. Medium/large only. */
  top_account?: { key: string; name: string; silent_days: number | null } | null;
}


/** Which build is serving — see backend/services/build_id.py. Unauthenticated
 *  and cheap on purpose: it is needed exactly when other things are broken. */
export interface BuildIdentity {
  fingerprint: string;
  routes_fingerprint: string;
  route_count: number;
  routes: string[];
  started_at: string;
}

export const getVersion = async (): Promise<BuildIdentity> =>
  (await api.get('/api/version')).data;

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
  // `?? []` is not defensive padding — without it a response missing this field
  // returns undefined, Today calls .filter on it during render, and the WHOLE
  // app is a blank screen with an exception no user can see. Observed in
  // production. A list endpoint that can't produce a list should degrade to
  // empty, never to undefined.
  return (await api.get(`/api/alerts?${q.toString()}`)).data?.alerts ?? [];
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
  (await api.get('/api/rules')).data?.rules ?? [];

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
  (await api.get('/api/label-rules')).data?.label_rules ?? [];

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
  /** When this folder last received something — a count alone can't tell an
   *  active folder from one that stopped being used in April. */
  last_filed_at?: string | null;
  last_filed_ago?: string;
}

export const getFolders = async (): Promise<{
  folders: MailFolder[];
  filing_enabled: boolean;
  pending: number;
}> => (await api.get('/api/folders')).data;

/** One conversation filed into a folder. */
export interface FolderThread {
  thread_id: string;
  subject: string;
  counterparty_email: string;
  counterparty_name: string;
  status: 'pending' | 'filed' | 'failed';
  filed_count: number;
  filed_at: string | null;
  filed_ago: string;
  error: string;
  deep_link: string;
}

/** What's actually in a folder. A folder that shows only a number is a claim
 *  the user can't check; this is what makes filing auditable. */
export const getFolderThreads = async (
  id: string,
  limit = 50,
): Promise<{ folder: MailFolder; threads: FolderThread[] }> =>
  (await api.get(`/api/folders/${id}/threads`, { params: { limit } })).data;

export const approveFolder = async (id: string, name?: string) =>
  (await api.post(`/api/folders/${id}/approve`, name ? { name } : {})).data;

export const rejectFolder = async (id: string) =>
  (await api.post(`/api/folders/${id}/reject`)).data;

export const setFilingEnabled = async (enabled: boolean): Promise<{ filing_enabled: boolean }> =>
  (await api.put('/api/folders/settings', { enabled })).data;

/** One line of "here's what organizing your existing mail would do". */
export interface BacklogPreviewRow {
  folder: string;
  /** Conversations that would MOVE — already-filed threads are excluded, so
   *  running it twice doesn't offer the same work again. */
  threads: number;
  exists: boolean;
  /** You said no to this folder before. Picking it now is a visible reversal. */
  rejected: boolean;
}

export const getBacklogPreview = async (
  days = 30,
): Promise<{ preview: BacklogPreviewRow[] }> =>
  (await api.get('/api/folders/backlog-preview', { params: { days } })).data;

/** File the mail that was already there. Automatic filing is forward-only from
 *  the moment it's switched on, so without this the backlog — the mail someone
 *  installed this to organize — is never touched. Ticking a folder in the
 *  preview IS the approval. Capped per run; `remaining` says what's left. */
export const organizeBacklog = async (
  folders: string[],
  days = 30,
): Promise<{
  success: boolean;
  filed: number;
  threads: number;
  by_folder: Record<string, number>;
  remaining: number;
  folders: string[];
}> => (await api.post('/api/folders/organize-backlog', { folders, days })).data;

// ── Nudges: chasing a thread that's gone quiet ──────────────────────────────
// The only message this app puts in front of someone the user didn't just hear
// from. Draft-only until explicitly approved, never pre-generated, and every
// refusal comes back as prose the UI shows verbatim — a silently disabled
// button reads as broken, an explained one reads as careful.
export interface Nudge {
  id: string;
  followup_id: string;
  attempt_no: number;
  tone: 'gentle' | 'direct' | 'closing';
  draft: string;
  subject: string;
  to_email: string;
  status: 'proposed' | 'sent' | 'skipped' | 'failed';
  sent_at: string | null;
  error: string;
  /** False when the draft is a template rather than the user's learned voice. */
  voice_matched?: boolean;
}

export const getNudge = async (
  followUpId: string,
): Promise<{ nudge: Nudge | null; blocked_reason: string; nudge_count: number }> =>
  (await api.get(`/api/followups/${followUpId}/nudge`)).data;

export const draftNudge = async (
  followUpId: string,
  tone?: 'gentle' | 'direct' | 'closing',
): Promise<{ nudge: Nudge }> =>
  (await api.post(`/api/followups/${followUpId}/nudge`, tone ? { tone } : {})).data;

export const sendNudge = async (
  nudgeId: string,
  body?: string,
): Promise<{ message_id: string; followup: FollowUp }> =>
  (await api.post(`/api/nudges/${nudgeId}/send`, body ? { body } : {})).data;

export const skipNudge = async (nudgeId: string) =>
  (await api.post(`/api/nudges/${nudgeId}/skip`)).data;

// ── People: who it would cost you to ignore ─────────────────────────────────
// Ranked from revealed preference — whether you reply, how fast, over how many
// threads — not from who emails most. `relationship` isn't cosmetic: it decides
// the filing folder (Clients/… vs Vendors/…) and how long silence is normal
// before a thread is treated as cold, so correcting it changes real behaviour.
export type Relationship = 'customer' | 'prospect' | 'internal' | 'vendor' | 'bulk' | 'unknown';

export interface Counterparty {
  id: string;
  email: string;
  domain: string;
  display_name: string;
  is_internal: boolean;
  thread_count: number;
  msg_in_count: number;
  msg_out_count: number;
  /** Of their threads, how many you answered — the strongest signal you care. */
  your_reply_rate: number;
  /** Of the threads you started, how many they answered. */
  their_reply_rate: number;
  your_median_reply_h: number | null;
  their_median_reply_h: number | null;
  relationship: Relationship;
  relationship_source: 'inferred' | 'crm' | 'user';
  importance: number;
  pinned: boolean;
  muted: boolean;
  crm: { source: string; company: string; stage: string; status: string };
  last_seen_at: string | null;
}

export const getCounterparties = async (
  limit = 50,
): Promise<{ counterparties: Counterparty[] }> =>
  (await api.get('/api/counterparties', { params: { limit } })).data;

export const updateCounterparty = async (
  id: string,
  patch: { relationship?: Relationship; pinned?: boolean; muted?: boolean; notes?: string },
): Promise<{ counterparty: Counterparty }> =>
  (await api.put(`/api/counterparties/${id}`, patch)).data;

// ── Activity: what this app actually did ────────────────────────────────────
// Changes, never runs. A scan that found nothing writes nothing, so every line
// in the feed is worth reading — the scan cadence lives on Today instead.

export type ActivityKind =
  | 'thread_filed'
  | 'filing_failed'
  | 'folder_proposed'
  | 'folder_approved'
  | 'folder_rejected'
  | 'mail_flagged'
  | 'replies_drafted'
  | 'reply_sent'
  | 'nudge_sent'
  | 'went_quiet'
  | 'loop_closed'
  | 'alert_auto_closed'
  | 'relationship_changed'
  | 'report_sent';

export interface ActivityEvent {
  id: string;
  at: string | null;
  kind: ActivityKind;
  /** The sentence, written server-side when it happened — so a folder renamed
   *  next month can't retroactively rewrite what happened in this one. */
  title: string;
  detail: string;
  subject_type: string;
  subject_id: string;
  counterparty_email: string;
  folder_name: string;
  count: number;
}

export interface ActivityDay {
  day: string;
  /** "Today" / "Yesterday" / a weekday — grouped server-side so the app and the
   *  daily report describe a day the same way. */
  label: string;
  events: ActivityEvent[];
}

export interface ActivitySummary {
  filed: number;
  flagged: number;
  drafted: number;
  sent: number;
  went_quiet: number;
  days: number;
  total: number;
}

export const getActivity = async (
  days = 14,
): Promise<{ days: ActivityDay[]; summary: ActivitySummary; total: number; window_days: number }> =>
  (await api.get('/api/activity', { params: { days } })).data;

// ── Insights: true statements about how this mailbox works ──────────────────
// Countable facts only. No modelled hours saved, no imputed money value — one
// invented number a user can disprove makes every other number here suspect.

export interface Insights {
  coverage: { days: number; messages: number; threads: number; since: string | null };
  response: {
    groups: {
      relationship: Relationship;
      label: string;
      people: number;
      you_answer_in_h: number | null;
      they_answer_in_h: number | null;
      /** Too few conversations to be a pattern — shown, but labelled as thin. */
      thin: boolean;
    }[];
    caveat: string;
  };
  attention: {
    people: {
      email: string;
      display_name: string;
      relationship: Relationship;
      relationship_label: string;
      thread_count: number;
      your_reply_rate: number;
      importance: number;
    }[];
  };
  at_risk: {
    counts: FollowUpCounts;
    threads: {
      id: string;
      thread_id: string;
      who: string;
      email: string;
      subject: string;
      silent_days: number;
      risk: number;
    }[];
  };
  handled: ActivitySummary & { folders_active: number; folders_pending: number };
}

export const getInsights = async (): Promise<Insights> => (await api.get('/api/insights')).data;

// ── Refining a draft you're already looking at ──────────────────────────────
// The edit people make when a draft is nearly right. Without it they retype it
// themselves, which throws away the voice matching the draft existed for.
export type Refinement = 'shorter' | 'warmer' | 'firmer' | 'formal';

/** Rewrite a passage — the whole draft, or just the selection. Persists nothing;
 *  the caller keeps the text and the user still approves before anything sends.
 *  A 503 means it genuinely couldn't (no AI connection) — show the message
 *  rather than pretending the button worked. */
export const refineDraft = async (
  text: string,
  how: Refinement,
  context = '',
): Promise<{ text: string }> =>
  (await api.post('/api/reply/refine', { text, how, context })).data;

// ── The worklist: what your email needs from you, ranked ────────────────────
// The app used to show inventory — alerts here, loops there, junk counts in a
// third place — and leave you to assemble the plan. This is the plan.

export type WorkKind = 'reply' | 'owe' | 'chase';

export interface WorkItem {
  id: string;
  kind: WorkKind;
  who: string;
  email: string;
  /** The company behind the person — "" when we don't know them yet. Ties a
   *  worklist row to its account without a second request. */
  company?: string;
  /** What to DO — the extracted ask when we have one, else the subject. */
  headline: string;
  subject: string;
  urgent: boolean;
  due_at: string | null;
  /** "due Friday" / "2 days overdue" — empty when we genuinely don't know. */
  due_label: string;
  overdue: boolean;
  age_label: string;
  reply_ready: boolean;
  thread_id: string;
  alert_id: string;
  followup_id: string;
}

export interface Worklist {
  items: WorkItem[];
  total: number;
  /** Cleared in the last 24h — the thing that makes this finishable. */
  done_today: number;
  ready_to_send: number;
  overdue: number;
}

/**
 * Build a worklist out of alerts alone.
 *
 * `/api/worklist` composes fresh mail with open loops, and it is the newer of
 * the two endpoints. When a server is running an older build it 404s — and this
 * platform rewrites that 404 into the SPA shell with a 200, so the client sees
 * a page where data should be and Today shows nothing at all.
 *
 * Alerts have been there since the first release and still answer. They are
 * only half the picture — no open loops, no chase rows — but "the mail that
 * needs an answer" is most of why anyone opens the app, and half a list beats
 * an error where a list should be. The caller says plainly that it is partial;
 * this does not pretend to be the real thing.
 */
export function worklistFromAlerts(alerts: Alert[]): Worklist {
  const items: WorkItem[] = alerts
    .filter((a) => a.tier === 'urgent' || a.tier === 'needs_reply')
    .map((a) => ({
      id: `alert:${a.id}`,
      kind: 'reply' as WorkKind,
      who: (a.sender || '').split('<')[0].trim() || a.sender || 'someone',
      email: a.sender || '',
      company: '',
      headline: a.subject || '(no subject)',
      subject: a.subject || '',
      urgent: a.tier === 'urgent',
      due_at: null,
      due_label: '',
      overdue: false,
      age_label: '',
      reply_ready: Boolean((a.reply_draft || '').trim()) && a.reply_status !== 'sent',
      thread_id: a.thread_id || '',
      alert_id: a.id,
      followup_id: '',
    }));
  return {
    items,
    total: items.length,
    done_today: 0,
    ready_to_send: items.filter((i) => i.reply_ready).length,
    overdue: 0,
  };
}

export const getWorklist = async (limit = 12): Promise<Worklist> => {
  // Normalise at the boundary. The worklist IS the landing screen, so a body
  // without `items` doesn't degrade this one component — it throws during
  // render and takes the whole app with it.
  const d = (await api.get('/api/worklist', { params: { limit } })).data ?? {};
  // The server reports its own failure in the payload, because this platform's
  // edge turns a 5xx into the SPA shell with a 200 — see the route. Surfacing it
  // as a rejection keeps the caller's existing error path working.
  if (d.error) {
    throw Object.assign(new Error(String(d.error)), {
      isAxiosError: true,
      response: { status: 200, data: { detail: String(d.error) } },
    });
  }
  return {
    ...d,
    items: Array.isArray(d.items) ? d.items : [],
    total: d.total ?? 0,
    done_today: d.done_today ?? 0,
    ready_to_send: d.ready_to_send ?? 0,
    overdue: d.overdue ?? 0,
  };
};

// ── Accounts: the companies behind the mailbox ──────────────────────────────
// Every other surface is organised the way mail arrives — a message, a thread,
// a person. This is the one organised the way the business is actually run.
// `needs_you` is rolled up from the SAME worklist rows Today renders, so an
// account card and the list beneath it can never disagree.

export interface Account {
  key: string;
  name: string;
  relationship: string;
  relationship_label: string;
  people_count: number;
  open_threads: number;
  /** The single most pressing ask on this account, in the user's own words. */
  headline: string;
  needs_you: number;
  you_owe: number;
  chasing: number;
  at_risk: boolean;
  silent_days: number | null;
  last_contact_at: string | null;
  your_median_reply_h: number | null;
  importance: number;
}

export interface AccountsResponse {
  accounts: Account[];
  total: number;
  at_risk: number;
  needs_you: number;
  you_owe: number;
}

export interface AccountPerson {
  email: string;
  display_name: string;
  relationship: string;
  relationship_label: string;
  your_reply_rate: number;
  thread_count: number;
  last_seen_at: string | null;
}

export interface AccountThread {
  id: string;
  thread_id: string;
  subject: string;
  who: string;
  email: string;
  ball: string;
  state: string;
  risk: number;
  last_activity_at: string | null;
}

export interface AccountDetail extends Account {
  people: AccountPerson[];
  threads: AccountThread[];
}

// ── Ask: plain language over everything the app knows ──────────────────────
// The model only ROUTES the question; every figure in the answer comes from a
// real query (see backend/services/ask.py). Anything that would change
// something arrives as a `proposal` and does nothing until it's approved.

export interface AskLine {
  text: string;
  strong?: boolean;
  muted?: boolean;
}

export interface AskProposal {
  /** `nudge` is the only one that leaves the building — it sends a drafted
   *  message. The others change a setting inside the app. */
  kind: 'rule' | 'label_rule' | 'config' | 'nudge';
  /** Button text — already phrased as the action ("File into Ops"). */
  label: string;
  payload: Record<string, unknown>;
}

export interface AskStat {
  value: string;
  label: string;
  /** 'warn' only when the number is bad news — colouring everything makes
   *  nothing stand out. */
  tone?: string;
}

export interface AskAnswer {
  intent: string;
  title: string;
  /** Headline figures, rendered as a report. Always counted rows. */
  stats?: AskStat[];
  lines: AskLine[];
  /** Where to go for the full view, when there is one. */
  link?: string;
  proposal?: AskProposal;
}

/** `context` is the route asked from, so "what's going on here?" on an account
 *  page resolves to that account rather than the whole mailbox. */
export const ask = async (question: string, context?: string): Promise<AskAnswer> =>
  (await api.post('/api/ask', { question, context })).data;

// ── Commitments: what YOU said you'd do ────────────────────────────────────
// Not "what needs a reply" — what you promised. Each row carries the sentence
// you actually wrote, so it can be checked rather than trusted. Exists only
// because the app reads threads now instead of counting them.

export interface Commitment {
  thread_id: string;
  /** The promise, one line. */
  what: string;
  /** The sentence you wrote, verified verbatim against the message. */
  quote: string;
  to: string;
  subject: string;
  promised_at: string | null;
  due_at: string | null;
  overdue_days: number;
}

export interface CommitmentsResponse {
  commitments: Commitment[];
  total: number;
  overdue: number;
}

export const getCommitments = async (limit = 20): Promise<CommitmentsResponse> =>
  (await api.get('/api/commitments', { params: { limit } })).data;

export const getAccounts = async (limit = 100): Promise<AccountsResponse> =>
  (await api.get('/api/accounts', { params: { limit } })).data;

/** One account. 404s honestly when the key is gone — a domain-keyed account
 *  becomes CRM-keyed the moment a CRM lookup lands, so a stale bookmark should
 *  say so rather than render a company with nothing in it. */
export const getAccount = async (key: string): Promise<AccountDetail> =>
  (await api.get(`/api/accounts/${encodeURIComponent(key)}`)).data;

// ── First run: reading the mailbox now, not over the next two hours ─────────
// A normal scan indexes 20 messages and the ledger walks 48 hours per sweep, so
// a freshly-connected mailbox takes hours to become useful — indistinguishable
// from the app being broken. `backfill` sweeps under a server-side time budget
// and returns progress; call it until `backfill_done`.

export interface OnboardingProgress {
  messages_indexed: number;
  threads: number;
  backfill_done: boolean;
  horizon_days: number;
  last_error: string;
  /** Open loops that would render as "(no subject) · someone" — indexed but not
   *  yet hydrated. A list you can't triage isn't a finished first run. */
  anonymous_loops: number;
  /** Indexed AND readable. This, not backfill_done, is the finish line. */
  complete?: boolean;
  swept?: number;
  /** Set when Gmail's broker throttled us mid-walk. Not a failure — wait this
   *  many seconds and call again; the walk resumes where it stopped. */
  paused_seconds?: number;
}

export const getOnboardingProgress = async (): Promise<OnboardingProgress> =>
  (await api.get('/api/onboarding/progress')).data;

export const runBackfill = async (): Promise<OnboardingProgress> =>
  (await api.post('/api/onboarding/backfill')).data;

// ── Mail: reading and writing ───────────────────────────────────────────────
// The watchdog half hands you a short list; this is for when a row isn't
// enough and you need to read the thread, reply in context, or write to
// someone the app never flagged.

export type MailBox = 'inbox' | 'unread' | 'sent' | 'starred' | 'archive';

export interface MailRow {
  id: string;
  thread_id: string;
  sender: string;
  subject: string;
  snippet: string;
  unread: boolean;
  starred: boolean;
  rfc822_msgid: string;
}

export interface MailMessage {
  id: string;
  sender: string;
  subject: string;
  body: string;
  /** Sent by the user — rendered on the other side of the conversation. */
  outbound: boolean;
  rfc822_msgid: string;
}

export interface MailThread {
  thread_id: string;
  subject: string;
  messages: MailMessage[];
  /** The ledger didn't know this conversation, so this is ONE message rather
   *  than the exchange. Said out loud instead of implying completeness. */
  partial: boolean;
  deep_link: string;
}

export const getMail = async (
  box: MailBox = 'inbox',
  pageToken = '',
  q = '',
): Promise<{ messages: MailRow[]; next_page_token: string; query: string }> =>
  (await api.get('/api/mail', { params: { box, page_token: pageToken, q } })).data;

export const getMailThread = async (threadId: string, seed = ''): Promise<MailThread> =>
  (await api.get(`/api/mail/thread/${threadId}`, { params: { seed } })).data;

/** Sends for real. A Gmail message id comes back, or it throws — never an
 *  optimistic success. 409 = Gmail not connected. */
export const sendMail = async (m: {
  to: string;
  subject?: string;
  body: string;
  thread_id?: string;
  in_reply_to?: string;
}): Promise<{ success: boolean; message_id: string }> =>
  (await api.post('/api/mail/send', m)).data;

export const archiveMail = async (id: string): Promise<void> => {
  await api.post(`/api/mail/${id}/archive`);
};
