"""
Ingestion (Objective 2): load operations_policies.json, treat each record's
`answer` field as the authoritative policy passage (it already contains the
grounding content + a case reference), tag it with metadata (policy_id =
`id`, department = `category`, source = `source`), embed, and index in FAISS.

Each JSON record is short enough (1-3 sentences) to be used as a single chunk
without further splitting — chunking logic is included for completeness and
would kick in automatically for longer policy documents.
"""
import json
import pickle
from typing import List, Tuple
import numpy as np

from app import config
from app.services.vectorstore import Chunk, VectorStore
from app.services.embeddings import get_embedder

MAX_CHUNK_CHARS = 800  # chunk boundary for longer source documents


def _split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    # naive sentence-boundary-aware splitter
    parts, current = [], ""
    for sentence in text.replace("\n", " ").split(". "):
        if len(current) + len(sentence) > max_chars and current:
            parts.append(current.strip())
            current = sentence
        else:
            current += (". " if current else "") + sentence
    if current:
        parts.append(current.strip())
    return parts


def load_policy_chunks() -> List[Chunk]:
    with open(config.POLICIES_JSON, "r", encoding="utf-8") as f:
        records = json.load(f)

    chunks: List[Chunk] = []
    for rec in records:
        policy_id = rec["id"]
        department = rec["category"]
        source = rec["source"]
        # The "answer" is the authoritative grounding text; "question" is kept
        # out of the embedded text but could be included to boost recall.
        for i, piece in enumerate(_split_long_text(rec["answer"])):
            chunks.append(Chunk(
                policy_id=f"{policy_id}" if i == 0 else f"{policy_id}-c{i}",
                department=department,
                source=source,
                text=piece,
            ))
    return chunks


def build_and_persist_index() -> Tuple[VectorStore, str]:
    chunks = load_policy_chunks()
    texts = [c.text for c in chunks]

    embedder, embedder_desc = get_embedder()
    if hasattr(embedder, "fit"):
        embedder.fit(texts)
    vectors = embedder.embed(texts)

    store = VectorStore(dim=vectors.shape[1])
    store.build(chunks, vectors)

    config.INDEX_DIR.mkdir(exist_ok=True)
    with open(config.INDEX_DIR / "vectorstore.pkl", "wb") as f:
        pickle.dump({
            "chunks": chunks,
            "vectors": store.vectors,
            "embedder_desc": embedder_desc,
            "embedder": embedder if not hasattr(embedder, "client") else None,  # don't pickle OpenAI client
        }, f)

    print(f"Indexed {len(chunks)} policy chunks using embedder: {embedder_desc}")
    return store, embedder_desc


def load_persisted_index() -> Tuple[VectorStore, str, object]:
    path = config.INDEX_DIR / "vectorstore.pkl"
    if not path.exists():
        store, embedder_desc = build_and_persist_index()
        with open(path, "rb") as f:
            payload = pickle.load(f)
        return store, embedder_desc, payload.get("embedder")

    with open(path, "rb") as f:
        payload = pickle.load(f)
    store = VectorStore(dim=payload["vectors"].shape[1])
    store.build(payload["chunks"], payload["vectors"])
    return store, payload["embedder_desc"], payload.get("embedder")


if __name__ == "__main__":
    build_and_persist_index()
