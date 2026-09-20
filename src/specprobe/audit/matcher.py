"""Path template normalization and operation matching algorithms for test artifacts."""

import re

from specprobe.audit.models import ArtifactTestItem

__all__ = [
    "match_operation",
    "match_path",
    "normalize_path",
]


def _clean_url_prefix(raw_path: str) -> str:
    """Strip protocol, host, and baseUrl variables from a path string."""
    cleaned = raw_path.strip()
    # Strip protocol and host
    cleaned = re.sub(r"^https?://[^/]+", "", cleaned)
    # Strip variable placeholders at start like {{baseUrl}} or @baseUrl
    cleaned = re.sub(r"^{{[^}]+}}", "", cleaned)
    cleaned = re.sub(r"^@[^/]+", "", cleaned)
    # Strip query string
    if "?" in cleaned:
        cleaned = cleaned.split("?", 1)[0]
    # Ensure leading slash
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    # Strip trailing slash unless root
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned


def normalize_path(path: str) -> str:
    """Normalize path template by converting all parameter placeholders to '{}'.

    Examples
    --------
    - '/pets/{petId}' -> '/pets/{}'
    - '/pets/:petId' -> '/pets/{}'
    - '/pets/{{petId}}' -> '/pets/{}'
    - '{{baseUrl}}/pets/{{petId}}' -> '/pets/{}'
    - '/pets?limit=10' -> '/pets'
    """
    cleaned = _clean_url_prefix(path)
    if cleaned == "/":
        return "/"

    segments = cleaned.strip("/").split("/")
    norm_segments: list[str] = []
    for seg in segments:
        # Check if segment is placeholder: {id}, {{id}}, or :id
        if (seg.startswith("{") and seg.endswith("}")) or seg.startswith(":"):
            norm_segments.append("{}")
        else:
            norm_segments.append(seg)
    return "/" + "/".join(norm_segments)


def match_path(spec_path: str, artifact_path: str) -> bool:
    """Determine whether an artifact request path matches an OpenAPI specification path.

    Handles concrete substituted values (e.g. '/pets/123') matching parameter templates
    (e.g. '/pets/{petId}'), as well as alternate parameter placeholder formats (:petId, {{petId}}).
    """
    clean_spec = _clean_url_prefix(spec_path)
    clean_art = _clean_url_prefix(artifact_path)

    if clean_spec == clean_art:
        return True

    spec_segments = clean_spec.strip("/").split("/")
    art_segments = clean_art.strip("/").split("/")

    if len(spec_segments) != len(art_segments):
        return False

    for s_seg, a_seg in zip(spec_segments, art_segments, strict=True):
        is_spec_param = s_seg.startswith("{") and s_seg.endswith("}")
        is_art_param = (a_seg.startswith("{") and a_seg.endswith("}")) or a_seg.startswith(":")

        if is_spec_param:
            # Spec expects parameter, artifact provides either concrete value or placeholder
            if not a_seg:
                return False
            continue
        elif is_art_param:
            # Artifact provides placeholder, but spec is static segment
            continue
        elif s_seg != a_seg:
            return False

    return True


def match_operation(spec_method: str, spec_path: str, test_item: ArtifactTestItem) -> bool:
    """Return True if test_item exercises the specified OpenAPI method and path."""
    if spec_method.strip().upper() != test_item.method.strip().upper():
        return False
    return match_path(spec_path, test_item.path)
