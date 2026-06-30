import {
  ArrowRight,
  Sparkles,
  Activity,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  PageHeader,
  Section,
  Card,
  CardContent,
  Stat,
  List,
  Row,
  Button,
  EmptyState,
} from '@clarittyai/app-ui';
import { appName } from '@/lib/app-meta';

/**
 * The app's landing page — the STARTER home that generation replaces with the
 * real work screen. It's also a worked example of composing a page from the
 * @clarittyai/app-ui kit: PageHeader (one primary action) → a Stat row → a
 * Section with a List → an EmptyState. Renders inside <Layout> (header + bg).
 */
export default function Dashboard() {
  return (
    <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6 lg:py-10">
      <PageHeader
        title={appName}
        description="Your starter app. Replace this page with the real work your users came for."
        action={
          <Button icon={<Sparkles className="h-4 w-4" />}>Get started</Button>
        }
      />

      {/* A Stat row — the at-a-glance metrics a home screen opens with. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-5">
            <Stat label="Active" value="—" icon={<Activity className="h-4 w-4" />} />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <Stat
              label="Done today"
              value="—"
              icon={<CheckCircle2 className="h-4 w-4" />}
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <Stat label="Pending" value="—" icon={<Clock className="h-4 w-4" />} />
          </CardContent>
        </Card>
      </div>

      <Section title="Build your app">
        <List>
          <Row
            title="Compose from the kit"
            subtitle="Use @clarittyai/app-ui primitives (PageHeader, Section, Card, Stat, List, Table, Dialog, EmptyState/ErrorState) so every screen stays on-brand and handles its states."
          />
          <Row
            title="Wire your data"
            subtitle="Add backend agents, workflows, and triggers; surface a glance in the widget — then route this page to your real home screen."
          />
        </List>
        <Link
          to="/tasks"
          className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-accent"
        >
          See the example task screen <ArrowRight className="h-4 w-4" />
        </Link>
      </Section>

      <Section title="Your home screen">
        <EmptyState
          title="Nothing here yet"
          description="This is where your app's primary content will live once you build it."
          action={<Button variant="secondary">Open the example</Button>}
        />
      </Section>
    </div>
  );
}
