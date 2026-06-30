import { test, expect } from '@playwright/test';

/**
 * Widget visual constraints — enforces the canonical Claritty sizes:
 *   small  170×170 (1:1 square)
 *   medium 360×170 (2.1:1 wide)
 *   large  360×360 (2:2 square)
 * plus the shared invariants: 16px padding (p-4), 24px radius (rounded-3xl),
 * overflow-hidden, no scrollbars, and window-size invariance.
 *
 * Each size is rendered standalone at /widget?size=<size>.
 */

const BASE = 'http://localhost:3200';

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

      test('has 16px padding, 24px radius, overflow hidden, no shadow', async ({ page }) => {
        const widget = await gotoWidget(page, size);
        const css = await widget.evaluate((el) => {
          const s = window.getComputedStyle(el);
          return {
            pad: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(parseFloat),
            radius: parseFloat(s.borderTopLeftRadius),
            overflow: s.overflow,
            shadow: s.boxShadow,
          };
        });
        expect(css.pad).toEqual([16, 16, 16, 16]);   // internal content padding stays
        expect(css.radius).toBe(24);                 // rounded tile stays
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
    // Loading: delay the API and assert the skeleton holds the size box.
    await page.route('**/api/widget*', (route) => setTimeout(() => route.continue(), 4000));
    await page.goto(`${BASE}/widget?size=medium`);
    const loading = page.locator('.animate-pulse').first();
    const lbox = await loading.boundingBox();
    if (lbox) {
      expect(lbox.width).toBeCloseTo(360, 0);
      expect(lbox.height).toBeCloseTo(170, 0);
    }
    await page.unroute('**/api/widget*');

    // Error: abort the API and assert the error box holds the size.
    await page.route('**/api/widget*', (route) => route.abort('failed'));
    await page.goto(`${BASE}/widget?size=large`);
    const err = page.locator('[data-widget-size="large"]');
    const ebox = await err.boundingBox();
    if (ebox) {
      expect(ebox.width).toBeCloseTo(360, 0);
      expect(ebox.height).toBeCloseTo(360, 0);
    }
  });
});
