# Feature Specification: AWS Bedrock LLM Gateway Support

**Feature Branch**: `009-bedrock-llm-backend`

**Created**: 2026-09-21

**Status**: Draft

**Input**: User description: "Add AWS Bedrock support as an LLM backend for the generate and audit commands' LiteLLM gateway (src/specprobe/generator/gateway.py)."

## Clarifications

### Session 2026-09-21

- Q: How should the CLI `--api-base` option in `specprobe generate` be configured so Bedrock invocations do not inadvertently receive the local LM Studio default URL? → A: Set Click `--api-base` default to `None` in `src/specprobe/cli.py`, allowing `LLMGateway` to conditionally apply `http://localhost:1234/v1` for local models and omit `api_base` for `bedrock/*` models unless explicitly provided by the user or `SPECPROBE_LLM_API_BASE`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bedrock Model Routing & Cloud Opt-In Enforcement (Priority: P1) 🎯 MVP

A developer or automated pipeline targeting AWS Bedrock specifies a `bedrock/<model-id>` model string. The system enforces SpecProbe Constitution Principle IV (cloud providers strictly opt-in) by verifying that an explicit AWS environment signal is present before initiating inference. If the required environment signal is missing, the command fails fast with a clear, descriptive error instructing the user how to configure AWS authentication.

**Why this priority**: Without this check, Bedrock models bypass cloud opt-in verification entirely (a security/governance bug), or fail ungracefully deep in the call stack.

**Independent Test**: Can be tested independently by initializing the gateway with `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` with and without AWS environment variables; verifies clean rejection when opt-in is absent, and clean validation when present.

**Acceptance Scenarios**:

1. **Given** a model string starting with `bedrock/` and no AWS opt-in environment variables set, **When** `LLMGateway` initializes or validates cloud opt-in, **Then** it raises a descriptive error explaining that Bedrock is a cloud provider requiring explicit configuration.
2. **Given** a model string starting with `bedrock/` and valid AWS environment configuration present, **When** `LLMGateway` initializes, **Then** opt-in validation passes without error.

---

### User Story 2 - Provider-Aware Endpoint Resolution & api_base Handling (Priority: P1)

A developer invoking a Bedrock model expects Bedrock's native authentication (boto3 / AWS SDK credential chain) and region resolution to function without interference from the default local LM Studio URL (`http://localhost:1234/v1`). The gateway must avoid passing `api_base` to LiteLLM for Bedrock by default, while still honoring explicit `--api-base` / `SPECPROBE_LLM_API_BASE` overrides when a custom gateway or enterprise proxy (such as Fiserv Aitrium) is in use.

**Why this priority**: Passing `http://localhost:1234/v1` to a Bedrock completion call breaks Bedrock's transport routing or results in connection errors to a nonexistent local server.

**Independent Test**: Can be tested by verifying the arguments forwarded to `litellm.completion()`: `api_base` must be omitted (`None` or not passed) for default Bedrock calls, but included when explicitly specified by the user. Existing local LM Studio models (`openai/local-model`) must continue to receive `http://localhost:1234/v1` by default.

**Acceptance Scenarios**:

1. **Given** model `bedrock/<model-id>` and no explicit `api_base` provided, **When** `gateway.complete()` calls LiteLLM, **Then** `api_base` is omitted from the call arguments.
2. **Given** model `bedrock/<model-id>` and an explicit `--api-base https://aitrium.internal.proxy/v1`, **When** `gateway.complete()` calls LiteLLM, **Then** the explicit `api_base` is passed to the call arguments.
3. **Given** the default model `openai/local-model` and no explicit `api_base`, **When** `gateway.complete()` calls LiteLLM, **Then** `api_base` defaults to `http://localhost:1234/v1` as before.

---

### User Story 3 - End-to-End CLI Integration in `generate` and `audit` (Priority: P2)

A developer uses `specprobe generate` or `specprobe audit` with `--model bedrock/<model-id>` (or `SPECPROBE_LLM_MODEL=bedrock/...`). The commands successfully route prompt completions through Bedrock, cache responses in the local disk cache (keyed on prompt, model, temperature), and return validated test cases or audit critiques.

**Why this priority**: Delivers end-to-end usability across both SpecProbe commands that invoke LLMs.

**Independent Test**: Run CLI integration tests with a mock Bedrock completion (or replay cache fixture), verifying end-to-end execution without errors and verifying disk cache hit behavior.

**Acceptance Scenarios**:

1. **Given** `specprobe generate` invoked with `--model bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` and mock completion, **Then** it generates validated test cases and records the cache entry with the Bedrock model identifier.
2. **Given** `specprobe audit` invoked with `--model bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` and mock completion, **Then** it outputs JSONL audit critique records.

---

### Edge Cases

- **Custom Bedrock Endpoints / Proxies**: When an enterprise user routes Bedrock calls through an internal proxy (e.g. Aitrium) using an explicit `--api-base`, how does the gateway behave? (It passes the explicit URL through without reverting to local defaults).
- **Missing Region**: AWS Bedrock requires an AWS region. If a user provides credentials (e.g., `AWS_ACCESS_KEY_ID`) but no region, what happens?
- **IAM Role / SSO Environments**: On AWS EC2/ECS/EKS or when using AWS IAM Identity Center (SSO), users authenticate without static access keys. The opt-in check must accommodate environment configurations that rely on instance profiles, ECS task roles, or named profiles.
- **Cache Key Consistency**: Cache records must record the exact `bedrock/<model-id>` model string and omit `api_base` in cache metadata when not specified.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST identify model identifiers starting with `bedrock/` as remote cloud models subject to SpecProbe Constitution Principle IV.
- **FR-002**: System MUST validate that an AWS region environment variable (`AWS_REGION` or `AWS_DEFAULT_REGION`) is set before permitting Bedrock completion calls. If neither variable is set, the system MUST reject the call with a descriptive error.
- **FR-003**: System MUST raise a descriptive error on missing opt-in configuration that specifically instructs the user that Bedrock cloud models require `AWS_REGION` or `AWS_DEFAULT_REGION` per SpecProbe Constitution Principle IV.
- **FR-004**: System MUST omit `api_base` from `litellm.completion()` calls when targeting `bedrock/` models, unless the user explicitly provided an `api_base` via CLI option `--api-base` or environment variable `SPECPROBE_LLM_API_BASE`.
- **FR-005**: System MUST continue to default `api_base` to `http://localhost:1234/v1` for local models (`openai/local-model` or any model where `is_local_endpoint` is true) and when no model or default model is used.
- **FR-006**: System MUST pass through user-provided `api_base` (via CLI option `--api-base` or environment variable `SPECPROBE_LLM_API_BASE`) for `bedrock/` models when explicitly specified, accommodating enterprise gateways and VPC proxies (such as Fiserv Aitrium).
- **FR-007**: Both `specprobe generate` and `specprobe audit` MUST support `bedrock/<model-id>` models via CLI `--model` option and `SPECPROBE_LLM_MODEL` environment variable.
- **FR-008**: System MUST deterministically key disk cache records using the full model identifier (including `bedrock/` prefix) and temperature, correctly storing and retrieving cached completions without live network calls.
- **FR-009**: CLI option `--api-base` in `specprobe generate` MUST default to `None`, deferring default URL assignment to `LLMGateway` based on the targeted model.

### Key Entities *(include if feature involves data)*

- **LLMGateway Configuration**: Holds resolved `model`, `api_base`, `api_key`, and `temperature`. Distinguishes between explicitly provided `api_base` vs. system default `api_base`.
- **Bedrock Model Identifier**: Model string with prefix `bedrock/` followed by AWS Bedrock model ID (e.g. `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`, `bedrock/amazon.nova-pro-v1:0`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of calls targeting `bedrock/*` models without AWS opt-in configuration are rejected before any network request is attempted.
- **SC-002**: 100% of default Bedrock calls execute without passing `http://localhost:1234/v1` as `api_base` to LiteLLM.
- **SC-003**: All existing unit and integration tests for local LM Studio and cloud providers (`openai/`, `anthropic/`, `gemini/`) continue to pass without regression.
- **SC-004**: Test execution in CI completes fully offline without requiring real AWS credentials.

## Assumptions

- Bedrock model invocations follow LiteLLM's standard prefix convention `bedrock/<model-id>`.
- LiteLLM and boto3 handle low-level AWS SigV4 signing, credential discovery, and API serialization when given valid environment variables.
- Offline CI and unit tests will mock `litellm.completion()` or use pre-recorded disk cache fixtures, adhering to Constitution Principle VI.
