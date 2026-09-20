"""Deterministic parsers for Postman Collection v2.1 and REST Client (.http) test artifacts."""

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from specprobe.audit.models import ArtifactTestItem

__all__ = [
    "parse_artifact",
    "parse_http_document",
    "parse_postman_collection",
]

_STATUS_CODE_REGEX = re.compile(
    r"(?:pm\.response\.to\.have\.status\s*\(\s*(\d+)\s*\)|#\s*Expected\s+Status:\s*(\d+))",
    re.IGNORECASE,
)
_JSON_SCHEMA_REGEX = re.compile(
    r"(?:pm\.response\.to\.have\.jsonSchema|#\s*Expected\s+Schema:)",
    re.IGNORECASE,
)
_PROPERTY_REGEX = re.compile(
    r"(?:pm\.expect\([^)]+\)\.to\.have\.property|#\s*Expected\s+Properties:)",
    re.IGNORECASE,
)
_HTTP_REQUEST_LINE_REGEX = re.compile(
    r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)(?:\s+HTTP/[\d.]+)?$",
    re.IGNORECASE,
)


def _extract_path_and_query(raw_url: str) -> tuple[str, list[str]]:
    """Extract normalized path and query parameter keys from a URL string."""
    clean_url = raw_url.strip()
    clean_url = re.sub(r"^https?://[^/]+", "", clean_url)
    clean_url = re.sub(r"^{{[^}]+}}", "", clean_url)
    clean_url = re.sub(r"^@[^/]+", "", clean_url)

    if "?" in clean_url:
        path_part, query_part = clean_url.split("?", 1)
        parsed_qs = urllib.parse.parse_qs(query_part, keep_blank_values=True)
        query_keys = list(parsed_qs.keys())
    else:
        path_part = clean_url
        query_keys = []

    if not path_part.startswith("/"):
        path_part = f"/{path_part}"
    return path_part, query_keys


def _traverse_postman_items(items: list[dict[str, Any]], results: list[ArtifactTestItem]) -> None:
    """Recursively traverse Postman item arrays and extract ArtifactTestItem models."""
    for item in items:
        if not isinstance(item, dict):
            continue

        if "item" in item and isinstance(item["item"], list):
            _traverse_postman_items(item["item"], results)

        if "request" in item and isinstance(item["request"], dict):
            req = item["request"]
            method = str(req.get("method", "GET")).upper()
            url_obj = req.get("url", "")

            query_params: list[str] = []
            if isinstance(url_obj, dict):
                raw_url = str(url_obj.get("raw", ""))
                path_segments = url_obj.get("path", [])
                if isinstance(path_segments, list) and path_segments:
                    path = "/" + "/".join(str(s) for s in path_segments if s)
                else:
                    path, _ = _extract_path_and_query(raw_url)

                query_list = url_obj.get("query", [])
                if isinstance(query_list, list):
                    for q in query_list:
                        if isinstance(q, dict) and "key" in q:
                            query_params.append(str(q["key"]))
            else:
                path, query_params = _extract_path_and_query(str(url_obj))

            # Headers
            headers: dict[str, str] = {}
            header_list = req.get("header", [])
            if isinstance(header_list, list):
                for h in header_list:
                    if isinstance(h, dict) and "key" in h:
                        headers[str(h["key"])] = str(h.get("value", ""))

            # Body
            has_body = "body" in req and bool(req["body"])

            # Test script assertions
            expected_status: int | None = None
            has_schema_assertion = False
            has_property_assertions = False

            events = item.get("event", [])
            if isinstance(events, list):
                for ev in events:
                    if isinstance(ev, dict) and ev.get("listen") == "test":
                        script = ev.get("script", {})
                        exec_lines = script.get("exec", [])
                        script_text = (
                            "\n".join(exec_lines)
                            if isinstance(exec_lines, list)
                            else str(exec_lines)
                        )

                        # Match status
                        status_match = _STATUS_CODE_REGEX.search(script_text)
                        if status_match:
                            code_str = status_match.group(1) or status_match.group(2)
                            if code_str:
                                expected_status = int(code_str)

                        if _JSON_SCHEMA_REGEX.search(script_text):
                            has_schema_assertion = True
                        if _PROPERTY_REGEX.search(script_text):
                            has_property_assertions = True

            results.append(
                ArtifactTestItem(
                    name=str(item.get("name", "")),
                    method=method,
                    path=path,
                    query_params=query_params,
                    headers=headers,
                    has_body=has_body,
                    expected_status=expected_status,
                    has_schema_assertion=has_schema_assertion,
                    has_property_assertions=has_property_assertions,
                    raw_source="postman",
                )
            )


def parse_postman_collection(content: str | dict[str, Any]) -> list[ArtifactTestItem]:
    """Parse Postman Collection v2.1 JSON into normalized ArtifactTestItem instances."""
    if isinstance(content, str):
        if not content.strip():
            return []
        data = json.loads(content)
    else:
        data = content

    items = data.get("item", [])
    results: list[ArtifactTestItem] = []
    if isinstance(items, list):
        _traverse_postman_items(items, results)
    return results


def parse_http_document(content: str) -> list[ArtifactTestItem]:
    """Parse an RFC 7230 REST Client (.http) file into normalized ArtifactTestItem instances."""
    if not content.strip():
        return []

    blocks = content.split("###")
    results: list[ArtifactTestItem] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        name = ""
        expected_status: int | None = None
        has_schema_assertion = False
        has_property_assertions = False
        request_line_idx: int | None = None
        method = "GET"
        raw_url = ""

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("# @name"):
                name = stripped[7:].strip()
            elif _STATUS_CODE_REGEX.search(stripped):
                status_match = _STATUS_CODE_REGEX.search(stripped)
                if status_match:
                    code_str = status_match.group(1) or status_match.group(2)
                    if code_str:
                        expected_status = int(code_str)
            if _JSON_SCHEMA_REGEX.search(stripped):
                has_schema_assertion = True
            if _PROPERTY_REGEX.search(stripped):
                has_property_assertions = True

            req_match = _HTTP_REQUEST_LINE_REGEX.match(stripped)
            if req_match and request_line_idx is None:
                request_line_idx = idx
                method = req_match.group(1).upper()
                raw_url = req_match.group(2)

        if request_line_idx is None:
            continue

        path, query_params = _extract_path_and_query(raw_url)

        # Headers and body
        headers: dict[str, str] = {}
        has_body = False

        after_req = lines[request_line_idx + 1 :]
        header_lines: list[str] = []
        body_lines: list[str] = []
        in_body = False

        for req_line in after_req:
            if not in_body and not req_line.strip():
                in_body = True
                continue
            if in_body:
                body_lines.append(req_line)
            else:
                header_lines.append(req_line)

        for h in header_lines:
            if ":" in h and not h.strip().startswith("#"):
                k, v = h.split(":", 1)
                headers[k.strip()] = v.strip()

        if "".join(body_lines).strip():
            has_body = True

        results.append(
            ArtifactTestItem(
                name=name,
                method=method,
                path=path,
                query_params=query_params,
                headers=headers,
                has_body=has_body,
                expected_status=expected_status,
                has_schema_assertion=has_schema_assertion,
                has_property_assertions=has_property_assertions,
                raw_source="rest_client",
            )
        )

    return results


def parse_artifact(source: str | Path) -> list[ArtifactTestItem]:
    """Parse a test artifact by path or raw content string, auto-detecting format."""
    if isinstance(source, Path):
        if not source.is_file():
            return []
        content = source.read_text(encoding="utf-8")
        if source.suffix.lower() == ".json":
            return parse_postman_collection(content)
        return parse_http_document(content)

    source_str = str(source).strip()
    if not source_str:
        return []

    # If source is a string, only attempt filesystem resolution if it is a plausible
    # path (single line, not JSON object syntax, within POSIX PATH_MAX limits) to
    # prevent OSError(ENAMETOOLONG) when multi-kilobyte in-memory artifacts are passed.
    if (
        "\n" not in source_str
        and "\r" not in source_str
        and not source_str.startswith("{")
        and len(source_str) < 4096
    ):
        try:
            path_candidate = Path(source_str)
            if path_candidate.is_file():
                content = path_candidate.read_text(encoding="utf-8")
                if path_candidate.suffix.lower() == ".json":
                    return parse_postman_collection(content)
                return parse_http_document(content)
        except OSError:
            pass

    # In-memory raw content
    if source_str.startswith("{"):
        return parse_postman_collection(source_str)
    return parse_http_document(source_str)
