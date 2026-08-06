"""Being throttled must not make the app try harder.

Gmail reaches this app through Claritty's broker, which throttles per app. A
first read walks the mailbox in six-hour buckets — the burstiest thing the app
ever does — so a 429 is ordinary, not exceptional. It surfaced as "Couldn't read
your mail: HTTP 429 ThrottlerException" and abandoned the walk part-way, which
reads as the app being broken when the truth is "wait a moment".

The trap these guard: everything that reads mail speculatively runs on a timer or
a poll. If a throttle doesn't stop them, a brief limit becomes a sustained one —
the app responds to being told to slow down by making MORE requests.
"""
import time

import pytest

from backend.shared import adapters
from backend.shared.adapters import (
    IntegrationError,
    IntegrationRateLimited,
    cooling_down,
    note_rate_limited,
)


@pytest.fixture(autouse=True)
def _clear():
    adapters._cooldowns.clear()
    yield
    adapters._cooldowns.clear()


def test_a_throttle_is_a_kind_of_integration_error():
    """Every existing `except IntegrationError` must keep catching it, or code
    that used to degrade gracefully starts raising in a new way."""
    assert issubclass(IntegrationRateLimited, IntegrationError)


def test_a_throttle_puts_the_service_on_cooldown():
    note_rate_limited("gmail")
    assert cooling_down("gmail") > 0


def test_the_brokers_retry_after_is_honoured():
    note_rate_limited("gmail", "5")
    assert 3 < cooling_down("gmail") <= 5


def test_a_nonsense_retry_after_falls_back_to_the_default():
    note_rate_limited("gmail", "soon-ish")
    assert cooling_down("gmail") > 30


def test_a_cooldown_cannot_be_pushed_absurdly_far_out():
    """A broker asking us to wait a day would otherwise mute the app for a day."""
    note_rate_limited("gmail", "86400")
    assert cooling_down("gmail") <= 300


def test_one_service_being_throttled_does_not_mute_another():
    note_rate_limited("gmail")
    assert cooling_down("slack") == 0


def test_a_cooldown_expires():
    adapters._cooldowns["gmail"] = time.monotonic() - 1
    assert cooling_down("gmail") == 0


def test_the_keepalive_scan_stands_down_while_throttled(monkeypatch):
    """The one that matters. This runs on every widget poll — if a throttle
    doesn't stop it, being rate-limited makes the app scan MORE."""
    from backend.services import sentry

    called = []
    monkeypatch.setattr(sentry, "run_scan", lambda *a, **k: called.append(1))
    note_rate_limited("gmail")

    sentry.scan_if_due("u1")

    assert called == []


def test_the_background_first_read_stands_down_while_throttled(monkeypatch):
    from backend.services import sentry, ledger

    called = []
    monkeypatch.setattr(ledger, "sync_ledger", lambda *a, **k: called.append(1))
    note_rate_limited("gmail")

    sentry.sweep_if_unread("u1")

    assert called == []
