# specprobe

[![CI](https://github.com/mwalczyk81/specprobe/actions/workflows/ci.yml/badge.svg)](https://github.com/mwalczyk81/specprobe/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mwalczyk81/specprobe/graph/badge.svg)](https://codecov.io/gh/mwalczyk81/specprobe)

A CLI that turns an OpenAPI spec into a searchable, locally-indexed knowledge base, generates schema-validated API test cases from it, exports runnable test suites with environment configs, and spins up a local mock server to validate them against — no cloud calls required unless you opt in.

```
spec.yaml ──→ chunk ──→ index ──→ search ──→ generate ──→ export ──→ run / mock
             (parse)   (embed)   (retrieve)  (LLM + validate)  (artifacts & envs)   (local test server)
                                                    │
                                                    └───→ audit (spec vs artifact gap analysis)
```

## What it does

**`chunk`** — Deterministically decomposes an OpenAPI 3.0/3.1 spec into one self-contained JSON object per operation: method, path, merged parameters, pruned `$ref`-resolved schemas, referenced `components.securitySchemes`, tags, security requirements, and a token estimate. No LLM involved — same spec in, same chunks out, every time.

**`index`** — Embeds each chunk (dense + BM25 sparse vectors, via local ONNX models through FastEmbed) into an on-disk Qdrant collection. Runs fully offline; no spec text or embeddings ever leave the machine.

**`search`** — Natural-language retrieval over the index, in three modes: `dense` (cosine similarity), `hybrid` (dense + sparse fused with RRF), or `hybrid-rerank` (hybrid retrieval + local cross-encoder reranking). Supports metadata filters (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`).

**`generate`** — Takes `search --full` output and asks an LLM to produce a happy-path test case per operation: concrete request fixtures, expected status/headers, and a schema-shape assertion (hardened to valid JSON Schema Draft 7). Generates negative test cases by default: authentication negatives (401 missing credentials and 403 protocol-valid invalid credentials for secured operations, controlled by `--negative-auth`/`--no-negative-auth`), 404 resource-not-found negatives (mutating leaf path parameters to nonexistent sentinels, controlled by `--not-found`/`--no-not-found`), and 400 invalid-input negatives (minimal schema-violating body mutations for JSON-body-constrained operations, controlled by `--invalid-input`/`--no-invalid-input`). All negative flags default to enabled. Every output is validated against a strict Pydantic schema; a validation failure triggers exactly one self-correcting retry with the error fed back to the model, then the operation is marked failed and the batch continues. Calls are cached to disk (SHA-256 of messages + model + temperature) so repeat runs and CI are zero-cost and don't need a live model.

**`export`** — Deterministically transforms `GeneratedTestCase` JSONL records into runnable test artifacts: Postman Collection v2.1 JSON (with primary tag folders and embedded `pm.test` assertions) and VS Code REST Client `.http` files (with `###` request blocks and metadata documentation). Exports native multi-environment configuration files (`<env>.postman_environment.json` per Postman Environment v2.1 schema with deterministic UUIDv5, and `http-client.env.json` for REST Client) via repeatable `--env <name>=<url>` options or `--env-file <path>` (supporting JSON and YAML). Replaces hardcoded URLs with dynamic `{{baseUrl}}` references and extracts security credentials into environment variables (`{{schemeName}}` / `@schemeName`). Serializes negative test cases as sibling items (`[401]`, `[403]`, `[404]`, and `[400]` item prefixes in Postman; `# @name <op>_401`, `_403`, `_404`, `_400` in REST Client) with matching status assertions; unlike 401/403 (which use inline invalid literals and are excluded from variable parameterization), 404 and 400 test cases retain full credential parameterization since they assert resource lookup and input validation rather than authentication. Strictly zero-LLM, zero-network, and 100% byte-identical across runs per Constitution Principle II.

**`mock`** — Launches a lightweight, local, multi-threaded HTTP mock server (`http.server.ThreadingHTTPServer`) backed by positive `GeneratedTestCase` fixtures (passed via file argument or piped from stdin). Each positive fixture serves its path template, so a fixture for `/pets/{petId}` answers `/pets/123`, `/pets/7`, or any other single-segment value. Exact paths win over templates, and more literal templates win over less literal ones (`/pets/search` beats `/pets/{petId}`). 404 fixtures are served at their own sentinel path, so the exported not-found tests get a real 404. Paths are percent-decoded and trailing slashes normalized before matching, and each route returns its canned status code and headers. When a test case defines a Draft 7 JSON Schema shape (`response.schema_shape`), the mock server uses an in-memory schema synthesizer to dynamically emit valid sample JSON payloads matching the schema (types, properties, required fields, nested objects, arrays, enums, `allOf`/`anyOf`/`oneOf` composition, `pattern`, and `minLength`/`maxLength`) so exported Postman tests pass their `pm.response.to.have.jsonSchema(...)` assertions out of the box. Features a rich terminal startup banner, detailed access logging, and helpful 404/405 diagnostic error bodies listing available routes and allowed methods. The mock does not check auth headers or request bodies, so the exported 401/403/400 negative tests fail against it by design. The happy-path and 404 tests are the ones to run against it.

**`audit`** — Compares an OpenAPI spec against an existing test artifact (Postman collection or `.http` file) for coverage gap analysis, via a hybrid pipeline (deterministic structural diff + per-operation LLM critique through the same LiteLLM gateway), streaming JSONL critique records to stdout with an optional `--summary` human-readable table.

## Design principles

- **Local-first by default.** Embeddings and reranking always run on-device. The LLM gateway defaults to a local LM Studio endpoint (`http://localhost:1234/v1`) with no API key required; cloud providers (OpenAI, Anthropic, Gemini, AWS Bedrock) are strictly opt-in and refuse to run without the matching `*_API_KEY` (or `AWS_REGION` / `AWS_DEFAULT_REGION` for Bedrock) env var.
- **Deterministic where it can be.** Chunking and exported test artifacts are pure parsing/templating — no LLM, no drift, reproducible byte-for-byte.
- **One gateway.** All model calls route through [LiteLLM](https://github.com/BerriAI/litellm), so switching between local and cloud models is a `--model`/`--api-base` flag, not a code change.

Full rationale lives in [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## Install

Requires Python 3.11+. Dependency management is [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run specprobe --help
```

## Quickstart

```bash
# 1. Chunk a spec
uv run specprobe chunk petstore.yaml > chunks.jsonl

# 2. Build the local index
uv run specprobe index chunks.jsonl

# 3. Search it
uv run specprobe search "cancel a pending order" --mode hybrid-rerank --limit 3

# 4. Generate validated test cases from semantic search matches
uv run specprobe search "cancel a pending order" --full --limit 3 \
  | uv run specprobe generate

# 5. Spec-wide generation: extract an entire spec unranked and generate tests for all operations
#    (saved to a file so export and mock can both reuse it without re-running the LLM)
uv run specprobe search --source-title "Petstore API" --full \
  | uv run specprobe generate > cases.jsonl

# 6. Export test cases to runnable Postman collection, REST Client .http files, and environment configs
uv run specprobe export cases.jsonl --format both --output ./exported_tests \
  --env local=http://127.0.0.1:8000 --env staging=https://staging.example.com

# 7. Start the local mock server to run the exported happy-path and 404 tests against
uv run specprobe mock cases.jsonl --port 8000
# Or pipe directly from generation without intermediate files:
# uv run specprobe search --source-title "Petstore API" --full \
#   | uv run specprobe generate \
#   | uv run specprobe mock --port 8000

# 8. Audit an existing test artifact against the spec for coverage gaps
uv run specprobe audit ./exported_tests/collection.json --spec petstore.yaml --summary
```

`generate` streams one JSON Lines object per successful test case to stdout and per-operation error diagnostics to stderr, which can be piped directly into `export` or `mock` to produce runnable test artifacts or spin up a local mock server without intermediate files.

## CLI reference

| Command | Purpose | Key options |
|---|---|---|
| `chunk <spec_file>` | Parse a spec into JSONL chunks | `--schema-depth`, `--max-tokens`, `--op <id>` (spot-check one operation), `--stats` (summary table instead of chunks) |
| `index [chunk_file]` | Ingest chunks into the vector store (file arg or stdin) | `--index-dir`, `--stats` (collection health/counts) |
| `search [query]` | Natural-language retrieval or unranked filter-only spec extraction | `--mode {dense,hybrid,hybrid-rerank}`, `-n/--limit`, `--tag`, `--method`, `--deprecated/--no-deprecated`, `--source-title`, `--source-version`, `--full`, `--index-dir` |
| `generate [results_file]` | LLM test-case generation from search results (file arg or stdin) | `--model`, `--api-base`, `--temperature`, `--max-tokens`, `--timeout`, `--cache-dir`, `--no-cache`, `--negative-auth/--no-negative-auth`, `--not-found/--no-not-found`, `--invalid-input/--no-invalid-input` |
| `export [test_cases_file]` | Transform generated test cases into runnable Postman or REST Client artifacts (file arg or stdin) | `--format {both,postman,http}`, `-o/--output <path/dir>`, `--collection-name <name>`, `--base-url <url>`, `--env <name>=<url>`, `--env-file <path>` |
| `mock [test_cases_file]` | Run a local multi-threaded HTTP mock server serving canned test cases and synthesized JSON schemas (file arg or stdin) | `-p/--port <port>`, `-h/--host <host>` |
| `audit [artifact_file]` | Compare a spec against test artifacts for coverage gaps (file arg or stdin) | `--index-dir`, `--spec`, `--summary`, `--no-cache`, `--cache-dir`, `--model`, `--api-base` |

When `search` is called without a `<query>`, it operates in filter-only mode: all operations matching the provided metadata filter(s) are retrieved unranked (`score: 0.0`) with unlimited pagination by default (or respecting explicit `-n/--limit`). Either `<query>` or at least one metadata filter must be provided.

Every command also accepts input via stdin where a file argument is optional, so all stages pipe directly into each other.

## Configuration

The LLM, cache, and index settings can be set via environment variable instead (flag takes precedence). `audit` has no `--max-tokens`/`--timeout` flags but honors the matching env vars. The negative-test toggles (`--negative-auth`, `--not-found`, `--invalid-input`) and `audit`'s `--spec`/`--summary` are flag-only.

| Env var | Default |
|---|---|
| `SPECPROBE_LLM_MODEL` | `openai/local-model` |
| `SPECPROBE_LLM_API_BASE` | `http://localhost:1234/v1` (omitted for Bedrock) |
| `SPECPROBE_LLM_API_KEY` | *(none)* |
| `SPECPROBE_LLM_TEMPERATURE` | `0.0` |
| `SPECPROBE_LLM_MAX_TOKENS` | `16384` (a completion truncated at this limit fails that operation) |
| `SPECPROBE_LLM_TIMEOUT` | `600` seconds per completion |
| `SPECPROBE_CACHE_DIR` | `.specprobe/cache` |
| `SPECPROBE_AUDIT_CACHE_DIR` | `.specprobe/cache/audit` |
| `SPECPROBE_NO_CACHE` | `false` |
| `SPECPROBE_INDEX_DIR` | `.specprobe/index` |

To use a cloud model, set `--model openai/gpt-4o` (or `anthropic/...`, `gemini/...`, or `bedrock/...`) and the corresponding credentials/configuration:
- For OpenAI, Anthropic, or Gemini: set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`.
- For AWS Bedrock: set `--model bedrock/<model-id>` (e.g. `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`) and ensure `AWS_REGION` or `AWS_DEFAULT_REGION` is configured. Bedrock calls omit `--api-base` by default to use native AWS SDK regional routing, but an explicit `--api-base` (or `SPECPROBE_LLM_API_BASE`) can be passed to route through an enterprise proxy (e.g. Fiserv Aitrium).

Omitting the required environment variable fails fast with an explanatory error rather than silently falling back.

## Development

```bash
uv run pytest                      # full test suite (unit, integration, property tests)
uv run ty check src/               # static type checking
uv run ruff check .                # lint
uv run ruff format --check .       # format check
uv run pre-commit run --all-files  # git hooks validation
```

Feature work follows a spec-first workflow — see `specs/` for the spec, plan, and task breakdown behind each feature, and `.specify/memory/constitution.md` for the constraints every change is checked against.

## Project layout

```
src/specprobe/
├── audit/       # Spec-vs-artifact coverage gap analysis and LLM critique
├── chunker/     # OpenAPI parsing, schema pruning, token estimation
├── exporter/    # Deterministic Postman and REST Client artifact & environment serializers
├── formatters/  # Output serialization (JSONL, etc.)
├── generator/   # LLM gateway, prompt synthesis, validation/retry, disk cache
├── index/       # FastEmbed embedding + Qdrant storage
├── mock/        # Local HTTP mock server, route matching, schema synthesizer
├── search/      # Multi-mode retrieval engine
├── models.py    # Shared Pydantic models
└── cli.py       # Click command group
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
