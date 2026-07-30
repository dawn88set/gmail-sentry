import { test, expect } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Marketplace screenshots — regenerated, never hand-captured.
 *
 * `app-config.json#clarity_marketplace.screenshot_instructions.required_files`
 * declares these paths, and the listing is the first thing a user sees. Hand
 * capturing them means they silently rot the moment the widget changes, so this
 * spec is the source of truth: `npm run screenshots`.
 *
 * Two details that matter:
 *  - We screenshot the ELEMENT (`[data-widget-size]`), not the page, so the file
 *    is exactly the widget's fixed frame at 2x with no chrome and no cropping
 *    guesswork.
 *  - The fixture carries pre-rendered relative strings ("4m ago") rather than
 *    timestamps, so re-running produces byte-identical files instead of a noisy
 *    diff on every commit.
 *
 * This spec is NOT part of `test:all` — it writes files, so it runs on demand.
 */

const BASE = 'http://localhost:3200';
// ESM scope — no __dirname. Resolve relative to this file so the output path
// doesn't depend on where the runner was invoked from.
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, '../../screenshots');

// Read rather than `import ... with { type: 'json' }` — the import-attribute
// syntax varies across Node/TS versions and this has no such sharp edges.
const fixture = JSON.parse(readFileSync(resolve(HERE, 'fixtures/widget-marketing.json'), 'utf8'));

const SIZES = [
  { size: 'small', w: 170, h: 170 },
  { size: 'medium', w: 360, h: 170 },
  { size: 'large', w: 360, h: 360 },
] as const;

test.use({ deviceScaleFactor: 2 });

test.beforeAll(() => {
  mkdirSync(OUT, { recursive: true });
});

for (const { size, w, h } of SIZES) {
  test(`widget-${size} screenshot`, async ({ page }) => {
    await page.route('**/api/widget*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixture),
      }),
    );

    await page.goto(`${BASE}/widget?size=${size}`);
    const widget = page.locator(`[data-widget-size="${size}"]`);
    await expect(widget).toBeVisible();
    // Wait out the skeleton so we never capture a half-loaded pulse.
    await expect(widget).not.toHaveClass(/animate-pulse/);

    const box = await widget.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeCloseTo(w, 0);
    expect(box!.height).toBeCloseTo(h, 0);

    const path = resolve(OUT, `widget-${size}.png`);
    mkdirSync(dirname(path), { recursive: true });
    await widget.screenshot({ path });
  });
}
