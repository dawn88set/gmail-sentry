# Marketplace screenshots

**Generated — do not hand-edit.**

```bash
cd frontend && npm run screenshots
```

That runs `frontend/tests/screenshots.spec.ts`, which route-intercepts
`/api/widget` with `frontend/tests/fixtures/widget-marketing.json` and takes an
**element** screenshot of `[data-widget-size]` at `deviceScaleFactor: 2`. The
files come out at exactly the widget's fixed frame — 170×170, 360×170 and
360×360 at 2x — with no page chrome and no cropping.

These paths are declared in
`app-config.json#clarity_marketplace.screenshot_instructions.required_files`, and
they're the first thing a user sees on the listing. **Re-run the command after
any widget change** so they can't drift from the real thing.

The fixture deliberately carries pre-rendered relative strings (`"4m ago"`)
rather than timestamps, so regenerating produces byte-identical files instead of
a noisy diff on every commit.
