# Gmail Sentry — Brief

## Problem & users
A business owner's inbox holds their obligations, and none of them are labelled.
The urgent mail is buried under Promotions; the quote a client is waiting on looks
identical to a newsletter; and the prospect who stopped replying twelve days ago
generates no notification at all — because **silence sends no email**. That last
one is where deals die, and no inbox surfaces it.

**Gmail Sentry** watches the mailbox and answers four questions:

| | |
|---|---|
| What needs me now? | AI triage against rules the user writes in plain language |
| What do I owe people? | Threads where the ball is in their court |
| What's going quiet? | People who haven't answered — where customers get lost |
| Where does this go? | Conversations filed into folders the user approved |

Target user: anyone whose business runs through their inbox — founders, sales,
account managers, consultants — who can't afford to lose a thread.

## What it does

1. **Triage** — every 5 minutes, judge new mail as `urgent` / `needs_reply` /
   `fyi`, fusing natural-language rules, VIP senders, keywords and deadline
   detection. The *ask* is pulled out in one line at the same time, so a row says
   "needs the revised quote before Friday" rather than "Re: Q3".
2. **Notify** — Slack / WhatsApp / Telegram / Discord, per-channel urgency, with
   a drafted reply and a one-tap approve link.
3. **Reply in their voice** — drafted from the user's real sent mail. Nothing is
   ever sent without an explicit approval that names the recipient.
4. **Track open loops** — a reply doesn't end a thread, it flips it to "waiting on
   them". Aging is per-relationship: a lawyer who answers in three days isn't
   chased after one; a customer who normally answers in two hours is cold at two
   days. A reply sent from the user's phone closes the alert on its own.
5. **File conversations** — by who they're with (`Clients/Northwind`), applied to
   every message in the thread including the user's own replies. Folders are
   proposed and never created without approval; filing never removes mail from
   the inbox.
6. **Report daily** — what needs answering, who has gone quiet, what got filed.
7. **Clean** — one-tap bulk clear of Promotions / Social / Spam.

## Architecture

The load-bearing piece is the **thread ledger** (`backend/services/ledger.py`):
an incrementally-synced index of every observed message, in and out, keyed by
thread. The broker exposes no `get_thread` verb and `get_message` returns no
date, so time is recovered from the *query window* (`after:`/`before:` epoch) and
thread topology comes free on the search stub. Two searches per sweep —
`in:inbox` and `in:sent` — give ball position, aging, phone-reply detection and
incremental sync for **zero LLM calls**.

It also fixed the app's worst cost bug: a message judged `fyi` used to leave no
trace, so every 5-minute scan re-classified it for two days (~5,760 model calls a
day on a quiet inbox). Every judged message now records a verdict and is judged
exactly once, ever.

- **Models** (all `user_id`-scoped): `TriageRule`, `LabelRule`, `Alert`, `ScanRun`,
  `SentryConfig`, `CommProfile`, `ThreadMessage`, `ThreadSyncState`,
  `Counterparty`, `FollowUp`, `Nudge`, `MailFolder`, `ThreadFolder`.
- **Services**: `ledger`, `counterparty` (who matters, from revealed preference —
  who you answer and how fast, not who emails most), `followups`, `filing`,
  `triage`, `reply`, `learn`, `digest`.
- **Agents**: `triage-agent`, `digest-agent` — thin manifest-bound wrappers with
  offline fallbacks. All intelligence lives in the services.
- **Triggers**: `sentry-scan` (INTERVAL, 5 min), `sentry-digest` (DAILY).

## Integrations
Catalog-first, platform OAuth, no keys, no mocks. **gmail** (required) and
**slack** (required), plus telegram / discord / twilio. Not connected → an honest
409 connect prompt, never a faked success.

## Design identity
Google blue accent on cool-charcoal surfaces, Roboto, shield+envelope mark.

## Definition of done
A new email needing a reply arrives → the user is notified on their channel with
a draft in their own voice and a one-tap approve link → approving really sends it
in-thread through Gmail → the thread stays visible as an open loop waiting on
them, and surfaces as going cold if they never answer → a reply sent from the
phone closes the alert on its own → the conversation is filed into a folder the
user approved, their own replies included → a daily report says what needs
answering, who has gone quiet, and what was filed. Any missing integration shows
a clear connect prompt, never a faked success.

## Following up on silence
A thread that's gone quiet can be chased with a short follow-up in the user's
voice, escalating gentle → direct → close-it-out. It is the only message the app
puts in front of someone the user didn't just hear from, so it's mostly guards:

- **never pre-generated** — drafting happens only when asked, because a
  ready-to-send nudge nobody requested is one mis-tap from an unwanted email;
- **backfill guard** — threads from the initial history import are never
  eligible, or the first sync would offer to chase everyone the user
  deliberately stopped replying to;
- **three per thread, ever** — a fourth is harassment sent in the user's name;
- **48h between nudges to one person**, across all their threads;
- **the button names the recipient** and arms before sending;
- every refusal is prose the UI shows verbatim — a silently disabled control
  reads as broken, an explained one reads as careful.

Same honest-failure contract as replies: not connected → 409 with the draft
preserved, a real failure → 502 recorded for retry, and only a genuine Gmail
message id marks it sent.
