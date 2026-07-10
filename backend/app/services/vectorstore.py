"""
Thin FAISS wrapper storing dense vectors + parallel metadata list.
Supports metadata filtering (department/category) by pre-filtering the
candidate set before the similarity search — simple and fully transparent,
appropriate for a corpus of this size (~1k chunks).
"""
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import faiss


@dataclass
class Chunk:
    policy_id: str
    department: str
    source: str
    text: str


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)  # cosine similarity via normalized vectors + inner product
        self.chunks: List[Chunk] = []
        self.vectors: Optional[np.ndarray] = None

    @staticmethod
    def _normalize(vecs: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1e-8
        return vecs / norms

    def build(self, chunks: List[Chunk], vectors: np.ndarray):
        assert len(chunks) == vectors.shape[0]
        vectors = self._normalize(vectors.astype("float32"))
        self.index.add(vectors)
        self.chunks = chunks
        self.vectors = vectors

    def search(self, query_vec: np.ndarray, top_k: int = 4, department: Optional[str] = None):
        query_vec = self._normalize(query_vec.astype("float32").reshape(1, -1))

        if department is None:
            scores, idxs = self.index.search(query_vec, top_k)
            idxs, scores = idxs[0], scores[0]
            results = [(self.chunks[i], float(s)) for i, s in zip(idxs, scores) if i != -1]
            return results

        # Metadata-filtered search: search a wider pool, then filter by department,
        # then keep top_k. Simple and correct for corpus sizes in the low thousands.
        pool = min(len(self.chunks), max(top_k * 20, 100))
        scores, idxs = self.index.search(query_vec, pool)
        idxs, scores = idxs[0], scores[0]
        filtered = [
            (self.chunks[i], float(s))
            for i, s in zip(idxs, scores)
            if i != -1 and self.chunks[i].department == department
        ]
        return filtered[:top_k]
