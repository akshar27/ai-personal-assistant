"""The hybrid classifier: keyword heuristic first, LLM 'second opinion' only
when the keywords fall through to chat, and a silent degrade to chat on any
LLM failure."""

import pytest

from graph import intent as intent_mod
from graph.intent import classify_intent
from models.schemas import IntentClassification


def test_keyword_hit_never_calls_the_llm(monkeypatch):
    called = False

    def boom(*a, **k):
        nonlocal called
        called = True
        raise AssertionError("LLM should not be consulted when keywords are confident")

    monkeypatch.setattr(intent_mod, "invoke_structured_with_fallback", boom)
    result, _ = classify_intent("summarize my unread emails")
    assert result == "email_summary"
    assert called is False


def test_llm_rescues_a_phrasing_the_keywords_miss(monkeypatch):
    monkeypatch.setattr(
        intent_mod,
        "invoke_structured_with_fallback",
        lambda schema, prompt: IntentClassification(intent="send_email"),
    )
    result, action_type = classify_intent("could you fire off a note to Sam for me")
    assert result == "send_email"
    assert action_type == "email_send"


def test_llm_failure_degrades_to_chat(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no network / bad key")

    monkeypatch.setattr(intent_mod, "invoke_structured_with_fallback", boom)
    result, action_type = classify_intent("what's the meaning of life")
    assert result == "chat"
    assert action_type == "chat"


def test_llm_saying_chat_stays_chat(monkeypatch):
    monkeypatch.setattr(
        intent_mod,
        "invoke_structured_with_fallback",
        lambda schema, prompt: IntentClassification(intent="chat"),
    )
    result, _ = classify_intent("hello friend")
    assert result == "chat"


def test_llm_garbage_intent_is_ignored(monkeypatch):
    class Bogus:
        intent = "definitely_not_a_real_intent"

    monkeypatch.setattr(
        intent_mod, "invoke_structured_with_fallback", lambda schema, prompt: Bogus()
    )
    result, _ = classify_intent("ramble ramble")
    assert result == "chat"
