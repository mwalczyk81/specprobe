# Feature Specification: Local Vector Indexing & Semantic Search

**Feature Branch**: `002-index-embed`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: "A `specprobe index` command that reads the JSONL chunk stream produced by `specprobe chunk` (via stdin or a file argument) and builds a local, persistent vector index of the operation chunks. Indexing is idempotent: re-indexing the same spec replaces its previous chunks rather than duplicating them, keyed on source title, source version, and operationId. A companion `specprobe search` command takes a natural-language query plus optional filters (tag, method, deprecated, source title/version) and returns the top-N matching operation chunks ranked by relevance. Search supports three retrieval modes selectable by flag: dense-only, hybrid (dense plus keyword/sparse), and hybrid with a reranking pass over the top candidates, so retrieval quality can be compared across modes later. Results are inspectable as JSON, showing each match's operationId, path, method, and relevance score, so retrieval quality can be verified before anything reaches a generation step. Indexing and search run entirely locally: no network calls, no LLM invocations. The index persists on disk across CLI invocations. An `--stats` mode on `specprobe index` reports collection size, per-source-spec chunk counts, and index health."

## Clarifications

### Session 2026-09-19
- Q: When re-indexing a specification, how should operations that were removed from the updated specification be handled? → A: Spec-level replacement: Purge all existing chunks for the matching (source_title, source_version) before writing the incoming batch, ensuring deleted operations do not linger as orphans.
- Q: What level of detail should 'specprobe search' JSON output include by default? → A: Compact by default with opt-in full payload: Emit match metadata and score (operationId, path, method, score, tags, summary, source_title, source_version), with a --full flag to include complete chunk bodies and schemas.
- Q: Where should specprobe index and specprobe search store and look for the index directory by default when --index-dir is not specified? → A: Project-local .specprobe/index in the current working directory (overrideable via --index-dir option or SPECPROBE_INDEX_DIR environment variable).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Idempotent Local Vector Indexing of Operation Chunks (Priority: P1)

As an API developer, tester, or automation engineer, I want to index the JSONL operation chunks produced by `specprobe chunk` into a persistent local vector database, so that my API operations are prepared for semantic retrieval without sending any data to external cloud services.

**Why this priority**: Indexing is the foundational ingestion engine. Without local persistent vector storage and idempotent upsert guarantees, no downstream semantic search, comparative evaluation, or test generation can take place.

**Independent Test**: Can be tested independently by feeding a JSONL chunk file or piping `specprobe chunk <file> | specprobe index` into `specprobe index`, verifying that vector embeddings and metadata records are saved to the local persistent store on disk, and confirming that indexing the same file a second time updates existing records rather than duplicating them.

**Acceptance Scenarios**:

1. **Given** a stream of valid JSONL operation chunks from `stdin`, **When** the user runs `specprobe chunk <spec> | specprobe index`, **Then** the system parses the chunks, generates dense vector representations locally, and stores them in a persistent disk index, exiting with code 0.
2. **Given** a path to a JSONL chunk file on disk, **When** the user runs `specprobe index <path/to/chunks.jsonl>`, **Then** the system reads the file, indexes all operation chunks, and commits them to the persistent disk index.
3. **Given** an existing index containing operations from `Petstore API v1.0.0`, **When** the user re-indexes `Petstore API v1.0.0` (with identical, updated, or removed operation chunks), **Then** the system performs a spec-level replacement by purging prior chunks matching `(source_title, source_version)` before writing the new batch, ensuring that removed or renamed operations do not linger as orphans.
4. **Given** an existing index with operations from multiple specifications (e.g. `Billing API v2.0` and `Users API v1.0`), **When** `Billing API v2.0` is re-indexed, **Then** only `Billing API v2.0` chunks are replaced or updated; `Users API v1.0` chunks remain untouched.
5. **Given** invalid JSONL input or a non-existent chunk file, **When** the user runs `specprobe index`, **Then** the system reports a descriptive error message on standard error and exits with code 1 without corrupting existing index data.

---

### User Story 2 - Semantic and Filtered Search with Multi-Mode Retrieval (Priority: P2)

As a developer exploring an API surface, I want to query the indexed operations using natural language with optional metadata filters across three selectable retrieval modes (`dense`, `hybrid`, `hybrid-rerank`), so that I can find the most relevant endpoints and evaluate retrieval quality before test generation.

**Why this priority**: Semantic retrieval is the primary consumption mechanism. Supporting selectable search strategies allows developers to benchmark sparse vs. dense vs. reranked retrieval quality across varied API query structures (e.g., semantic intent vs. exact path/parameter terms).

**Independent Test**: Can be tested independently by executing `specprobe search "<query>"` against a pre-populated index with each retrieval mode (`--mode dense`, `--mode hybrid`, `--mode hybrid-rerank`), verifying that relevant matches are returned as JSON with similarity scores, and confirming that metadata filters (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`) properly narrow the candidate pool.

**Acceptance Scenarios**:

1. **Given** an index populated with API operations, **When** the user runs `specprobe search "find a pet by its identifier"`, **Then** the system returns the top-N matching operation chunks formatted as compact JSON by default, sorted by relevance score in descending order, emitting match metadata and scores (`operationId`, `path`, `method`, `score`, `tags`, `summary`, `source_title`, `source_version`) without embedding full chunk schema bodies.
2. **Given** an explicit `--mode dense` flag, **When** the user executes a search, **Then** the system performs pure dense vector semantic similarity search using local query embeddings.
3. **Given** an explicit `--mode hybrid` flag, **When** the user executes a search, **Then** the system combines dense vector semantic search with sparse keyword/lexical matching, yielding balanced ranking for queries with both technical keywords and conceptual descriptions.
4. **Given** an explicit `--mode hybrid-rerank` flag, **When** the user executes a search, **Then** the system retrieves initial top candidates via hybrid search, applies a local reranking pass over those candidates, and outputs the reranked list with updated relevance scores.
5. **Given** metadata filter options (e.g. `--method GET --tag pets --no-deprecated`), **When** the user executes a search query, **Then** only operations that satisfy all active filter criteria are considered and returned in the result set.
6. **Given** an index that contains operations from multiple API specifications, **When** the user filters by `--source-title "Petstore API"` and `--source-version "1.2.0"`, **Then** only operations belonging to that specific API version are returned.
7. **Given** a `--limit <N>` argument (defaulting to 5), **When** the search executes, **Then** no more than `N` matches are returned.
8. **Given** an explicit `--full` flag, **When** the user runs `specprobe search "query" --full`, **Then** the system includes the complete `OperationChunk` data payload (parameters and pruned schemas) under a `chunk` field in each returned result object.
9. **Given** a search query with no matching operations (or filters that exclude all results), **When** search executes, **Then** the system outputs an empty JSON results array `[]` and exits with code 0.

---

### User Story 3 - Index Health and Collection Diagnostics via `--stats` (Priority: P3)

As an engineer managing local index storage, I want to inspect the size, composition, and health of my persistent vector index, so that I know which specification versions are indexed and whether the store is consistent.

**Why this priority**: Operational visibility is essential for understanding index footprint, verifying that idempotency succeeded, detecting schema/index mismatches, and debugging multi-spec collections.

**Independent Test**: Can be tested independently by running `specprobe index --stats` against an empty, partially populated, and fully populated index, verifying that human-readable summary metrics are printed to standard output.

**Acceptance Scenarios**:

1. **Given** an active index containing operation chunks, **When** the user runs `specprobe index --stats`, **Then** the system outputs a summary displaying: total indexed operations count, total unique source specifications, breakdown of chunk counts per specification (`source_title` and `source_version`), vector dimension details, and index storage health status.
2. **Given** an empty index or an environment where no index has been created yet, **When** the user runs `specprobe index --stats`, **Then** the system reports that the index is empty (0 operations) without throwing an error or crashing.
3. **Given** `--stats` mode is invoked, **When** execution completes, **Then** the command operates in exclusive inspection mode without attempting to read from `stdin` or ingest chunks.

---

### Edge Cases

- **Piping from `specprobe chunk`**: The index command must handle standard input streams dynamically, detecting EOF without blocking indefinitely when stdin is empty or malformed.
- **Empty JSONL Stream**: When standard input or a provided chunk file contains zero lines or only whitespace, the indexer must emit an informational message and complete with exit code 0 without modifying the index.
- **Malformed Lines in JSONL Stream**: If one line in a multi-line JSONL stream is invalid JSON, the system must report a parsing error identifying the line number, preserve previously indexed specifications, and fail safely without leaving a half-written corrupt index.
- **Duplicate Chunks Within the Same Ingestion Batch**: If the input stream contains multiple chunks with the exact same compound key `(source_title, source_version, operationId)`, the last occurrence in the stream wins, maintaining unique records.
- **Search Queries on Uninitialized Index**: Running `specprobe search` when no index directory exists on disk must return a clear, user-facing error message (e.g. `Error: Index not found. Run 'specprobe index' first.`) and exit with code 1.
- **Very Short or Special Character Queries**: Search queries containing punctuation, single characters, or stopwords must not crash the keyword or vector search components.
- **Conflicting Filter Combinations**: Specifying conflicting filters (e.g. `--method GET --method POST` or mutually exclusive criteria) must validate cleanly or narrow to an empty result list without process errors.
- **Index Directory Concurrency / Re-entrancy**: Index operations must ensure atomic writes or directory-level consistency so subsequent searches read a consistent snapshot of the index.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `specprobe index` CLI command that accepts JSONL operation chunk data via standard input (`stdin`) or via an optional file path argument.
- **FR-002**: System MUST persist and locate index data in a project-local directory `.specprobe/index` in the current working directory by default, configurable via `--index-dir` CLI option or `SPECPROBE_INDEX_DIR` environment variable.
- **FR-003**: System MUST enforce idempotency during indexing: re-indexing an existing specification matching `(source_title, source_version)` MUST purge all prior chunks belonging to that specification version before committing the new batch, ensuring deleted or renamed operations do not persist as orphans.
- **FR-004**: System MUST construct searchable text representations for each operation chunk that incorporate its method, path, operationId, tags, summary, description, and key parameter/response schema fields.
- **FR-005**: System MUST compute dense vector embeddings for indexed chunks locally using a local embedding model, with zero outbound network calls and zero cloud API invocations.
- **FR-006**: System MUST persist both vector representations and chunk metadata (including full raw chunk payload, `operationId`, `path`, `method`, `tags`, `deprecated`, `source_title`, and `source_version`) in the local index store.
- **FR-007**: System MUST provide a `specprobe search` CLI command that accepts a natural language query string as an argument.
- **FR-008**: System MUST support three selectable retrieval modes via `--mode` option on `specprobe search`:
  - `dense`: Pure dense vector similarity search using cosine similarity over local embeddings.
  - `hybrid`: Combined dense vector search and sparse lexical/keyword scoring (using rank fusion or normalized score combination).
  - `hybrid-rerank`: Initial candidate retrieval via hybrid mode followed by a local cross-encoder / reranker scoring pass over the top candidate pool.
- **FR-009**: System MUST default to `hybrid` retrieval mode when `--mode` is omitted.
- **FR-010**: System MUST support filtering search results by the following optional CLI options:
  - `--tag <tag>`: Filter to operations containing the specified tag.
  - `--method <method>`: Filter to operations matching the specified HTTP method (case-insensitive, matched uppercase).
  - `--deprecated / --no-deprecated`: Filter by deprecation status.
  - `--source-title <title>`: Filter to operations from the specified source API title.
  - `--source-version <version>`: Filter to operations from the specified source API version.
- **FR-011**: System MUST provide a `--limit <int>` (or `-n <int>`) option on `specprobe search` defaulting to 5, capping the maximum number of matches returned.
- **FR-012**: System MUST format `specprobe search` output by default as compact, structured, inspectable JSON written to standard output (`stdout`), emitting an array of result objects containing:
  - `operationId`: Operation identifier.
  - `path`: Endpoint URI template.
  - `method`: HTTP method in uppercase.
  - `score`: Numeric relevance score (normalized or rank-based score reflecting match strength).
  - `tags`: List of operation tags.
  - `summary`: Short summary string (or null if absent in operation).
  - `source_title`: API title.
  - `source_version`: API version.
- **FR-013**: System MUST provide a `--full` flag on `specprobe search` to include the complete `OperationChunk` data payload (parameters, request bodies, responses, and pruned schemas) under a `chunk` field in each result object.
- **FR-014**: System MUST provide a `--stats` flag on `specprobe index` that operates in exclusive diagnostic mode, reporting total collection size, breakdown of chunk counts per specification, vector dimensionality, and index health.
- **FR-015**: System MUST execute all search and indexing workflows fully locally without calling any LLM, cloud endpoint, or external service, strictly complying with the local-first principle.
- **FR-016**: System MUST exit with code 0 on successful indexing and successful search queries (including searches that yield zero matches).
- **FR-017**: System MUST exit with code 1 and emit a descriptive diagnostic message to standard error (`stderr`) when index files are missing, input files cannot be opened, or malformed data is encountered.

### Key Entities *(include if feature involves data)*

- **Indexed Operation Record**: The persistent database entity representing an indexed chunk. Contains the unique compound key `(source_title, source_version, operationId)`, the dense vector embedding, sparse token representations, filter metadata attributes (`path`, `method`, `tags`, `deprecated`, `source_title`, `source_version`), and the raw `OperationChunk` JSON payload.
- **Search Query & Filter Context**: The runtime entity capturing the user's search intent. Includes the query string, requested retrieval mode (`dense`, `hybrid`, `hybrid-rerank`), candidate limit $N$, and active metadata predicates (`tag`, `method`, `deprecated`, `source_title`, `source_version`).
- **Search Match Result**: The formatted output entity representing a matched operation. Contains `operationId`, `path`, `method`, `score`, `tags`, `summary`, and specification provenance (`source_title`, `source_version`). When `--full` is specified, also embeds the full `OperationChunk` payload under `chunk`.
- **Index Health & Statistics Report**: The aggregate diagnostic entity summarizing index status: total indexed operations, unique specifications breakdown, vector model metadata, store integrity, and disk footprint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid operation chunks streamed from `specprobe chunk` can be ingested and indexed into persistent local storage via shell piping (`specprobe chunk ... | specprobe index`) or file argument without lost records.
- **SC-002**: Re-indexing an existing specification containing $M$ operations performs an idempotent replace, resulting in exactly $M$ operations stored with 0 duplicate records.
- **SC-003**: Semantic queries return relevant operations matching natural language intent across dense, hybrid, and reranked modes, with top results verifiable via inspectable JSON relevance scores.
- **SC-004**: Metadata filtering (`--tag`, `--method`, `--deprecated`, `--source-title`, `--source-version`) achieves 100% precision: 0 returned results violate any active filter constraint.
- **SC-005**: Query execution in dense and hybrid retrieval modes completes in under 250 milliseconds for collections containing up to 1,000 operations.
- **SC-006**: Index and search commands execute 100% offline with zero outbound network requests and zero LLM invocations.
- **SC-007**: When executed with `--stats`, `specprobe index` outputs collection metrics and health diagnostics in under 100 milliseconds.

## Assumptions

- **Local Compute Environment**: The user's workstation has sufficient CPU and memory resources to run lightweight local embedding models and lexical indexing without requiring dedicated GPU hardware.
- **Index Storage Location**: By default, index files are stored in a `.specprobe/index` directory in the current working directory, overrideable via CLI option `--index-dir` or environment variable `SPECPROBE_INDEX_DIR`.
- **Chunk Format Conformance**: Input to `specprobe index` conforms to the JSON Lines format emitted by `specprobe chunk` (each line serializing an `OperationChunk` object containing `metadata`, `operation`, and `components`).
- **Dense Embedding Model**: A compact, standard local model provides high-quality semantic representations for API descriptions and operation metadata while maintaining fast local inference.
- **Sparse/Lexical Scoring**: Hybrid search combines semantic similarity with standard lexical keyword scoring (e.g. BM25 or token matching) using reciprocal rank fusion or weighted scoring.
- **Reranker**: The reranking pass operates locally over the top candidate pool (e.g. top 20 candidates) to refine ranking before returning the final top-N matches.
