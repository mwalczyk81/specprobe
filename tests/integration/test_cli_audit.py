"""Integration tests for specprobe audit CLI command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from specprobe.audit.models import OperationCritique
from specprobe.chunker.extractor import OperationExtractor
from specprobe.chunker.loader import load_openapi_spec
from specprobe.cli import cli
from specprobe.index.store import index_chunk_stream


def _mock_completion_response(content: str):
    """Create a mock LiteLLM completion response object."""
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp.choices = [mock_choice]
    return mock_resp


def test_audit_with_direct_spec_postman() -> None:
    """Verify audit runs with direct --spec and Postman collection artifact."""
    runner = CliRunner()
    artifact_path = "tests/fixtures/audit_postman_collection.json"
    spec_path = "tests/fixtures/valid_openapi_30.yaml"

    mock_critique = json.dumps(
        {
            "operation_id": "listPets",
            "assertion_quality_score": 0.7,
            "critique_summary": "Status code and property assertions present, lacks schema.",
            "gaps": [
                {
                    "gap_type": "weak_assertion",
                    "severity": "suggestion",
                    "target": "listPets",
                    "description": "Lacks JSON Schema assertion.",
                    "recommendation": "Use pm.response.to.have.jsonSchema(...)",
                }
            ],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_critique)):
        result = runner.invoke(
            cli,
            ["audit", artifact_path, "--spec", spec_path, "--no-cache"],
        )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    assert len(lines) >= 1

    critiques = [OperationCritique.model_validate_json(line) for line in lines]
    op_ids = [c.operation_id for c in critiques]
    assert "listPets" in op_ids


def test_audit_with_direct_spec_http() -> None:
    """Verify audit runs with direct --spec and .http artifact."""
    runner = CliRunner()
    artifact_path = "tests/fixtures/audit_sample_requests.http"
    spec_path = "tests/fixtures/valid_openapi_30.yaml"

    mock_critique = json.dumps(
        {
            "operation_id": "listPets",
            "assertion_quality_score": 0.6,
            "critique_summary": "Only expected status code is checked.",
            "gaps": [],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_critique)):
        result = runner.invoke(
            cli,
            ["audit", artifact_path, "--spec", spec_path, "--no-cache"],
        )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    assert len(lines) >= 1

    critiques = [OperationCritique.model_validate_json(line) for line in lines]
    op_ids = [c.operation_id for c in critiques]
    assert "listPets" in op_ids


def test_audit_stdin_pipe() -> None:
    """Verify audit reads artifact from stdin pipe when '-' is specified."""
    runner = CliRunner()
    artifact_path = Path("tests/fixtures/audit_sample_requests.http")
    content = artifact_path.read_text(encoding="utf-8")
    spec_path = "tests/fixtures/valid_openapi_30.yaml"

    mock_critique = json.dumps(
        {
            "operation_id": "listPets",
            "assertion_quality_score": 0.6,
            "critique_summary": "Only expected status code is checked.",
            "gaps": [],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_critique)):
        result = runner.invoke(
            cli,
            ["audit", "-", "--spec", spec_path, "--no-cache"],
            input=content,
        )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    assert len(lines) >= 1


def test_audit_with_summary_flag() -> None:
    """Verify --summary flag renders coverage metrics table to stderr."""
    runner = CliRunner()
    artifact_path = "tests/fixtures/audit_postman_collection.json"
    spec_path = "tests/fixtures/valid_openapi_30.yaml"

    mock_critique = json.dumps(
        {
            "operation_id": "listPets",
            "assertion_quality_score": 0.7,
            "critique_summary": "Summary text",
            "gaps": [],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_critique)):
        result = runner.invoke(
            cli,
            ["audit", artifact_path, "--spec", spec_path, "--summary", "--no-cache"],
        )

    assert result.exit_code == 0
    # stderr must contain the summary report
    assert "SpecProbe Audit Summary" in result.stderr
    assert "Operations:" in result.stderr
    assert "Status Codes:" in result.stderr
    assert "Coverage Gaps by Severity:" in result.stderr


def test_audit_empty_artifact(tmp_path: Path) -> None:
    """Verify empty artifact reports 0% coverage and exits code 0."""
    runner = CliRunner()
    empty_file = tmp_path / "empty.http"
    empty_file.write_text("", encoding="utf-8")
    spec_path = "tests/fixtures/valid_openapi_30.yaml"

    result = runner.invoke(
        cli,
        ["audit", str(empty_file), "--spec", spec_path],
    )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    assert len(lines) >= 1
    critiques = [OperationCritique.model_validate_json(line) for line in lines]
    for c in critiques:
        assert c.matched_tests_count == 0
        assert c.assertion_quality_score == 0.0


def test_audit_missing_artifact_file() -> None:
    """Verify missing artifact file exits with code 1 and descriptive error."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "audit",
            "nonexistent_artifact_file.json",
            "--spec",
            "tests/fixtures/valid_openapi_30.yaml",
        ],
    )
    assert result.exit_code == 1
    assert "does not exist" in result.stderr.lower() or "does not exist" in result.stdout.lower()


def test_audit_missing_spec_and_index(tmp_path: Path) -> None:
    """Verify missing spec and index exits with code 1 and helpful instruction."""
    runner = CliRunner()
    artifact_path = "tests/fixtures/audit_postman_collection.json"
    fake_index = tmp_path / "empty_index"

    result = runner.invoke(
        cli,
        ["audit", artifact_path, "--index-dir", str(fake_index)],
    )
    assert result.exit_code == 1
    assert "specprobe index" in result.stderr.lower() or "--spec" in result.stderr.lower()


def test_audit_with_index_dir(tmp_path: Path) -> None:
    """Verify audit loads specification chunks from an indexed Qdrant directory."""
    # Index valid_openapi_30.yaml first
    spec = load_openapi_spec("tests/fixtures/valid_openapi_30.yaml")
    chunks = list(OperationExtractor(spec).extract_operations())
    chunk_lines = [chunk.model_dump_json() for chunk in chunks]

    index_dir = tmp_path / "qdrant_idx"
    index_chunk_stream(chunk_lines, index_path=index_dir)

    runner = CliRunner()
    artifact_path = "tests/fixtures/audit_postman_collection.json"

    mock_critique = json.dumps(
        {
            "operation_id": "listPets",
            "assertion_quality_score": 0.8,
            "critique_summary": "Good tests",
            "gaps": [],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_critique)):
        result = runner.invoke(
            cli,
            ["audit", artifact_path, "--index-dir", str(index_dir), "--no-cache"],
        )

    assert result.exit_code == 0
    lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    assert len(lines) >= 1


def test_audit_llm_failure_exit_code() -> None:
    """Verify LLM gateway failure exits code 1 with error message."""
    runner = CliRunner()
    artifact_path = "tests/fixtures/audit_postman_collection.json"
    spec_path = "tests/fixtures/valid_openapi_30.yaml"

    with patch("litellm.completion", side_effect=RuntimeError("LiteLLM connection timeout")):
        result = runner.invoke(
            cli,
            ["audit", artifact_path, "--spec", spec_path, "--no-cache"],
        )

    assert result.exit_code == 1
    assert "LiteLLM connection timeout" in result.stderr or "LLM" in result.stderr


def test_audit_full_pipeline_composition() -> None:
    """Verify full pipeline composition: export -> audit piped via stdin."""
    runner = CliRunner()
    fixture_path = Path("tests/fixtures/generated_tests.jsonl")
    gen_content = fixture_path.read_text(encoding="utf-8")

    # Step 1: Export generated test cases to Postman collection
    export_res = runner.invoke(cli, ["export", "--format", "postman"], input=gen_content)
    assert export_res.exit_code == 0
    exported_postman = export_res.stdout

    # Step 2: Audit exported Postman collection piped through stdin
    spec_path = "tests/fixtures/valid_openapi_30.yaml"
    mock_critique = json.dumps(
        {
            "operation_id": "listPets",
            "assertion_quality_score": 0.9,
            "critique_summary": "Full JSON Schema validation verified.",
            "gaps": [],
        }
    )

    with patch("litellm.completion", return_value=_mock_completion_response(mock_critique)):
        audit_res = runner.invoke(
            cli,
            ["audit", "-", "--spec", spec_path, "--summary", "--no-cache"],
            input=exported_postman,
        )

    assert audit_res.exit_code == 0
    lines = [line.strip() for line in audit_res.stdout.strip().split("\n") if line.strip()]
    assert len(lines) >= 1
    assert "SpecProbe Audit Summary" in audit_res.stderr
