# Data Model: OpenAPI Operation Chunking

This document defines the core domain entities, schema definitions, and validation rules used by the `specprobe chunk` command.

---

## 1. Entities & Schemas

### 1.1 `ChunkMetadata`
Represents the contextual metadata attached to each individual operation chunk.

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | `str` | Yes | The endpoint URI template (e.g., `/api/v1/users/{id}`). |
| `method` | `str` | Yes | Uppercase HTTP method (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `OPTIONS`, `HEAD`, `TRACE`). |
| `tags` | `list[str]` | Yes | Associated operation tags, or empty list if absent. |
| `operationId` | `str` | Yes | Explicit operation identifier or deterministically synthesized fallback. |
| `security` | `list[dict[str, list[str]]]` | Yes | Resolved security schemes: operation-level, global fallback, or empty list if explicitly disabled (`security: []`). |
| `deprecated` | `bool` | Yes | Indicates if the operation is flagged deprecated (default `False`). |
| `source_title` | `str` | Yes | Title extracted from root `info.title` (defaults to "Untitled API"). |
| `source_version` | `str` | Yes | API version extracted from root `info.version` (defaults to "0.0.0"). |
| `estimated_tokens` | `int` | Yes | Approximate token count computed via character heuristic (~4 chars/token). |
| `warnings` | `list[str]` | Yes | List of warning strings specific to this chunk (e.g., budget overages, unsupported external references). |

### 1.2 `OperationChunk`
The atomic unit emitted per line in the JSONL output stream.

| Field | Type | Required | Description |
|---|---|---|---|
| `metadata` | `ChunkMetadata` | Yes | Operational metadata block. |
| `operation` | `dict[str, Any]` | Yes | The self-contained operation object with path-level parameters merged and operation-level parameters taking precedence. |
| `components` | `dict[str, Any]` | Yes | Component dictionary containing only `schemas` reachable from this operation. |

### 1.3 `ChunkingStats`
The aggregate statistical summary entity emitted in exclusive mode when `--stats` is specified.

| Field | Type | Required | Description |
|---|---|---|---|
| `total_operations` | `int` | Yes | Count of all operations extracted across all paths. |
| `min_tokens` | `int` | Yes | Smallest chunk token size encountered. |
| `max_tokens` | `int` | Yes | Largest chunk token size encountered. |
| `median_tokens` | `float` | Yes | Median chunk token size. |
| `avg_tokens` | `float` | Yes | Arithmetic mean of chunk token sizes. |
| `oversized_chunks` | `int` | Yes | Count of chunks whose token count exceeded `--max-tokens`. |
| `warnings` | `list[str]` | Yes | Comprehensive list of all warnings emitted across all chunks. |

---

## 2. Validation & Invariant Rules

1. **Operation Isolation Invariant**:
   - For every chunk $C_i$, the component dictionary $C_i.\text{components.schemas}$ MUST ONLY contain schemas transitively reachable from $C_i.\text{operation}$.
   - No schema unreferenced by $C_i$ may exist in $C_i.\text{components.schemas}$.
2. **Circular Reference Representation**:
   - Internal recursive references MUST retain local `$ref` pointers (e.g., `"#/components/schemas/Node"`).
   - In circular chains ($A \rightarrow B \rightarrow A$), both $A$ and $B$ exist in `components.schemas`, but recursive expansion terminates once a schema key is in the traversal visited set.
3. **Parameter Merge Order**:
   - Given path parameters $P_{path}$ and operation parameters $P_{op}$, merged parameters $P = P_{op} \cup \{p \in P_{path} \mid \forall q \in P_{op}: (p.name \neq q.name \lor p.in \neq q.in)\}$.
4. **Operation ID Synthesis Invariant**:
   - If missing, `operationId` is synthesized as `f"{method.lower()}_{sanitized_path}"`.
   - In case of collision across duplicate synthetic IDs, append `_1`, `_2`, etc.
5. **Token Count Heuristic Invariant**:
   - `estimated_tokens = max(1, round(len(canonical_json_string) / 4))`.
