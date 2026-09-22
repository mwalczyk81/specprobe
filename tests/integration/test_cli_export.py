"""Integration tests for specprobe export CLI environment options (US3 / T017)."""

import json
from pathlib import Path

from click.testing import CliRunner

from specprobe.cli import cli

INPUT_FIXTURE = "tests/fixtures/generated_tests.jsonl"
ENV_YAML_FIXTURE = "tests/fixtures/environments/sample_env.yaml"
ENV_JSON_FIXTURE = "tests/fixtures/environments/sample_env.json"


def test_cli_export_multiple_env_flags_postman(tmp_path: Path) -> None:
    """Verify CLI exports separate Postman environment files for repeatable --env flags."""
    runner = CliRunner()
    out_dir = tmp_path / "postman_multi"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "postman",
            "-o",
            str(out_dir),
            "--env",
            "local=http://localhost:8000",
            "--env",
            "work=https://api.work.internal",
        ],
    )

    assert result.exit_code == 0
    col_file = out_dir / "collection.json"
    env_local = out_dir / "local.postman_environment.json"
    env_work = out_dir / "work.postman_environment.json"

    assert col_file.exists()
    assert env_local.exists()
    assert env_work.exists()

    col_data = json.loads(col_file.read_text(encoding="utf-8"))
    assert col_data["variable"] == []

    local_data = json.loads(env_local.read_text(encoding="utf-8"))
    assert local_data["name"] == "local"
    assert any(
        v["key"] == "baseUrl" and v["value"] == "http://localhost:8000"
        for v in local_data["values"]
    )

    work_data = json.loads(env_work.read_text(encoding="utf-8"))
    assert work_data["name"] == "work"
    assert any(
        v["key"] == "baseUrl" and v["value"] == "https://api.work.internal"
        for v in work_data["values"]
    )


def test_cli_export_multiple_env_flags_http(tmp_path: Path) -> None:
    """Verify CLI exports http-client.env.json alongside .http file for repeatable --env flags."""
    runner = CliRunner()
    dest_file = tmp_path / "http_multi" / "suite.http"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "http",
            "-o",
            str(dest_file),
            "--env",
            "local=http://localhost:8000",
            "--env",
            "work=https://api.work.internal",
        ],
    )

    assert result.exit_code == 0
    assert dest_file.exists()
    env_file = dest_file.parent / "http-client.env.json"
    assert env_file.exists()

    http_text = dest_file.read_text(encoding="utf-8")
    assert "@baseUrl" not in http_text
    assert "{{baseUrl}}/pets" in http_text

    env_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert "local" in env_data
    assert "work" in env_data
    assert env_data["local"]["baseUrl"] == "http://localhost:8000"
    assert env_data["work"]["baseUrl"] == "https://api.work.internal"


def test_cli_export_env_file_yaml(tmp_path: Path) -> None:
    """Verify CLI loads YAML environment file and emits corresponding artifacts."""
    runner = CliRunner()
    out_dir = tmp_path / "postman_yaml"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "postman",
            "-o",
            str(out_dir),
            "--env-file",
            ENV_YAML_FIXTURE,
        ],
    )

    assert result.exit_code == 0
    env_local = out_dir / "local.postman_environment.json"
    assert env_local.exists()

    local_data = json.loads(env_local.read_text(encoding="utf-8"))
    assert any(
        v["key"] == "apiKey" and v["value"] == "local-dev-token" for v in local_data["values"]
    )


def test_cli_export_env_file_json(tmp_path: Path) -> None:
    """Verify CLI loads JSON environment file and emits http-client.env.json."""
    runner = CliRunner()
    dest_file = tmp_path / "http_json" / "requests.http"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "http",
            "-o",
            str(dest_file),
            "--env-file",
            ENV_JSON_FIXTURE,
        ],
    )

    assert result.exit_code == 0
    env_file = dest_file.parent / "http-client.env.json"
    assert env_file.exists()

    env_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert env_data["work"]["baseUrl"] == "https://api.work.internal"
    assert env_data["work"]["apiKey"] == "work-staging-token"


def test_cli_export_env_override_file(tmp_path: Path) -> None:
    """Verify CLI --env flag takes precedence over --env-file with identical name."""
    runner = CliRunner()
    out_dir = tmp_path / "override_test"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "postman",
            "-o",
            str(out_dir),
            "--env-file",
            ENV_YAML_FIXTURE,
            "--env",
            "local=http://localhost:9999",
        ],
    )

    assert result.exit_code == 0
    env_local = out_dir / "local.postman_environment.json"
    assert env_local.exists()

    local_data = json.loads(env_local.read_text(encoding="utf-8"))
    base_val = next(v["value"] for v in local_data["values"] if v["key"] == "baseUrl")
    assert base_val == "http://localhost:9999"


def test_cli_export_missing_output_with_env_fails() -> None:
    """Verify error reporting and exit code 1 when --env is used without --output."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "http",
            "--env",
            "local=http://localhost:8000",
        ],
    )

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "Option '--output' is required when exporting environments." in output


def test_cli_export_missing_output_with_env_file_fails() -> None:
    """Verify error reporting and exit code 1 when --env-file is used without --output."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "postman",
            "--env-file",
            ENV_JSON_FIXTURE,
        ],
    )

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "Option '--output' is required when exporting environments." in output


def test_cli_export_duplicate_env_names_fails(tmp_path: Path) -> None:
    """Verify error reporting when duplicate environment names are passed via --env."""
    runner = CliRunner()
    out_dir = tmp_path / "dups"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "postman",
            "-o",
            str(out_dir),
            "--env",
            "dev=http://localhost:8000",
            "--env",
            "dev=http://localhost:9000",
        ],
    )

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "Duplicate environment name 'dev'" in output


def test_cli_export_invalid_env_file_path_fails(tmp_path: Path) -> None:
    """Verify error reporting when --env-file path does not exist."""
    runner = CliRunner()
    out_dir = tmp_path / "bad_path"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "postman",
            "-o",
            str(out_dir),
            "--env-file",
            "non_existent_environments_file.yaml",
        ],
    )

    assert result.exit_code == 1
    output = result.output + (result.stderr or "")
    assert "not found" in output.lower()


def test_cli_export_legacy_base_url_backward_compatibility(tmp_path: Path) -> None:
    """Verify legacy --base-url without --env/--env-file emits default environment files
    (FR-005).
    """
    runner = CliRunner()
    out_dir = tmp_path / "out_compat"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "both",
            "-o",
            str(out_dir),
            "--base-url",
            "http://custom-host:9000",
        ],
    )

    assert result.exit_code == 0
    col_file = out_dir / "collection.json"
    http_file = out_dir / "requests.http"
    env_pm = out_dir / "default.postman_environment.json"
    env_rest = out_dir / "http-client.env.json"

    assert col_file.exists()
    assert http_file.exists()
    assert env_pm.exists()
    assert env_rest.exists()

    col_data = json.loads(col_file.read_text(encoding="utf-8"))
    assert col_data["variable"] == []

    http_content = http_file.read_text(encoding="utf-8")
    assert "@baseUrl" not in http_content

    pm_data = json.loads(env_pm.read_text(encoding="utf-8"))
    assert pm_data["name"] == "default"
    assert any(
        v["key"] == "baseUrl" and v["value"] == "http://custom-host:9000" for v in pm_data["values"]
    )

    rest_data = json.loads(env_rest.read_text(encoding="utf-8"))
    assert "default" in rest_data
    assert rest_data["default"]["baseUrl"] == "http://custom-host:9000"


def test_cli_export_both_format_with_environments(tmp_path: Path) -> None:
    """Verify dual export (--format both) writes all collection, http, and environment files."""
    runner = CliRunner()
    out_dir = tmp_path / "out_both"

    result = runner.invoke(
        cli,
        [
            "export",
            INPUT_FIXTURE,
            "--format",
            "both",
            "-o",
            str(out_dir),
            "--env",
            "local=http://localhost:8000",
            "--env",
            "work=https://api.work.internal",
        ],
    )

    assert result.exit_code == 0
    assert (out_dir / "collection.json").exists()
    assert (out_dir / "requests.http").exists()
    assert (out_dir / "local.postman_environment.json").exists()
    assert (out_dir / "work.postman_environment.json").exists()
    assert (out_dir / "http-client.env.json").exists()
