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

        # Extract event_id from user prompt if present
        event_id = "evt_mock_001"
        match = re.search(r'Event ID:\s*([^\s\n]+)', user_prompt)
        if match:
            event_id = match.group(1).strip()

        mock_payload = {
            "event_id": event_id,
            "summary": "Mock diagnostic summary: Encountered unexpected execution failure.",
            "likely_cause": "The error was triggered by an unresolved symbol or invalid runtime state.",
            "evidence": [
                "Command exited with non-zero exit code",
                "Error message captured in diagnostic execution",
            ],
            "hypotheses": [
                "Dependency or configuration mismatch",
                "Transient network or socket binding condition",
            ],
            "recommended_steps": [
                "Verify dependencies and virtual environment configuration",
                "Inspect recent diffs in the affected module",
                "Re-run command in isolated test mode",
            ],
            "uncertainty_description": "Diagnosis synthesized by mock provider without live LLM inference.",
            "confidence": 0.85,
            "verification_steps": [
                "Re-execute command with debugging flags enabled",
            ],
            "fix_status": "unverified",
        }
        return json.dumps(mock_payload)
