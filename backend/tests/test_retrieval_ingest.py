import pytest

from retrieval.ingest import chunk_text, ingest_user_history
from retrieval.search import search_history
from retrieval.store import get_store


@pytest.fixture
def store(fake_embeddings):
    return get_store()


def test_chunk_text_overlaps_and_covers():
    text = "".join(chr(ord("a") + i % 26) for i in range(300))
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) >= 3
    # consecutive chunks share a 20-char tail/head
    assert chunks[0][-20:] == chunks[1][:20]
    # every original character appears in some chunk
    assert set("".join(chunks)) == set(text)


def test_chunk_text_short_input_is_one_chunk():
    assert chunk_text("just a line") == ["just a line"]
    assert chunk_text("   ") == []


def test_ingest_then_search_finds_the_right_message(fake_google, store):
    fake_google["messages"] = [
        {"id": "m1", "subject": "Contract", "sender": "sam@corp.com",
         "body": "Confirming the renewal date is March 3rd 2027 and the price is locked."},
        {"id": "m2", "subject": "Lunch", "sender": "jo@corp.com",
         "body": "Want to grab tacos on Friday afternoon near the office?"},
    ]
    stats = ingest_user_history("u1", store=store)
    assert stats["messages_indexed"] == 2
    assert stats["chunks_added"] >= 2

    hits = search_history("u1", "when is the contract renewal date", store=store)
    assert hits
    assert hits[0].message_id == "m1"
    assert hits[0].subject == "Contract"


def test_ingest_is_idempotent(fake_google, store):
    fake_google["messages"] = [
        {"id": "m1", "subject": "X", "body": "some indexable content here about widgets"},
    ]
    first = ingest_user_history("u1", store=store)
    assert first["messages_indexed"] == 1

    second = ingest_user_history("u1", store=store)
    assert second["messages_indexed"] == 0
    assert second["skipped_already_indexed"] == 1
    assert store.count("u1") == first["chunks_added"]


def test_ingest_skips_empty_bodies(fake_google, store):
    fake_google["messages"] = [{"id": "m1", "subject": "empty", "body": "   "}]
    stats = ingest_user_history("u1", store=store)
    assert stats["messages_indexed"] == 0
    assert stats["messages_empty"] == 1


def test_search_blank_query_returns_nothing(store):
    assert search_history("u1", "   ", store=store) == []
