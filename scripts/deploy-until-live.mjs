#!/usr/bin/env node
/**
 * Deploy THIS app to Claritty and keep trying until it actually lands, then
 * publish it live.
 *
 * Claritty's image build currently succeeds only intermittently. On 2026-08-02
 * five consecutive deploys to this app built fine between 16:38 and 17:29Z;
 * outside windows like that, everything fails — including an untouched
 * `create-claritty-app` seed, which is how we know it isn't this repo.
 *
 * So the only thing left is patience, applied correctly:
 *
 *   1. deploy to the SAME app (the one pinned in .claritty.json), so the URL,
 *      the data, the integrations and the marketplace submission all survive.
 *      deploy-fresh.mjs makes a new app instead and throws those away — use
 *      this one unless you specifically want a new app.
 *   2. ignore what the CLI prints. It says "is live in your workspace" before
 *      the build finishes, says the same when the build fails, and has also
 *      reported failure for a build that was still running. Only the API's
 *      draftDeployedAt / draftErrorAt tell the truth.
 *   3. when the draft finally builds, PUBLISH it — a successful draft does not
 *      update the live app on its own.
 *   4. confirm the live app actually moved before claiming anything.
 *
 * Usage:  node scripts/deploy-until-live.mjs
 *         ATTEMPTS=60 WAIT_MIN=10 node scripts/deploy-until-live.mjs
 *
 * Don't run `claritty deploy` by hand while this is going — two deploys to one
 * app collide, and the loser reports a confusing error about a purged source.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';

const API = 'https://api.claritty.ai';
const ROOT = path.resolve(import.meta.dirname, '..');
const ATTEMPTS = Number(process.env.ATTEMPTS || 60);
const WAIT_MIN = Number(process.env.WAIT_MIN || 10);

const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
const stamp = () => new Date().toISOString().slice(11, 19);

const token = () =>
  JSON.parse(readFileSync(path.join(homedir(), '.claritty/credentials.json'), 'utf8'))[API]
    .session.accessToken;

const api = (method, url, body) => {
  const args = ['-s', '-X', method, '-H', `Authorization: Bearer ${token()}`];
  if (body) args.push('-H', 'Content-Type: application/json', '-d', JSON.stringify(body));
  args.push(`${API}${url}`);
  try { return JSON.parse(execFileSync('curl', args, { encoding: 'utf8' })); } catch { return null; }
};

const templateId = JSON.parse(readFileSync(path.join(ROOT, '.claritty.json'), 'utf8'))
  .deployments?.[API]?.templateId;
if (!templateId) {
  console.error('  .claritty.json has no templateId — run `claritty deploy` once first.');
  process.exit(1);
}

const appRow = () => {
  const d = api('GET', '/api/apps')?.data;
  const rows = Array.isArray(d) ? d : d?.apps || [];
  return rows.find((a) => a?.templateId === templateId) || null;
};

const app = appRow();
if (!app) {
  console.error(`  no installed app found for template ${templateId}.`);
  process.exit(1);
}
console.log(`  app        ${app.name}  (${app.id})`);
console.log(`  live build ${app.deployedAt}`);
console.log(`  retrying every ${WAIT_MIN} min, up to ${ATTEMPTS} times\n`);

const state = () => {
  const a = api('GET', `/api/apps/${app.id}`)?.data || {};
  return { err: a.draftErrorAt || null, draft: a.draftDeployedAt || null, live: a.deployedAt || null };
};

let base = state();

for (let n = 1; n <= ATTEMPTS; n++) {
  console.log(`  ${stamp()}  attempt ${n}/${ATTEMPTS} …`);
  spawnSync('claritty', ['deploy', '--yes', '--skip-gates'], { cwd: ROOT, encoding: 'utf8' });

  // Wait for a terminal signal from the API, not from the CLI.
  let outcome = 'timeout';
  for (let i = 0; i < 30; i++) {
    sleep(15000);
    const s = state();
    if (s.draft && s.draft !== base.draft) { outcome = 'built'; base = s; break; }
    if (s.err && s.err !== base.err) { outcome = 'failed'; base = s; break; }
  }

  if (outcome !== 'built') {
    console.log(`  ${stamp()}  ${outcome === 'failed' ? 'build failed' : 'no verdict'} — waiting ${WAIT_MIN} min`);
    if (n === ATTEMPTS) break;
    sleep(WAIT_MIN * 60_000);
    continue;
  }

  // The draft built. That does NOT update the live app — publish it.
  console.log(`  ${stamp()}  draft BUILT (${base.draft}) — publishing to live …`);
  api('POST', `/api/generation/apps/${app.id}/publish-draft`, {});

  for (let i = 0; i < 40; i++) {
    sleep(15000);
    const s = state();
    if (s.live && s.live !== app.deployedAt) {
      console.log(`\n  ✓ LIVE — deployedAt ${s.live}`);
      console.log(`    https://app.claritty.ai/apps/${app.id}`);
      process.exit(0);
    }
    if (s.err && s.err !== base.err) { console.log(`  ${stamp()}  publish failed — back to retrying`); base = s; break; }
  }
  if (n === ATTEMPTS) break;
  sleep(WAIT_MIN * 60_000);
}

console.error(`\n  ✗ ${ATTEMPTS} attempts and Claritty's build never succeeded.`);
console.error('    Nothing was left behind; the live app is untouched.');
process.exit(1);
