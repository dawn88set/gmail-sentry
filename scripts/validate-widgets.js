#!/usr/bin/env node
/**
 * Widget validation CLI — `npm run validate:widgets`
 *
 * The widget is built on the Claritty UI kit (@clarittyai/widget-toolkit):
 * <WidgetContainer size={...}> owns the dimensions (small 170×170, medium
 * 360×170, large 360×360), radius, padding and overflow — so we validate the
 * KIT USAGE + the fixed-size constraints, not literal Tailwind size classes
 * (which no longer appear in source).
 */
const fs = require('fs');
const path = require('path');

// Anchor to the repo root (this script lives in <root>/scripts/), so it works
// no matter the cwd the npm script runs from.
const ROOT = path.join(__dirname, '..');
const WIDGET = path.join(ROOT, 'frontend/src/components/Widget.tsx');
const SIZES = path.join(ROOT, 'frontend/src/lib/widget-sizes.ts');

console.log('🔍 Validating widget constraints...\n');

let errors = 0;
let warnings = 0;
const fail = (m) => { console.error('❌ ' + m); errors++; };
const warn = (m) => { console.warn('⚠️  ' + m); warnings++; };
const ok = (m) => console.log('✅ ' + m);

if (!fs.existsSync(WIDGET)) { fail(`Widget.tsx not found at ${WIDGET}`); process.exit(1); }
const w = fs.readFileSync(WIDGET, 'utf-8');

// 1. Uses the Claritty UI kit.
if (/@clarittyai\/widget-toolkit/.test(w) && /<WidgetContainer\b/.test(w)) {
  ok('Uses the UI kit (<WidgetContainer> from @clarittyai/widget-toolkit)');
} else {
  fail('Widget must import @clarittyai/widget-toolkit and wrap the root in <WidgetContainer size={...}>');
}

// 2. Handles all THREE sizes (branches on the size prop; quote-agnostic).
if (/\bsmall\b/.test(w) && /\bmedium\b/.test(w) && /\blarge\b/.test(w)) {
  ok('Branches on all three sizes (small / medium / large)');
} else {
  warn('Widget should render distinct layouts for small, medium AND large');
}

// 3. Fixed-size constraint: no responsive prefixes / viewport reads.
const forbidden = [
  [/\b(sm|md|lg|xl|2xl):/, 'Tailwind responsive prefix (sm:/md:/…)'],
  [/window\.innerWidth|window\.matchMedia|ResizeObserver|@media/, 'viewport/media query (window.innerWidth, matchMedia, ResizeObserver, @media)'],
];
let clean = true;
for (const [re, label] of forbidden) {
  if (re.test(w)) { fail(`Widget must be window-size invariant — found ${label}`); clean = false; }
}
if (clean) ok('Window-size invariant (no responsive prefixes / viewport reads)');

// 4. Canonical sizes are the 3-size Apple HIG set.
if (fs.existsSync(SIZES)) {
  const s = fs.readFileSync(SIZES, 'utf-8');
  const has = (a, b) => new RegExp(`width:\\s*${a}[^}]*height:\\s*${b}`).test(s.replace(/\s+/g, ' '));
  if (has(170, 170) && has(360, 170) && has(360, 360)) {
    ok('widget-sizes.ts defines small 170×170, medium 360×170, large 360×360');
  } else {
    warn('widget-sizes.ts should define small 170×170, medium 360×170, large 360×360');
  }
}

console.log('\n' + '='.repeat(50));
if (errors) { console.error(`\n❌ Widget validation FAILED (${errors} error(s)).`); process.exit(1); }
if (warnings) { console.warn(`\n⚠️  Passed with ${warnings} warning(s).`); process.exit(0); }
console.log('\n✅ All widget constraints validated.');
process.exit(0);
