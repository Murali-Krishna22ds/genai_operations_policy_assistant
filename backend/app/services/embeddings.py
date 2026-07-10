"""
Two interchangeable embedding backends, selected via EMBEDDING_PROVIDER:

  - "openai": calls OpenAI's text-embedding-3-small (or configured model).
              Requires OPENAI_API_KEY. Used in production per project brief
              (Objective 1/2: "text-embedding-ada-002" family).
  - "tfidf":  a deterministic local TF-IDF + SVD dense projection. No network
              calls, no API cost, fully reproducible with a fixed seed.
              Used automatically when no API key is configured, so the
              pipeline can be built/tested/evaluated offline.

Both expose the same `embed(texts: list[str]) -> np.ndarray` interface so the
rest of the pipeline (ingestion, retrieval) is agnostic to which is active.
"""
from typing import List
import numpy as np

from app import config


class OpenAIEmbedder:
    def __init__(self, model: str = None):
        from openai import OpenAI
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = model or config.OPENAI_EMBEDDING_MODEL

    def embed(self, texts: List[str]) -> np.ndarray:
        # Batch to stay well under request size limits.
        vectors = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend([d.embedding for d in resp.data])
        return np.array(vectors, dtype="float32")


class TfidfEmbedder:
    """Deterministic, dependency-light local embedder used as an offline fallback."""

    def __init__(self, dim: int = 256, seed: int = 42):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        self.dim = dim
        self.seed = seed
        self.vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 2), stop_words="english")
        self.svd = TruncatedSVD(n_components=dim, random_state=seed)
        self._fitted = False

    def fit(self, corpus_texts: List[str]):
        tfidf = self.vectorizer.fit_transform(corpus_texts)
        self.svd.fit(tfidf)
        self._fitted = True

    def embed(self, texts: List[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TfidfEmbedder must be fit() on the corpus before embed().")
        tfidf = self.vectorizer.transform(texts)
        return self.svd.transform(tfidf).astype("float32")


def get_embedder():
    """Factory: returns a ready embedder based on config, with automatic fallback."""
    if config.EMBEDDING_PROVIDER == "openai" and config.using_live_llm():
        return OpenAIEmbedder(), "openai:" + config.OPENAI_EMBEDDING_MODEL
    # Fallback (either explicitly requested, or no API key present)
    return TfidfEmbedder(dim=config.TFIDF_DIM), f"local-tfidf-svd:dim={config.TFIDF_DIM}"
