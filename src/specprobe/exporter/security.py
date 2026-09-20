"""Security scheme resolution, parameterization, and formatting for test export.

Adheres strictly to SpecProbe Constitution Principle II: zero-LLM, fully deterministic
resolution of OpenAPI security schemes into Postman collection variables and REST Client
file variables.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "ResolvedCredential",
    "SecurityResolver",
    "format_postman_security_desc",
    "format_security_comment",
    "sanitize_variable_name",
]

# Priority tiers per FR-005:
# Tier 1: HTTP Bearer / OAuth2
# Tier 2: API Key in header
# Tier 3: API Key in query
# Tier 4: HTTP Basic
# Tier 5: Unresolved fallback
_PRIORITY_BEARER_OAUTH = 1
_PRIORITY_APIKEY_HEADER = 2
_PRIORITY_APIKEY_QUERY = 3
_PRIORITY_BASIC = 4
_PRIORITY_FALLBACK = 5


def sanitize_variable_name(name: str) -> str:
    """Sanitize an OpenAPI security scheme name into a valid variable identifier.

    Replaces non-alphanumeric/underscore characters with underscores and prefixes
    with an underscore if the identifier begins with a digit.
    """
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_")
    if not clean:
        return "auth_credential"
    if clean[0].isdigit():
        clean = f"_{clean}"
    return clean


@dataclass(frozen=True)
class ResolvedCredential:
    """Resolved credential binding for test case export."""

    scheme_name: str
    variable_name: str
    transport: Literal["header", "query"]
    target_name: str
    wire_value_template: str
    default_placeholder: str
    is_optional: bool = False
    scopes: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)


def format_security_comment(cred: ResolvedCredential) -> list[str]:
    """Format documentation comment lines for REST Client (.http) export."""
    lines: list[str] = []
    opt_suffix = " (optional)" if cred.is_optional else ""
    lines.append(f"# Security: {cred.scheme_name}{opt_suffix}")

    if cred.alternatives:
        alts_str = ", ".join(cred.alternatives)
        lines.append(f"# Alternatives: {alts_str}")

    if cred.scopes:
        scopes_str = ", ".join(cred.scopes)
        lines.append(f"# Scopes: {scopes_str}")

    return lines


def format_postman_security_desc(cred: ResolvedCredential) -> str:
    """Format security documentation lines for Postman request descriptions."""
    parts: list[str] = []
    opt_suffix = " (optional)" if cred.is_optional else ""
    parts.append(f"Security: {cred.scheme_name}{opt_suffix}")

    if cred.alternatives:
        parts.append(f"Alternatives: {', '.join(cred.alternatives)}")

    if cred.scopes:
        parts.append(f"Scopes: {', '.join(cred.scopes)}")

    return "\n".join(parts)


class SecurityResolver:
    """Deterministic resolver for OpenAPI security requirements and scheme definitions."""

    @staticmethod
    def _get_scheme_priority_and_details(
        scheme_name: str,
        security_schemes: dict[str, Any],
    ) -> tuple[int, Literal["header", "query"], str, str, str]:
        """Determine priority rank, transport, target name, template, and default placeholder.

        Returns (priority_score, transport, target_name, wire_value_template, default_placeholder).
        """
        var_name = sanitize_variable_name(scheme_name)
        def_obj = security_schemes.get(scheme_name)

        if isinstance(def_obj, dict):
            raw_type = str(def_obj.get("type", "")).lower()
            scheme = str(def_obj.get("scheme", "")).lower()

            if raw_type == "http":
                if scheme == "bearer":
                    return (
                        _PRIORITY_BEARER_OAUTH,
                        "header",
                        "Authorization",
                        f"Bearer {{{{{var_name}}}}}",
                        "<token>",
                    )
                if scheme == "basic":
                    return (
                        _PRIORITY_BASIC,
                        "header",
                        "Authorization",
                        f"Basic {{{{{var_name}}}}}",
                        "<credentials>",
                    )
                # Fallback for other HTTP schemes
                return (
                    _PRIORITY_BEARER_OAUTH,
                    "header",
                    "Authorization",
                    f"Bearer {{{{{var_name}}}}}",
                    "<token>",
                )

            if raw_type in ("oauth2", "openidconnect"):
                return (
                    _PRIORITY_BEARER_OAUTH,
                    "header",
                    "Authorization",
                    f"Bearer {{{{{var_name}}}}}",
                    "<token>",
                )

            if raw_type == "apikey":
                in_loc = str(def_obj.get("in", "header")).lower()
                param_name = str(def_obj.get("name") or scheme_name)
                if in_loc == "query":
                    return (
                        _PRIORITY_APIKEY_QUERY,
                        "query",
                        param_name,
                        f"{{{{{var_name}}}}}",
                        "<api_key>",
                    )
                # Header or cookie default
                return (
                    _PRIORITY_APIKEY_HEADER,
                    "header",
                    param_name,
                    f"{{{{{var_name}}}}}",
                    "<api_key>",
                )

        # FR-011 Deterministic Substring Heuristics when definition is missing
        s_lower = scheme_name.lower()
        if "bearer" in s_lower or "jwt" in s_lower:
            return (
                _PRIORITY_BEARER_OAUTH,
                "header",
                "Authorization",
                f"Bearer {{{{{var_name}}}}}",
                "<token>",
            )
        if "basic" in s_lower:
            return (
                _PRIORITY_BASIC,
                "header",
                "Authorization",
                f"Basic {{{{{var_name}}}}}",
                "<credentials>",
            )
        if "oauth" in s_lower:
            return (
                _PRIORITY_BEARER_OAUTH,
                "header",
                "Authorization",
                f"Bearer {{{{{var_name}}}}}",
                "<token>",
            )

        # Default fallback is an API key header with the scheme name
        return (
            _PRIORITY_FALLBACK,
            "header",
            scheme_name,
            f"{{{{{var_name}}}}}",
            "<api_key>",
        )

    @classmethod
    def resolve_credentials(
        cls,
        security_requirements: list[dict[str, list[str]]],
        security_schemes: dict[str, Any] | None = None,
    ) -> list[ResolvedCredential]:
        """Resolve security requirements into concrete ResolvedCredential instances.

        Parameters
        ----------
        security_requirements : list[dict[str, list[str]]]
            OpenAPI operation security requirement objects (representing alternatives).
        security_schemes : dict[str, Any] | None
            OpenAPI components.securitySchemes mapping, if available.

        Returns
        -------
        list[ResolvedCredential]
            Ordered list of resolved credentials to apply to the exported request.
        """
        if not security_requirements:
            return []

        schemes_lookup = security_schemes or {}

        # Check for optional security: an empty dict {} in the requirements list
        is_optional = any(len(req) == 0 for req in security_requirements)

        # Filter out empty dicts to evaluate active requirements
        active_reqs = [req for req in security_requirements if len(req) > 0]
        if not active_reqs:
            return []

        # Score each alternative requirement by the minimum priority score of its schemes
        scored_reqs: list[tuple[int, dict[str, list[str]]]] = []
        for req in active_reqs:
            min_score = min(
                cls._get_scheme_priority_and_details(s_name, schemes_lookup)[0]
                for s_name in req.keys()
            )
            scored_reqs.append((min_score, req))

        # Sort stably so the lowest priority score (highest precedence) comes first
        scored_reqs.sort(key=lambda item: item[0])
        best_req = scored_reqs[0][1]

        # Collect alternatives: all unique scheme names in other requirements not in best_req
        alternatives: list[str] = []
        for _, req in scored_reqs[1:]:
            for s_name in req.keys():
                if s_name not in best_req and s_name not in alternatives:
                    alternatives.append(s_name)

        # Build ResolvedCredential for each scheme in the winning requirement (compound support)
        resolved: list[ResolvedCredential] = []
        for s_name, s_scopes in sorted(best_req.items()):
            _, transport, target_name, wire_template, placeholder = (
                cls._get_scheme_priority_and_details(s_name, schemes_lookup)
            )
            var_name = sanitize_variable_name(s_name)

            resolved.append(
                ResolvedCredential(
                    scheme_name=s_name,
                    variable_name=var_name,
                    transport=transport,
                    target_name=target_name,
                    wire_value_template=wire_template,
                    default_placeholder=placeholder,
                    is_optional=is_optional,
                    scopes=list(s_scopes) if s_scopes else [],
                    alternatives=list(alternatives),
                )
            )

        return resolved
