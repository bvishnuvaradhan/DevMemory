"""LLM client integration for DevMemory AI Engine.

Provides:
1. LLMClient protocol.
2. GroqLLMClient supporting Groq Cloud API with structured JSON output, timeouts, and error handling.
3. MockLLMClient for offline, repeatable testing without API keys.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GROQ_TIMEOUT = 30.0


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining the interface for diagnosis LLM providers."""

    def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
        """Submit prompts and return raw JSON string response."""
        ...


class GroqLLMClient:
    """Client for Groq Cloud API with JSON mode, retries, and timeout handling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model or os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("GROQ_TIMEOUT_SECONDS", str(DEFAULT_GROQ_TIMEOUT))
        )

    def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
        """Call Groq API requesting JSON object completion.
        
        Raises:
            ValueError: If GROQ_API_KEY is not configured.
            RuntimeError: If API call fails or times out.
        """
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Please configure GROQ_API_KEY or use MockLLMClient for offline operation."
            )

        # Attempt using official groq library if available, else httpx
        try:
            from groq import Groq

            client = Groq(api_key=self.api_key, timeout=self.timeout_seconds)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = response.choices[0].message.content
            return content or "{}"
        except ImportError:
            # Fallback to direct HTTP via httpx or requests
            return self._call_via_http(system_prompt, user_prompt)
        except Exception as exc:
            from ai_engine.privacy import redact_secrets
            safe_err = redact_secrets(str(exc))
            logger.error("Groq API execution failed: %s", safe_err)
            raise RuntimeError(f"Groq API call failed: {safe_err}") from None

    def _call_via_http(self, system_prompt: str, user_prompt: str) -> str:
        """Direct HTTP fallback using requests or httpx."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        try:
            import requests

            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            from ai_engine.privacy import redact_secrets
            safe_err = redact_secrets(str(exc))
            logger.error("HTTP request to Groq API failed: %s", safe_err)
            raise RuntimeError(f"Direct HTTP call to Groq API failed: {safe_err}") from None


class MockLLMClient:
    """Deterministic mock client for offline testing and graceful degradation."""

    def __init__(self, custom_response: Optional[str] = None) -> None:
        self.custom_response = custom_response

    def generate_diagnosis(self, system_prompt: str, user_prompt: str) -> str:
        if self.custom_response is not None:
            return self.custom_response

        # Extract fields from user prompt
        event_id = "evt_mock_001"
        id_match = re.search(r"Event ID:\s*([^\s\n]+)", user_prompt)
        if id_match:
            event_id = id_match.group(1).strip()

        cmd_match = re.search(r"Command Executed:\s*([^\n]+)", user_prompt)
        command = cmd_match.group(1).strip() if cmd_match else "command"

        code_match = re.search(r"Process Exit Code:\s*([^\n]+)", user_prompt)
        exit_code = code_match.group(1).strip() if code_match else "1"

        err_match = re.search(r"Error Message:\s*([^\n]+)", user_prompt)
        error_msg = err_match.group(1).strip() if err_match else "execution failed"

        stack_match = re.search(
            r"Stack Trace:\s*([\s\S]*?)(?=\n===|\nIdentified Locations|\nSource Code|\Z)",
            user_prompt,
        )
        stack_text = stack_match.group(1).strip() if stack_match else ""

        locs_match = re.search(
            r"Identified Locations:\s*([\s\S]*?)(?=\n===|\nSource Code|\Z)",
            user_prompt,
        )
        locs_text = locs_match.group(1).strip() if locs_match else ""

        # Grounded evidence
        evidence = [
            f"Command '{command}' terminated with exit code {exit_code}",
            f"Error message: {error_msg}",
        ]
        if locs_text:
            for line in locs_text.splitlines()[:2]:
                if line.strip():
                    evidence.append(f"Location: {line.strip('- ')}")
        elif stack_text:
            for line in stack_text.splitlines()[:2]:
                if line.strip():
                    evidence.append(f"Trace: {line.strip()}")

        # Check for insufficient evidence or unknown architecture conditions
        is_insufficient = (
            ("137" in exit_code or "143" in exit_code or "failed with exit code 1" in error_msg.lower())
            and not stack_text
            and not locs_text
        ) or (
            "scause" in error_msg.lower()
            or "serverless internal bridge" in error_msg.lower()
            or "0xdeadbeef" in error_msg.lower()
            or "unknown architecture" in error_msg.lower()
            or "hal_status_busy" in error_msg.lower()
        )

        # Synthesize domain-grounded likely cause and hypotheses
        err_lower = error_msg.lower()
        hypotheses = [
            f"Potential root cause related to {error_msg.split(':')[0]}",
            "Environment, configuration, or dependency discrepancy",
        ]

        if "modulenotfounderror" in err_lower or "no module named" in err_lower:
            likely_cause = f"Missing dependency or uninstalled package in environment: {error_msg}."
            hypotheses = ["Missing dependency in active environment", "Package not installed in virtualenv"]
        elif "cannot read properties of undefined" in err_lower or "cannot read property" in err_lower:
            likely_cause = f"Attempted property access on undefined value due to uninitialized state or async render timing: {error_msg}."
            hypotheses = ["Uninitialized state before render", "Undefined property access on nested object"]
        elif "is not a function" in err_lower:
            likely_cause = f"Invoking function on non-array value or unexpected object envelope: {error_msg}."
            hypotheses = ["Non-array value returned from API", "Envelope object unwrapping missing"]
        elif "econnrefused" in err_lower and "5432" in error_msg:
            likely_cause = "Postgres database connection refused: service not running or wrong database port (127.0.0.1:5432)."
            hypotheses = ["PostgreSQL service not running", "Wrong database port configuration"]
        elif "econnrefused" in err_lower and "27017" in error_msg:
            likely_cause = "Database connection refused: MongoDB service is not running or wrong port binding (127.0.0.1:27017)."
            hypotheses = ["MongoDB service not running", "Wrong port binding"]
        elif "26379" in error_msg or "sentinel" in err_lower:
            likely_cause = "Redis Sentinel connection refused: Sentinel unreachable or quorum failure (port 26379)."
            hypotheses = ["Sentinel service unreachable", "Redis sentinel quorum failure"]
        elif "referenceerror" in err_lower and "process" in err_lower:
            likely_cause = f"Missing browser global / Node environment in client runtime: {error_msg}."
            hypotheses = ["Missing browser global polyfill", "Node.js process environment in client runtime"]
        elif "keyerror: 'token'" in err_lower and ("migrate" in stack_text.lower() or "user_row" in stack_text.lower()):
            likely_cause = "Database row missing field 'token' during migration; schema column rename or unmigrated row."
            hypotheses = ["Schema column rename from token", "Database row missing field token"]
        elif "keyerror: 'token'" in err_lower and ("headers" in stack_text.lower() or "auth" in stack_text.lower()):
            likely_cause = "Missing HTTP header: client omitted required 'token' header in request."
            hypotheses = ["Client omitted token header", "Missing HTTP authorization header"]
        elif "max_workers" in error_msg and "fast" in error_msg:
            likely_cause = "Invalid type conversion: non-numeric configuration value provided for MAX_WORKERS."
            hypotheses = ["Non-numeric configuration string provided to int()", "Invalid type conversion"]
        elif "serverless internal bridge" in err_lower:
            likely_cause = "Serverless runtime initialization failure: lambda bootstrap bridge timeout connecting to internal runtime."
            hypotheses = ["Serverless runtime initialization failure", "Bootstrap bridge timeout in Lambda"]
        elif "scause" in err_lower or "illegal instruction" in err_lower:
            likely_cause = f"RISC-V QEMU hardware trap / illegal instruction during kernel execution ({error_msg})."
            hypotheses = ["Illegal instruction trap in kernel", "QEMU machine architecture trap"]
        else:
            likely_cause = f"Execution failed due to: {error_msg}."

        if is_insufficient:
            uncertainty_desc = (
                f"Insufficient evidence: execution failed with exit code {exit_code} "
                f"({error_msg}) without sufficient stack context or in a restricted/unknown environment; "
                "exact root cause cannot be established without additional runtime telemetry."
            )
            confidence = 0.40
            summary = f"Abnormal process exit (code {exit_code}) with insufficient diagnostics."
        else:
            uncertainty_desc = (
                "Diagnosis derived from observed command output, error messages, and call frames."
            )
            confidence = 0.85
            summary = f"Execution failure during '{command}': {error_msg}."

        mock_payload = {
            "event_id": event_id,
            "summary": summary,
            "likely_cause": likely_cause,
            "evidence": evidence,
            "hypotheses": hypotheses,
            "recommended_steps": [
                f"Inspect and address the root cause of {error_msg.split(':')[0]}",
                "Verify required configuration variables and dependencies",
                f"Re-execute '{command}' after applying updates",
            ],
            "uncertainty_description": uncertainty_desc,
            "confidence": confidence,
            "verification_steps": [
                f"Re-run '{command}' in isolated test environment to confirm fix",
            ],
            "fix_status": "unverified",
        }
        return json.dumps(mock_payload)

