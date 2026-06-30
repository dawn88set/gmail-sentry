import { useEffect, useState } from 'react';
import { Plus, Trash2, Check, ListTodo, AlertCircle } from 'lucide-react';
import {
  Button,
  Input,
  Textarea,
  Field,
  Card,
  Dialog,
  Table,
  THead,
  TBody,
  TR,
  TH,
  TD,
  EmptyState,
  Skeleton,
  Badge,
  type BadgeTone,
} from '@clarittyai/app-ui';
import {
  getTasks,
  createTask,
  toggleTask,
  deleteTask,
  type Task,
  type TaskPriority,
} from '@/lib/api';
import { cn } from '@/lib/utils';

/**
 * A REAL app screen (list → create → toggle → delete) built from the
 * @clarittyai/app-ui kit against the Task API. This is the pattern to copy for
 * your own pages: page-level loading / empty / error states, a form dialog
 * (<Field> + <Input>), and a <Table>.
 */

const PRIORITY_TONE: Record<TaskPriority, BadgeTone> = {
  urgent: 'destructive',
  high: 'warning',
  medium: 'accent',
  low: 'neutral',
};

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [status, setStatus] = useState<'loading' | 'error' | 'ready'>('loading');
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setStatus('loading');
    try {
      setTasks(await getTasks());
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || saving) return;
    setSaving(true);
    try {
      const created = await createTask(title.trim(), notes.trim() || undefined);
      setTasks((prev) => [created, ...prev]);
      setTitle('');
      setNotes('');
      setCreating(false);
    } catch {
      /* keep the dialog open on failure */
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (id: string) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
    try {
      await toggleTask(id);
    } catch {
      void load();
    }
  };

  const remove = async (id: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
    try {
      await deleteTask(id);
    } catch {
      void load();
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Tasks</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            An example CRUD screen — each task is auto-prioritized by the agent.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> New task
        </Button>
      </header>

      {status === 'loading' && (
        <Card className="divide-y divide-border">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3 p-4">
              <Skeleton className="h-5 w-5 rounded-full" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-5 w-14 rounded-full" />
            </div>
          ))}
        </Card>
      )}

      {status === 'error' && (
        <EmptyState
          icon={<AlertCircle className="h-7 w-7" />}
          title="Couldn't load your tasks"
          description="The backend may still be starting."
          action={
            <Button variant="secondary" onClick={() => void load()}>
              Try again
            </Button>
          }
        />
      )}

      {status === 'ready' && tasks.length === 0 && (
        <EmptyState
          icon={<ListTodo className="h-7 w-7" />}
          title="No tasks yet"
          description="Create your first task — it'll be prioritized automatically."
          action={<Button onClick={() => setCreating(true)}>New task</Button>}
        />
      )}

      {status === 'ready' && tasks.length > 0 && (
        <Table>
          <THead>
            <TR>
              <TH className="w-10" />
              <TH>Task</TH>
              <TH className="w-24">Priority</TH>
              <TH className="w-10" />
            </TR>
          </THead>
          <TBody>
            {tasks.map((t) => (
              <TR key={t.id}>
                <TD>
                  <button
                    onClick={() => void toggle(t.id)}
                    aria-label={t.done ? 'Mark not done' : 'Mark done'}
                    className={cn(
                      'flex h-5 w-5 items-center justify-center rounded-full border-2 transition-colors',
                      t.done ? 'border-success bg-success text-white' : 'border-border hover:border-accent',
                    )}
                  >
                    {t.done && <Check className="h-3 w-3" />}
                  </button>
                </TD>
                <TD>
                  <div className={cn('font-medium', t.done && 'text-muted-foreground line-through')}>{t.title}</div>
                  {t.suggested_action && !t.done && (
                    <div className="mt-0.5 text-xs text-muted-foreground">{t.suggested_action}</div>
                  )}
                </TD>
                <TD>
                  <Badge tone={PRIORITY_TONE[t.priority] ?? 'neutral'} className="capitalize">
                    {t.priority}
                  </Badge>
                </TD>
                <TD>
                  <button
                    onClick={() => void remove(t.id)}
                    aria-label="Delete task"
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <Dialog open={creating} onClose={() => setCreating(false)} title="New task" description="It'll be prioritized by the agent on create.">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Title" htmlFor="t-title">
            <Input
              id="t-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Reply to the partnership email"
              autoFocus
            />
          </Field>
          <Field label="Notes (optional)" htmlFor="t-notes">
            <Textarea id="t-notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any context…" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!title.trim() || saving}>
              {saving ? 'Adding…' : 'Add task'}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
