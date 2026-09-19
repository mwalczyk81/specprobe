<!--
SYNC IMPACT REPORT
==================
- Version change: 1.0.0 -> 1.1.0 (Tooling Stack Amendment)
- Rationale: Replaced Poetry with uv as the mandatory build tool, virtual environment manager,
  and dependency resolver. Under the Constitution's Versioning Policy, Core Principles I-VI
  and architectural determinism/privacy guarantees remain unchanged; this amends tooling requirements
  and workflow quality gates, qualifying as a MINOR version bump.
- Technology Stack & Tooling Constraints modifications:
  * Dependency & Package Management: Replaced Poetry mandate and poetry.lock with uv and uv.lock.
- Development Workflow & Quality Gates modifications:
  * Pre-Merge Test Execution: Updated quality gate command from `poetry run pytest` to `uv run pytest`.
- Added sections: None
- Removed sections: None
- Deferred items / TODOs: None
-->

# SpecProbe Constitution

## Core Principles

### I. Clear Idiomatic Code Over Abstractions
The codebase MUST prioritize clarity, readability, and idiomatic Python 3.11+ patterns over unnecessary abstractions, speculative framework layers, or deep inheritance hierarchies.
- Code MUST remain explicit, straightforward to inspect, and simple to debug.
- Abstractions, helper wrappers, and generic layers MUST only be introduced when there is concrete, existing duplication across multiple callers—never in anticipation of hypothetical future use cases (YAGNI).
- Standard Python idioms, type annotations, and explicit function signatures MUST be preferred over metaclasses, dynamic reflection, or obfuscated indirection.

*Rationale*: High abstraction ceilings obscure system mechanics and hinder maintenance. Clear, idiomatic code ensures transparency, simpler testability, and lower cognitive load.

### II. Deterministic Artifact Generation (Zero-LLM)
The generation of Postman collections (`.json`) and REST Client (`.http`) test files MUST be fully deterministic and MUST NEVER invoke an LLM.
- Parsing OpenAPI specifications, extracting paths and operations, constructing request definitions, and rendering test file artifacts MUST be performed exclusively using deterministic Python parsers and templates.
- Identical input specifications and configuration options MUST yield identical, reproducible output artifacts every time.
- No probabilistic inference, prompt-based transformation, or external network requests are permitted within the artifact generation pipeline.

*Rationale*: API testing artifacts require 100% predictable, reproducible syntax and reliable structure. Involving probabilistic models creates drift, hallucinations, unnecessary latency, and token costs for operations that are fundamentally algorithmic.

### III. Local-First Privacy & Compute (Local Embeddings & Reranking)
Embeddings generation and candidate reranking MUST always execute locally on the host machine.
- Under no circumstances may raw API specifications, endpoint documentation, search queries, or text chunks be sent to external cloud APIs for embeddings or reranking.
- Local model runtimes and weights MUST run self-contained on the user's workstation.
- Search, indexing, and retrieval mechanisms MUST function seamlessly in offline, air-gapped environments.

*Rationale*: Proprietary API schemas frequently contain sensitive endpoints, internal data models, and business logic. Local execution guarantees complete data privacy, eliminates per-query cost, and maximizes indexing speed.

### IV. Unified Gateway, Local-Default LLM & Disk Caching
All LLM invocations across the system MUST route through LiteLLM as the single unified gateway, default to local execution, and persist responses to disk.
- LLM interactions MUST use LiteLLM (`litellm`); direct integration with vendor-specific SDKs (e.g., OpenAI, Anthropic, Google) is prohibited.
- System defaults MUST target a local LM Studio model endpoint without requiring cloud API keys or external connectivity.
- Cloud providers (e.g., OpenAI, Anthropic, Gemini) are strictly opt-in and MUST ONLY be activated when explicit API key environment variables are set by the user.
- All LLM calls MUST be cached to local disk, keyed deterministically on a cryptographic hash of the prompt/message payload and model identifier. Cached hits MUST return immediately without performing inference calls.

*Rationale*: A unified gateway prevents vendor lock-in, a local LM Studio default guarantees zero cost and privacy out of the box, opt-in cloud access respects user intent, and persistent disk caching eliminates redundant inference costs during development and automated runs.

### V. Strict Pydantic Validation, Single Retry & Operation Traceability
All probabilistic LLM outputs MUST be rigorously validated against strict Pydantic schemas, limited in retry behavior, and explicitly traceable.
- Every LLM-generated payload MUST be parsed and validated through a defined Pydantic model before use.
- If schema validation fails, the system MUST retry the LLM invocation exactly once, providing the schema validation error context to allow self-correction. If the retry fails, the operation MUST immediately fail with a descriptive error.
- Every generated test case, assertion, or scenario MUST explicitly name and link to the specific API operation (e.g., `operationId` or `METHOD /path`) it targets. Anonymous or unassociated test cases are strictly prohibited.

*Rationale*: Enforcing strict validation bounds probabilistic outputs and shields downstream pipelines from runtime errors. A single retry balances error recovery against infinite loop and cost risks. Operation-level naming ensures full traceability between specifications and generated tests.

### VI. Comprehensive Testing (Every Feature Ships with Tests)
Every feature, command, and module MUST ship with comprehensive automated test coverage before it is considered ready for release or integration.
- No code change or feature implementation shall be merged without corresponding automated tests.
- Test suites MUST be implemented using `pytest`.
- Postman and `.http` exporters MUST include deterministic unit and regression tests verifying exact structural fidelity against standard OpenAPI sample specifications.
- Test suites executing in standard CI pipelines MUST NOT require live LLM instances; all LLM-dependent tests MUST use disk cache fixtures or deterministic mocks.

*Rationale*: SpecProbe is a tool designed to verify and probe API specifications. A testing tool must hold itself to uncompromising standards of correctness and reliability.

## Technology Stack & Tooling Constraints

SpecProbe development and execution environment is strictly standardized on the following tooling:

- **Runtime**: Python 3.11 or higher (`>= 3.11`). Modern language capabilities, built-in structural pattern matching, and comprehensive type hinting must be utilized.
- **Dependency & Package Management**: uv is the mandatory build tool, virtual environment manager, and dependency resolver. All dependencies must be locked in `uv.lock`.
- **CLI Framework**: Click (`click`) is the standard CLI framework for all user-facing commands, argument validation, and subcommands.
- **Testing Framework**: pytest (`pytest`) is the standard testing engine for unit, functional, and integration tests.
- **LLM Gateway**: LiteLLM (`litellm`) provides uniform routing, parameter mapping, and local/cloud provider abstraction.
- **Data Modeling & Validation**: Pydantic (`pydantic`) defines all system schemas, configuration models, and LLM output targets.
- **CLI Interface Protocols**: CLI commands must accept arguments/options cleanly, write primary user output to standard output (`stdout`), direct logging and diagnostics to standard error (`stderr`), and return non-zero exit codes on failure.

## Development Workflow & Quality Gates

All contributions and feature workflows MUST satisfy the following quality gates:

- **Pre-Merge Test Execution**: `uv run pytest` must execute and pass 100% of test cases cleanly.
- **Deterministic Pipeline Verification**: Exporters for Postman collections and `.http` files must pass verification tests without invoking network requests or mock LLM sessions.
- **Local Privacy Verification**: Embedding and reranking tests must confirm that no remote outbound sockets are opened.
- **Cache Hit Integrity**: Disk-based LLM caching logic must be verified for exact hit retrieval and serialization correctness.
- **Traceability Audit**: Generated test artifacts must be inspected to ensure every generated test case explicitly declares its target operation identifier.
- **Code Review**: PRs and reviews must verify compliance with idiomatic Python standards, avoidance of premature abstraction, and adherence to this constitution.

## Governance

This Constitution is the supreme design and implementation policy for SpecProbe. It supersedes all informal discussions, conventions, and ad-hoc architectural decisions.

- **Authority**: All developers, code reviews, and automated AI agents must comply with the principles and constraints established herein. Complexity, non-idiomatic abstractions, or bypasses of local-first privacy must be rejected unless granted a constitutional amendment.
- **Amendment Procedure**: Any change to principles, technology constraints, or quality gates requires a formal proposal, review of impact, and documentation update.
- **Versioning Policy**: This Constitution follows Semantic Versioning:
  - **MAJOR**: Incompatible principle changes, relaxation of privacy/determinism guarantees, or breaking architectural shifts.
  - **MINOR**: Addition of new principles, new supported output formats, or expanded tooling requirements.
  - **PATCH**: Non-semantic clarifications, typo corrections, and minor wording refinements.
- **Compliance Review**: Every implementation plan (`plan.md`) and task breakdown (`tasks.md`) produced by Spec Kit workflows must explicitly verify compliance with these principles before code execution begins.

**Version**: 1.1.0 | **Ratified**: 2026-09-18 | **Last Amended**: 2026-09-19
