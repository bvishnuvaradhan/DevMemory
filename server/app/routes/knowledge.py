"""FastAPI route endpoints for the curated programming knowledge base."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.db.mongo import get_database
from app.schemas import ResponseEnvelope
from app.schemas.knowledge import KnowledgeBaseMatch, KnowledgeBaseSeedResponse
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])


@router.post(
    "/seed",
    response_model=ResponseEnvelope[KnowledgeBaseSeedResponse],
    summary="Seed or update the curated programming knowledge base in MongoDB",
)
def seed_knowledge_base_endpoint(
    force_reembed: bool = Query(default=False, description="Force regeneration of vector embeddings"),
    db: Database = Depends(get_database),
):
    summary = knowledge_service.seed_knowledge_base(db, force_reembed=force_reembed)
    return ResponseEnvelope[KnowledgeBaseSeedResponse](success=True, data=summary, error=None)


@router.get(
    "",
    response_model=ResponseEnvelope[List[Dict[str, Any]]],
    summary="List curated programming knowledge entries",
)
def list_knowledge_base_endpoint(
    language: Optional[str] = Query(default=None, description="Filter by language (e.g. python, javascript, http, mongodb)"),
    category: Optional[str] = Query(default=None, description="Filter by category (e.g. runtime, database, api, networking)"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Database = Depends(get_database),
):
    items = knowledge_service.list_knowledge_base_items(
        db, language=language, category=category, limit=limit
    )
    return ResponseEnvelope[List[Dict[str, Any]]](success=True, data=items, error=None)


@router.post(
    "/search",
    response_model=ResponseEnvelope[List[KnowledgeBaseMatch]],
    summary="Search general programming knowledge entries",
)
def search_knowledge_base_endpoint(
    query_text: Optional[str] = Query(default=None, description="Error message, symptom, or diagnostic query text"),
    query: Optional[str] = Query(default=None, description="Alias for query_text"),
    limit: int = Query(default=5, ge=1, le=20),
    min_score: float = Query(default=0.40, ge=0.0, le=1.0),
    db: Database = Depends(get_database),
):
    resolved_query = (query_text or query or "").strip()
    matches = knowledge_service.search_knowledge_base(
        db, query_text=resolved_query, limit=limit, min_score=min_score
    )
    return ResponseEnvelope[List[KnowledgeBaseMatch]](success=True, data=matches, error=None)
