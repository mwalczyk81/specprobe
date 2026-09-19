"""Unified LLM gateway routing calls through LiteLLM with local-first defaults."""

import ipaddress
import os
from typing import Any
from urllib.parse import urlparse

import litellm

DEFAULT_LOCAL_MODEL = "openai/local-model"
DEFAULT_LOCAL_API_BASE = "http://localhost:1234/v1"
DEFAULT_TEMPERATURE = 0.0

_TAILSCALE_CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


def is_local_endpoint(api_base: str | None) -> bool:
    """Return True if api_base points to a loopback, private LAN, dev host, or local domain."""
    if not api_base:
        return False

    parsed = urlparse(api_base)
    hostname = parsed.hostname
    if not hostname:
        parsed = urlparse(f"http://{api_base}")
        hostname = parsed.hostname

    if not hostname:
        return False

    hostname = hostname.lower().strip(".")

    # Known local and development hostnames
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname == "host.docker.internal"
        or hostname == "docker.for.win"
        or hostname == "docker.for.mac"
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
    ):
        return True

    # IP address analysis: loopback, RFC1918 private, link-local, unspecified, or Tailscale CGNAT
    try:
        ip = ipaddress.ip_address(hostname)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_unspecified
            or ip.is_link_local
            or (ip in _TAILSCALE_CGNAT_NET)
        )
    except ValueError:
        return False


class LLMGateway:
    """Unified LiteLLM client wrapper enforcing local-default privacy and opt-in cloud access."""

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
    ) -> None:
        resolved_model = model or os.environ.get("SPECPROBE_LLM_MODEL") or DEFAULT_LOCAL_MODEL
        resolved_api_base = (
            api_base or os.environ.get("SPECPROBE_LLM_API_BASE") or DEFAULT_LOCAL_API_BASE
        )
        resolved_temp = (
            temperature
            if temperature is not None
            else float(os.environ.get("SPECPROBE_LLM_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
        )

        self.model = resolved_model
        self.api_base = resolved_api_base
        self.temperature = resolved_temp
        self.api_key = api_key or os.environ.get("SPECPROBE_LLM_API_KEY")

        self._validate_cloud_opt_in()

    def _validate_cloud_opt_in(self) -> None:
        """Enforce SpecProbe Constitution Principle III & IV: cloud providers strictly opt-in."""
        # If targeting a local or private network endpoint, dummy key is sufficient
        if is_local_endpoint(self.api_base):
            if not self.api_key:
                self.api_key = "lm-studio"
            return

        # Remote/Cloud model requested: verify corresponding environment variable is present
        model_lower = self.model.lower()
        if model_lower.startswith("openai/") or model_lower.startswith("gpt-"):
            if not os.environ.get("OPENAI_API_KEY") and not self.api_key:
                raise ValueError(
                    f"Cloud model '{self.model}' requires OPENAI_API_KEY environment variable. "
                    "Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."
                )
        elif model_lower.startswith("anthropic/") or model_lower.startswith("claude-"):
            if not os.environ.get("ANTHROPIC_API_KEY") and not self.api_key:
                raise ValueError(
                    f"Cloud model '{self.model}' requires ANTHROPIC_API_KEY environment variable. "
                    "Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."
                )
        elif model_lower.startswith("gemini/"):
            if not os.environ.get("GEMINI_API_KEY") and not self.api_key:
                raise ValueError(
                    f"Cloud model '{self.model}' requires GEMINI_API_KEY environment variable. "
                    "Cloud providers are strictly opt-in per SpecProbe Constitution Principle IV."
                )

    def complete(
        self,
        messages: list[dict[str, str]],
        cache: Any | None = None,
    ) -> str:
        """Dispatch chat completion to LiteLLM, checking disk cache when provided.

        Parameters
        ----------
        messages : list[dict[str, str]]
            Chat conversation messages.
        cache : Any | None
            Optional DiskCache instance.

        Returns
        -------
        str
            Raw completion text returned by model or retrieved from cache.
        """
        if cache is not None:
            cached_completion = cache.get(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
            )
            if cached_completion is not None:
                return cached_completion

        try:
            response = litellm.completion(
                model=self.model,
                api_base=self.api_base,
                api_key=self.api_key,
                messages=messages,
                temperature=self.temperature,
            )
            content = response.choices[0].message.content or ""
        except Exception as exc:
            if is_local_endpoint(self.api_base):
                raise ConnectionError(
                    f"Failed to connect to local model endpoint at {self.api_base}. "
                    "Ensure LM Studio or your local model server is running and accessible: "
                    f"{exc}"
                ) from exc
            raise RuntimeError(
                f"LLM completion call failed for model '{self.model}': {exc}"
            ) from exc

        if cache is not None and content:
            cache.set(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                completion_text=content,
                api_base=self.api_base,
            )

        return content
