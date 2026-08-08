"""Smart setup proposes PATTERNS, not the senders that happened to write most.

The proposal this replaces read the inbox's most frequent senders and offered
them as urgent VIPs. Frequency is the wrong signal — the most frequent senders
in any mailbox are its newsletters — so it produced, verbatim:

    Urgent  From Samsung
    Urgent  From Trip.com
    File    innovations.samsungusa.com → Newsletters
    File    newsletter.trip.com        → Newsletters

marking the same domains urgent and noise at once, while the owner had just
said "I want to manage my client cycles and invoices and contacts" — which was
stored as a single opaque rule that matched almost nothing.
"""
from backend.services.onboarding import _heuristic, _intent_keywords, _normalize

SIGNALS = {
    "top_senders": [
        {"email": "innovations@samsungusa.com", "domain": "innovations.samsungusa.com",
         "name": "Samsung", "count": 9, "personal": True},
        {"email": "news@newsletter.trip.com", "domain": "newsletter.trip.com",
         "name": "Trip.com", "count": 7, "personal": True},
    ],
    "promo_domains": ["innovations.samsungusa.com", "newsletter.trip.com"],
    "sample_subjects": ["Invoice 4821 for June", "Contract for signature"],
    "correspondents": [
        {"email": "dana@northwind.co", "name": "Dana Levi", "reply_rate": 90,
         "importance": 80, "reason": "you reply to them 90% of the time"},
    ],
    "counts": {},
}
ASK = "i want to manage my client cycles and invoices and contacts"


def _draft(desc=ASK, role="founder", signals=SIGNALS):
    return _heuristic(description=desc, role=role, noise="balanced", signals=signals)


def test_what_they_asked_for_becomes_patterns():
    values = [r["value"] for r in _draft()["triage_rules"]]
    assert "invoice" in values
    assert "contract" in values or "proposal" in values


def test_the_sentence_is_not_stored_as_one_opaque_rule():
    """"manage my client cycles and invoices" as a single rule says nothing and
    matches almost nothing — it has to become the patterns it implies."""
    rules = _draft()["triage_rules"]
    assert not any(r["kind"] == "nl" and ASK[:20] in r["value"] for r in rules)


def test_a_frequent_newsletter_sender_is_never_made_urgent():
    """The exact defect: Samsung and Trip.com proposed as urgent."""
    vips = [r["value"] for r in _draft()["triage_rules"] if r["kind"] == "vip_sender"]
    assert not any("samsung" in v or "trip.com" in v for v in vips)


def test_a_sender_cannot_be_urgent_and_archived_at_once():
    """Two instructions that cancel out is not a preference to weigh up."""
    out = _normalize({
        "triage_rules": [
            {"name": "From Samsung", "kind": "vip_sender",
             "value": "innovations@samsungusa.com", "tier": "urgent"},
            {"name": "Invoice", "kind": "keyword", "value": "invoice", "tier": "needs_reply"},
        ],
        "label_rules": [
            {"name": "File", "match_type": "domain", "match_value": "samsungusa.com",
             "target_label": "Newsletters", "archive_after": True},
        ],
    })
    kinds = [(r["kind"], r["value"]) for r in out["triage_rules"]]
    assert ("vip_sender", "innovations@samsungusa.com") not in kinds
    assert ("keyword", "invoice") in kinds       # the pattern survives


def test_only_someone_you_reply_to_becomes_a_vip():
    vips = [r["value"] for r in _draft()["triage_rules"] if r["kind"] == "vip_sender"]
    assert vips == ["dana@northwind.co"]


def test_no_correspondents_means_no_vips_rather_than_a_guess():
    signals = {**SIGNALS, "correspondents": []}
    vips = [r["value"] for r in _draft(signals=signals)["triage_rules"] if r["kind"] == "vip_sender"]
    assert vips == []


def test_an_address_they_typed_is_still_honoured():
    """A named sender is a deliberate instruction, not an inference."""
    d = _draft(desc="anything from priya@acme.io is urgent")
    vips = [r["value"] for r in d["triage_rules"] if r["kind"] == "vip_sender"]
    assert "priya@acme.io" in vips


def test_the_noise_is_still_filed():
    labels = [r["match_value"] for r in _draft()["label_rules"]]
    assert "innovations.samsungusa.com" in labels


def test_a_vague_ask_still_yields_something_usable():
    """No intent match, no signals — it must not return an empty setup."""
    d = _heuristic(description="", role="sales", noise="balanced", signals=None)
    assert d["triage_rules"]


def test_intent_matching_is_stem_based():
    """"invoices" and "invoicing" are the same ask as "invoice"."""
    assert "invoice" in _intent_keywords("track my invoices", "")
    assert "invoice" in _intent_keywords("invoicing is a mess", "")
