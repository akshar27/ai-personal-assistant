"""Query side of retrieval: embed the question, pull the nearest email chunks."""

from retrieval import embeddings
from retrieval.store import SearchHit, VectorStore, get_store

DEFAULT_K = 6
# Below this cosine score a chunk is almost certainly noise for this query.
MIN_SCORE = 0.15


def search_history(
    user_id: str,
    query: str,
    *,
    k: int = DEFAULT_K,
    store: VectorStore | None = None,
) -> list[SearchHit]:
    store = store or get_store()
    query = (query or "").strip()
    if not query:
        return []

    q_vec = embeddings.embed_query(query)
    hits = store.search(user_id, q_vec, k=k)
    return [h for h in hits if h.score >= MIN_SCORE]
