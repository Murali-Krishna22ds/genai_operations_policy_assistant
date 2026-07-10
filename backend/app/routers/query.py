from fastapi import APIRouter
from app.schemas import QueryRequest, QueryResponse, RetrievedChunk
from app.services import ingestion, retrieval, generation, case_context as case_ctx_service, audit
from app import config

router = APIRouter()

_store, _embedder_desc, _embedder = ingestion.load_persisted_index()
if _embedder is None:
    # OpenAI embedder isn't pickled (unpicklable client) — reconstruct it.
    from app.services.embeddings import get_embedder
    _embedder, _ = get_embedder()


@router.post("/query", response_model=QueryResponse)
def query_policy_assistant(req: QueryRequest):
    case_context = case_ctx_service.get_case_context(
        ticket_id=req.ticket_id, order_id=req.order_id, customer_id=req.customer_id
    )
    department = case_context.get("routed_policy_department")

    results = retrieval.retrieve(_store, _embedder, req.query, department=department)
    answer, mode = generation.generate_answer(req.query, results, case_context)

    grounded = len(results) > 0 and "I don't have a policy on file" not in answer

    citation_ids = [c.policy_id for c, _ in results]
    if req.ticket_id:
        entity_type, entity_id = "ticket", req.ticket_id
    elif req.order_id:
        entity_type, entity_id = "order", req.order_id
    elif req.customer_id:
        entity_type, entity_id = "customer", req.customer_id
    else:
        entity_type, entity_id = "policy_query", ""

    log_id = audit.log_query(
        actor=req.actor, query=req.query, answer=answer,
        citation_ids=citation_ids, grounded=grounded, mode=mode,
        entity_id=entity_id, entity_type=entity_type,
    )

    return QueryResponse(
        answer=answer,
        citations=[RetrievedChunk(policy_id=c.policy_id, department=c.department,
                                   source=c.source, text=c.text, score=score)
                   for c, score in results],
        case_context=case_context,
        grounded=grounded,
        mode=mode,
        audit_log_id=log_id,
    )
