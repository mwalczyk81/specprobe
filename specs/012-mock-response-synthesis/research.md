# Research & Technical Decisions: Higher-Fidelity Mock Response Synthesis

**Feature**: `012-mock-response-synthesis` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/spec.md)

---

## 1. Format-Aware Representative Literals

### Decision

Use one fixed, hand-picked literal per supported `format` value, chosen from well-known reserved/example ranges rather than anything that could resemble live data:

| `format` | Literal | Source of the value |
|----------|---------|----------------------|
| `date-time` | `"2024-01-01T00:00:00Z"` | RFC 3339 UTC timestamp; fixed calendar date, not derived from `datetime.now()`. |
| `date` | `"2024-01-01"` | RFC 3339 full-date. |
| `email` | `"user@example.com"` | `example.com` is IANA/RFC 2606 reserved for documentation — guaranteed non-routable. |
| `uuid` | `"3fa85f64-5717-4562-b3fc-2c963f66afa6"` | The canonical example UUID used throughout the OpenAPI/Swagger documentation itself — recognizable as a placeholder to anyone who has read OpenAPI examples. |
| `uri` / `url` | `"https://example.com/sample"` | `example.com`, RFC 2606 reserved. |
| `ipv4` | `"203.0.113.1"` | RFC 5737 `TEST-NET-3` — reserved for documentation, cannot collide with a real host. |

### Rationale
- Every literal is drawn from an IANA/RFC-reserved "documentation" range or a well-known spec-ecosystem convention, so it reads as obviously synthetic to anyone familiar with the standard, while still being syntactically valid for its format (satisfies spec SC-001).
- Fixed constants (not generated from `datetime.now()`, `uuid.uuid4()`, or `random`) preserve Constitution Principle II — identical input always yields identical output (spec FR-002).
- No new runtime dependency is needed to *validate* these values, since they are hand-verified once at authoring time; the synthesizer never needs to check its own output.

### Alternatives Considered
- **`datetime.now(UTC)` / `uuid.uuid4()` at synthesis time**: Rejected outright — directly violates Principle II and spec FR-002 (byte-identical output required across repeated runs).
- **Private/internal-looking ranges (`192.168.1.1`, `test@company.com`)**: Rejected — these can be mistaken for real internal infrastructure or a real mailbox, reintroducing the "is this a bug?" confusion the feature exists to remove.
- **All-zero/minimal placeholders (`"0000-01-01T00:00:00Z"`, nil UUID `00000000-0000-0000-0000-000000000000`)**: Considered for continuity with the current all-zero aesthetic, but rejected — still reads as "probably broken" rather than "obviously sample data," undermining spec SC-005.

---

## 2. Key-Threading Design (resolves the `/speckit-clarify` session decision)

### Decision
Add an internal `key: str | None = None` parameter to the recursive `_synthesize` helper (the public `synthesize_sample_from_schema` entry point is unaffected — it starts the recursion with `key=None`):
- `_synthesize_object` passes `key=<property name>` when recursing into each `properties[<property name>]` value.
- `_synthesize_array` passes through whatever `key` it was called with, unchanged, when recursing into `items` — so array items inherit the nearest *enclosing object property's* key, not a per-item identity.
- The string-synthesis branch uses `f"sample_{key}"` when `key is not None`, else the fixed literal `"sample_value"`.

### Rationale
- Matches the `/speckit-clarify` decision exactly: thread the nearest enclosing property key through arbitrary array/`items` nesting; fall back to a fixed generic value only when no enclosing key exists anywhere (a bare root-level string schema, or a root-level array of plain strings).
- A single extra keyword-only parameter, defaulted to `None`, keeps the function's existing call sites (`_synthesize(node, root)` recursive calls that don't touch strings, e.g. from `_synthesize_array` for non-string items) working without modification — no signature churn beyond the one new optional parameter.

### Alternatives Considered
- **Fixed generic fallback everywhere (`sample_item`) regardless of enclosing context**: Rejected in `/speckit-clarify` (Option C) — throws away useful, already-available context for the common array-of-strings case (e.g. a `"tags"` array) for no benefit.
- **No fallback for arrays/rootless strings (`""` unchanged there)**: Rejected in `/speckit-clarify` (Option B) — leaves the exact unreadable-placeholder problem unresolved for a common shape (string arrays).

---

## 3. Precedence Order & Existing Test Impact

### Decision
Extend `_synthesize`'s existing top-of-function short-circuit chain — `$ref` resolution, then `const`, then `enum` — with two new checks inserted immediately after `enum` and before the `type`-based dispatch: `example` (if present, return it verbatim), then `default` (if present and no `example`, return it verbatim). This ordering is a direct implementation of spec FR-008: constraints that bind the instance value (`const`, `enum`) are checked first and therefore still win over non-binding annotations (`example`, `default`).

Because `_synthesize_object` and `_synthesize_array` are just the `object`/`array` branches of the same type-dispatch, `example`/`default` on an object- or array-typed node is checked *before* those branches ever run — so a declared `example`/`default` value replaces the entire synthesized subtree for that node, per the spec's edge-case note.

### Existing Test Impact
Five existing assertions in `tests/unit/test_mock_synth.py` encode the *current* placeholder-everything behavior and MUST be updated as part of this change (not left in place, and not silently deleted without replacement — Principle VI requires the suite to keep proving the new, current behavior):

| Test | Old expectation | New expectation | Why |
|------|------------------|-------------------|-----|
| `test_synthesize_string_type` | `""` | `"sample_value"` | Bare root string schema, no enclosing property key → FR-004a generic fallback. |
| `test_synthesize_string_format_is_ignored` | Asserts format is ignored (`""` for both `date-time` and `uuid`) | Replaced with format-aware assertions (`"2024-01-01T00:00:00Z"`, `"3fa85f64-5717-4562-b3fc-2c963f66afa6"`) | Directly contradicts new FR-001; the test's premise is reversed by this feature. |
| `test_synthesize_object_required_only` | `{"id": 0, "name": ""}` | `{"id": 0, "name": "sample_name"}` | `"name"` has a property key now used per FR-004. |
| `test_synthesize_array_of_objects` | `[{"id": 0, "name": ""}]` | `[{"id": 0, "name": "sample_name"}]` | Same as above, inside an array of objects. |
| `test_synthesize_resolves_local_definitions_ref` | `[""]` | `["sample_value"]` | Root-level array of plain strings — no enclosing object property anywhere → FR-004a generic fallback (§2 above). |

All other existing tests in that module (enum/const precedence, integer/number/boolean/null handling, `$ref` resolution producing non-string leaves, empty/absent `required`) are unaffected and must continue to pass unmodified.

---

## Summary of Technical Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Format literals | Fixed constants per format, from RFC-reserved/OpenAPI-canonical values (§1) | Deterministic, obviously-synthetic, syntactically valid. |
| Key threading | Optional `key` parameter on `_synthesize`, passed through arrays, set per object property (§2) | Matches clarified design; minimal, additive signature change. |
| Precedence | `$ref` → `const` → `enum` → `example` → `default` → type dispatch (§3) | Preserves existing schema-validity guarantee (FR-008) while adding the two new short-circuits. |
| New dependencies | None | Constitution Principle I; literals are self-evidently valid, no validation library needed. |
