/**
 * Canonical Claritty widget sizes — the single source of truth for this app.
 * Mirrors clarity-platform/src/lib/widget-sizes.ts (= clarity-api's copy).
 *
 * Apple HIG, 170px column pitch + 20px gap:
 *   small  170×170  (1×1)  — one quick metric
 *   medium 360×170  (2×1)  — a compact row / short list   (170 + 20 + 170 = 360)
 *   large  360×360  (2×2)  — a rich multi-row view        (170 + 20 + 170 = 360)
 *
 * Do NOT invent other dimensions: only these three exist. Widgets must be
 * window-size invariant (fixed px, never responsive to the viewport).
 */
export type WidgetSize = 'small' | 'medium' | 'large';

export interface WidgetDimensions {
  width: number;
  height: number;
  colSpan: number;
  rowSpan: number;
}

export const WIDGET_DIMENSIONS: Record<WidgetSize, WidgetDimensions> = {
  small: { width: 170, height: 170, colSpan: 1, rowSpan: 1 },
  medium: { width: 360, height: 170, colSpan: 2, rowSpan: 1 },
  large: { width: 360, height: 360, colSpan: 2, rowSpan: 2 },
};

// Static Tailwind literals (must be inlined so the JIT compiler keeps them).
export const WIDGET_SIZE_CLASSES: Record<WidgetSize, string> = {
  small: 'w-[170px] h-[170px]',
  medium: 'w-[360px] h-[170px]',
  large: 'w-[360px] h-[360px]',
};

export const TOUCH_TARGET_MIN = 44; // px (iOS HIG)
export const FONT_SIZE_MIN = 12; // px
