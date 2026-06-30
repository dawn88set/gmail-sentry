/**
 * ⚠️ VENDORED MIRROR — keep in sync with the engine's source of truth:
 *   clarity-api/src/modules/generation/services/visual-audit.ts
 * The seed is forked standalone (no access to the engine package), so the pure
 * audit logic is duplicated here verbatim until it ships as a published subpath
 * (e.g. `@clarittyai/app-ui/audit`), at which point both consumers import it.
 * Do not edit one copy without the other — the whole point of G5 is that the
 * engine and the dev/CI path hold apps to the SAME rendered bar.
 *
 * Deterministic, objective visual audit of a RENDERED page — the half of G5
 * that needs no LLM and can therefore BLOCK a build. Split in two:
 *
 *   1. `collectAuditSnapshot()` — runs IN THE BROWSER (via Playwright
 *      `page.evaluate`), self-contained (no imports), walks the DOM + computed
 *      styles and returns a serializable `AuditSnapshot` of measurements.
 *   2. `evaluateAudit(snapshot)` — a PURE Node-side function that turns the
 *      snapshot into findings (WCAG contrast, ≥44px targets, horizontal
 *      overflow, accent-color count, off-8pt spacing, missing states).
 *
 * The pure half (contrast math + evaluation) is unit-tested without a browser;
 * the same module is consumed by the engine sidecar and the dev/CI seed spec.
 */

export type RGBA = [r: number, g: number, b: number, a: number];

export interface TextSample {
  /** Foreground color as a CSS color string (rgb/rgba). */
  fg: string;
  /** Effective background (first non-transparent ancestor) as a CSS string. */
  bg: string;
  fontPx: number;
  fontWeight: number;
  /** Trimmed sample of the text (for the finding message). */
  text: string;
}

export interface InteractiveSample {
  tag: string;
  w: number;
  h: number;
  label: string;
}

export interface AuditSnapshot {
  theme: 'light' | 'dark';
  viewport: { w: number; h: number };
  docScrollWidth: number;
  docClientWidth: number;
  textSamples: TextSample[];
  interactives: InteractiveSample[];
  /** Distinct "saturated" colors (non-neutral) used as fg/bg on meaningful area. */
  accentColors: string[];
  /** Distinct font sizes (px) seen on text. */
  fontSizes: number[];
  /** Sampled spacing values (px) from padding/gap. */
  spacingValues: number[];
  /** Best-effort state signals (class/text heuristics from the DOM). */
  hasSkeleton: boolean;
  hasEmptyState: boolean;
  hasErrorAffordance: boolean;
}

export type AuditSeverity = 'hard' | 'soft';

export interface AuditFinding {
  key: string;
  severity: AuditSeverity;
  message: string;
}

export interface AuditOptions {
  /** Min WCAG contrast for normal text (AA = 4.5). */
  minContrast?: number;
  /** Min contrast for large text (AA = 3.0). */
  minContrastLarge?: number;
  /** Apple HIG ideal tap target (44) — referenced in the message, not the floor. */
  minTouchPx?: number;
  /**
   * HARD floor: a control smaller than this in either dimension is genuinely
   * too small to tap reliably. Kept BELOW the kit's own default control height
   * (h-10 = 40px) so a correctly kit-built app passes; this catches the real
   * "20px icon button" / collapsed-hit-area bugs, not 40-vs-44 nitpicks.
   */
  hardTouchPx?: number;
  /** Max distinct saturated accent colors (restraint). */
  maxAccents?: number;
}

const DEFAULTS: Required<AuditOptions> = {
  minContrast: 4.5,
  minContrastLarge: 3.0,
  minTouchPx: 44,
  hardTouchPx: 32,
  maxAccents: 2, // one accent + occasional status; >2 = rainbow tell
};

// ---------------------------------------------------------------------------
// Pure color math (WCAG 2.x) — unit-tested.
// ---------------------------------------------------------------------------

/** Parse "rgb(r,g,b)" / "rgba(r,g,b,a)" / "#rrggbb" / "#rgb" → RGBA (a in 0..1). */
export function parseColor(input: string): RGBA | null {
  const s = (input || '').trim().toLowerCase();
  if (!s || s === 'transparent') return [0, 0, 0, 0];
  const m = s.match(/^rgba?\(([^)]+)\)$/);
  if (m) {
    const parts = m[1].split(',').map((x) => x.trim());
    const r = parseFloat(parts[0]);
    const g = parseFloat(parts[1]);
    const b = parseFloat(parts[2]);
    const a = parts[3] !== undefined ? parseFloat(parts[3]) : 1;
    if ([r, g, b].some((n) => Number.isNaN(n))) return null;
    return [r, g, b, Number.isNaN(a) ? 1 : a];
  }
  const hex = s.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/);
  if (hex) {
    let h = hex[1];
    if (h.length === 3)
      h = h
        .split('')
        .map((c) => c + c)
        .join('');
    return [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
      1,
    ];
  }
  return null;
}

/** Composite a (possibly translucent) foreground over an opaque background. */
export function compositeOver(fg: RGBA, bg: RGBA): RGBA {
  const a = fg[3];
  return [
    Math.round(fg[0] * a + bg[0] * (1 - a)),
    Math.round(fg[1] * a + bg[1] * (1 - a)),
    Math.round(fg[2] * a + bg[2] * (1 - a)),
    1,
  ];
}

function channelLuminance(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function relativeLuminance(rgb: RGBA): number {
  return (
    0.2126 * channelLuminance(rgb[0]) +
    0.7152 * channelLuminance(rgb[1]) +
    0.0722 * channelLuminance(rgb[2])
  );
}

/** WCAG contrast ratio between an (alpha-composited) fg and an opaque bg. */
export function contrastRatio(fg: RGBA, bg: RGBA): number {
  const fgOpaque = fg[3] < 1 ? compositeOver(fg, bg) : fg;
  const l1 = relativeLuminance(fgOpaque);
  const l2 = relativeLuminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

/** Large text per WCAG: ≥24px, or ≥18.66px when bold (weight ≥ 700). */
export function isLargeText(fontPx: number, weight: number): boolean {
  return fontPx >= 24 || (fontPx >= 18.66 && weight >= 700);
}

/**
 * A "saturated" (brand-accent) color vs a neutral (gray/black/white). Used to
 * grade contrast failures: a neutral that fails is the critical "invisible gray
 * text" bug (HARD); a saturated accent that merely dips below 4.5:1 (but still
 * clears the 3:1 UI floor) is the theming reality that one accent can't be AA as
 * text in BOTH light and dark — graded SOFT so it doesn't dead-end the build.
 */
export function isSaturatedColor(rgb: RGBA): boolean {
  return (
    Math.max(rgb[0], rgb[1], rgb[2]) - Math.min(rgb[0], rgb[1], rgb[2]) > 16
  );
}

// ---------------------------------------------------------------------------
// Pure evaluation — snapshot → findings.
// ---------------------------------------------------------------------------

export function evaluateAudit(
  snapshot: AuditSnapshot,
  options: AuditOptions = {},
): AuditFinding[] {
  const opts = { ...DEFAULTS, ...options };
  const findings: AuditFinding[] = [];

  // 1. Contrast — the "no invisible text" guarantee. Neutral/muted text that
  //    fails AA is HARD (the real bug). A saturated ACCENT that dips below AA
  //    but still clears the 3:1 UI floor is SOFT (one accent can't be AA as
  //    text in both light AND dark without a per-theme ramp); an accent below
  //    3:1 is genuinely invisible → HARD.
  let hardN = 0;
  let softN = 0;
  let worstHard: { ratio: number; text: string } | null = null;
  let worstSoft: { ratio: number; text: string } | null = null;
  for (const t of snapshot.textSamples) {
    const fg = parseColor(t.fg);
    const bg = parseColor(t.bg);
    if (!fg || !bg || bg[3] === 0) continue; // can't resolve a bg → skip
    const ratio = contrastRatio(fg, bg);
    const min = isLargeText(t.fontPx, t.fontWeight)
      ? opts.minContrastLarge
      : opts.minContrast;
    if (ratio >= min) continue;
    const accentDip = isSaturatedColor(fg) && ratio >= opts.minContrastLarge;
    if (accentDip) {
      softN++;
      if (!worstSoft || ratio < worstSoft.ratio)
        worstSoft = { ratio, text: t.text };
    } else {
      hardN++;
      if (!worstHard || ratio < worstHard.ratio)
        worstHard = { ratio, text: t.text };
    }
  }
  if (hardN > 0 && worstHard) {
    findings.push({
      key: 'contrast',
      severity: 'hard',
      message: `${hardN} text element(s) fail WCAG AA contrast (worst ${worstHard.ratio.toFixed(2)}:1 on "${worstHard.text.slice(0, 40)}"). Use a higher-contrast token (text-foreground on a card/background) so every label is legible in this theme.`,
    });
  }
  if (softN > 0 && worstSoft) {
    findings.push({
      key: 'contrast-accent',
      severity: 'soft',
      message: `${softN} accent-colored text element(s) dip below WCAG AA in this theme (worst ${worstSoft.ratio.toFixed(2)}:1 on "${worstSoft.text.slice(0, 40)}"). A single brand accent rarely clears 4.5:1 as text in BOTH light and dark — reserve the accent for fills/large headings, or give dark mode a lighter accent.`,
    });
  }

  // 2. Touch targets (HARD). Inline text links (<a>) are not touch CONTROLS —
  // they're keyboard/pointer affordances and routinely sit below 44px in nav
  // and prose; excluding them avoids flagging every header/wordmark link. The
  // floor catches genuinely-untappable controls, not 40-vs-44 nitpicks.
  const small = snapshot.interactives.filter(
    (i) =>
      i.tag !== 'a' &&
      i.w > 0 &&
      i.h > 0 &&
      (i.w < opts.hardTouchPx || i.h < opts.hardTouchPx),
  );
  if (small.length > 0) {
    const ex = small[0];
    findings.push({
      key: 'touch-target',
      severity: 'hard',
      message: `${small.length} control(s) are too small to reliably tap (e.g. ${ex.tag} "${ex.label.slice(0, 24)}" at ${Math.round(ex.w)}×${Math.round(ex.h)}, under ${opts.hardTouchPx}px). Apple HIG wants ≥${opts.minTouchPx}px — use the kit Button (h-10/h-11) or enlarge the hit area.`,
    });
  }

  // 3. Horizontal overflow (HARD) — mobile breakage.
  if (snapshot.docScrollWidth > snapshot.docClientWidth + 2) {
    findings.push({
      key: 'overflow',
      severity: 'hard',
      message: `The page scrolls horizontally (content ${snapshot.docScrollWidth}px > viewport ${snapshot.docClientWidth}px at ${snapshot.viewport.w}px wide). Constrain width and wrap/stack rows so there's no horizontal scroll on mobile.`,
    });
  }

  // 4. Accent restraint (SOFT) — rainbow tell.
  if (snapshot.accentColors.length > opts.maxAccents) {
    findings.push({
      key: 'accent-count',
      severity: 'soft',
      message: `${snapshot.accentColors.length} distinct saturated colors are in use — reserve ONE accent for the primary action + key status and keep the rest neutral.`,
    });
  }

  // 5. Font-scale chaos (SOFT).
  if (snapshot.fontSizes.length > 7) {
    findings.push({
      key: 'type-scale',
      severity: 'soft',
      message: `${snapshot.fontSizes.length} distinct font sizes — collapse to a clear scale (title / section / body / meta). Let weight + tracking carry hierarchy.`,
    });
  }

  // 6. Off-8pt spacing (SOFT).
  const offGrid = snapshot.spacingValues.filter(
    (v) => v > 0 && v % 4 !== 0,
  ).length;
  if (
    snapshot.spacingValues.length >= 8 &&
    offGrid / snapshot.spacingValues.length > 0.4
  ) {
    findings.push({
      key: 'spacing-grid',
      severity: 'soft',
      message: `Most spacing is off the 8pt grid (${offGrid}/${snapshot.spacingValues.length} values not multiples of 4px). Use the 4/8/12/16/24/32 rhythm.`,
    });
  }

  return findings;
}

/** Convenience: does this snapshot pass the HARD (blocking) checks? */
export function passesHardAudit(
  snapshot: AuditSnapshot,
  options?: AuditOptions,
): boolean {
  return !evaluateAudit(snapshot, options).some((f) => f.severity === 'hard');
}

// ---------------------------------------------------------------------------
// G6 — rubric scorecard. Turns the deterministic findings + snapshot into a
// per-criterion score against the versioned DESIGN_RUBRIC, so every kit / prompt
// / template change is MEASURED (not just pass/fail). The audit covers the
// objective criteria; `hierarchy` and `coherence` are subjective → left to the
// vision critic (scored elsewhere), reported here as automated:false / null.
//
// RUBRIC_VERSION is duplicated from design-rubric.ts so this stays vendorable
// into the seed; an engine calibration test asserts the two never drift.
// ---------------------------------------------------------------------------

export const RUBRIC_VERSION = '1.0.0';

/** Which rubric criterion each deterministic finding key counts against. */
export const RUBRIC_FINDING_MAP: Record<string, string> = {
  contrast: 'contrast',
  'contrast-accent': 'contrast',
  'touch-target': 'mobile',
  overflow: 'mobile',
  'accent-count': 'restraint',
  'type-scale': 'typography',
  'spacing-grid': 'spacing',
};

/** Rubric criteria the deterministic audit can score from a render. */
export const AUTOMATED_RUBRIC_KEYS = [
  'contrast',
  'restraint',
  'typography',
  'spacing',
  'states',
  'mobile',
] as const;

export interface RubricCriterionScore {
  key: string;
  /** 0 fail / 1 partial / 2 pass; null when not scored automatically. */
  score: number | null;
  automated: boolean;
  findings: string[];
}

export interface RubricScore {
  version: string;
  criteria: RubricCriterionScore[];
  /** Sum of the automated criterion scores. */
  automatedScore: number;
  /** Max possible automated score (2 × automated criteria). */
  automatedMax: number;
  /** True iff no automated criterion scored 0 (a hard failure on that axis). */
  pass: boolean;
}

const ALL_RUBRIC_KEYS = [
  'hierarchy',
  'spacing',
  'restraint',
  'typography',
  'states',
  'contrast',
  'coherence',
  'mobile',
] as const;

/**
 * Score a rendered snapshot + its findings against the rubric. A criterion
 * scores 0 if a HARD finding maps to it, 1 if only SOFT findings do, else 2;
 * `states` is read from the snapshot's affordance signals. Subjective criteria
 * (hierarchy/coherence) return null with automated:false.
 */
export function scoreAgainstRubric(
  snapshot: AuditSnapshot,
  findings: AuditFinding[],
): RubricScore {
  const automated = new Set<string>(AUTOMATED_RUBRIC_KEYS);
  const criteria: RubricCriterionScore[] = ALL_RUBRIC_KEYS.map((key) => {
    if (!automated.has(key)) {
      return { key, score: null, automated: false, findings: [] };
    }
    if (key === 'states') {
      const has =
        snapshot.hasSkeleton ||
        snapshot.hasEmptyState ||
        snapshot.hasErrorAffordance;
      return {
        key,
        score: has ? 2 : 1,
        automated: true,
        findings: has ? [] : ['No loading/empty/error affordance detected.'],
      };
    }
    const mapped = findings.filter((f) => RUBRIC_FINDING_MAP[f.key] === key);
    const score = mapped.some((f) => f.severity === 'hard')
      ? 0
      : mapped.length
        ? 1
        : 2;
    return { key, score, automated: true, findings: mapped.map((f) => f.message) };
  });
  const scored = criteria.filter((c) => c.automated);
  return {
    version: RUBRIC_VERSION,
    criteria,
    automatedScore: scored.reduce((n, c) => n + (c.score ?? 0), 0),
    automatedMax: scored.length * 2,
    pass: !scored.some((c) => c.score === 0),
  };
}

// ---------------------------------------------------------------------------
// Browser-side collector — serialized into Playwright `page.evaluate`.
// Self-contained: NO imports, NO closures over module scope.
// ---------------------------------------------------------------------------

// Browser globals — `collectAuditSnapshot` runs in the page via Playwright
// `page.evaluate`, never in Node, so the backend tsconfig (no DOM lib) types
// them as `any`. This keeps the audit module buildable in clarity-api.
declare const document: any;
declare const window: any;
declare const getComputedStyle: (el: any) => any;

/**
 * Returns an `AuditSnapshot` from the live document. Designed to be passed to
 * `page.evaluate(collectAuditSnapshot)`. Keep it dependency-free and defensive.
 */
export function collectAuditSnapshot(): AuditSnapshot {
  const NEUTRAL_MAX_CHROMA = 16; // rgb spread below this = treated as neutral

  // Resolve the OPAQUE background a text element actually sits on, compositing
  // any stacked translucent layers (e.g. a `bg-accent/10` tile) down over their
  // ancestors to the body/white base — so a readable tint isn't mis-scored as
  // 1:1 just because its nearest background happens to be semi-transparent.
  const parseRgba = (c: string): number[] | null => {
    const m = c && c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x: string) => parseFloat(x.trim()));
    return [p[0], p[1], p[2], p[3] === undefined ? 1 : p[3]];
  };
  const effectiveBg = (el: any): string => {
    const layers: number[][] = []; // top-most first
    let node: any = el;
    while (node) {
      const p = parseRgba(getComputedStyle(node).backgroundColor);
      if (p && p[3] > 0) {
        layers.push(p);
        if (p[3] >= 1) break; // opaque — nothing behind it matters
      }
      node = node.parentElement;
    }
    const bodyP = parseRgba(getComputedStyle(document.body).backgroundColor);
    let result =
      bodyP && bodyP[3] > 0 ? [bodyP[0], bodyP[1], bodyP[2]] : [255, 255, 255];
    for (let i = layers.length - 1; i >= 0; i--) {
      const f = layers[i];
      const a = f[3];
      result = [
        Math.round(f[0] * a + result[0] * (1 - a)),
        Math.round(f[1] * a + result[1] * (1 - a)),
        Math.round(f[2] * a + result[2] * (1 - a)),
      ];
    }
    return `rgb(${result[0]}, ${result[1]}, ${result[2]})`;
  };

  const isSaturated = (color: string): boolean => {
    const m = color.match(/rgba?\(([^)]+)\)/);
    if (!m) return false;
    const p = m[1].split(',').map((x) => parseFloat(x.trim()));
    const a = p[3] === undefined ? 1 : p[3];
    if (a < 0.4) return false;
    const max = Math.max(p[0], p[1], p[2]);
    const min = Math.min(p[0], p[1], p[2]);
    return max - min > NEUTRAL_MAX_CHROMA;
  };

  const textSamples: AuditSnapshot['textSamples'] = [];
  const fontSizes = new Set<number>();
  const accents = new Set<string>();
  const spacing: number[] = [];

  const all: any[] = Array.from(document.querySelectorAll('body *')).slice(
    0,
    1500,
  );
  for (const el of all) {
    const cs = getComputedStyle(el);
    // Direct text content (not from children).
    const direct = Array.from(el.childNodes)
      .filter((n: any) => n.nodeType === 3)
      .map((n: any) => (n.textContent || '').trim())
      .join(' ')
      .trim();
    const fontPx = parseFloat(cs.fontSize) || 0;
    if (direct && fontPx > 0) {
      fontSizes.add(Math.round(fontPx));
      if (textSamples.length < 400) {
        textSamples.push({
          fg: cs.color,
          bg: effectiveBg(el),
          fontPx,
          fontWeight: parseInt(cs.fontWeight, 10) || 400,
          text: direct.slice(0, 60),
        });
      }
      if (isSaturated(cs.color)) accents.add(cs.color);
    }
    if (isSaturated(cs.backgroundColor)) accents.add(cs.backgroundColor);
    for (const v of [cs.paddingTop, cs.paddingLeft, cs.gap, cs.marginTop]) {
      const n = parseFloat(v);
      if (!Number.isNaN(n) && n > 0 && spacing.length < 200) spacing.push(n);
    }
  }

  const interactives: AuditSnapshot['interactives'] = Array.from(
    document.querySelectorAll(
      'button, a[href], input, select, textarea, [role="button"]',
    ),
  )
    .slice(0, 300)
    .map((el: any) => {
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName.toLowerCase(),
        w: r.width,
        h: r.height,
        label: (el.textContent || el.getAttribute?.('aria-label') || '')
          .trim()
          .slice(0, 40),
      };
    })
    .filter((i) => i.w > 0 && i.h > 0);

  const bodyText = document.body.innerText || '';
  const html = document.body.innerHTML || '';

  return {
    theme: document.documentElement.classList.contains('dark')
      ? 'dark'
      : 'light',
    viewport: { w: window.innerWidth, h: window.innerHeight },
    docScrollWidth: document.documentElement.scrollWidth,
    docClientWidth: document.documentElement.clientWidth,
    textSamples,
    interactives,
    accentColors: Array.from(accents),
    fontSizes: Array.from(fontSizes),
    spacingValues: spacing,
    hasSkeleton: /animate-pulse|skeleton/i.test(html),
    hasEmptyState: /no |nothing|empty|get started|add your first/i.test(
      bodyText,
    ),
    hasErrorAffordance: /retry|try again|couldn'?t|failed|error/i.test(
      bodyText,
    ),
  };
}
