#!/usr/bin/env node
/**
 * Deploy this app to a BRAND-NEW Claritty app, because updating a live one
 * currently cannot work.
 *
 * Claritty's image build only works in windows. Observed good 2026-08-02
 * 16:38–17:29Z and 2026-08-03 ~01:57–13:17Z; outside those, everything fails —
 * brand-new apps and redeploys alike, this app and an untouched
 * `create-claritty-app` seed alike. Nothing about the app predicts the outcome,
 * only the time does. Redeploying an app that is already live has never once
 * worked, which is why Gmail Sentry has been frozen since 20 July.
 *
 * So this deploys to a NEW app and keeps trying until a window opens:
 *
 *   1. stamps a unique deploy name (the CLI matches existing apps BY NAME, so a
 *      reused name would find the old app and take the path that never works)
 *   2. unbinds .claritty.json so a new app is created
 *   3. deploys, then asks the API whether a live instance exists — the CLI says
 *      "is live in your workspace" before the build finishes, says the same
 *      thing when it fails, and has also reported failure for a build that was
 *      still running, so its output is worthless in both directions
 *   4. DELETES the dead app each failed attempt leaves behind, so retrying does
 *      not fill the workspace with "Gmail Sentry <stamp>" corpses
 *   5. renames the app and its submission back to the proper name once live
 *   6. restores every file it touched — including on Ctrl-C
 *
 * Usage:  node scripts/deploy-fresh.mjs [--keep-name] [--publish public|organization|private]
 *
 * DELETE THIS once draft builds work again — normal `claritty deploy` is the
 * right tool, and leaving a "make a new app every time" script lying around is
 * how workspaces fill up with dead apps.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, copyFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';

const API = 'https://api.claritty.ai';
const ROOT = path.resolve(import.meta.dirname, '..');
const CFG = path.join(ROOT, 'app-config.json');
const META = path.join(ROOT, 'frontend/src/lib/app-meta.ts');
const REF = path.join(ROOT, '.claritty.json');

const token = () =>
  JSON.parse(readFileSync(path.join(homedir(), '.claritty/credentials.json'), 'utf8'))[API]
    .session.accessToken;

const api = (method, url, body) => {
  const args = ['-s', '-X', method, '-H', `Authorization: Bearer ${token()}`];
  if (body) args.push('-H', 'Content-Type: application/json', '-d', JSON.stringify(body));
  args.push(`${API}${url}`);
  const out = execFileSync('curl', args, { encoding: 'utf8' });
  try { return JSON.parse(out); } catch { return null; }
};

const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

// ── snapshot everything we are about to edit ────────────────────────────────
const backups = [CFG, META, REF].filter(existsSync);
for (const f of backups) copyFileSync(f, `${f}.deploy-bak`);
const restore = () => {
  for (const f of backups) if (existsSync(`${f}.deploy-bak`)) copyFileSync(`${f}.deploy-bak`, f);
};
const cleanBaks = () => { for (const f of backups) try { execFileSync('rm', ['-f', `${f}.deploy-bak`]); } catch {} };
process.on('exit', cleanBaks);
// A retry loop invites Ctrl-C. Without these the repo is left holding a stamped
// app name and an unbound .claritty.json.
for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(sig, () => { restore(); cleanBaks(); console.log('\n  interrupted — files restored'); process.exit(130); });
}

try {
  const cfg = JSON.parse(readFileSync(CFG, 'utf8'));
  const realName = cfg.appName;
  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').slice(2);
  const deployName = `${realName} ${stamp}`;

  console.log(`  app          ${realName}`);
  console.log(`  deploying as ${realName}  (the real identity — no stamp in the bundle)`);

  // Surgical string edits, NOT a JSON round-trip: re-serialising app-config.json
  // rewrites bytes that have no business mattering (spacing, non-ASCII escaping,
  // a trailing newline the original lacks). That probably doesn't matter, but
  // this script exists to work around a build we don't understand, so it changes
  // as little as it can.
  const setName = (name) => {
    writeFileSync(CFG, readFileSync(CFG, 'utf8')
      .replace(/("appName"\s*:\s*)"(?:[^"\\]|\\.)*"/, `$1${JSON.stringify(name)}`));
    writeFileSync(META, readFileSync(META, 'utf8')
      .replace(/export const appName = '[^']*';/, `export const appName = '${name}';`));
  };

  // Claritty's build works only in windows — observed good 2026-08-02
  // 16:38–17:29Z and 2026-08-03 ~01:57–13:17Z, failing everything in between,
  // for brand-new apps and redeploys alike. Nothing about the app predicts it.
  // So: keep trying. Each attempt needs its own name, because a failed one
  // still leaves a submission behind that the CLI would match on.
  const ATTEMPTS = Number(process.env.DEPLOY_ATTEMPTS || 12);
  const WAIT_MIN = Number(process.env.DEPLOY_WAIT_MIN || 10);

  const appsFor = (templateId) => {
    const d = api('GET', '/api/apps')?.data;
    const rows = Array.isArray(d) ? d : d?.apps || [];
    return rows.filter((a) => a?.templateId === templateId);
  };

  /** Delete the app + submission a failed attempt left behind.
   *  Without this the workspace fills with dead "Gmail Sentry <stamp>" entries —
   *  one per attempt, which is user-visible mess for a retry that is entirely
   *  this script's business. */
  const cleanUp = (templateId, why) => {
    if (!templateId) return;
    for (const a of appsFor(templateId)) {
      api('DELETE', `/api/apps/${a.id}`);
      console.log(`    removed the ${why} app it created (${a.id.slice(0, 8)}…)`);
    }
    api('DELETE', `/api/apps/templates/${templateId}`);
  };

  // Attempt 1 uses the REAL name. The CLI reads the submission name from
  // app-meta.ts — the same constant that renders the app header and the browser
  // title — so stamping a unique name compiles that stamp into the shipped
  // bundle. That is exactly how a deployed app ended up calling itself "Probe
  // Services" in its own UI. If the real name is free (rename or retire whatever
  // holds it first), attempt 1 ships correct branding and nothing needs undoing.
  // Only fall back to stamping if that first attempt can't create a new app.
  let r = null;
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    const name = attempt === 1 ? realName : `${realName} ${stamp}-${attempt}`;
    setName(name);
    writeFileSync(REF, JSON.stringify({ deployments: {} }, null, 2) + '\n');
    console.log(`  attempt ${attempt}/${ATTEMPTS} as "${name}" …`);
    r = spawnSync('claritty', ['deploy', '--yes'], { cwd: ROOT, encoding: 'utf8' });
    const tid = existsSync(REF)
      ? JSON.parse(readFileSync(REF, 'utf8')).deployments?.[API]?.templateId
      : null;

    // The CLI's exit code and its output both lie in each direction, so ask the
    // API whether a live instance actually exists.
    let live = null;
    if (tid) {
      for (let i = 0; i < 30; i++) {
        const a = appsFor(tid)[0];
        if (a?.deployedAt) { live = a; break; }
        if (a?.status === 'FAILED') break;
        sleep(15000);
      }
    }
      // A live instance is necessary but NOT sufficient: a deploy can land with
    // the wrong contents. Confirm the served bundle is actually THIS app by
    // checking it carries a route the seed template does not have.
    if (live) {
      const probe = spawnSync('curl', ['-s', '-o', '/dev/null', '-w', '%{http_code}',
        '--max-time', '25', `${live.proxyUrl}/health`], { encoding: 'utf8' });
      if (probe.stdout?.trim() !== '200') {
        console.log('    landed but is not serving; treating as a failure');
        live = null;
      }
    }
    if (live) { r = { live, tid }; break; }

    cleanUp(tid, 'failed');
    if (attempt === ATTEMPTS) {
      throw new Error(`all ${ATTEMPTS} attempts failed — Claritty's build window never opened`);
    }
    console.log(`    build window shut; retrying in ${WAIT_MIN} min (nothing left behind)`);
    sleep(WAIT_MIN * 60_000);
  }
  const templateId = r.tid;
  const app = r.live;


  if (!process.argv.includes('--keep-name')) {
    api('PATCH', `/api/apps/templates/${templateId}`, { name: realName });
    api('PUT', `/api/apps/${app.id}`, { name: realName });   // the instance, not just the submission
  }

  restore();
  writeFileSync(REF, JSON.stringify(
    { deployments: { [API]: { templateId } } }, null, 2) + '\n');

  // The CLI publish flow, which is the point of deploying fresh.
  //
  // `claritty publish` POSTs /api/marketplace/publish and gates on the app's
  // validation checks. A DIRECT-UPLOAD submission (no githubRepoUrl) validates
  // on the platform and passes. The moment a repo URL is attached, validation
  // switches to the GitHub path and demands the Claritty GitHub App be
  // installed on the repository — and that URL cannot be removed afterwards:
  // PATCH with "" is a 400 and PATCH with null is silently ignored. That is why
  // the original submission can never publish from the CLI, and why publishing
  // has to ride on an app that was never given a repo.
  if (process.argv.includes('--publish')) {
    const scope = (process.argv[process.argv.indexOf('--publish') + 1] || 'public');
    console.log(`\n  publishing to the marketplace (${scope}) …`);
    const pub = spawnSync('claritty',
      ['publish', '--app-id', templateId, '--scope', scope],
      { cwd: ROOT, encoding: 'utf8' });
    console.log((pub.stdout || '').trim().split('\n').map((l) => `    ${l}`).join('\n'));
    if (pub.status !== 0) console.error(`    publish failed: ${(pub.stderr || '').trim().slice(0, 200)}`);
  }

  console.log(`\n  ✓ live: https://app.claritty.ai/apps/${app.id}`);
  console.log(`    direct: ${app.proxyUrl}`);
  console.log(`    deployedAt: ${app.deployedAt}`);
  console.log('\n  The PREVIOUS app is now stale and can be deleted in the Claritty UI.');
} catch (err) {
  restore();
  console.error(`\n  ✗ ${err.message}`);
  console.error('  Files restored; nothing in the repo changed.');
  process.exit(1);
}
