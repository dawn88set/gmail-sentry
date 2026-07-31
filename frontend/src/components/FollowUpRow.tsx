import { Badge, type BadgeTone } from '@clarittyai/app-ui';
import { Avatar } from '@/components/Avatar';
import { ListRow } from '@/components/ios/List';
import type { FollowUp } from '@/lib/api';
import { cn } from '@/lib/utils';

/** How long ago, compactly. */
function since(iso?: string | null): { label: string; hours: number } {
  if (!iso) return { label: '', hours: 0 };
  const t = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).getTime();
  if (Number.isNaN(t)) return { label: '', hours: 0 };
  const mins = Math.max(0, Math.floor((Date.now() - t) / 60000));
  const hours = mins / 60;
  if (mins < 60) return { label: `${mins}m`, hours };
  if (mins < 1440) return { label: `${Math.floor(mins / 60)}h`, hours };
  const days = Math.floor(mins / 1440);
  if (days < 14) return { label: `${days}d`, hours };
  return { label: `${Math.floor(days / 7)}w`, hours };
}

const STATE_LABEL: Record<string, string> = {
  awaiting_you: 'You owe',
  awaiting_them: 'Waiting on',
  going_cold: 'Going cold',
  snoozed: 'Snoozed',
  done: 'Done',
  ignored: 'Not a loop',
};

/**
 * One open loop.
 *
 * The row leads with the **ask**, not the subject: "Re: Q3" tells you nothing,
 * "needs the revised quote before Friday" tells you what to do without opening
 * the email. The subject drops to a secondary chip.
 *
 * The age chip is the risk signal — it escalates from muted to warning once the
 * thread passes what's normal *for this person*, and to destructive when it's
 * gone properly cold. That threshold is per-relationship (see the backend's
 * stale_after_hours), which is why a slow correspondent doesn't turn red early.
 */
export function FollowUpRow({ followUp, onClick }: { followUp: FollowUp; onClick: () => void }) {
  const f = followUp;
  const clock = f.state === 'awaiting_you' ? f.last_inbound_at : f.last_outbound_at;
  const age = since(clock ?? f.last_activity_at);

  const stale = Math.max(1, f.stale_after_hours || 72);
  const ageTone =
    f.state === 'going_cold' || age.hours >= stale * 1.5
      ? 'text-destructive'
      : age.hours >= stale
        ? 'text-warning'
        : 'text-muted-foreground';

  const stateTone: BadgeTone =
    f.state === 'going_cold' ? 'warning' : f.state === 'awaiting_you' ? 'accent' : 'neutral';

  const who = f.counterparty_name || f.counterparty_email || 'Unknown';
  // Fall back to the subject when nothing was asked — better than an empty row.
  const headline = f.ask_summary || f.subject || '(no subject)';

  return (
    <ListRow
      onClick={onClick}
      leading={<Avatar name={f.counterparty_name} email={f.counterparty_email} className="h-9 w-9 text-sm" />}
      title={
        <div className="flex items-baseline gap-2">
          <span className="min-w-0 flex-1 truncate text-[15px] font-semibold text-foreground">{who}</span>
          {age.label && (
            <span className={cn('flex-shrink-0 text-[12px] font-medium tabular-nums', ageTone)}>
              {age.label}
            </span>
          )}
        </div>
      }
      subtitle={
        <div className="mt-0.5 space-y-1">
          <div className="truncate text-[13px] text-foreground/80">{headline}</div>
          <div className="flex items-center gap-1.5">
            <Badge tone={stateTone}>{STATE_LABEL[f.state] ?? f.state}</Badge>
            {f.ask_summary && f.subject && (
              <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">
                {f.subject}
              </span>
            )}
            {f.nudge_count > 0 && (
              <span className="flex-shrink-0 text-[12px] text-muted-foreground">
                nudged {f.nudge_count}×
              </span>
            )}
          </div>
        </div>
      }
      chevron
    />
  );
}

export default FollowUpRow;
