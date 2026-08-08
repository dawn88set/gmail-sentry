import { test, expect } from '@playwright/test';

/**
 * Widget visual constraints — enforces the canonical Claritty sizes:
 *   small  170×170 (1:1 square)
 *   medium 360×170 (2.1:1 wide)
 *   large  360×360 (2:2 square)
 * plus the shared invariants: 16px padding (p-4), the `rounded-3xl` radius,
 * overflow-hidden, no scrollbars, and window-size invariance.
 *
 * Each size is rendered standalone at /widget?size=<size>.
 */

/**
 * Honour AUDIT_BASE_URL, exactly like the design audit does.
 *
 * This was pinned to :3200. That port is also what `docker compose` publishes,
 * so whichever container happened to hold it got graded — and when the mapping
 * moved to :3217, every one of these tests failed against a 404 from an
 * unrelated container while the widget itself was perfectly fine. A suite that
 * silently grades whatever answers a fixed port is worse than one that fails
 * loudly: it can pass while testing something that is not this app.
 */
const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:3200';

const SIZES = [
  { size: 'small', w: 170, h: 170 },
  { size: 'medium', w: 360, h: 170 },
  { size: 'large', w: 360, h: 360 },
] as const;

async function gotoWidget(page: import('@playwright/test').Page, size: string) {
  await page.goto(`${BASE}/widget?size=${size}`);
  await page.waitForLoadState('networkidle');
  return page.locator(`[data-widget-size="${size}"]`);
}

test.describe('Widget visual constraints', () => {
  for (const { size, w, h } of SIZES) {
    test.describe(`${size} (${w}×${h})`, () => {
      test('has exact dimensions', async ({ page }) => {
        const widget = await gotoWidget(page, size);
        await expect(widget).toBeVisible();
        const box = await widget.boundingBox();
        expect(box).not.toBeNull();
        if (box) {
          expect(box.width).toBeCloseTo(w, 0);
          expect(box.height).toBeCloseTo(h, 0);
        }
      });

      test('has 16px padding, rounded-3xl radius, overflow hidden, no shadow', async ({ page }) => {
        const widget = await gotoWidget(page, size);
        const css = await widget.evaluate((el) => {
          const s = window.getComputedStyle(el);
          // Resolve what `rounded-3xl` actually means in THIS app's Tailwind
          // config rather than hardcoding stock Tailwind's 24px. The contract is
          // "the widget uses rounded-3xl"; the pixel value is a theme decision
          // (IDENTITY.md explicitly invites reskinning the radius ramp), and
          // this app sets 3xl to 2rem. Probing keeps the test enforcing the
          // contract without freezing a number the theme owns.
          const probe = document.createElement('div');
          probe.className = 'rounded-3xl';
          probe.style.position = 'absolute';
          probe.style.visibility = 'hidden';
          document.body.appendChild(probe);
          const expected = parseFloat(window.getComputedStyle(probe).borderTopLeftRadius);
          probe.remove();
          return {
            pad: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(parseFloat),
            radius: parseFloat(s.borderTopLeftRadius),
            expectedRadius: expected,
            overflow: s.overflow,
            shadow: s.boxShadow,
          };
        });
        expect(css.pad).toEqual([16, 16, 16, 16]);   // internal content padding stays
        expect(css.expectedRadius).toBeGreaterThan(0); // probe resolved a real value
        expect(css.radius).toBe(css.expectedRadius);   // rounded tile stays (rounded-3xl)
        expect(css.overflow).toBe('hidden');
        // The iframe is sized exactly to the widget, so a drop-shadow would be
        // clipped — the widget must cast none.
        expect(css.shadow).toBe('none');
      });

      test('host adds no background/margin around the widget (flush in iframe)', async ({ page }) => {
        await gotoWidget(page, size);
        const body = await page.evaluate(() => {
          const s = window.getComputedStyle(document.body);
          return { margin: s.margin, bg: s.backgroundColor };
        });
        expect(body.margin).toBe('0px');
        // transparent (rgba alpha 0) — the parent/iframe shows through, no blush halo
        expect(body.bg === 'rgba(0, 0, 0, 0)' || body.bg === 'transparent').toBe(true);
      });

      test('does not scroll (content fits)', async ({ page }) => {
        const widget = await gotoWidget(page, size);
        const overflows = await widget.evaluate(
          (el) => el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth,
        );
        expect(overflows).toBe(false);
      });

      test('keeps dimensions across viewports (window-size invariant)', async ({ page }) => {
        for (const vp of [
          { width: 1920, height: 1080 },
          { width: 768, height: 1024 },
          { width: 390, height: 844 },
        ]) {
          await page.setViewportSize(vp);
          const widget = await gotoWidget(page, size);
          const box = await widget.boundingBox();
          if (box) {
            expect(box.width).toBeCloseTo(w, 0);
            expect(box.height).toBeCloseTo(h, 0);
          }
        }
      });
    });
  }

  test('loading + error states keep dimensions', async ({ page }) => {
    // Loading. Two things this test used to get wrong:
    //  1. It waited for `load` before looking. WebKit counts the still-pending
    //     /api/widget request toward that, so the skeleton had already been
    //     replaced by the time the assertion ran — hence a webkit-only failure.
    //     `waitUntil: 'commit'` returns as soon as navigation commits.
    //  2. It located `.animate-pulse` and then guarded on `if (lbox)`, so a
    //     missing skeleton silently passed instead of failing. The skeleton is
    //     itself a WidgetContainer, so it carries data-widget-size — assert on
    //     that stable locator and check the pulse class on it.
    await page.route('**/api/widget*', (route) => setTimeout(() => route.abort('failed'), 8000));
    await page.goto(`${BASE}/widget?size=medium`, { waitUntil: 'commit' });
    const loading = page.locator('[data-widget-size="medium"]');
    await expect(loading).toHaveClass(/animate-pulse/);
    const lbox = await loading.boundingBox();
    expect(lbox).not.toBeNull();
    expect(lbox!.width).toBeCloseTo(360, 0);
    expect(lbox!.height).toBeCloseTo(170, 0);
    await page.unroute('**/api/widget*');

    // Error: abort the API and assert the settled error box holds the size.
    await page.route('**/api/widget*', (route) => route.abort('failed'));
    await page.goto(`${BASE}/widget?size=large`);
    const err = page.locator('[data-widget-size="large"]');
    await expect(err).toBeVisible();
    await expect(err).not.toHaveClass(/animate-pulse/);
    const ebox = await err.boundingBox();
    expect(ebox).not.toBeNull();
    expect(ebox!.width).toBeCloseTo(360, 0);
    expect(ebox!.height).toBeCloseTo(360, 0);
  });
});
