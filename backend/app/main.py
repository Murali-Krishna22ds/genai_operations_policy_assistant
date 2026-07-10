from fastapi import FastAPI
from app.routers import query, health

app = FastAPI(
    title="GenAI Operations & Policy Assistant",
    description="RAG pipeline grounding policy Q&A in operations_policies.json, "
                "with live case context from orders/returns/support tickets and "
                "a compliance audit trail.",
    version="1.0.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(query.router, tags=["query"])
