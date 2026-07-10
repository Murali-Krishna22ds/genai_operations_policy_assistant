from typing import Optional, List
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., description="Staff member's natural-language policy question")
    ticket_id: Optional[str] = Field(None, description="Optional support ticket to pull live case context from")
    order_id: Optional[str] = Field(None, description="Optional order to pull live case context from")
    customer_id: Optional[str] = Field(None, description="Optional customer to pull live case context from")
    actor: str = Field("unknown_agent", description="Identifier of the staff member/agent issuing the query, for audit logging")


class RetrievedChunk(BaseModel):
    policy_id: str
    department: str
    source: str
    text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: List[RetrievedChunk]
    case_context: dict
    grounded: bool
    mode: str  # "live_llm" or "extractive_fallback"
    audit_log_id: str
