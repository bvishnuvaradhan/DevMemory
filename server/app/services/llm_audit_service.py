"""LLM request payload audit and frontend security evidence service.

Provides:
1. AuditedLLMClient wrapping external provider adapters immediately before dispatch.
2. Sensitive secret detection and policy verification with fail-closed enforcement.
3. Separate request preparation, dispatch, and completion tracking.
4. Redaction category/count analysis and deterministic payload hashing.
5. Strict project-isolated audit retrieval and security evidence summary calculations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pymongo.database import Database

from ai_engine.llm_client import GroqLLMClient, LLMClient, MockLLMClient
from ai_engine.privacy import redact_secrets as engine_redact_secrets
from app.schemas.llm_audit import (
    LLMRequestAuditItem,
    LLMSecuritySummary,
    RedactionSummary,
    SanitizedPromptPayload,
)
from devmemory.integration.models import redact_secrets

logger = logging.getLogger(__name__)

# Patterns used for secondary safety verification to ensure no live raw secrets slip through
UNREDACTED_CREDENTIAL_PATTERNS = [
    ("api_key", re.compile(r"\b(sk-(?:proj-)?[a-zA-Z0-9_\-]{20,}|gsk_[a-zA-Z0-9_\-]{20,})\b")),
    ("github_token", re.compile(r"\b(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b")),
    ("aws_key", re.compile(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
    ("db_connection_uri", re.compile(r"(?i)[a-z][a-z0-9+\-\.]*://[^:\s@/]+:[^@\s/]{3,}@")),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.]{20,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----")),
    ("key_assignment", re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|auth[_-]?token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{12,})['\"]?")),
    ("generic_secret", re.compile(r"(?i)\b(?:fake[_-]secret[_-]key|test[_-]secret[_-]key)[_-]?[a-zA-Z0-9_\-]{10,}\b")),
]

# Patterns for identifying and categorizing redactions in sanitized prompt text
REDACTION_TAG_PATTERNS = [
    ("api_keys", re.compile(r"(?i)\[REDACTED_(?:API_KEY|GITHUB_TOKEN|SLACK_TOKEN|STRIPE_KEY|SENDGRID_KEY|AWS_KEY|AWS_SECRET)\]")),
    ("passwords", re.compile(r"(?i)\[REDACTED_(?:PASSWORD|AUTH|BASIC_AUTH|COOKIE)\]")),
    ("tokens", re.compile(r"(?i)\[REDACTED_TOKEN\]")),
    ("credentials", re.compile(r"(?i)\[REDACTED_(?:CREDENTIAL|SECRET)\]|\[REDACTED\]")),
    ("paths", re.compile(r"(?i)\[REDACTED_PATH\]|<path>")),
]


class PayloadSecurityPolicyViolation(RuntimeError):
    """Raised when an outbound LLM payload fails security validation and must not be transmitted."""
    pass


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of the sanitized payload dictionary."""
    canonical_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def analyze_redactions(text: str) -> RedactionSummary:
    """Analyze and categorize redaction tags present in the sanitized prompt text."""
    if not text:
        return RedactionSummary(total_redactions=0, has_redactions=False, categories={}, detected_types=[])

    categories: Dict[str, int] = {}
    total = 0
    detected_types = []

    for cat_name, pattern in REDACTION_TAG_PATTERNS:
        matches = pattern.findall(text)
        count = len(matches)
        if count > 0:
            categories[cat_name] = count
            total += count
            detected_types.append(cat_name)

    return RedactionSummary(
        total_redactions=total,
        has_redactions=total > 0,
        categories=categories,
        detected_types=detected_types,
    )


def validate_outbound_safety(system_prompt: str, user_prompt: str) -> Tuple[bool, Optional[str]]:
    """Verify that no unredacted live credentials exist in outbound prompt text.

    Fails closed if active raw credential patterns are detected.
    """
    combined = f"{system_prompt}\n{user_prompt}"

    for pattern_name, pattern in UNREDACTED_CREDENTIAL_PATTERNS:
        for match in pattern.finditer(combined):
            matched_str = match.group(0)
            # Ignore redaction placeholder tokens themselves
            if matched_str.startswith("[REDACTED") or matched_str.startswith("<path"):
                continue
            return False, f"Unredacted sensitive credential pattern detected: {pattern_name}"

    return True, None


def scrub_unredacted_credentials(text: str) -> str:
    """Aggressively scrub any unredacted credential patterns to ensure they never enter DB."""
    scrubbed = text
    for pattern_name, pattern in UNREDACTED_CREDENTIAL_PATTERNS:
        scrubbed = pattern.sub(f"[REDACTED_{pattern_name.upper()}]", scrubbed)
    return scrubbed


class AuditedLLMClient:
    """Adapter wrapping an LLMClient that intercepts, verifies, and audits outbound payloads.

    Guarantees:
    1. Intercepts immediately before provider dispatch.
    2. Records only sanitized payloads; never raw environment keys or authorization headers.
    3. Separates prepared, dispatched, and completed/failed transmission states.
    4. Computes deterministic SHA-256 payload hash and redaction categorizations.
    5. Fails closed (status="blocked_by_policy") if safety verification fails.
    6. Correlates retries using stable event_id and incident_id with attempt sequence numbering.
    7. Accurate capture boundary description ("provider_adapter_input").
    """

    def __init__(
        self,
        db: Database,
        project_id: str,
        incident_id: Optional[str] = None,
        event_id: Optional[str] = None,
        diagnosis_id: Optional[str] = None,
        underlying_client: Optional[LLMClient] = None,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.incident_id = incident_id
        self.event_id = event_id
        self.diagnosis_id = diagnosis_id
        self.underlying_client = underlying_client

    def _resolve_client_and_metadata(self) -> Tuple[LLMClient, str, str]:
        """Resolve active client instance, provider name, and model identifier."""
        if self.underlying_client is not None:
            prov = getattr(self.underlying_client, "provider_name", "custom")
            mod = getattr(self.underlying_client, "model", "custom-model")
            if isinstance(self.underlying_client, GroqLLMClient):
                prov = "groq"
                mod = getattr(self.underlying_client, "model", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
            elif isinstance(self.underlying_client, MockLLMClient):
                prov = "mock"
                mod = getattr(self.underlying_client, "model", "mock-diagnostic-v1")
            return self.underlying_client, prov, mod

        if os.getenv("GROQ_API_KEY") and not (
            os.getenv("DEV_MEMORY_DISABLE_EXTERNAL_AI", "").lower() in ("1", "true", "yes")
            or os.getenv("DEVMEMORY_OFFLINE_MODE", "").lower() in ("1", "true", "yes")
            or os.getenv("AI_PRIVACY_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")
        ):
            client = GroqLLMClient()
            return client, "groq", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        client = MockLLMClient()
        return client, "mock", "mock-diagnostic-v1"

    def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
        """Audit and submit diagnosis prompts to provider with strict lifecycle tracking."""
        client, provider, model = self._resolve_client_and_metadata()

        # Step 1: Pre-flight safety check on incoming prompts
        is_safe, violation_reason = validate_outbound_safety(system_prompt, user_prompt)

        # Step 2: Prepare sanitized representation for storage and transmission
        # Even if unsafe, scrub detected secrets so raw credentials never enter MongoDB
        if not is_safe:
            db_sys = scrub_unredacted_credentials(redact_secrets(engine_redact_secrets(system_prompt)))
            db_user = scrub_unredacted_credentials(redact_secrets(engine_redact_secrets(user_prompt)))
        else:
            db_sys = redact_secrets(engine_redact_secrets(system_prompt))
            db_user = redact_secrets(engine_redact_secrets(user_prompt))

        combined_text = f"{db_sys}\n{db_user}"
        redaction_summary = analyze_redactions(combined_text)

        messages = [
            {"role": "system", "content": db_sys},
            {"role": "user", "content": db_user},
        ]
        sanitized_payload = SanitizedPromptPayload(
            system_prompt=db_sys,
            user_prompt=db_user,
            messages=messages,
        )
        payload_hash = compute_payload_hash(sanitized_payload.model_dump())

        # Step 3: Correlate attempt index
        attempt = 1
        if self.incident_id:
            try:
                attempt = self.db.llm_request_audits.count_documents({"incident_id": self.incident_id}) + 1
            except Exception:
                attempt = 1

        audit_id = f"audit_{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc)

        # Step 4: Handle policy block (Fail Closed without external transmission)
        if not is_safe:
            block_msg = f"Security verification blocked outbound transmission: {violation_reason}"
            logger.warning(
                "Audit %s: Outbound payload blocked by policy (%s). Failing closed without provider dispatch.",
                audit_id,
                violation_reason,
            )
            blocked_doc: Dict[str, Any] = {
                "audit_id": audit_id,
                "project_id": self.project_id,
                "event_id": self.event_id,
                "incident_id": self.incident_id,
                "diagnosis_id": self.diagnosis_id,
                "attempt": attempt,
                "provider": provider,
                "model": model,
                "transmission_status": "blocked_by_policy",
                "sanitized_payload": sanitized_payload.model_dump(),
                "redaction_summary": redaction_summary.model_dump(),
                "payload_hash": payload_hash,
                "capture_boundary": "provider_adapter_input",
                "created_at": created_at,
                "dispatched_at": None,
                "completed_at": created_at,
                "duration_ms": 0.0,
                "error_message": block_msg,
            }
            try:
                self.db.llm_request_audits.insert_one(blocked_doc)
            except Exception as exc:
                logger.error("Failed to insert blocked LLM audit record: %s", exc)

            raise PayloadSecurityPolicyViolation(block_msg)

        # Step 6: Safe payload - persist PREPARED record
        audit_doc: Dict[str, Any] = {
            "audit_id": audit_id,
            "project_id": self.project_id,
            "event_id": self.event_id,
            "incident_id": self.incident_id,
            "diagnosis_id": self.diagnosis_id,
            "attempt": attempt,
            "provider": provider,
            "model": model,
            "transmission_status": "prepared",
            "sanitized_payload": sanitized_payload.model_dump(),
            "redaction_summary": redaction_summary.model_dump(),
            "payload_hash": payload_hash,
            "capture_boundary": "provider_adapter_input",
            "created_at": created_at,
            "dispatched_at": None,
            "completed_at": None,
            "duration_ms": None,
            "error_message": None,
        }

        try:
            self.db.llm_request_audits.insert_one(audit_doc)
        except Exception as exc:
            logger.error("Failed to insert prepared LLM audit record: %s", exc)

        # Step 7: Mark DISPATCHED
        dispatched_at = datetime.now(timezone.utc)
        try:
            self.db.llm_request_audits.update_one(
                {"audit_id": audit_id},
                {
                    "$set": {
                        "transmission_status": "dispatched",
                        "dispatched_at": dispatched_at,
                    }
                },
            )
        except Exception as exc:
            logger.error("Failed to update dispatched audit record: %s", exc)

        # Step 7: Dispatch to Provider Adapter
        start_time = time.perf_counter()
        try:
            response_json = client.generate_diagnosis(db_sys, db_user)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            completed_at = datetime.now(timezone.utc)

            # Step 8a: Mark COMPLETED
            try:
                self.db.llm_request_audits.update_one(
                    {"audit_id": audit_id},
                    {
                        "$set": {
                            "transmission_status": "completed",
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                        }
                    },
                )
            except Exception as exc:
                logger.error("Failed to update completed audit record: %s", exc)

            return response_json

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            completed_at = datetime.now(timezone.utc)
            # Never record raw provider credentials or sensitive headers in error message
            sanitized_err = scrub_unredacted_credentials(redact_secrets(engine_redact_secrets(str(exc))))

            # Step 8b: Mark FAILED
            try:
                self.db.llm_request_audits.update_one(
                    {"audit_id": audit_id},
                    {
                        "$set": {
                            "transmission_status": "failed",
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                            "error_message": sanitized_err[:1000],
                        }
                    },
                )
            except Exception as audit_exc:
                logger.error("Failed to update failed audit record: %s", audit_exc)

            raise


def get_audited_llm_client(
    db: Database,
    project_id: str,
    incident_id: Optional[str] = None,
    event_id: Optional[str] = None,
    diagnosis_id: Optional[str] = None,
    underlying_client: Optional[LLMClient] = None,
) -> AuditedLLMClient:
    """Factory creating an AuditedLLMClient configured for the active incident context."""
    return AuditedLLMClient(
        db=db,
        project_id=project_id,
        incident_id=incident_id,
        event_id=event_id,
        diagnosis_id=diagnosis_id,
        underlying_client=underlying_client,
    )


# ==============================================================================
# Audit Retrieval & Security Evidence Reporting Services
# ==============================================================================

def list_audits_for_project(
    db: Database,
    project_id: str,
    provider: Optional[str] = None,
    transmission_status: Optional[str] = None,
    incident_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[LLMRequestAuditItem], int]:
    """Retrieve paginated audit records strictly authorized to the requesting project.

    Guarantees:
    - Never returns another project's private audit records.
    - Filters by provider, transmission_status, incident_id, and date ranges.
    - Returns total count and validated items.
    """
    filter_q: Dict[str, Any] = {"project_id": project_id}

    if provider:
        filter_q["provider"] = provider.lower().strip()
    if transmission_status:
        filter_q["transmission_status"] = transmission_status.lower().strip()
    if incident_id:
        filter_q["incident_id"] = incident_id.strip()

    date_filter: Dict[str, Any] = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date
    if date_filter:
        filter_q["created_at"] = date_filter

    total = db.llm_request_audits.count_documents(filter_q)
    cursor = (
        db.llm_request_audits.find(filter_q, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    items = [LLMRequestAuditItem.model_validate(doc) for doc in cursor]
    return items, total


def get_audit_by_id(
    db: Database,
    project_id: str,
    audit_id: str,
) -> Optional[LLMRequestAuditItem]:
    """Retrieve a single audit record strictly verifying project-level ownership."""
    doc = db.llm_request_audits.find_one(
        {"audit_id": audit_id, "project_id": project_id},
        {"_id": 0},
    )
    if not doc:
        return None
    return LLMRequestAuditItem.model_validate(doc)


def get_project_security_summary(
    db: Database,
    project_id: str,
) -> LLMSecuritySummary:
    """Compute aggregated security evidence statistics for the frontend security-monitor panel.

    Guarantees:
    - Strictly computed from real persisted records in llm_request_audits.
    - No hardcoded numbers or fictitious badges.
    """
    cursor = db.llm_request_audits.find({"project_id": project_id}, {"_id": 0})

    total_requests = 0
    status_counts: Dict[str, int] = {
        "prepared": 0,
        "dispatched": 0,
        "completed": 0,
        "failed": 0,
        "blocked_by_policy": 0,
    }
    total_redactions = 0
    categories: Dict[str, int] = {}
    providers = set()
    latest_at: Optional[datetime] = None

    for doc in cursor:
        total_requests += 1
        stat = doc.get("transmission_status", "unknown")
        status_counts[stat] = status_counts.get(stat, 0) + 1

        prov = doc.get("provider")
        if prov:
            providers.add(prov)

        created = doc.get("created_at")
        if created:
            if latest_at is None or created > latest_at:
                latest_at = created

        red_sum = doc.get("redaction_summary", {})
        total_redactions += red_sum.get("total_redactions", 0)
        for cat, cnt in red_sum.get("categories", {}).items():
            categories[cat] = categories.get(cat, 0) + cnt

    return LLMSecuritySummary(
        project_id=project_id,
        total_requests=total_requests,
        status_counts=status_counts,
        total_redactions_applied=total_redactions,
        redaction_categories=categories,
        providers_used=sorted(list(providers)),
        latest_transmission_at=latest_at,
    )
