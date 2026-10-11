from __future__ import annotations

import json
import os
import re
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
DEFAULT_DIAGNOSIS_TIMEOUT_SECONDS = float(os.getenv("DEVMEMORY_DIAGNOSIS_TIMEOUT", "30.0"))
DEFAULT_MAX_RETRIES = 1
DEFAULT_BACKOFF_SECONDS = 0.2
RUNS_ENDPOINT_PATH = "/api/v1/runs"
PROJECTS_ENDPOINT_PATH = "/api/v1/projects"
INCIDENTS_ENDPOINT_PATH = "/api/v1/incidents"


@dataclass
class ProjectRegistrationResult:
    """Result of attempting to register a project on the backend."""
    success: bool
    is_offline: bool
    status_code: Optional[int] = None
    project_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class IngestionResult:
    """Result of attempting to submit a run event to the backend."""
    success: bool
    is_offline: bool
    status_code: Optional[int] = None
    incident_id: Optional[str] = None
    diagnosis: Optional[BackendDiagnosisResponse] = None
    error_message: Optional[str] = None
    attempts: int = 1


class DevMemoryClient:
    """
    Lightweight, dependency-free HTTP integration client with retry policy,
    bounded timeouts, and graceful offline fallback, communicating with Member 2's FastAPI backend.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        diagnosis_timeout: float = DEFAULT_DIAGNOSIS_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.diagnosis_timeout = diagnosis_timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    @property
    def runs_url(self) -> str:
        return f"{self.base_url}{RUNS_ENDPOINT_PATH}"

    @property
    def projects_url(self) -> str:
        return f"{self.base_url}{PROJECTS_ENDPOINT_PATH}"

    def register_project(
        self,
        project_id: str,
        name: str,
        language: Optional[str] = None,
    ) -> ProjectRegistrationResult:
        """
        Register a project at POST /api/v1/projects.
        If the project already exists (409 Conflict), treats it as successfully registered.
        """
        payload = {
            "project_id": project_id,
            "name": name,
            "language": language or "unknown",
            "settings": {},
        }
        req_body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "DevMemory-CLI/1.0.0",
        }

        req = urllib.request.Request(
            url=self.projects_url,
            data=req_body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                code = resp.getcode()
                return ProjectRegistrationResult(
                    success=True,
                    is_offline=False,
                    status_code=code,
                    project_id=project_id,
                )
        except urllib.error.HTTPError as http_err:
            # 409 Conflict means project is already registered on backend - treat as success
            if http_err.code == 409:
                return ProjectRegistrationResult(
                    success=True,
                    is_offline=False,
                    status_code=409,
                    project_id=project_id,
                )
            return ProjectRegistrationResult(
                success=False,
                is_offline=False,
                status_code=http_err.code,
                error_message=f"HTTP {http_err.code}: {http_err.reason}",
            )
        except (urllib.error.URLError, TimeoutError, OSError) as net_err:
            return ProjectRegistrationResult(
                success=False,
                is_offline=True,
                error_message=f"Connection failed: {net_err}",
            )

    def submit_incident(self, payload: IncidentPayload) -> IngestionResult:
        """
        Submit a command execution run to POST /api/v1/runs.
        Extracts incident_id if created and optionally fetches incident history.
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
                url=self.runs_url,
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

                    # Extract RunResponse from ResponseEnvelope
                    data_obj = resp_json.get("data") or {}
                    incident_id = data_obj.get("incident_id")

                    diag = None
                    if incident_id:
                        # Attempt active AI diagnosis first
                        diag = self.diagnose_incident(incident_id, payload.event_id)
                        # Enrich memory matches if diagnosis was unavailable
                        if diag and diag.status == "unavailable" and not diag.similar_incidents:
                            hist = self._fetch_incident_history(incident_id, payload.event_id)
                            if hist and hist.similar_incidents:
                                diag.similar_incidents = hist.similar_incidents

                    return IngestionResult(
                        success=True,
                        is_offline=False,
                        status_code=status_code,
                        incident_id=incident_id,
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

    def _fetch_incident_history(
        self, incident_id: str, event_id: str
    ) -> Optional[BackendDiagnosisResponse]:
        """Fetch historical incident and cross-project matches from GET /api/v1/incidents/{incident_id}/history."""
        url = f"{self.base_url}{INCIDENTS_ENDPOINT_PATH}/{incident_id}/history"
        headers = {
            "Accept": "application/json",
            "User-Agent": "DevMemory-CLI/1.0.0",
        }
        req = urllib.request.Request(url=url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8", errors="replace"))
                data = resp_data.get("data") or {}

                similar_matches: list[SimilarIncidentMatch] = []
                # Same-project matches
                for item in data.get("same_project_matches") or []:
                    similar_matches.append(
                        SimilarIncidentMatch(
                            incident_id=str(item.get("incident_id", "unknown")),
                            project_name="Current Project",
                            similarity_score=1.0,
                            summary=str(item.get("error_message") or item.get("error_type") or ""),
                            is_cross_project=False,
                        )
                    )
                # Cross-project matches
                for item in data.get("cross_project_matches") or []:
                    similar_matches.append(
                        SimilarIncidentMatch(
                            incident_id=str(item.get("incident_id", "unknown")),
                            project_name=str(item.get("project_id", "cross-project")),
                            similarity_score=0.9,
                            summary=str(item.get("error_message") or item.get("error_type") or ""),
                            is_cross_project=True,
                        )
                    )

                return BackendDiagnosisResponse(
                    status="success",
                    event_id=event_id,
                    incident_id=incident_id,
                    similar_incidents=similar_matches,
                    raw_response=data,
                )
        except Exception:
            # History fetch is optional enhancement; return None if unavailable
            return None

    def diagnose_incident(
        self,
        incident_id: str,
        event_id: str,
        allow_cross_project: bool = True,
        force_recheck: bool = False,
        fresh_analysis: bool = False,
    ) -> Optional[BackendDiagnosisResponse]:
        """Trigger AI diagnosis for an incident via POST /api/v1/incidents/{incident_id}/diagnose."""
        url = (
            f"{self.base_url}{INCIDENTS_ENDPOINT_PATH}/{incident_id}/diagnose"
            f"?allow_cross_project={'true' if allow_cross_project else 'false'}"
            f"&force_recheck={'true' if force_recheck else 'false'}"
            f"&fresh_analysis={'true' if fresh_analysis else 'false'}"
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DevMemory-CLI/1.0.0",
        }
        req = urllib.request.Request(url=url, headers=headers, method="POST", data=b"{}")

        try:
            with urllib.request.urlopen(req, timeout=self.diagnosis_timeout) as resp:
                resp_bytes = resp.read()
                resp_text = resp_bytes.decode("utf-8", errors="replace")
                resp_data = json.loads(resp_text)
                data = resp_data.get("data") or {}

                hypotheses_raw = data.get("hypotheses") or []
                hypotheses_list = [
                    h.get("cause") if isinstance(h, dict) else str(h)
                    for h in hypotheses_raw
                ]

                similar_matches: list[SimilarIncidentMatch] = []
                for m in data.get("matched_memory") or []:
                    similar_matches.append(
                        SimilarIncidentMatch(
                            incident_id=str(m.get("source_id", "unknown")),
                            project_name=str(m.get("source_type", "memory")),
                            similarity_score=1.0,
                            summary=str(m.get("relevance_reason") or ""),
                            is_cross_project=(m.get("source_type") == "cross_project"),
                        )
                    )

                # Format suggested steps: split on semicolons or newlines if joined
                suggested_steps: list[str] = []
                raw_fix = data.get("suggested_fix")
                if raw_fix:
                    split_steps = [s.strip() for s in re.split(r";\s*|\n+", raw_fix) if s.strip()]
                    suggested_steps = split_steps if split_steps else [raw_fix]

                source_val = data.get("source")
                is_reused = bool(data.get("idempotent"))
                is_fallback = bool(source_val and "fallback" in source_val.lower())
                status_str = "reused" if is_reused else ("fallback" if is_fallback else "success")
                probable_cause = data.get("likely_cause") or data.get("summary")

                return BackendDiagnosisResponse(
                    status=status_str,
                    event_id=event_id,
                    incident_id=incident_id,
                    probable_cause=probable_cause,
                    hypotheses=hypotheses_list,
                    suggested_steps=suggested_steps,
                    similar_incidents=similar_matches,
                    is_verified_fix=bool(data.get("is_verified_fix", False)),
                    source=source_val,
                    is_reused=is_reused,
                    is_fallback=is_fallback,
                    llm_skipped=data.get("llm_skipped"),
                    decision_reason=data.get("decision_reason"),
                    raw_response=data,
                )
        except urllib.error.HTTPError as http_err:
            status_code = http_err.code
            err_body = http_err.read().decode("utf-8", errors="replace") if hasattr(http_err, "read") else ""
            err_msg = f"HTTP {status_code}: {http_err.reason}"
            try:
                err_json = json.loads(err_body)
                if isinstance(err_json, dict) and "detail" in err_json:
                    err_msg = str(err_json["detail"])
            except Exception:
                pass
            return BackendDiagnosisResponse(
                status="unavailable",
                event_id=event_id,
                incident_id=incident_id,
                error_message=err_msg,
            )
        except (TimeoutError, urllib.error.URLError, OSError) as net_err:
            err_name = "Timeout" if isinstance(net_err, TimeoutError) or "timed out" in str(net_err).lower() else "Connection error"
            return BackendDiagnosisResponse(
                status="unavailable",
                event_id=event_id,
                incident_id=incident_id,
                error_message=f"{err_name}: {net_err}",
            )
        except Exception as exc:
            return BackendDiagnosisResponse(
                status="unavailable",
                event_id=event_id,
                incident_id=incident_id,
                error_message=f"Diagnosis error: {exc}",
            )
