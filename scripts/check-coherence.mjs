#!/usr/bin/env node
/*
 * Coherence / completeness gate.
 *
 * The identity gate (check-not-template.mjs) proves the app no longer LOOKS
 * like the seed. This gate proves the app is actually COHERENT and COMPLETE on
 * the dimensions that can be checked deterministically — the things a build can
 * silently skip and still "look done":
 *
 *   1. A real Definition of Done exists (you decided what success means).
 *   2. The discovery brief exists (you understood the problem before building).
 *   3. Multi-tenancy: every domain model is user-scoped (no cross-user leak).
 *
 * The SEMANTIC half — does the app actually SOLVE the problem, and is the
 * agent → workflow → widget wiring coherent — is judged by the `reviewer`
 * sub-agent (.claude/agents/reviewer.md), which a human/Claude Code runs before
 * declaring done. Together they mirror the platform's internal DoD gate so an
 * app built in Claude Code is held to the same bar as one the platform
 * generates.
 *
 * Runs:
 *   - as a Claude Code Stop hook (.claude/settings.json) alongside the identity
 *     gate — blocks "done" while a dimension is incomplete,
 *   - as `npm run check:coherence` (optional), and in CI.
 *
 * Inactive on the pristine seed: while `.claritty-seed-pristine` exists the gate
 * is off (the untouched template legitimately has no DoD/brief yet). Delete that
 * marker the moment you start building (see IDENTITY.md) to turn it on.
 */

import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PRISTINE_MARKER = join(ROOT, '.claritty-seed-pristine');

const read = (rel) => {
  const p = join(ROOT, rel);
  return existsSync(p) ? readFileSync(p, 'utf8') : null;
};

const failures = [];
const fail = (title, fix) => failures.push({ title, fix });

// Untouched seed: gate inactive (same contract as the identity gate).
if (existsSync(PRISTINE_MARKER)) {
  console.log(
    '✓ coherence gate inactive (pristine seed marker present). ' +
      'Delete .claritty-seed-pristine when you start building to enable it.',
  );
  process.exit(0);
}

// ── 1) Definition of Done must be set (app-config.json → …core_action.definition_of_done).
// Recursive search so we don't break if the surrounding key path is reshaped.
function findDefinitionOfDone(node) {
  if (!node || typeof node !== 'object') return undefined;
  if (typeof node.definition_of_done === 'string') return node.definition_of_done;
  for (const v of Object.values(node)) {
    const found = findDefinitionOfDone(v);
    if (found !== undefined) return found;
  }
  return undefined;
}
const cfgRaw = read('app-config.json');
if (cfgRaw === null) {
  fail('app-config.json is missing', 'Restore it from the seed.');
} else {
  let cfg = null;
  try {
    cfg = JSON.parse(cfgRaw);
  } catch {
    fail('app-config.json is not valid JSON', 'Fix the JSON syntax.');
  }
  if (cfg) {
    const dod = (findDefinitionOfDone(cfg) || '').trim();
    if (!dod) {
      fail(
        'No Definition of Done set (app-config.json … core_action.definition_of_done is empty)',
        'Write ONE concrete end-to-end success sentence — the bar for "done" — into ' +
          'app-config.json → core_action.definition_of_done (see .claude/prompts/brainstorm.md §6c).',
      );
    }
  }
}

// ── 2) The discovery brief must exist (problem understood before building).
if (!existsSync(join(ROOT, 'docs/plans/0001-brief.md'))) {
  fail(
    'Discovery brief missing (docs/plans/0001-brief.md)',
    'Run the discovery playbook (.claude/prompts/brainstorm.md): restate the problem, propose ' +
      '2 outcomes, ask the focused questions, and save the brief to docs/plans/0001-brief.md.',
  );
}

// ── 3) Multi-tenancy: every SQLAlchemy model (class …(Base)) must be user-scoped.
// A domain model without `user_id` silently leaks data across users.
const models = read('backend/models.py');
if (models === null) {
  fail('backend/models.py is missing', 'Restore it; every domain model lives here.');
} else {
  // Split into per-class blocks; a block runs until the next top-level `class `.
  const blocks = models.split(/\nclass /).map((b, i) => (i === 0 ? b : 'class ' + b));
  for (const block of blocks) {
    const m = block.match(/^class\s+(\w+)\s*\(\s*Base\s*\)/);
    if (!m) continue; // not a SQLAlchemy model
    const name = m[1];
    const hasTable = /__tablename__/.test(block);
    const hasUserId = /\buser_id\b\s*=\s*Column/.test(block);
    if (hasTable && !hasUserId) {
      fail(
        `Model "${name}" has no user_id column (multi-tenancy leak)`,
        `Add \`user_id = Column(String, nullable=False, index=True)\` to ${name} and filter every ` +
          `query by it (request.headers['X-User-ID']). See backend/models.py Task for the pattern.`,
      );
    }
  }
}

if (failures.length === 0) {
  console.log('✓ coherence gate passed (DoD set, brief present, models user-scoped).');
  process.exit(0);
}

console.error('\n✗ Coherence gate failed — the app is not coherent/complete yet:\n');
for (const { title, fix } of failures) {
  console.error(`  • ${title}`);
  console.error(`    → ${fix}\n`);
}
console.error(
  'Fix the items above (these are deterministic). Then run the `reviewer` sub-agent ' +
    '(.claude/agents/reviewer.md) for the semantic review before calling it done.\n',
);
process.exit(1);
