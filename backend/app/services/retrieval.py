from typing import Optional, List, Tuple
from app.services.vectorstore import Chunk
from app import config


def retrieve(store, embedder, query: str, department: Optional[str] = None,
             top_k: int = None) -> List[Tuple[Chunk, float]]:
    top_k = top_k or config.TOP_K
    query_vec = embedder.embed([query])[0]
    results = store.search(query_vec, top_k=top_k, department=department)

    # Graceful degrade: if a department filter starves results (e.g. a
    # mis-routed or unrecognized ticket category), fall back to an
    # unfiltered search rather than returning nothing.
    if not results and department is not None:
        results = store.search(query_vec, top_k=top_k, department=None)
    return results
