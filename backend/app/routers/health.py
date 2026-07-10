from fastapi import APIRouter
from app import config

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "generation_model": config.GENERATION_MODEL,
        "generation_mode": "live_llm" if config.using_live_llm() else "extractive_fallback",
        "embedding_provider": config.EMBEDDING_PROVIDER if config.using_live_llm() else "local-tfidf-fallback",
    }
