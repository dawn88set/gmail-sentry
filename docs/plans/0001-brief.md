# Gmail Sentry — Brief

## Problem & users
Busy Gmail users drown in a noisy inbox. The few emails that actually need attention
(from a boss, a deadline, an explicit ask) get buried under Promotions, Social, and Spam.
**Gmail Sentry** watches incoming mail, pings the user on Slack only when something matters
(with a deep link straight to the email), and makes clearing the junk a one-tap action.

Target user: anyone who lives in Gmail + Slack and wants to stop checking their inbox
reflexively but never miss the important stuff.

## What it does (the value path)
1. **Triage** — every 5 minutes, scan new inbox mail and classify each message into
   `urgent` / `needs_reply` / `fyi`, fusing four signals the user controls:
   - natural-language rules ("anything from my manager", "invoices due this week"),
   - VIP senders (addresses/domains),
   - keywords,
   - deadline/action detection (an explicit ask, a due date, a meeting/payment request).
2. **Notify** — for each new urgent/needs-reply email, send a **Slack message** to the
   user's configured channel with sender, subject, the one-line reason, and a **deep link**
   to the email in Gmail.
3. **File** — apply user-defined **label rules** ("from sender X → label Y, optionally archive").
4. **Clean** — surface Promotions / Social / Spam counts; the user clears each category in
   bulk with one tap (archive or trash). Never auto-deletes.

## Backend
- **Agent** `triage-agent` — classifies one email against the user's rules (LLM via the
  Claritty proxy, with a deterministic heuristic fallback so it works offline).
- **Tool** `app.run_inbox_scan` — runs the full scan engine for the caller.
- **Workflow** `scan-inbox` — single step that invokes the agent/tool to do a full scan.
- **Trigger** `sentry-scan` — SCHEDULE (interval), default every 5 minutes.
- **Models** (all `user_id`-scoped): `TriageRule`, `LabelRule`, `Alert`, `ScanRun`,
  `SentryConfig`.

## Integrations (catalog-first; platform OAuth, no keys, no mocks)
- **gmail** — `list_messages` / `search` / `get_message` / labels / trash (via the bundled
  Gmail client adapter).
- **slack** — `post_message` to the user's configured channel.
- Not connected → honest **409 / connect prompt**, never a faked success.

## Widget (the glance)
Data: `{ urgentCount, lastScanAt, allClear, topAlert{subject,sender,deepLink}, cleanup{promo,social,spam} }`.
- **small (170×170):** urgent count + all-clear state → deep link into app.
- **medium (360×170):** urgent count + last scan + top urgent subject/sender → deep link.
- **large (360×360):** top urgent alerts + cleanup counts with one-tap **Clear** buttons
  (`runQuickAction`) + deep link.

## Design identity (Google theme)
- Accent Google blue `#4285F4` (HSL `217 89% 61%`), hover `#1A73E8` (`214 82% 51%`),
  primary `#1967D2` (`213 74% 46%`). Semantic: red `#EA4335` (spam/urgent), yellow
  `#FBBC04` (promotions), green `#34A853` (all-clear/social).
- Font **Roboto** (Google Fonts). Clean white Material surfaces, Google grey-900 text.
- Mark: a shield + envelope glyph in Google colors. App name **Gmail Sentry**.

## Definition of done
A new urgent email arrives → within a scan the user gets a Slack message with a working
Gmail deep link, the email shows in the dashboard + widget as urgent, label rules file
matching mail, and the user can one-tap clear Promotions/Social/Spam — or sees a clear
"connect Gmail/Slack" prompt when an integration isn't connected.
