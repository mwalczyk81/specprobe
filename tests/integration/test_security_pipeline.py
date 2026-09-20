"""End-to-end integration tests for security-scheme-aware test generation and export pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from specprobe.cli import cli

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "specs"


def _mock_completion(content: str) -> MagicMock:
    """Helper to generate a mock LiteLLM completion response object."""
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    return mock_resp


def test_full_security_pipeline(tmp_path: Path) -> None:
    """Verify chunk -> generate -> export pipeline with multi-scheme security."""
    runner = CliRunner()
    spec_file = str(FIXTURES_DIR / "security_schemes.json")
    out_dir = tmp_path / "exported_security"

    # Step 1: Chunk the security specification
    chunk_res = runner.invoke(cli, ["chunk", spec_file])
    assert chunk_res.exit_code == 0, f"chunk failed: {chunk_res.output}"

    # Step 2: Generate test cases from chunk output using mock LLM
    # Each operation will receive realistic completion text; engine will enforce placeholders
    mock_json = json.dumps(
        {
            "operation_id": "test_op",
            "description": "Happy path scenario",
            "request": {
                "headers": {},
                "query_params": {},
                "path_params": {},
            },
            "response": {
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "schema_shape": None,
            },
            "tags": ["security"],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion(mock_json)):
        gen_res = runner.invoke(
            cli,
            ["generate", "--no-cache"],
            input=chunk_res.output,
        )
    assert gen_res.exit_code == 0, f"generate failed: {gen_res.output}"
    assert len(gen_res.output.strip().splitlines()) >= 5

    # Step 3: Export generated test cases to both Postman and .http formats
    export_res = runner.invoke(
        cli,
        ["export", "--format", "both", "--output", str(out_dir)],
        input=gen_res.output,
    )
    assert export_res.exit_code == 0, f"export failed: {export_res.output}"

    # Step 4: Validate exported artifacts
    postman_files = list(out_dir.glob("*.json"))
    http_files = list(out_dir.glob("*.http"))
    assert len(postman_files) == 1, "Expected 1 Postman collection JSON file"
    assert len(http_files) == 1, "Expected 1 .http file"

    # Inspect Postman collection
    with open(postman_files[0], encoding="utf-8") as f:
        col = json.load(f)

    var_keys = {v["key"]: v["value"] for v in col["variable"]}
    assert "baseUrl" in var_keys
    assert "bearerAuth" in var_keys
    assert var_keys["bearerAuth"] == "<token>"
    assert "apiKeyHeaderAuth" in var_keys
    assert var_keys["apiKeyHeaderAuth"] == "<api_key>"
    assert "apiKeyQueryAuth" in var_keys
    assert var_keys["apiKeyQueryAuth"] == "<api_key>"

    # Inspect .http file
    with open(http_files[0], encoding="utf-8") as f:
        http_content = f.read()

    assert "@baseUrl =" in http_content
    assert "@bearerAuth = <token>" in http_content
    assert "@apiKeyHeaderAuth = <api_key>" in http_content
    assert "@apiKeyQueryAuth = <api_key>" in http_content
    assert "# Security:" in http_content
