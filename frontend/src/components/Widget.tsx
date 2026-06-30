import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { WidgetContainer, WidgetButton, WidgetBadge } from '@clarittyai/widget-toolkit';
import { getWidgetData, toggleTask, toApiError, type WidgetData, type TaskPriority, type WidgetTask } from '@/lib/api';
import { runQuickAction, notifyWidgetStateChanged } from '@/lib/widget-actions';
import { useToast } from '@/components/Toast';
import { cn } from '@/lib/utils';
import type { WidgetSize } from '@/lib/widget-sizes';

export type { WidgetSize };

interface WidgetProps {
  size?: WidgetSize;
  className?: string;
}

// Priority → Claritty UI-kit badge variant (consistent across all apps).
type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';
const PRIORITY_BADGE: Record<TaskPriority, { variant: BadgeVariant; label: string }> = {
  urgent: { variant: 'error', label: 'Urgent' },
  high: { variant: 'warning', label: 'High' },
  medium: { variant: 'info', label: 'Medium' },
  low: { variant: 'neutral', label: 'Low' },
};
function pBadge(p?: TaskPriority | null) {
  return PRIORITY_BADGE[(p as TaskPriority) || 'medium'] ?? PRIORITY_BADGE.medium;
}

/**
 * The dashboard widget — built from the published Claritty UI kit
 * (@clarittyai/widget-toolkit): WidgetContainer owns the liquid-glass surface,
 * rounded-3xl, exact sizes, padding, overflow, and the data-widget-size attr;
 * WidgetButton / WidgetBadge keep actions + chips on-brand. This is the shape
 * every generated app follows (see the platform's WIDGET_RULES).
 */
export default function Widget({ size = 'medium', className }: WidgetProps) {
  const [data, setData] = useState<WidgetData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { show } = useToast();

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => void fetchData(), 30000);
    // Refetch immediately when something in the same page mutates task data
    // (e.g. the agent-graph runner's "Run trigger" creates a task).
    const onRefresh = () => void fetchData();
    window.addEventListener('claritty:widget-refresh', onRefresh);
    return () => {
      clearInterval(interval);
      window.removeEventListener('claritty:widget-refresh', onRefresh);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size]);

  const fetchData = async () => {
    try {
      setData(await getWidgetData(size));
      setError(null);
    } catch (err) {
      setError('Failed to load tasks');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Meaningful action: complete a task in place. Optimistic, real API, then resync.
  const completeTask = async (id?: string | null) => {
    if (!id) return;
    setData((d) =>
      d
        ? {
            ...d,
            open_count: Math.max(0, (d.open_count ?? 0) - 1),
            done_today: (d.done_today ?? 0) + 1,
            tasks: (d.tasks ?? []).filter((t) => t.id !== id),
            top_task: undefined,
          }
        : d,
    );
    try {
      await runQuickAction({ actionId: 'complete-task', run: () => toggleTask(id) });
      notifyWidgetStateChanged();
    } catch (err) {
      // Never fail silently — tell the user why. A 409 means an integration this
      // action needs isn't connected; everything else shows the real message. The
      // finally-block refetch restores the optimistic change.
      const e = toApiError(err);
      show({
        tone: 'error',
        text:
          e.status === 409 || e.code === 'not_connected'
            ? 'Connect the required integration, then try again.'
            : `Couldn’t complete that: ${e.message}`,
      });
    } finally {
      void fetchData();
    }
  };

  if (loading) {
    return (
      <WidgetContainer size={size} className={cn('animate-pulse', className)}>
        <div className="mb-4 h-4 w-3/4 rounded bg-muted" />
        <div className="h-8 w-1/2 rounded bg-muted" />
      </WidgetContainer>
    );
  }

  if (error || !data) {
    // High-contrast on the glass surface in BOTH themes: the headline uses
    // text-foreground (muted-on-glass is ~2:1 and reads as invisible), and the
    // Retry uses the themed WidgetButton — never a hardcoded blue.
    return (
      <WidgetContainer
        size={size}
        className={cn('flex flex-col items-center justify-center gap-2 text-center', className)}
      >
        <p className="text-sm font-medium text-foreground">{error ?? 'No data yet'}</p>
        <WidgetButton variant="secondary" onClick={() => void fetchData()}>
          Retry
        </WidgetButton>
      </WidgetContainer>
    );
  }

  const open = data.open_count ?? 0;
  const done = data.done_today ?? 0;
  const tasks = data.tasks ?? [];

  // ---- Small: headline metric + one meaningful action ----------------------
  if (size === 'small') {
    return (
      <WidgetContainer size="small" className={cn('flex flex-col justify-between', className)}>
        <div>
          <div className={cn('text-5xl font-bold leading-none', open > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {open}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">
            open task{open === 1 ? '' : 's'}
          </div>
        </div>
        {open > 0 ? (
          <WidgetButton
            variant="primary"
            onClick={() => void completeTask(data.top_task_id)}
            icon={<Check className="h-4 w-4" />}
            className="w-full"
          >
            Complete top
          </WidgetButton>
        ) : (
          <span className="text-sm font-medium text-muted-foreground">All caught up ✓</span>
        )}
      </WidgetContainer>
    );
  }

  // ---- Medium: count + a 2-task peek you can complete ----------------------
  if (size === 'medium') {
    const shown = tasks.slice(0, 2);
    return (
      <WidgetContainer size="medium" className={cn('flex flex-row items-center gap-4', className)}>
        <div className="flex w-[34%] flex-shrink-0 flex-col justify-center">
          <div className={cn('text-4xl font-bold leading-none', open > 0 ? 'text-foreground' : 'text-muted-foreground')}>
            {open}
          </div>
          <div className="mt-1 text-xs font-medium text-muted-foreground">open</div>
          {done > 0 && <div className="mt-0.5 text-xs text-success">{done} done</div>}
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2.5">
          {shown.length > 0 ? (
            shown.map((t) => <TaskRow key={t.id} task={t} onComplete={completeTask} />)
          ) : (
            <span className="text-sm text-muted-foreground">All caught up ✓</span>
          )}
        </div>
      </WidgetContainer>
    );
  }

  // ---- Large: header + up to 3 completable tasks + footer ------------------
  const shown = tasks.slice(0, 3);
  const hidden = Math.max(0, open - shown.length);
  return (
    <WidgetContainer size="large" className={cn('flex flex-col', className)}>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold leading-none text-foreground">{open}</span>
          <span className="text-sm text-muted-foreground">open</span>
        </div>
        {done > 0 && <WidgetBadge variant="success">{done} done</WidgetBadge>}
      </div>

      <div className="flex flex-1 flex-col gap-3 overflow-hidden">
        {shown.length > 0 ? (
          shown.map((t, i) => <TaskRow key={t.id} task={t} detail={i === 0} onComplete={completeTask} />)
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            All caught up ✓
          </div>
        )}
      </div>

      {(hidden > 0 || data.last_updated) && (
        <div className="mt-3 truncate text-xs text-muted-foreground">
          {hidden > 0 ? `+${hidden} more · ` : ''}updated {data.last_updated}
        </div>
      )}
    </WidgetContainer>
  );
}

// A completable task row: a tap-to-complete circle + title (+ optional detail on
// the large widget's top row) + a UI-kit priority badge.
function TaskRow({
  task,
  detail = false,
  onComplete,
}: {
  task: WidgetTask & { suggested_action?: string | null };
  detail?: boolean;
  onComplete: (id: string) => void;
}) {
  const b = pBadge(task.priority);
  return (
    <div className="flex items-start gap-2.5">
      <button
        onClick={() => onComplete(task.id)}
        aria-label={`Complete "${task.title}"`}
        className="group mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-2 border-slate-300 transition-colors hover:border-success hover:bg-success dark:border-white/30"
      >
        <Check className="h-3 w-3 text-transparent group-hover:text-white" />
      </button>
      <div className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{task.title}</span>
        {detail && task.suggested_action && (
          <span className="block truncate text-xs text-muted-foreground">{task.suggested_action}</span>
        )}
      </div>
      <WidgetBadge variant={b.variant}>{b.label}</WidgetBadge>
    </div>
  );
}
