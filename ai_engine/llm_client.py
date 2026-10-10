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
            logger.error("Groq API execution failed: %s", exc)
            raise RuntimeError(f"Groq API call failed: {exc}") from exc

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
            logger.error("HTTP request to Groq API failed: %s", exc)
            raise RuntimeError(f"Direct HTTP call to Groq API failed: {exc}") from exc


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

        # Check for insufficient evidence conditions
        is_insufficient = (
            ("137" in exit_code or "143" in exit_code or "failed with exit code 1" in error_msg.lower())
            and not stack_text
            and not locs_text
        )

        if is_insufficient:
            uncertainty_desc = (
                f"Insufficient evidence: execution failed with exit code {exit_code} "
                "without stack trace or source context; exact root cause cannot be established."
            )
            confidence = 0.40
            likely_cause = f"Process terminated prematurely with code {exit_code} ({error_msg})."
            summary = f"Abnormal process exit (code {exit_code}) with insufficient diagnostics."
        else:
            uncertainty_desc = (
                "Diagnosis derived from observed command output, error messages, and call frames."
            )
            confidence = 0.85
            likely_cause = f"Execution failed due to: {error_msg}."
            summary = f"Execution failure during '{command}': {error_msg}."

        mock_payload = {
            "event_id": event_id,
            "summary": summary,
            "likely_cause": likely_cause,
            "evidence": evidence,
            "hypotheses": [
                f"Potential root cause related to {error_msg.split(':')[0]}",
                "Environment, configuration, or dependency discrepancy",
            ],
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

