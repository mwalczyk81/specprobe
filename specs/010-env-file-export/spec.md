# Feature Specification: Environment File Export for Postman and REST Client

**Feature Branch**: `010-env-file-export`

**Created**: 2026-09-21

**Status**: Draft

**Input**: User description: "Add environment file export for Postman and REST Client, replacing the current single baked-in --base-url with support for multiple named environments."

## Clarifications

### Session 2026-09-21

- Q: How should `specprobe export` handle environment file generation when no destination path is provided via `--output` (streaming to standard output)? → A: Require `--output` whenever `--env` or `--env-file` is used (exit with code 1 and a descriptive error).
- Q: Where should environment files be written when `--output` is specified as a file path rather than a directory (e.g., `--output ./tests/my_collection.json` or `--output ./tests/requests.http`)? → A: Place environment files in the parent directory of the specified output file path alongside the exported collection or `.http` document.
- Q: What file formats should be supported by the `--env-file` configuration option? → A: Support both JSON and YAML, auto-detected by `.json`, `.yaml`, or `.yml` file extension.
- Q: What default placeholder value should be populated for security credential variables in generated environment files when no custom credential values are provided in `--env-file`? → A: Reuse SecurityResolver's existing `default_placeholder` values (`<token>`, `<api_key>`, `<credentials>`) directly without introducing a new placeholder format.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Environment REST Client Export (`http-client.env.json`) (Priority: P1) 🎯 MVP

A developer exporting API test cases for VS Code REST Client needs to target multiple deployment stages (e.g. `local` and `work`) without re-exporting the `.http` file or manually editing URLs. The export command generates the `.http` request document alongside a standard `http-client.env.json` multi-environment configuration file containing the named environments. The `.http` file drops its top-level `@baseUrl = ...` line and directly references `{{baseUrl}}`, allowing the developer to switch environments instantaneously in VS Code via the environment picker.

**Why this priority**: Eliminates URL baking in `.http` files and provides immediate multi-target test execution in VS Code REST Client.

**Independent Test**: Run `specprobe export --format http -o ./tests_out --env local=http://localhost:8000 --env work=https://api.work.internal`. Inspect `./tests_out/requests.http` to verify `@baseUrl` is omitted from file headers and requests reference `{{baseUrl}}`. Inspect `./tests_out/http-client.env.json` to verify `local` and `work` environments exist with correct `baseUrl` values.

**Acceptance Scenarios**:

1. **Given** test cases and multiple environment definitions (`local`, `work`), **When** `specprobe export` runs with `--format http`, **Then** it writes `http-client.env.json` containing top-level keys for each environment with their respective `baseUrl` values.
2. **Given** test cases exported with environment files, **When** examining the emitted `.http` file, **Then** it does not contain a hardcoded `@baseUrl = ...` assignment, and all request lines reference `{{baseUrl}}`.
3. **Given** endpoints secured with API keys or tokens, **When** environment files are generated, **Then** the security credential placeholders are defined in `http-client.env.json` for each environment rather than baked into `@schemeName = ...` lines inside the `.http` file.

---

### User Story 2 - Native Postman Environment Export (`.postman_environment.json`) (Priority: P1)

A developer or QA engineer using Postman needs to import exported collections into workspaces that support switching between distinct target servers (e.g., local mock server vs. corporate staging API). The export command emits a native `.postman_environment.json` file for each specified environment alongside `collection.json`. The collection itself does not bake a concrete host into its `variable` array, referencing `{{baseUrl}}` and credential variables resolved dynamically by the selected Postman active environment.

**Why this priority**: Postman teams manage URLs and credentials via environment files; baking static URLs into collections creates synchronization issues and risk of secret leakage.

**Independent Test**: Run `specprobe export --format postman -o ./tests_out --env local=http://localhost:8000 --env work=https://api.work.internal`. Verify that `./tests_out/local.postman_environment.json` and `./tests_out/work.postman_environment.json` are valid Postman v2.1 environment JSON files, and `./tests_out/collection.json` references `{{baseUrl}}` without baking the local URL.

**Acceptance Scenarios**:

1. **Given** multiple named environments specified, **When** `specprobe export` runs with `--format postman`, **Then** it creates a `.postman_environment.json` file for each environment matching Postman's native schema (`{"name": ..., "values": [{"key": ..., "value": ..., "enabled": true}]}`).
2. **Given** a generated Postman collection, **When** inspecting `collection.json`, **Then** `baseUrl` and security credential variables are not declared as hardcoded collection-level variables, delegating variable resolution entirely to the imported `.postman_environment.json` file.
3. **Given** secured operations, **When** Postman environments are emitted, **Then** security credential variables are populated in each environment file's `values` list.

---

### User Story 3 - Unified CLI Multi-Environment Configuration & Backward Compatibility (Priority: P2)

A developer invoking `specprobe export` (or a CI pipeline running existing scripts) needs a flexible, intuitive CLI interface to specify multiple environments with optional per-environment credential values, while existing commands using `--base-url` continue to work without breaking.

**Why this priority**: Provides a clean developer experience for both simple single-URL workflows and complex multi-stage/multi-credential deployments without breaking existing pipelines.

**Independent Test**: Run export with legacy `--base-url http://localhost:8000` and verify it produces working artifacts with a default environment; run with multiple `--env` definitions and verify proper configuration parsing.

**Acceptance Scenarios**:

1. **Given** an invocation using legacy `--base-url http://localhost:8000` without explicit `--env` flags, **When** export runs, **Then** it treats it as shorthand for a single default environment (`default`), creating compatible environment artifacts (`default.postman_environment.json` and/or `http-client.env.json` with a `default` entry) without breaking callers.
2. **Given** multiple `--env` flags specified on the CLI, **When** export runs, **Then** all specified environments are parsed, validated, and serialized across both Postman and REST Client outputs.
3. **Given** dual format export (`--format both`), **When** multiple environments are provided, **Then** the output directory contains `collection.json`, `requests.http`, `http-client.env.json`, and all corresponding `.postman_environment.json` files.

---

### Edge Cases

- What happens if environment flags (`--env` or `--env-file`) are used without `--output` (streaming to stdout)? The CLI MUST exit with code 1 and a descriptive error explaining that `--output <path>` is required when exporting environments.
- What happens if an environment name contains invalid filename characters (e.g. slashes or colons)? System must sanitize environment names for Postman environment filenames.
- How are negative authentication test cases (401/403) handled? Per Constitution Principle II and Feature 007, negative auth cases use inline invalid literal values on the request itself and are explicitly excluded from variable parameterization; their behavior must remain strictly unchanged.
- What happens if duplicate environment names are supplied? The CLI must reject duplicate environment names with a clear validation error.
- What happens if both `--env` and `--env-file` specify the same environment name? CLI `--env` definitions take precedence and override values specified in `--env-file`.
- What happens if `--env-file` points to an unreadable, non-existent, or malformed file, or an unsupported file extension? The CLI MUST exit with an explicit validation error identifying the bad file path, parse failure, or unsupported format.
- What happens if `--output` is specified as a file path (e.g. `tests/collection.json` or `tests/requests.http`) instead of a directory? Environment files are written into the file's parent directory (`tests/`) alongside the exported collection or `.http` document.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support exporting environment configuration files for both Postman (`*.postman_environment.json`) and VS Code REST Client (`http-client.env.json`).
- **FR-002**: System MUST omit hardcoded `baseUrl` values from emitted `.http` files and Postman collection files when environment files are generated, relying exclusively on dynamic variable resolution via `{{baseUrl}}`.
- **FR-003**: System MUST support declaring multiple named environments in a single export invocation via repeatable `--env <name>=<url>` CLI flags (e.g., `--env local=http://localhost:8000 --env work=https://api.work.internal`), and optionally via an `--env-file <path>` configuration file supporting JSON (`.json`) and YAML (`.yaml`, `.yml`, auto-detected by extension) defining environments, target URLs, and custom credential mappings. CLI `--env` definitions take precedence over file-defined environments with identical names.
- **FR-004**: System MUST move credential placeholders entirely into environment files (`http-client.env.json` and `*.postman_environment.json`). The primary collection JSON and `.http` files MUST reference credential variables via `{{schemeName}}` without including inline placeholder declarations or `@schemeName = ...` header assignments, preventing secret leakage in version-controlled collection files. In generated environment files, credential variables MUST reuse `SecurityResolver`'s existing `default_placeholder` values (`<token>`, `<api_key>`, `<credentials>`) unless explicit credential values are supplied via `--env-file`.
- **FR-005**: System MUST maintain backward compatibility when `--base-url <url>` is provided without explicit `--env` or `--env-file` flags by treating it as shorthand for `--env default=<url>`. In this mode, the system MUST emit standard environment files containing a single `default` environment while omitting hardcoded URLs from the primary collection and `.http` files.
- **FR-006**: When exporting VS Code REST Client artifacts with environments, the system MUST emit `http-client.env.json` with top-level keys matching environment names, each mapping to a dictionary of variable keys and values.
- **FR-007**: When exporting Postman artifacts with environments, the system MUST emit a separate `.postman_environment.json` for each named environment, conforming to the Postman Environment v2.1 schema (`id`, `name`, `values`, `_postman_variable_scope`).
- **FR-008**: Dual format export (`--format both`) MUST emit both `http-client.env.json` and all `*.postman_environment.json` files into the specified output directory alongside `requests.http` and `collection.json`.
- **FR-009**: Export generation MUST remain 100% deterministic (zero-LLM per Constitution Principle II), producing identical environment files and collection artifacts for identical inputs and options.
- **FR-010**: System MUST require `--output` whenever `--env` or `--env-file` is specified, terminating execution with an error message on `stderr` and exit code 1 if `--output` is omitted.
- **FR-011**: When `--output` designates a file path rather than a directory, the system MUST write all corresponding environment files into that file's parent directory alongside the primary collection or `.http` document.

### Key Entities *(include if feature involves data)*

- **ExportEnvironment**: Represents a named deployment environment containing a name (e.g. `local`, `work`, `staging`), a target `base_url`, and optional environment-specific credential variable mappings.
- **PostmanEnvironmentFile**: Schema representing Postman's native environment file format (`name`, `values` array containing `key`, `value`, `enabled`, `type`).
- **RestClientEnvironmentFile**: Schema representing VS Code REST Client's `http-client.env.json` format (top-level environment names mapping to key-value pairs).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Exported `.http` and Postman collection files contain zero hardcoded environment URLs, enabling artifact check-in to version control without committing environment-specific hosts.
- **SC-002**: 100% of defined environments are exported in a single command run without requiring repeated `export` calls.
- **SC-003**: Developers can toggle between exported environments in VS Code REST Client and Postman without modifying any request files.
- **SC-004**: All existing export tests and golden file fixtures pass or update cleanly with verified backward-compatibility.

## Assumptions

- VS Code REST Client reads `http-client.env.json` placed in the same directory as the `.http` file or in the workspace root.
- Postman environment files are imported individually into Postman workspaces via Postman's native import mechanism.
- Security credential placeholder names (`schemeName`) continue to match those generated by `SecurityResolver`.
