"""
Refining a draft the user is already looking at (services/reply.refine_draft).

The draft is 80% right and the last 20% is where people give up and retype it —
which throws away the voice matching the draft existed for. These guard the two
things that make the feature safe rather than merely clever:

  * it REFUSES rather than silently returning the input, because a button that
    appears to do nothing is worse than one that says why it can't;
  * it never invents scaffolding, because it may be handed a fragment from the
    middle of an email rather than a whole message.
"""
import pytest

from backend.services.reply import REFINEMENTS, RefusedToRefine, refine_draft


class _Client:
    """Captures the prompt so we can assert on the instructions actually sent."""

    def __init__(self, reply="Rewritten."):
        self.reply, self.prompt, self.system = reply, "", ""

    def chat(self, messages, **kw):
        self.prompt = messages[0]["content"]
        self.system = kw.get("system", "")
        return type("R", (), {"content": self.reply})()


@pytest.fixture
def llm(monkeypatch):
    client = _Client()
    import sys, types
    mod = types.ModuleType("claritty_sdk.llm")
    mod.get_llm_client = lambda *_a, **_k: client
    pkg = types.ModuleType("claritty_sdk")
    pkg.llm = mod
    monkeypatch.setitem(sys.modules, "claritty_sdk", pkg)
    monkeypatch.setitem(sys.modules, "claritty_sdk.llm", mod)
    return client


def test_every_offered_refinement_has_an_instruction():
    """The UI chips and the backend vocabulary must not drift apart."""
    assert set(REFINEMENTS) == {"shorter", "warmer", "firmer", "formal"}
    for how, text in REFINEMENTS.items():
        assert len(text) > 20, how


def test_it_rewrites_and_returns_the_new_text(llm):
    llm.reply = "Sending the numbers today."
    assert refine_draft("I will be sending you the numbers at some point today.",
                        "shorter") == "Sending the numbers today."


def test_an_empty_selection_is_refused_not_silently_ignored():
    with pytest.raises(RefusedToRefine) as e:
        refine_draft("   ", "shorter")
    assert "nothing selected" in str(e.value).lower()


def test_an_unknown_refinement_is_refused():
    with pytest.raises(RefusedToRefine):
        refine_draft("hello", "sassier")


def test_no_llm_refuses_rather_than_handing_the_text_back(monkeypatch):
    """draft_reply may fall back to a template — something beats a blank page.
    A refine has no such excuse: returning the input unchanged looks like the
    button did nothing, and a template would replace the user's own words."""
    import sys, types
    mod = types.ModuleType("claritty_sdk.llm")
    def boom(*_a, **_k): raise RuntimeError("no proxy")
    mod.get_llm_client = boom
    pkg = types.ModuleType("claritty_sdk"); pkg.llm = mod
    monkeypatch.setitem(sys.modules, "claritty_sdk", pkg)
    monkeypatch.setitem(sys.modules, "claritty_sdk.llm", mod)

    original = "Hi Dana, sending it over."
    with pytest.raises(RefusedToRefine) as e:
        refine_draft(original, "warmer")
    assert "untouched" in str(e.value).lower()


def test_an_empty_model_response_is_refused(llm):
    llm.reply = "   "
    with pytest.raises(RefusedToRefine):
        refine_draft("something", "firmer")


def test_it_is_told_not_to_add_greetings_or_invent_facts(llm):
    """It may be handed one paragraph out of the middle of an email."""
    refine_draft("the deck lands Tuesday", "warmer", context="Q3 quote")
    p = llm.prompt.lower()
    assert "do not add a greeting" in p
    assert "sign-off" in p
    assert "not already there" in p
    assert "q3 quote" in p


def test_the_users_voice_is_carried_into_the_rewrite(llm):
    refine_draft("ok will do", "formal",
                 style_samples=["Thanks so much — I'll take a look and revert."],
                 tone="warm and brisk")
    assert "warm and brisk" in llm.prompt
    assert "revert" in llm.prompt
