# Data Model: Higher-Fidelity Mock Response Synthesis

**Feature**: `012-mock-response-synthesis` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/spec.md)

This feature introduces no persisted entities, Pydantic models, or storage — `synthesize_sample_from_schema` remains a pure function over an in-memory JSON Schema Draft 7 dict. What follows is the domain model for the *value-selection logic* itself: the lookup table and the piece of recursion state the synthesizer now carries.

---

## 1. Format → Representative Value Table

A fixed, module-level constant mapping recognized `format` strings to their representative literal (see [research.md §1](research.md#1-format-aware-representative-literals) for source/rationale of each value). Not user-configurable, not schema-derived — a closed lookup table.

| `format` (key) | Representative value (literal) | JSON type |
|-----------------|----------------------------------|-----------|
| `date-time` | `"2024-01-01T00:00:00Z"` | string |
| `date` | `"2024-01-01"` | string |
| `email` | `"user@example.com"` | string |
| `uuid` | `"3fa85f64-5717-4562-b3fc-2c963f66afa6"` | string |
| `uri` | `"https://example.com/sample"` | string |
| `url` | `"https://example.com/sample"` | string |
| `ipv4` | `"203.0.113.1"` | string |

A `format` value not in this table (e.g. `hostname`, `ipv6`, `time`, `regex`, or any typo/case variant) is treated as absent — synthesis falls through to the key-based fallback (§2).

---

## 2. Key Resolution State

A single piece of state threaded through the existing recursive descent, representing "the key of the nearest enclosing object property, if any."

| Attribute | Type | Lifecycle |
|-----------|------|-----------|
| `key` | `str \| None` | `None` at the root call (`synthesize_sample_from_schema`). Set to the property's own name whenever `_synthesize_object` recurses into one of its `properties[name]` values. Passed through unchanged (inherited) whenever `_synthesize_array` recurses into its `items` schema. Never composed into a path (e.g. never `"address.city"`) — always the single nearest key. |

**Resolution outcome for a plain string node** (no `format`/`enum`/`const`, and no `example`/`default` short-circuit):

| `key` at that node | Emitted value |
|---------------------|----------------|
| `"name"` (or any non-`None` string) | `"sample_name"` (`f"sample_{key}"`) |
| `None` (no enclosing property anywhere — bare root string schema, or a root-level array of plain strings) | `"sample_value"` (fixed literal, per FR-004a) |

---

## 3. Value-Selection Precedence (per schema node)

Ordered list of checks the synthesizer performs for any single schema node, first match wins (unchanged steps carried from the existing implementation are marked *existing*; new steps are marked *new*):

1. **`$ref`** *(existing)* — resolve the local reference and recurse into the resolved node (with the same `key`).
2. **`const`** *(existing)* — return the literal value.
3. **`enum`** *(existing)* — return the first listed value.
4. **`example`** *(new, FR-005)* — return the literal value verbatim, for a node of any type.
5. **`default`** *(new, FR-006/FR-007)* — return the literal value verbatim, only if `example` was absent.
6. **Type-based dispatch** *(existing, with two additions)*:
   - `object` → recurse per-property, own key set for each (§2).
   - `array` → recurse into `items` once, `key` inherited unchanged (§2).
   - `string`, `format` in the table (§1) *(new, FR-001/FR-003)* → the table's literal.
   - `string`, no `format`/`enum`/`const` *(new, FR-004/FR-004a)* → `sample_<key>` or `sample_value` (§2).
   - `integer` / `number` *(existing, unchanged)* → `minimum` if present, else `0`.
   - `boolean` *(existing, unchanged)* → `False`.
   - anything else / no resolvable type *(existing, unchanged)* → `None`.

Steps 1–5 apply uniformly regardless of the node's declared `type` — an `example`/`default` on an `object`- or `array`-typed node replaces that node's entire synthesized subtree rather than being merged into it.
