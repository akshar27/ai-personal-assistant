import numpy as np
import pytest

from retrieval.embeddings import EMBEDDING_DIM
from retrieval.store import Chunk, SqliteVectorStore


def _vec(seed: int):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
    return (v / np.linalg.norm(v)).tolist()


@pytest.fixture
def store(tmp_path):
    s = SqliteVectorStore(str(tmp_path / "hist.db"))
    s.init()
    return s


def _chunk(msg_id, idx, text, vec, user="u1"):
    return Chunk(
        user_id=user, message_id=msg_id, thread_id="t" + msg_id, sender="a@b.com",
        subject="s", sent_at="2026-08-01T00:00:00", chunk_index=idx, text=text,
        embedding=vec,
    )


def test_add_and_count(store):
    assert store.add_chunks([_chunk("m1", 0, "hello", _vec(1))]) == 1
    assert store.count("u1") == 1
    assert store.count("other") == 0


def test_search_ranks_by_cosine_similarity(store):
    target = _vec(42)
    store.add_chunks([
        _chunk("m1", 0, "the renewal date is March 3", target),
        _chunk("m2", 0, "unrelated lunch plans", _vec(7)),
        _chunk("m3", 0, "also unrelated", _vec(9)),
    ])
    hits = store.search("u1", target, k=2)
    assert [h.message_id for h in hits][0] == "m1"
    assert hits[0].score > hits[1].score
    assert len(hits) == 2


def test_search_is_scoped_per_user(store):
    store.add_chunks([_chunk("m1", 0, "x", _vec(1), user="u1")])
    store.add_chunks([_chunk("m2", 0, "y", _vec(1), user="u2")])
    assert [h.message_id for h in store.search("u1", _vec(1), k=5)] == ["m1"]


def test_delete_message_is_idempotent_reindex(store):
    store.add_chunks([_chunk("m1", 0, "v1", _vec(1)), _chunk("m1", 1, "v1b", _vec(2))])
    assert store.delete_message("u1", "m1") == 2
    store.add_chunks([_chunk("m1", 0, "v2", _vec(3))])
    assert store.count("u1") == 1
    assert store.indexed_message_ids("u1") == {"m1"}


def test_wrong_embedding_dim_is_rejected(store):
    with pytest.raises(ValueError):
        store.add_chunks([_chunk("m1", 0, "x", [0.0, 1.0, 2.0])])


def test_search_on_empty_store_returns_nothing(store):
    assert store.search("u1", _vec(1)) == []
