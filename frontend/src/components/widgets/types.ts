/**
 * B5 — Shared widget data shape.
 *
 * The reusable widget components in this folder are PRESENTATIONAL: they take a
 * `data` object (the payload from the shared item_routes `/api/widget`) + a
 * `size` + optional action callbacks, and render. The app's own
 * `frontend/src/components/Widget.tsx` does the fetching/polling and composes
 * one of these — so a fork's Widget.tsx is a few lines.
 *
 * This matches what backend/shared/item_routes.py:make_item_router emits.
 */

export type Priority = 'low' | 'medium' | 'high' | 'urgent';

export interface WidgetItem {
  id: string;
  title: string;
  status: string;
  priority: Priority;
  body?: string | null;
}

export interface ItemWidgetData {
  title?: string | null;
  open_count: number;
  pending_count: number;
  published_today?: number;
  by_status?: Record<string, number>;
  items?: WidgetItem[];
  // small-size extras
  top_title?: string | null;
  top_id?: string | null;
  top_priority?: Priority | null;
  last_updated: string;
}

// KpiMetricWidget data (Finance/Exec) — a focal metric + optional secondary stats.
export interface KpiStat {
  label: string;
  value: string | number;
  delta?: string;
  deltaTone?: 'success' | 'error' | 'neutral';
}
export interface KpiWidgetData {
  title?: string | null;
  primary: KpiStat;
  stats?: KpiStat[];
  last_updated?: string;
}

// DigestWidget data (Marketing/Ops/Legal/Exec) — a short summarized list.
export interface DigestEntry {
  id: string;
  title: string;
  subtitle?: string | null;
}
export interface DigestWidgetData {
  title?: string | null;
  headline?: string | null;
  entries: DigestEntry[];
  last_updated?: string;
}

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';

export const PRIORITY_BADGE: Record<Priority, { variant: BadgeVariant; label: string }> = {
  urgent: { variant: 'error', label: 'Urgent' },
  high: { variant: 'warning', label: 'High' },
  medium: { variant: 'info', label: 'Medium' },
  low: { variant: 'neutral', label: 'Low' },
};

export function priorityBadge(p?: Priority | null) {
  return PRIORITY_BADGE[(p as Priority) || 'medium'] ?? PRIORITY_BADGE.medium;
}
