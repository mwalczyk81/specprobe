"""Unit tests for exporter engine orchestration and batch export."""

import json
from pathlib import Path

import pytest

from specprobe.exporter.engine import (
    export_batch,
    load_environment_config_file,
    merge_environments,
    parse_env_cli_option,
)
from specprobe.exporter.models import ExportConfig, ExportEnvironment, ExportFormat
from specprobe.generator.models import GeneratedTestCase, RequestFixture, ResponseAssertion


@pytest.fixture
def sample_test_case() -> GeneratedTestCase:
    """Return a representative GeneratedTestCase."""
    return GeneratedTestCase(
        operation_id="getPet",
        description="Get a pet by ID",
        request=RequestFixture(
            method="GET",
            path="/pets/{petId}",
            path_params={"petId": "1"},
            query_params={},
            headers={},
            body=None,
        ),
        response=ResponseAssertion(status_code=200, headers={}, schema_shape=None),
        tags=["pets"],
    )


def test_export_batch_http_with_environments_directory(
    tmp_path: Path, sample_test_case: GeneratedTestCase
) -> None:
    """Test HTTP export with environments targeting a directory."""
    out_dir = tmp_path / "http_out"
    envs = [
        ExportEnvironment(name="local", base_url="http://localhost:8000"),
        ExportEnvironment(name="work", base_url="https://api.work.internal"),
    ]
    config = ExportConfig(
        format=ExportFormat.HTTP,
        output_path=out_dir,
        environments=envs,
    )

    export_batch([sample_test_case], config)

    http_file = out_dir / "requests.http"
    env_file = out_dir / "http-client.env.json"

    assert http_file.exists()
    assert env_file.exists()

    http_content = http_file.read_text(encoding="utf-8")
    assert "@baseUrl" not in http_content
    assert "{{baseUrl}}/pets/1" in http_content

    env_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert "local" in env_data
    assert "work" in env_data
    assert env_data["local"]["baseUrl"] == "http://localhost:8000"
    assert env_data["work"]["baseUrl"] == "https://api.work.internal"


def test_export_batch_http_with_environments_file_path(
    tmp_path: Path, sample_test_case: GeneratedTestCase
) -> None:
    """Test HTTP export with environments targeting an explicit file path."""
    dest_file = tmp_path / "custom" / "my_tests.http"
    envs = [ExportEnvironment(name="staging", base_url="https://api.staging.example.com")]
    config = ExportConfig(
        format=ExportFormat.HTTP,
        output_path=dest_file,
        environments=envs,
    )

    export_batch([sample_test_case], config)

    assert dest_file.exists()
    env_file = dest_file.parent / "http-client.env.json"
    assert env_file.exists()

    env_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert "staging" in env_data
    assert env_data["staging"]["baseUrl"] == "https://api.staging.example.com"


def test_export_batch_http_no_environments_legacy(
    tmp_path: Path, sample_test_case: GeneratedTestCase
) -> None:
    """Test legacy HTTP export without environments retains @baseUrl in file."""
    dest_file = tmp_path / "legacy.http"
    config = ExportConfig(
        format=ExportFormat.HTTP,
        output_path=dest_file,
        base_url="http://legacy-host:9999",
    )

    export_batch([sample_test_case], config)

    assert dest_file.exists()
    env_file = dest_file.parent / "http-client.env.json"
    assert not env_file.exists()

    content = dest_file.read_text(encoding="utf-8")
    assert "@baseUrl = http://legacy-host:9999" in content


def test_export_batch_postman_with_environments_directory(
    tmp_path: Path, sample_test_case: GeneratedTestCase
) -> None:
    """Test Postman export with environments targeting a directory."""
    out_dir = tmp_path / "postman_out"
    envs = [
        ExportEnvironment(name="local", base_url="http://localhost:8000"),
        ExportEnvironment(name="work", base_url="https://api.work.internal"),
    ]
    config = ExportConfig(
        format=ExportFormat.POSTMAN,
        output_path=out_dir,
        environments=envs,
    )

    export_batch([sample_test_case], config)

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
    assert local_data["_postman_variable_scope"] == "environment"
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


def test_export_batch_postman_with_environments_file_path(
    tmp_path: Path, sample_test_case: GeneratedTestCase
) -> None:
    """Test Postman export with environments targeting an explicit file path."""
    dest_file = tmp_path / "custom_col" / "my_col.json"
    envs = [ExportEnvironment(name="qa/v1", base_url="https://api.qa.example.com")]
    config = ExportConfig(
        format=ExportFormat.POSTMAN,
        output_path=dest_file,
        environments=envs,
    )

    export_batch([sample_test_case], config)

    assert dest_file.exists()
    # Name 'qa/v1' sanitized to 'qa_v1.postman_environment.json'
    env_file = dest_file.parent / "qa_v1.postman_environment.json"
    assert env_file.exists()

    qa_data = json.loads(env_file.read_text(encoding="utf-8"))
    assert qa_data["name"] == "qa/v1"


def test_parse_env_cli_option_valid() -> None:
    """Test parsing valid <name>=<url> strings."""
    input_strs = ["local=http://localhost:8000", "work=https://api.work.internal"]
    envs = parse_env_cli_option(input_strs)
    assert len(envs) == 2
    assert envs[0].name == "local"
    assert envs[0].base_url == "http://localhost:8000"
    assert envs[1].name == "work"
    assert envs[1].base_url == "https://api.work.internal"


def test_parse_env_cli_option_whitespace_trimmed() -> None:
    """Test whitespace around name and url is stripped, and trailing slashes stripped."""
    input_strs = ["  staging  =  https://api.staging.example.com/  "]
    envs = parse_env_cli_option(input_strs)
    assert len(envs) == 1
    assert envs[0].name == "staging"
    assert envs[0].base_url == "https://api.staging.example.com"


def test_parse_env_cli_option_missing_equals() -> None:
    """Test error raised when '=' delimiter is missing."""
    with pytest.raises(ValueError, match="Expected '<name>=<url>'"):
        parse_env_cli_option(["invalid_format"])


def test_parse_env_cli_option_empty_parts() -> None:
    """Test error raised when name or url part is empty."""
    with pytest.raises(ValueError, match="Expected '<name>=<url>'"):
        parse_env_cli_option(["=http://localhost:8000"])

    with pytest.raises(ValueError, match="Expected '<name>=<url>'"):
        parse_env_cli_option(["local="])


def test_parse_env_cli_option_duplicate_name() -> None:
    """Test error raised when duplicate environment names are supplied on CLI."""
    with pytest.raises(ValueError, match="Duplicate environment name 'dev'"):
        parse_env_cli_option(["dev=http://localhost:8000", "dev=http://localhost:9000"])


def test_load_environment_config_file_json() -> None:
    """Test loading environments from JSON configuration fixture."""
    path = Path("tests/fixtures/environments/sample_env.json")
    envs = load_environment_config_file(path)
    assert len(envs) == 2

    local = next(e for e in envs if e.name == "local")
    assert local.base_url == "http://localhost:8000"
    assert local.variables == {"apiKey": "local-dev-token"}

    work = next(e for e in envs if e.name == "work")
    assert work.base_url == "https://api.work.internal"
    assert work.variables == {"apiKey": "work-staging-token"}


def test_load_environment_config_file_yaml() -> None:
    """Test loading environments from YAML configuration fixture."""
    path = Path("tests/fixtures/environments/sample_env.yaml")
    envs = load_environment_config_file(path)
    assert len(envs) == 2

    local = next(e for e in envs if e.name == "local")
    assert local.base_url == "http://localhost:8000"
    assert local.variables == {"apiKey": "local-dev-token"}

    work = next(e for e in envs if e.name == "work")
    assert work.base_url == "https://api.work.internal"
    assert work.variables == {"apiKey": "work-staging-token"}


def test_load_environment_config_file_not_found() -> None:
    """Test FileNotFoundError when file does not exist."""
    with pytest.raises(FileNotFoundError, match="Environment configuration file not found"):
        load_environment_config_file("tests/fixtures/environments/non_existent.json")


def test_load_environment_config_file_unsupported_extension(tmp_path: Path) -> None:
    """Test ValueError when file extension is not .json, .yaml, or .yml."""
    bad_file = tmp_path / "env.txt"
    bad_file.write_text("local: http://localhost:8000", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported environment file extension"):
        load_environment_config_file(bad_file)


def test_load_environment_config_file_invalid_syntax(tmp_path: Path) -> None:
    """Test ValueError when syntax is malformed."""
    bad_json = tmp_path / "env.json"
    bad_json.write_text("{broken json", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to parse environment file"):
        load_environment_config_file(bad_json)


def test_load_environment_config_file_invalid_structure(tmp_path: Path) -> None:
    """Test ValueError when structure is not a dictionary of environments."""
    list_json = tmp_path / "list.json"
    list_json.write_text('["local", "work"]', encoding="utf-8")
    with pytest.raises(ValueError, match="Expected top-level mapping"):
        load_environment_config_file(list_json)

    not_dict_env = tmp_path / "not_dict.json"
    not_dict_env.write_text('{"local": "http://localhost:8000"}', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a dictionary"):
        load_environment_config_file(not_dict_env)

    missing_url = tmp_path / "missing_url.json"
    missing_url.write_text('{"local": {"apiKey": "xyz"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required 'baseUrl'"):
        load_environment_config_file(missing_url)


def test_merge_environments_precedence() -> None:
    """Test CLI environments override file environments with matching names."""
    file_envs = [
        ExportEnvironment(name="dev", base_url="http://dev.internal", variables={"token": "file"}),
        ExportEnvironment(name="prod", base_url="https://api.prod.com"),
    ]
    cli_envs = [
        ExportEnvironment(name="dev", base_url="http://localhost:9000"),
        ExportEnvironment(name="staging", base_url="https://staging.internal"),
    ]

    merged = merge_environments(file_envs, cli_envs)
    assert len(merged) == 3

    dev = next(e for e in merged if e.name == "dev")
    assert dev.base_url == "http://localhost:9000"

    prod = next(e for e in merged if e.name == "prod")
    assert prod.base_url == "https://api.prod.com"

    staging = next(e for e in merged if e.name == "staging")
    assert staging.base_url == "https://staging.internal"


def test_export_batch_both_with_environments(
    tmp_path: Path, sample_test_case: GeneratedTestCase
) -> None:
    """Test dual format export (--format both) with environments."""
    out_dir = tmp_path / "dual_out"
    envs = [
        ExportEnvironment(name="local", base_url="http://localhost:8000"),
        ExportEnvironment(name="work", base_url="https://api.work.internal"),
    ]
    config = ExportConfig(
        format=ExportFormat.BOTH,
        output_path=out_dir,
        environments=envs,
        collection_name="Dual Test Collection",
    )

    export_batch([sample_test_case], config)

    col_file = out_dir / "collection.json"
    http_file = out_dir / "requests.http"
    env_local = out_dir / "local.postman_environment.json"
    env_work = out_dir / "work.postman_environment.json"
    rest_env = out_dir / "http-client.env.json"

    assert col_file.exists()
    assert http_file.exists()
    assert env_local.exists()
    assert env_work.exists()
    assert rest_env.exists()

    col_data = json.loads(col_file.read_text(encoding="utf-8"))
    assert col_data["variable"] == []

    http_content = http_file.read_text(encoding="utf-8")
    assert "@baseUrl" not in http_content
    assert "{{baseUrl}}/pets/1" in http_content

    rest_data = json.loads(rest_env.read_text(encoding="utf-8"))
    assert "local" in rest_data
    assert "work" in rest_data


def test_export_batch_both_missing_output_path(sample_test_case: GeneratedTestCase) -> None:
    """Test ValueError raised when output_path is None for dual export."""
    config = ExportConfig(
        format=ExportFormat.BOTH,
        output_path=None,
    )
    with pytest.raises(ValueError, match="Output directory is required"):
        export_batch([sample_test_case], config)
