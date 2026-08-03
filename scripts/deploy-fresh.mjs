#!/usr/bin/env node
/**
 * Deploy this app to a BRAND-NEW Claritty app, because updating a live one
 * currently cannot work.
 *
 * The platform builds two runtimes. A first upload (the app has no `deployedAt`
 * yet) builds the LIVE one and succeeds. Every later deploy of that same app
 * builds the DRAFT one, and the draft build is broken — so the moment an app
 * goes live it is frozen. Proven on 2026-08-03: an app deployed successfully at
 * 13:17Z, and the very next deploy of identical code to the same app failed
 * 29 minutes later. Gmail Sentry has been stuck this way since 20 July.
 *
 * Until Claritty fixes the draft build, the only way to ship is to create a new
 * app each time. This does that safely:
 *
 *   1. stamps a unique deploy name (the CLI matches existing apps BY NAME, so a
 *      reused name would find the old app and take the broken draft path)
 *   2. unbinds .claritty.json so a new app is created
 *   3. deploys, then WAITS for the app to actually go live — the CLI prints
 *      "is live in your workspace" before the build finishes and says the same
 *      thing when it fails, so its output cannot be trusted
 *   4. renames the app back to its proper name once it is live
 *   5. restores every file it touched, and records the new app id
 *
 * Usage:  node scripts/deploy-fresh.mjs [--keep-name]
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
process.on('exit', () => { for (const f of backups) try { execFileSync('rm', ['-f', `${f}.deploy-bak`]); } catch {} });

try {
  const cfg = JSON.parse(readFileSync(CFG, 'utf8'));
  const realName = cfg.appName;
  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').slice(2);
  const deployName = `${realName} ${stamp}`;

  console.log(`  app          ${realName}`);
  console.log(`  deploying as ${deployName}  (unique, so a NEW app is created)`);

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
  let r = null;
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    const name = attempt === 1 ? deployName : `${realName} ${stamp}-${attempt}`;
    setName(name);
    writeFileSync(REF, JSON.stringify({ deployments: {} }, null, 2) + '\n');
    console.log(`  attempt ${attempt}/${ATTEMPTS} as "${name}" …`);
    r = spawnSync('claritty', ['deploy', '--yes'], { cwd: ROOT, encoding: 'utf8' });
    const ref = existsSync(REF) ? JSON.parse(readFileSync(REF, 'utf8')) : {};
    if (r.status === 0 && ref.deployments?.[API]?.templateId) break;
    if (attempt === ATTEMPTS) throw new Error(`all ${ATTEMPTS} attempts failed — the platform build window is closed`);
    console.log(`    build failed; the platform's build window is shut. Retrying in ${WAIT_MIN} min.`);
    sleep(WAIT_MIN * 60_000);
  }

  const templateId = JSON.parse(readFileSync(REF, 'utf8'))
    .deployments?.[API]?.templateId;
  if (!templateId) throw new Error('no templateId was written — deploy did not create an app');

  // The CLI's success line is unreliable; wait for a real live instance.
  console.log('  waiting for the app to actually go live …');
  let app = null;
  for (let i = 0; i < 40; i++) {
    sleep(15000);
    const apps = api('GET', '/api/apps')?.data;
    const rows = Array.isArray(apps) ? apps : apps?.apps || [];
    app = rows.find((a) => a?.templateId === templateId);
    if (app?.deployedAt) break;
    if (app?.status === 'FAILED') throw new Error(`build failed: ${app.lastError || 'no detail'}`);
    process.stdout.write('.');
  }
  process.stdout.write('\n');
  if (!app?.deployedAt) throw new Error('timed out waiting for the app to go live');

  if (!process.argv.includes('--keep-name')) {
    api('PATCH', `/api/apps/templates/${templateId}`, { name: realName });
  }

  restore();
  writeFileSync(REF, JSON.stringify(
    { deployments: { [API]: { templateId } } }, null, 2) + '\n');

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
