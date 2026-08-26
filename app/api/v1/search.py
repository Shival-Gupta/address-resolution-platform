# File: app/api/v1/search.py
"""Search API endpoints for typeahead suggestions, full cascade resolution, and batching.

Exposes `/suggest`, `/resolve`, and `/batch` endpoints protected by API key authentication.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.api.deps import get_orchestrator, verify_api_key
from app.models.search import BatchRequest, SearchQuery, SearchResult
from app.pipeline.orchestrator import SearchOrchestrator

router = APIRouter(prefix="", tags=["search"], dependencies=[Depends(verify_api_key)])


@router.post(
    "/resolve",
    response_model=SearchResult,
    summary="Resolve address to canonical SAP Premise ID via 4-tier cascade",
)
@router.post(
    "/search/resolve",
    response_model=SearchResult,
    include_in_schema=False,
)
async def resolve_address(
    query: SearchQuery,
    orchestrator: SearchOrchestrator = Depends(get_orchestrator),
) -> SearchResult:
    """Resolve an unparsed, noisy address string to a canonical SAP Premise ID.

    Cascades through Tier 0 Normalization, Spatial Partitioning, Tier 1 Lexical Matching,
    Tier 2 Semantic Vector Search with Number-Blindness Guardrail, and Tier 3 LLM Disambiguation.

    Args:
        query: Inbound SearchQuery object.
        orchestrator: Injected SearchOrchestrator instance.

    Returns:
        SearchResult: Resolution response with ranked candidates and resolved best match.
    """
    return await orchestrator.resolve(query)


@router.post(
    "/suggest",
    response_model=SearchResult,
    summary="Fast typeahead suggestions (Tier 1 Lexical path, <20ms SLA)",
)
@router.post(
    "/search/suggest",
    response_model=SearchResult,
    include_in_schema=False,
)
async def suggest_address(
    query: SearchQuery,
    orchestrator: SearchOrchestrator = Depends(get_orchestrator),
) -> SearchResult:
    """Provide fast typeahead address candidate suggestions for UI auto-complete.

    Executes Tier 0 Normalization and Tier 1 Lexical matching only (<20ms latency).

    Args:
        query: Inbound SearchQuery object.
        orchestrator: Injected SearchOrchestrator instance.

    Returns:
        SearchResult: Top candidate matches.
    """
    return await orchestrator.suggest(query)


@router.post(
    "/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue asynchronous batch address resolution job",
)
@router.post(
    "/search/batch",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def batch_resolve(
    batch_req: BatchRequest,
    background_tasks: BackgroundTasks,
    orchestrator: SearchOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Queue a batch of address resolution requests for background processing.

    Args:
        batch_req: List of SearchQuery objects and optional callback URL.
        background_tasks: FastAPI BackgroundTasks runner.
        orchestrator: Injected SearchOrchestrator instance.

    Returns:
        dict[str, Any]: 202 Accepted response containing unique job_id.
    """
    job_id = str(uuid.uuid4())

    async def process_batch_job(
        items: list[SearchQuery], orch: SearchOrchestrator, _jid: str
    ) -> None:
        # Background worker resolving batch records
        for item in items:
            await orch.resolve(item)

    background_tasks.add_task(process_batch_job, batch_req.addresses, orchestrator, job_id)

    return {
        "job_id": job_id,
        "status": "QUEUED",
        "total_records": len(batch_req.addresses),
        "message": f"Queued {len(batch_req.addresses)} addresses for resolution.",
    }
