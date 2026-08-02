import { test, expect } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import {
  collectAuditSnapshot,
  evaluateAudit,
  scoreAgainstRubric,
  type RubricCriterionScore,
} from './visual-audit';

/**
 * G6 — design golden-set eval. Renders the app's pages across themes + widths,
 * scores each against the versioned DESIGN_RUBRIC (via the deterministic audit),
 * and reduces to the WORST score per criterion (a regression anywhere shows up).
 * Writes a versioned scorecard to test-results/design-score.json and fails if
 * any automated criterion scores 0 (a hard failure on that axis).
 *
 * This is the calibration harness: every kit / token / template / prompt change
 * is MEASURED here, not just eyeballed. The "golden-set" is the PAGES corpus —
 * grow it as the app gains routes so coverage tracks the product.
 */

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:3200';
// Golden corpus. Runs without a backend, so these are graded on their
// empty/error states — the first thing a new user actually sees.
const PAGES = ['/', '/followups', '/people', '/attention', '/activity'];
const THEMES = ['light', 'dark'] as const;
const VIEWPORTS = [
  { name: 'desktop', w: 1280, h: 900 },
  { name: 'mobile', w: 390, h: 844 },
] as const;

test('design golden-set — rubric scorecard', async ({ page }) => {
  // Worst (lowest) score seen per criterion across the whole corpus.
  const worst = new Map<string, RubricCriterionScore>();
  let version = '';
  const samples: Array<{ page: string; theme: string; viewport: string; score: number; max: number }> = [];

  for (const route of PAGES) {
    for (const theme of THEMES) {
      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.w, height: vp.h });
        await page.goto(`${BASE}${route}?theme=${theme}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(600);

        const snapshot = await page.evaluate(collectAuditSnapshot);
        const findings = evaluateAudit(snapshot);
        const score = scoreAgainstRubric(snapshot, findings);
        version = score.version;
        samples.push({
          page: route,
          theme,
          viewport: vp.name,
          score: score.automatedScore,
          max: score.automatedMax,
        });
        for (const c of score.criteria) {
          const prev = worst.get(c.key);
          // Keep the lowest non-null score (null = subjective, not scored here).
          if (
            !prev ||
            (c.score !== null && (prev.score === null || c.score < prev.score))
          ) {
            worst.set(c.key, c);
          }
        }
      }
    }
  }

  const criteria = [...worst.values()];
  const automated = criteria.filter((c) => c.automated);
  const report = {
    rubricVersion: version,
    generatedFromPages: PAGES,
    automatedScore: automated.reduce((n, c) => n + (c.score ?? 0), 0),
    automatedMax: automated.length * 2,
    criteria: criteria.map((c) => ({
      key: c.key,
      score: c.score,
      automated: c.automated,
      findings: c.findings,
    })),
    samples,
  };

  const dir = join(process.cwd(), 'test-results');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'design-score.json'), JSON.stringify(report, null, 2));

  // Human-readable scorecard in the test log.
  console.log(`\n── Design rubric v${version} (worst-case across corpus) ──`);
  for (const c of criteria) {
    const label = c.automated ? `${c.score}/2` : 'vision';
    console.log(`  ${label.padStart(6)}  ${c.key}`);
  }
  console.log(`  Automated: ${report.automatedScore}/${report.automatedMax}\n`);

  // The gate: no automated criterion may score 0 (a hard failure on that axis).
  const zeros = automated.filter((c) => c.score === 0);
  expect(
    zeros,
    `Rubric criteria failing (score 0):\n${zeros
      .map((c) => `  • ${c.key}: ${c.findings.join('; ')}`)
      .join('\n')}\n`,
  ).toEqual([]);
});
