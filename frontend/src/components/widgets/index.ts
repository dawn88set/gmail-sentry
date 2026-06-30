/**
 * B5 — Reusable widget templates.
 *
 * Compose one of these in your app's frontend/src/components/Widget.tsx instead
 * of hand-rolling. Each is presentational (data + size + callbacks). See each
 * file's header for which department/pattern it fits.
 *
 *   ApprovalCardWidget — draft → approve → send (Sales/Support/HR/IT)
 *   InboxQueueWidget    — read-first queue/count (Ops/generic triage)
 *   KpiMetricWidget     — focal metric + stats (Finance/Exec, read-only)
 *   DigestWidget        — summarized list (Marketing/Ops/Legal/Exec)
 */
export { ApprovalCardWidget } from './ApprovalCardWidget';
export { InboxQueueWidget } from './InboxQueueWidget';
export { KpiMetricWidget } from './KpiMetricWidget';
export { DigestWidget } from './DigestWidget';
export * from './types';
