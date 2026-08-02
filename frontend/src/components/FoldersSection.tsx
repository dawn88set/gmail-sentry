import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FolderTree, Sparkles } from 'lucide-react';
import { Badge } from '@clarittyai/app-ui';
import { useToast } from '@/components/Toast';
import { ListSection, ListGroup, ListRow } from '@/components/ios/List';
import { Toggle } from '@/components/ios/Toggle';
import { getFolders, setFilingEnabled, toApiError } from '@/lib/api';

/**
 * The smart-filing switch, and a way through to the folders themselves.
 *
 * This used to be the whole folder surface — the approval queue and the folder
 * list lived here, buried under notification settings. That was the wrong home
 * twice over: a proposed folder is a question about the user's mail rather than
 * a preference, and it was easy to miss among the toggles. Folders now live on
 * Activity, where the rest of "what happened to my mail" is; Rules keeps the
 * on/off switch, which genuinely is a setting.
 *
 * The pending count stays visible here because an unanswered folder proposal
 * means mail is queued and not being filed, and the user shouldn't have to go
 * looking to find that out.
 */
export function FoldersSection() {
  const navigate = useNavigate();
  const { show } = useToast();
  const [enabled, setEnabled] = useState(false);
  const [pending, setPending] = useState(0);
  const [active, setActive] = useState(0);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await getFolders();
      setEnabled(!!d.filing_enabled);
      setPending(d.pending || 0);
      setActive((d.folders || []).filter((f) => f.status === 'active').length);
    } catch {
      /* settings screen — a missing folder count shouldn't shout */
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (next: boolean) => {
    setEnabled(next); // optimistic; the refetch below restores truth
    try {
      await setFilingEnabled(next);
      show({
        tone: 'success',
        text: next
          ? 'Filing on. New conversations will be proposed a folder — nothing is filed until you approve it.'
          : 'Filing off.',
      });
    } catch (err) {
      show({ tone: 'error', text: `Couldn’t change that: ${toApiError(err).message}` });
    } finally {
      void load();
    }
  };

  if (!loaded) return null;

  return (
    <ListSection
      title="Organize my mail"
      footer="Conversations are filed by who they're with — both your replies and theirs, so a thread lives in one place. Filing never hides anything: labelled mail stays in your inbox until you archive it."
    >
      <ListGroup variant="plain-mobile">
        <ListRow
          leading={
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
              <FolderTree className="h-5 w-5" />
            </span>
          }
          title={<span className="block text-[15px] font-semibold text-foreground">Smart filing</span>}
          subtitle="Files new conversations into folders you approve"
          trailing={<Toggle checked={enabled} onChange={toggle} />}
        />

        {enabled && (
          <ListRow
            onClick={() => navigate('/activity?tab=folders')}
            chevron
            leading={
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-muted/60 text-accent">
                {pending > 0 ? <Sparkles className="h-5 w-5" /> : <FolderTree className="h-5 w-5" />}
              </span>
            }
            title={<span className="block text-[15px] font-semibold text-foreground">Folders</span>}
            subtitle={
              pending > 0
                ? `${pending} waiting for your OK — nothing is filed until you answer`
                : active > 0
                  ? `${active} folder${active === 1 ? '' : 's'} in use`
                  : 'No folders yet — they’ll be suggested as mail arrives'
            }
            trailing={pending > 0 ? <Badge tone="warning">{pending}</Badge> : undefined}
          />
        )}
      </ListGroup>
    </ListSection>
  );
}

export default FoldersSection;
