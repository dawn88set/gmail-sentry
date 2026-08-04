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
// APP_DIR lets this drive a copy of the app that carries a different identity
// (a second app instance, say) without touching the repo's own binding.
const ROOT = process.env.APP_DIR || path.resolve(import.meta.dirname, '..');
const ATTEMPTS = Number(process.env.ATTEMPTS || 60);
const WAIT_MIN = Number(process.env.WAIT_MIN || 10);

const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
const stamp = () => new Date().toISOString().slice(11, 19);

const token = () =>
  JSON.parse(readFileSync(path.join(homedir(), '.claritty/credentials.json'), 'utf8'))[API]
    .session.accessToken;

// Distinguishes "the call failed" from "the call said no". Without that, an
// expired session reads exactly like a build that hasn't finished — the loop
// would sit there for ten hours reporting "no verdict" and never say why.
const api = (method, url, body) => {
  const args = ['-s', '-w', '\n%{http_code}', '-X', method, '-H', `Authorization: Bearer ${token()}`];
  if (body) args.push('-H', 'Content-Type: application/json', '-d', JSON.stringify(body));
  args.push(`${API}${url}`);
  let raw;
  try { raw = execFileSync('curl', args, { encoding: 'utf8' }); }
  catch (e) { return { ok: false, why: `curl: ${e.message}` }; }
  const nl = raw.lastIndexOf('\n');
  const code = Number(raw.slice(nl + 1));
  if (code === 401 || code === 403) return { ok: false, why: `HTTP ${code} — run \`claritty login\`` };
  if (code >= 400) return { ok: false, why: `HTTP ${code}` };
  try { return { ok: true, body: JSON.parse(raw.slice(0, nl)) }; }
  catch { return { ok: false, why: 'non-JSON response' }; }
};

const templateId = JSON.parse(readFileSync(path.join(ROOT, '.claritty.json'), 'utf8'))
  .deployments?.[API]?.templateId;
if (!templateId) {
  console.error('  .claritty.json has no templateId — run `claritty deploy` once first.');
  process.exit(1);
}

const listed = api('GET', '/api/apps');
if (!listed.ok) {
  console.error(`  can't reach the platform: ${listed.why}`);
  process.exit(1);
}
const rowsRaw = listed.body?.data;
const rows = Array.isArray(rowsRaw) ? rowsRaw : rowsRaw?.apps || [];
const app = rows.find((a) => a?.templateId === templateId) || null;
if (!app) {
  console.error(`  no installed app found for template ${templateId}.`);
  process.exit(1);
}
console.log(`  app        ${app.name}  (${app.id})`);
console.log(`  live build ${app.deployedAt}`);
console.log(`  retrying every ${WAIT_MIN} min, up to ${ATTEMPTS} times\n`);

const state = () => {
  const r = api('GET', `/api/apps/${app.id}`);
  if (!r.ok) return { down: r.why };
  const a = r.body?.data || {};
  return {
    err: a.draftErrorAt || null,
    draft: a.draftDeployedAt || null,
    live: a.deployedAt || null,
    // A deploy the platform records as done is not a deploy that runs. On
    // 2026-08-04 app ace13c1b went ACTIVE / "Ready" / progress 100 with
    // isHealthy true and containerId null — nothing was started, the app pane
    // rendered blank, and hitting the origin never brought one up. So a moved
    // deployedAt is necessary but not sufficient: insist on a container.
    container: a.containerId || null,
    // The platform's own triage of the failure. Today it self-classifies as
    // infra — type UNKNOWN, userActionable false, "Deployment was interrupted -
    // please retry" — which is the whole justification for this loop. If that
    // ever changes into a real code error, retrying is the wrong move and the
    // loop stops instead of hammering a fault only we can fix.
    infra: (a.errorAnalysis?.userActionable ?? false) === false,
    why: a.errorAnalysis?.technicalDetails || a.draftError || a.error || '',
  };
};

/*
 * There is deliberately no HTTP serving probe here. The app origin
 * (`<id>.apps.claritty.ai`) answers 403 {"error":"Forbidden"} to every path —
 * `/`, `/api/*`, with a bearer token or without — because it is only reachable
 * through the platform's own proxy with a signed session. So curl returns 403
 * for old code and new code alike and can prove nothing.
 *
 * A moved `deployedAt` is therefore the strongest signal available from here,
 * and it is NOT the same as "the new build is serving" — the platform has
 * reported a deploy as active twice running when only the first landed. The
 * only real confirmation is opening the app in a signed-in browser and looking
 * for something that exists solely in this code (the Mail tab, the worklist on
 * Today). The script says so rather than overclaiming.
 */

let base = state();
if (base.down) { console.error(`  can't read app state: ${base.down}`); process.exit(1); }

for (let n = 1; n <= ATTEMPTS; n++) {
  console.log(`  ${stamp()}  attempt ${n}/${ATTEMPTS} …`);
  spawnSync('claritty', ['deploy', '--yes', '--skip-gates'], { cwd: ROOT, encoding: 'utf8' });

  // Wait for a terminal signal from the API, not from the CLI.
  let outcome = 'timeout';
  let down = null;
  for (let i = 0; i < 30; i++) {
    sleep(15000);
    const s = state();
    if (s.down) { down = s.down; continue; }
    // A first-time app has no draft to build — a successful deploy moves
    // deployedAt straight away, and there is nothing left to publish. Without
    // this the loop would sit through its whole timeout after actually winning.
    if (s.live && s.live !== app.deployedAt) {
      // Give the platform a moment to actually start something before judging.
      let c = s.container;
      for (let k = 0; k < 8 && !c; k++) { sleep(15000); c = state().container; }
      if (!c) { outcome = 'ghost'; base = state(); break; }
      outcome = 'live'; base = s; break;
    }
    if (s.draft && s.draft !== base.draft) { outcome = 'built'; base = s; break; }
    if (s.err && s.err !== base.err) { outcome = 'failed'; base = s; break; }
  }

  if (outcome === 'failed' && !base.infra) {
    // No longer "please retry" — the platform is now blaming something we own.
    console.error(`\n  ✗ STOPPING — this failure looks actionable, not infra:\n    ${base.why}`);
    console.error('    Retrying would just hammer a fault that needs a code fix.');
    process.exit(2);
  }

  if (outcome === 'live') {
    console.log(`\n  ✓ DEPLOYED — deployedAt ${base.live}`);
    console.log(`    https://app.claritty.ai/apps/${app.id}`);
    console.log('    NOT yet proof it is serving — open it and look for the Mail');
    console.log('    tab and the worklist on Today before calling it done.');
    process.exit(0);
  }

  if (outcome !== 'built') {
    const note = outcome === 'ghost' ? 'recorded as deployed but NO container started — retrying'
      : outcome === 'failed' ? 'build failed (platform-side, retryable)'
      : down ? `couldn't read state — ${down}` : 'no verdict';
    console.log(`  ${stamp()}  ${note} — waiting ${WAIT_MIN} min`);
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
    if (s.down) continue;
    if (s.live && s.live !== app.deployedAt) {
      console.log(`\n  ✓ PUBLISHED — deployedAt ${app.deployedAt} → ${s.live}`);
      console.log(`    https://app.claritty.ai/apps/${app.id}`);
      console.log('    NOT yet proof it is serving — open the app and look for the');
      console.log('    Mail tab and the worklist on Today before calling it done.');
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
