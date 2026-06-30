#!/usr/bin/env node
/*
 * B6 — Department-app fork tool.
 *
 * Forks THIS seed (including the shared "app factory" blocks in backend/shared/)
 * into a new local app directory, activates the identity gate, and pre-fills the
 * app for a chosen department from a preset (integrations + recommended shared
 * agents + a starter theme + identity).
 *
 * Why a local fork (vs `claritty:new` / create-claritty-app): the published CLI
 * clones the REMOTE seed over the network, which doesn't yet carry the B1–B3
 * factory blocks. This copies the local seed so every fork inherits the spine,
 * the make_item_router HITL, and the gmail/slack adapters immediately — offline.
 *
 * Usage:
 *   node scripts/new-department-app.mjs <app-slug> --dept <dept> \
 *        [--name "Display Name"] [--desc "One line"] [--dir <parent dir>]
 *
 * Departments: sales | support | finance | hr | marketing | operations | it |
 *              exec | legal
 *
 * After forking, the new app still needs the human/agent finishing the gate
 * requires (real Dashboard, own logo, delete seed example agent/workflow/trigger,
 * implement the domain). The fork does the mechanical 80%: copy + identity +
 * preset wiring + a NEXT_STEPS guide that points at the shared blocks.
 */

import {
  cpSync, existsSync, readFileSync, writeFileSync, rmSync, mkdirSync,
} from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve, basename } from 'node:path';

const SEED_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

// --- department presets ----------------------------------------------------
// `integrations` are catalog ids. NOTE: only ids present in
// shared/integrations-catalog.json render in the Connect UI today (gmail,
// openai). Others (slack, hubspot, stripe, google-*) have working ADAPTERS but
// still need a catalog entry before the Connect checklist shows them — flagged
// per fork in NEXT_STEPS so it's never a silent gap.
const PRESETS = {
  sales: {
    title: 'Sales',
    integrations: ['gmail', 'hubspot'],
    agents: ['triage-classify', 'draft-generate'],
    widget: 'ApprovalCardWidget',
    accent: '221 83% 53%', accent600: '221 83% 45%', primary: '222 47% 11%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Triage inbound leads, draft personalized follow-ups, approve before send.',
  },
  support: {
    title: 'Customer Support',
    integrations: ['gmail', 'slack'],
    agents: ['triage-classify', 'draft-generate'],
    widget: 'ApprovalCardWidget',
    accent: '173 80% 36%', accent600: '173 80% 28%', primary: '200 18% 12%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Classify tickets by intent/urgency, draft grounded replies, human approves.',
  },
  finance: {
    // NOTE: stripe/accounting are NOT Claritty-managed yet (not in
    // integrations-v2/config/oauth-configs.ts) — read invoices from email/drive
    // until stripe is added to the managed registry.
    title: 'Finance & Accounting',
    integrations: ['gmail', 'google-drive'],
    agents: ['extract-structured'],
    widget: 'KpiMetricWidget',
    accent: '142 71% 35%', accent600: '142 71% 27%', primary: '155 25% 10%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Extract invoices/payments to structured records, flag anomalies, route for approval.',
  },
  hr: {
    title: 'HR & Recruiting',
    integrations: ['gmail', 'google-drive'],
    agents: ['extract-structured', 'triage-classify'],
    widget: 'ApprovalCardWidget',
    accent: '262 83% 58%', accent600: '262 83% 50%', primary: '263 30% 12%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Parse resumes against a role, rank candidates, draft next-step emails.',
  },
  marketing: {
    title: 'Marketing',
    integrations: ['google-drive'],
    agents: ['draft-generate'],
    widget: 'DigestWidget',
    accent: '339 82% 52%', accent600: '339 82% 44%', primary: '335 25% 12%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Turn a brief into on-brand blog + social drafts; human edits/approves before publish.',
  },
  operations: {
    title: 'Operations',
    integrations: ['gmail', 'google-drive'],
    agents: ['extract-structured'],
    widget: 'DigestWidget',
    accent: '25 95% 53%', accent600: '25 95% 45%', primary: '24 30% 12%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Ingest forms/PDFs, extract to structured data, route by rules.',
  },
  it: {
    title: 'IT Help Desk',
    integrations: ['slack'],
    agents: ['triage-classify', 'draft-generate'],
    widget: 'ApprovalCardWidget',
    accent: '199 89% 48%', accent600: '199 89% 40%', primary: '205 30% 12%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Triage internal IT requests, draft grounded answers, route the rest.',
  },
  exec: {
    title: 'Executive / Leadership',
    integrations: ['gmail', 'google-calendar', 'google-drive'],
    agents: ['summarize-digest'],
    widget: 'KpiMetricWidget',
    accent: '243 75% 59%', accent600: '243 75% 51%', primary: '245 30% 12%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Read-only sweep across tools into one morning digest with KPIs + highlights.',
  },
  legal: {
    title: 'Legal & Compliance',
    integrations: ['google-drive'],
    agents: ['extract-structured', 'summarize-digest'],
    widget: 'DigestWidget',
    accent: '215 28% 35%', accent600: '215 28% 27%', primary: '215 30% 10%',
    font: "'Inter', system-ui, sans-serif",
    blurb: 'Extract key clauses/terms/risks from contracts into a structured summary.',
  },
};

// Claritty-MANAGED integration ids (platform-brokered OAuth in
// clarity-api integrations-v2/config/oauth-configs.ts). An app may only
// reference these for one-click Connect; anything else needs BYO/api-key or
// must be added to the managed registry first.
const MANAGED_IDS = new Set([
  'gmail', 'google-calendar', 'google-drive', 'outlook', 'outlook-calendar',
  'slack', 'microsoft-teams', 'hubspot', 'salesforce', 'github', 'jira',
  'linear', 'asana', 'notion', 'linkedin',
]);

// directories/files never copied into a fork.
const EXCLUDE = new Set([
  'node_modules', '.git', '__pycache__', '.pytest_cache', 'dist', 'build',
  '.venv', 'venv', 'coverage', '.DS_Store', '.env', '.claritty-seed-pristine',
]);

// --- arg parsing -----------------------------------------------------------
function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) out[a.slice(2)] = argv[++i];
    else out._.push(a);
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
const slug = args._[0];
const dept = (args.dept || 'sales').toLowerCase();

if (!slug || args.help) {
  console.error('Usage: node scripts/new-department-app.mjs <app-slug> --dept <dept> [--name "..."] [--desc "..."] [--dir <parent>]');
  console.error('Departments: ' + Object.keys(PRESETS).join(' | '));
  process.exit(slug ? 0 : 1);
}
const preset = PRESETS[dept];
if (!preset) {
  console.error(`Unknown department '${dept}'. Choose: ${Object.keys(PRESETS).join(' | ')}`);
  process.exit(1);
}

const displayName = args.name || `${preset.title} Assistant`;
const description = args.desc || preset.blurb;
const parentDir = resolve(args.dir || join(SEED_ROOT, '..'));
const target = join(parentDir, slug);

if (existsSync(target)) {
  console.error(`Target already exists: ${target}`);
  process.exit(1);
}

// --- copy ------------------------------------------------------------------
mkdirSync(target, { recursive: true });
cpSync(SEED_ROOT, target, {
  recursive: true,
  filter: (src) => {
    const name = basename(src);
    if (EXCLUDE.has(name)) return false;
    if (name.endsWith('.pyc')) return false;
    return true;
  },
});
// Guarantee the gate is active in the fork (marker must be absent).
const marker = join(target, '.claritty-seed-pristine');
if (existsSync(marker)) rmSync(marker);

// --- identity: app-meta.ts -------------------------------------------------
// Write a CLEAN file (don't regex-patch the seed's) — the seed's comment quotes
// "Claritty Template", and the identity gate's name check doesn't strip
// comments, so leaving it trips a false "still named the template" failure.
const metaPath = join(target, 'frontend/src/lib/app-meta.ts');
if (existsSync(metaPath)) {
  writeFileSync(metaPath, `/*
 * App identity for ${displayName}.
 */
export const appName = ${JSON.stringify(displayName)};
export const appDescription = ${JSON.stringify(description)};

// The marketplace widget host labels the widget from document.title, so set it
// from the app's OWN name.
if (typeof document !== 'undefined' && appName) {
  document.title = appName;
}
`);
}

// --- identity: theme.css starter override (gate requires an active --brand-) -
const themePath = join(target, 'frontend/src/theme.css');
if (existsSync(themePath)) {
  const base = readFileSync(themePath, 'utf8');
  const override = `\n/* ${preset.title} starter palette — tune these to the brand before demo. */\n:root {\n  --brand-accent: ${preset.accent};\n  --brand-accent-600: ${preset.accent600};\n  --brand-primary: ${preset.primary};\n  --brand-font: ${preset.font};\n}\n`;
  writeFileSync(themePath, base + override);
}

// --- intelligence.yaml: set id + integrations from preset ---------------------------
const yamlPath = join(target, 'intelligence.yaml');
if (existsSync(yamlPath)) {
  let yaml = readFileSync(yamlPath, 'utf8');
  yaml = yaml.replace(/^id:\s*.*$/m, `id: ${slug}`);
  const intLines = preset.integrations.length
    ? preset.integrations.map((id) => `  - ${id}`).join('\n')
    : '  []';
  yaml = yaml.replace(/^integrations:\s*\[\]\s*$/m, `integrations:\n${intLines}`);
  writeFileSync(yamlPath, yaml);
}

// --- NEXT_STEPS guide ------------------------------------------------------
const notReady = preset.integrations.filter((id) => !MANAGED_IDS.has(id));
const nextSteps = `# ${displayName} — fork next steps

Forked from the local seed for the **${preset.title}** department.
${description}

## What the fork already did
- Copied the seed **including** the shared factory blocks (\`backend/shared/spine.py\`,
  \`backend/shared/item_routes.py\`, \`backend/shared/adapters/\`).
- Activated the identity gate (\`.claritty-seed-pristine\` removed).
- Set app name/description (\`frontend/src/lib/app-meta.ts\`) and a starter palette
  (\`frontend/src/theme.css\`).
- Wired \`intelligence.yaml\`: \`id: ${slug}\`, integrations: ${preset.integrations.join(', ') || '(none)'}.

## What you still need to do (the gate enforces real work)
1. **Domain model** — in \`backend/models.py\`, replace \`Task\` with your item:
   \`\`\`python
   from backend.shared.spine import ItemMixin, LifecycleMixin
   class Item(Base, ItemMixin, LifecycleMixin):
       __tablename__ = "items"
   \`\`\`
2. **Routes** — replace \`backend/routes/app.py\` body with the factory:
   \`\`\`python
   from backend.shared.item_routes import make_item_router
   from backend.shared.adapters import gmail   # or slack
   def _publish(db, user_id, item): ...        # return {"external_id": ...}
   router = make_item_router(models.Item, publish=_publish)
   \`\`\`
3. **Agents** — implement the recommended shared patterns: ${preset.agents.join(', ')}
   (delete the seed example agent/workflow/trigger once yours exist).
4. **Widget** — compose \`${preset.widget}\` in \`frontend/src/components/Widget.tsx\`.
5. **Identity finish** — real Dashboard + own logo (gate still red until done).
6. Run \`npm run check:identity\` and the backend tests.
${notReady.length ? `
## ⚠ Not Claritty-managed
These ids are **not in the managed registry** (clarity-api
integrations-v2/config/oauth-configs.ts), so platform one-click Connect won't
work for them: **${notReady.join(', ')}**. Either use a managed id, ship an
api-key/BYO flow, or add them to oauth-configs.ts first.
` : ''}`;
writeFileSync(join(target, 'FORK_NEXT_STEPS.md'), nextSteps);

// --- report ----------------------------------------------------------------
console.log(`✅ Forked ${preset.title} app → ${target}`);
console.log(`   name: ${displayName}`);
console.log(`   integrations: ${preset.integrations.join(', ') || '(none)'}`);
console.log(`   shared agents to implement: ${preset.agents.join(', ')}`);
if (notReady.length) {
  console.log(`   ⚠ not Claritty-managed (no one-click Connect): ${notReady.join(', ')}`);
}
console.log(`\nNext: open ${slug}/FORK_NEXT_STEPS.md`);
