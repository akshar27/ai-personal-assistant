"""Pull the user's recent Gmail, chunk + embed the bodies, and upsert them into
the vector store. Idempotent per message: re-running only indexes what's new.
"""

import argparse
import logging

from config import settings
from integrations.gmail_client import list_message_ids, get_message_full
from retrieval import embeddings
from retrieval.store import Chunk, VectorStore, get_store

logger = logging.getLogger("ai_assistant.ingest")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    step = max(1, size - overlap)
    chunks = []
    for start in range(0, len(text), step):
        piece = text[start:start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(text):
            break
    return chunks


def ingest_user_history(
    user_id: str,
    *,
    max_messages: int | None = None,
    query: str | None = None,
    store: VectorStore | None = None,
    reindex: bool = False,
) -> dict:
    max_messages = max_messages or settings.history_ingest_max_messages
    query = query or settings.history_ingest_query
    store = store or get_store()

    refs = list_message_ids(query=query, max_results=max_messages)
    already = set() if reindex else store.indexed_message_ids(user_id)

    stats = {"messages_seen": len(refs), "skipped_already_indexed": 0,
             "messages_indexed": 0, "chunks_added": 0, "messages_empty": 0}

    for ref in refs:
        mid = ref["id"]
        if mid in already:
            stats["skipped_already_indexed"] += 1
            continue

        full = get_message_full(mid)
        pieces = chunk_text(full.get("body", ""))
        if not pieces:
            stats["messages_empty"] += 1
            continue

        vectors = embeddings.embed_texts(pieces)
        chunks = [
            Chunk(
                user_id=user_id, message_id=mid, thread_id=full.get("thread_id", ""),
                sender=full.get("sender", ""), subject=full.get("subject", ""),
                sent_at=full.get("sent_at", ""), chunk_index=i, text=piece,
                embedding=vec,
            )
            for i, (piece, vec) in enumerate(zip(pieces, vectors))
        ]
        store.delete_message(user_id, mid)
        stats["chunks_added"] += store.add_chunks(chunks)
        stats["messages_indexed"] += 1

    logger.info("history ingest for %s: %s", user_id, stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Index Gmail history for retrieval.")
    parser.add_argument("--user", default="default_user")
    parser.add_argument("--max-messages", type=int, default=None)
    parser.add_argument("--query", default=None)
    parser.add_argument("--reindex", action="store_true", help="re-embed everything")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    from auth.context import user_scope

    store = get_store()
    with user_scope(args.user):
        stats = ingest_user_history(
            args.user, max_messages=args.max_messages, query=args.query,
            store=store, reindex=args.reindex,
        )
    print(stats)


if __name__ == "__main__":
    main()
