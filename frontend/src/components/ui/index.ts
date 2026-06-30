/**
 * App UI primitives for full-app PAGES. This now re-exports the published,
 * canonical kit `@clarittyai/app-ui` so there is ONE source of truth — the older
 * local impls in this folder are deprecated. NEW code should import from
 * `@clarittyai/app-ui` directly (that's what the generation rules mandate); this
 * alias only keeps any older `@/components/ui` imports working. For dashboard
 * WIDGETS use `@clarittyai/widget-toolkit` instead.
 */
export * from '@clarittyai/app-ui';
