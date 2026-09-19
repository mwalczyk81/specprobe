"""Prompt builder for synthesizing test generation prompts from OpenAPI operation chunks."""

import json
import re

from specprobe.chunker.models import OperationChunk

SYSTEM_PROMPT = """You are an expert API testing engineer.
Your task is to generate a single realistic, executable happy-path (2xx success)
test case for the given OpenAPI operation.
You MUST output ONLY a valid JSON object matching the following structure without
any markdown code fences, commentary, or preamble:

{
  "operation_id": "<exact operation identifier>",
  "description": "<concise description of the happy-path test scenario>",
  "request": {
    "path_params": { "<parameter_name>": <realistic_value> },
    "query_params": { "<parameter_name>": <realistic_value> },
    "headers": { "<header_name>": "<value>" },
    "body": <concrete_request_body_or_null>
  },
  "response": {
    "status_code": <expected_2xx_integer_code_such_as_200_or_201>,
    "headers": { "<expected_response_header>": "<value>" },
    "schema_shape": <expected_json_structure_or_null>
  },
  "tags": ["<tag>", ...]
}

Guidelines:
- operation_id MUST match the operation's identifier (or fallback to METHOD_path if absent).
- Use concrete, realistic fixture data matching parameter types and schemas (avoid generic
  placeholders like "string" when realistic data like "rover" or "42" is appropriate).
- Response status_code MUST be an integer matching one of the defined successful 2xx responses.
"""


def clean_markdown_fences(text: str) -> str:
    """Remove leading and trailing markdown code block formatting (```json ... ```)."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def resolve_operation_id(chunk: OperationChunk) -> str:
    """Return operationId from operation dict, metadata, or fallback to METHOD_path."""
    op = chunk.operation
    meta = chunk.metadata
    if op.get("operationId"):
        return str(op["operationId"])
    if meta.operationId:
        return meta.operationId
    method = meta.method or op.get("method", "GET")
    path = meta.path or op.get("path", "/")
    sanitized_path = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")
    return f"{method.upper()}_{sanitized_path}"


class PromptBuilder:
    """Synthesizes structured LLM chat prompts from OpenAPI operation chunks."""

    @staticmethod
    def build_system_prompt() -> str:
        """Return the standard system prompt instructing the model on schema and output format."""
        return SYSTEM_PROMPT.strip()

    @staticmethod
    def build_user_prompt(chunk: OperationChunk) -> str:
        """Construct an information-dense user prompt summarizing the target operation."""
        op = chunk.operation
        meta = chunk.metadata
        op_id = resolve_operation_id(chunk)
        method = meta.method or op.get("method", "GET")
        path = meta.path or op.get("path", "/")

        sections: list[str] = [
            f"Target Operation: {method.upper()} {path}",
            f"Operation ID: {op_id}",
        ]

        if op.get("summary"):
            sections.append(f"Summary: {op['summary']}")
        if op.get("description"):
            sections.append(f"Description: {op['description']}")

        tags = op.get("tags") or meta.tags
        if tags:
            sections.append(f"Tags: {', '.join(tags)}")

        # Parameters
        parameters = op.get("parameters")
        if parameters:
            param_lines = ["Parameters:"]
            for param in parameters:
                p_name = param.get("name", "")
                p_in = param.get("in", "")
                p_req = "required" if param.get("required") else "optional"
                p_schema = param.get("schema", {})
                p_type = p_schema.get("type", "any")
                p_desc = param.get("description", "")
                desc_str = f" - {p_desc}" if p_desc else ""
                param_lines.append(f"  - {p_name} ({p_in}, {p_req}, type: {p_type}){desc_str}")
            sections.append("\n".join(param_lines))

        # Request Body
        request_body = op.get("requestBody")
        if request_body:
            rb_req = "required" if request_body.get("required") else "optional"
            content = request_body.get("content", {})
            media_types = list(content.keys())
            sections.append(
                f"Request Body ({rb_req}, media types: {', '.join(media_types)}):\n"
                f"  Schema: {json.dumps(content, indent=2)}"
            )

        # Responses (focus on 2xx)
        responses = op.get("responses")
        if responses:
            resp_lines = ["Defined Responses:"]
            for code, resp in responses.items():
                desc = resp.get("description", "") if isinstance(resp, dict) else str(resp)
                resp_lines.append(f"  - {code}: {desc}")
            sections.append("\n".join(resp_lines))

        # Component schemas if available
        if chunk.components and isinstance(chunk.components, dict):
            schemas = chunk.components.get("schemas")
            if schemas:
                sections.append(f"Referenced Component Schemas:\n{json.dumps(schemas, indent=2)}")

        sections.append("\nGenerate the single happy-path test case JSON object now:")
        return "\n\n".join(sections)

    @classmethod
    def build_initial_messages(cls, chunk: OperationChunk) -> list[dict[str, str]]:
        """Construct the initial chat conversation turn for an operation."""
        return [
            {"role": "system", "content": cls.build_system_prompt()},
            {"role": "user", "content": cls.build_user_prompt(chunk)},
        ]
