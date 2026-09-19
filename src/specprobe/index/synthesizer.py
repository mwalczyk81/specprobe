"""Synthesizes structured natural-language documents from OperationChunk instances.

This module converts OpenAPI operation chunks into clean, informative natural-language
text suitable for dense and sparse vector embeddings, eliminating JSON schema syntax noise.
"""

from typing import Any

from specprobe.chunker.models import OperationChunk


def _resolve_schema_label(schema: dict[str, Any] | None) -> str:
    """Extract a concise human-readable type or name from a schema dictionary."""
    if not schema or not isinstance(schema, dict):
        return "any"

    if "$ref" in schema:
        ref = schema["$ref"]
        return ref.split("/")[-1]

    if "title" in schema:
        return schema["title"]

    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items", {})
        item_type = _resolve_schema_label(items)
        return f"array of {item_type}"

    if schema_type:
        return str(schema_type)

    if "properties" in schema:
        return "object"

    return "any"


def build_embedding_text(chunk: OperationChunk | dict[str, Any]) -> str:
    """Construct a clean, information-dense natural-language document for an operation.

    Parameters
    ----------
    chunk : OperationChunk | dict[str, Any]
        The operation chunk model or dictionary.

    Returns
    -------
    str
        Structured natural-language text representation.
    """
    if isinstance(chunk, dict):
        metadata = chunk.get("metadata", {})
        operation = chunk.get("operation", {})
        method = metadata.get("method", "").upper()
        path = metadata.get("path", "")
        tags = operation.get("tags") or metadata.get("tags") or []
    else:
        metadata = chunk.metadata
        operation = chunk.operation
        method = metadata.method.upper()
        path = metadata.path
        tags = operation.get("tags") or metadata.tags or []

    summary = (operation.get("summary") or "").strip()
    description = (operation.get("description") or "").strip()

    lead_title = summary or description or "API endpoint"
    lines: list[str] = [f"{method} {path} — {lead_title}"]

    if summary and summary != lead_title:
        lines.append(f"Summary: {summary}")
    elif summary:
        lines.append(f"Summary: {summary}")

    if description and description != summary:
        lines.append(f"Description: {description}")

    if tags:
        lines.append(f"Tags: {', '.join(str(t) for t in tags)}")

    # Parameters
    params = operation.get("parameters") or []
    if params:
        param_lines: list[str] = []
        for param in params:
            if not isinstance(param, dict):
                continue
            name = param.get("name", "unnamed")
            location = param.get("in", "query")
            required = "required" if param.get("required") else "optional"
            p_desc = (param.get("description") or "").strip()
            p_schema = param.get("schema") or {}
            p_type = _resolve_schema_label(p_schema)

            entry = f"- {name} ({location}, {required})"
            if p_desc:
                entry += f": {p_desc}"
            if p_type and p_type != "any":
                entry += f" (type: {p_type})"
            param_lines.append(entry)

        if param_lines:
            lines.append("Parameters:")
            lines.extend(f"  {pl}" for pl in param_lines)

    # Request Body
    request_body = operation.get("requestBody") or operation.get("request_body")
    if request_body and isinstance(request_body, dict):
        rb_desc = (request_body.get("description") or "").strip()
        rb_content = request_body.get("content") or {}
        content_types = list(rb_content.keys())
        ct_str = ", ".join(content_types) if content_types else "payload"

        schema_labels: list[str] = []
        for media in rb_content.values():
            if isinstance(media, dict) and "schema" in media:
                label = _resolve_schema_label(media["schema"])
                if label not in schema_labels:
                    schema_labels.append(label)

        types_str = f" (type: {', '.join(schema_labels)})" if schema_labels else ""
        desc_str = f": {rb_desc}" if rb_desc else ""
        lines.append(f"Request Body ({ct_str}){desc_str}{types_str}")

    # Responses
    responses = operation.get("responses") or {}
    if responses and isinstance(responses, dict):
        resp_lines: list[str] = []
        for status_code, resp in responses.items():
            if not isinstance(resp, dict):
                continue
            r_desc = (resp.get("description") or "").strip()
            r_content = resp.get("content") or {}
            content_types = list(r_content.keys())
            ct_str = f" ({', '.join(content_types)})" if content_types else ""

            schema_labels = []
            for media in r_content.values():
                if isinstance(media, dict) and "schema" in media:
                    label = _resolve_schema_label(media["schema"])
                    if label not in schema_labels:
                        schema_labels.append(label)

            type_str = f" (type: {', '.join(schema_labels)})" if schema_labels else ""
            desc_str = f": {r_desc}" if r_desc else ""
            resp_lines.append(f"- {status_code}{ct_str}{desc_str}{type_str}")

        if resp_lines:
            lines.append("Responses:")
            lines.extend(f"  {rl}" for rl in resp_lines)

    return "\n".join(lines).strip()
