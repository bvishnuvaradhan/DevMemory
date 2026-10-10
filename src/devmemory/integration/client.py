from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from devmemory.integration.models import (
    BackendDiagnosisResponse,
    IncidentPayload,
    SimilarIncidentMatch,
)

DEFAULT_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_BACKOFF_SECONDS = 0.2
INGEST_ENDPOINT_PATH = "/api/runs/ingest"


@dataclass
class IngestionResult:
    """Result of attempting to submit an incident payload to the backend."""
    success: bool
    is_offline: bool
    status_code: Optional[int] = None
    diagnosis: Optional[BackendDiagnosisResponse] = None
    error_message: Optional[str] = None
    attempts: int = 1


class DevMemoryClient:
    """
    Lightweight, dependency-free HTTP integration client with retry policy,
    bounded timeouts, and graceful offline fallback.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        endpoint_path: str = INGEST_ENDPOINT_PATH,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    @property
    def ingest_url(self) -> str:
        return f"{self.base_url}{self.endpoint_path}"

    def submit_incident(self, payload: IncidentPayload) -> IngestionResult:
        """
        Submit incident payload to the backend with bounded retries for transient errors.
        Never crashes; returns typed IngestionResult.
        """
        payload_data = payload.to_dict()
        req_body = json.dumps(payload_data).encode("utf-8")

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": f"DevMemory-CLI/{payload.client_version}",
            "X-Event-ID": payload.event_id,
            "X-Project-ID": payload.project_id,
        }

        last_err: Optional[str] = None
        status_code: Optional[int] = None
        is_offline = False

        for attempt in range(1, self.max_retries + 2):
            req = urllib.request.Request(
                url=self.ingest_url,
                data=req_body,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status_code = resp.getcode()
                    resp_bytes = resp.read()
                    resp_text = resp_bytes.decode("utf-8", errors="replace")

                    try:
                        resp_json = json.loads(resp_text)
                    except json.JSONDecodeError as exc:
                        return IngestionResult(
                            success=False,
                            is_offline=False,
                            status_code=status_code,
                            error_message=f"Backend returned non-JSON response: {exc}",
                            attempts=attempt,
                        )

                    diag = self._parse_diagnosis_response(payload.event_id, resp_json)
                    return IngestionResult(
                        success=True,
                        is_offline=False,
                        status_code=status_code,
                        diagnosis=diag,
                        attempts=attempt,
                    )

            except urllib.error.HTTPError as http_err:
                status_code = http_err.code
                last_err = f"HTTP {status_code}: {http_err.reason}"

                # Do not retry 4xx client errors (400, 401, 403, 404, 422)
                if 400 <= status_code < 500:
                    return IngestionResult(
                        success=False,
                        is_offline=False,
                        status_code=status_code,
                        error_message=f"Client request error: {last_err}",
                        attempts=attempt,
                    )

                # 5xx server errors can be retried
                if attempt <= self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue

            except (urllib.error.URLError, TimeoutError, OSError) as net_err:
                is_offline = True
                last_err = f"Connection failed: {net_err}"

                # Transient connection error retry
                if attempt <= self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)
                    continue

        return IngestionResult(
            success=False,
            is_offline=is_offline,
            status_code=status_code,
            error_message=last_err,
            attempts=self.max_retries + 1,
        )

    def _parse_diagnosis_response(
        self, event_id: str, data: Dict[str, Any]
    ) -> BackendDiagnosisResponse:
        """Parse backend JSON response into structured BackendDiagnosisResponse model."""
        status = data.get("status", "success")
        probable_cause = data.get("probable_cause") or data.get("cause")
        hypotheses = data.get("hypotheses", [])
        suggested_steps = data.get("suggested_steps") or data.get("suggested_actions") or []
        kb_match = data.get("knowledge_base_match")
        is_verified = bool(data.get("is_verified_fix", False))

        similar_list: list[SimilarIncidentMatch] = []
        raw_sim = data.get("similar_incidents") or data.get("historical_matches") or []
        if isinstance(raw_sim, list):
            for item in raw_sim:
                if isinstance(item, dict):
                    similar_list.append(
                        SimilarIncidentMatch(
                            incident_id=str(item.get("incident_id", "unknown")),
                            project_name=str(item.get("project_name", "cross-project")),
                            similarity_score=float(item.get("similarity_score", 0.0)),
                            summary=str(item.get("summary", "")),
                            verified_fix=item.get("verified_fix"),
                            is_cross_project=bool(item.get("is_cross_project", False)),
                        )
                    )

        return BackendDiagnosisResponse(
            status=status,
            event_id=event_id,
            probable_cause=probable_cause,
            hypotheses=hypotheses if isinstance(hypotheses, list) else [str(hypotheses)],
            suggested_steps=suggested_steps if isinstance(suggested_steps, list) else [str(suggested_steps)],
            similar_incidents=similar_list,
            knowledge_base_match=kb_match,
            is_verified_fix=is_verified,
            raw_response=data,
        )
