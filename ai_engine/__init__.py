"""DevMemory AI & Cross-Project Memory Engine.

Provides intelligence, 3-level memory retrieval, and structured diagnosis
for developer troubleshooting workflows.
"""

from .matching import (
    calculate_similarity,
    compute_error_signature,
    extract_exception_type,
    extract_stack_frames,
    normalize_error_message,
    rank_candidates,
)
from .privacy import (
    is_cross_project_sharing_permitted,
    redact_secrets,
    sanitize_diagnosis_request,
    sanitize_file_path,
    sanitize_source_location,
    sanitize_source_snippet,
)
from .diagnosis import diagnose_error
from .knowledge import get_default_knowledge_base, load_knowledge_base
from .llm_client import GroqLLMClient, LLMClient, MockLLMClient
from .prompts import build_diagnosis_prompt
from .retrieval import (
    AuthorizationContext,
    InMemoryIncidentRepository,
    IncidentRepository,
    RetrievalResult,
    retrieve_memory,
)
from .schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    FixOutcome,
    FixStatus,
    FixVerificationStatus,
    IncidentMatch,
    KnowledgeBaseItem,
    MatchSource,
    SourceLocation,
    SourceSnippet,
)


__all__ = [
    "DiagnosisRequest",
    "DiagnosisResponse",
    "FixOutcome",
    "FixStatus",
    "FixVerificationStatus",
    "IncidentMatch",
    "KnowledgeBaseItem",
    "MatchSource",
    "SourceLocation",
    "SourceSnippet",
    "calculate_similarity",
    "compute_error_signature",
    "extract_exception_type",
    "extract_stack_frames",
    "normalize_error_message",
    "rank_candidates",
    "is_cross_project_sharing_permitted",
    "redact_secrets",
    "sanitize_diagnosis_request",
    "sanitize_file_path",
    "sanitize_source_location",
    "sanitize_source_snippet",
    "get_default_knowledge_base",
    "load_knowledge_base",
    "AuthorizationContext",
    "InMemoryIncidentRepository",
    "IncidentRepository",
    "RetrievalResult",
    "retrieve_memory",
    "build_diagnosis_prompt",
    "LLMClient",
    "GroqLLMClient",
    "MockLLMClient",
    "diagnose_error",
]



