# Feature Specification: Higher-Fidelity Mock Response Synthesis

**Feature Branch**: `012-mock-response-synthesis`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Feature: Higher-fidelity mock response synthesis

specprobe mock's response body synthesizer (src/specprobe/mock/synth.py) currently collapses every string to \"\" and every unconstrained number to 0, which produces technically-valid but unreadable bodies (e.g. {\"id\": 0, \"name\": \"\"}) that make it hard to tell mock output from a bug. Improve the synthesizer's fidelity without abandoning determinism (Constitution Principle II — zero-LLM) or the required-properties-only shape decided for this feature originally.

Three additions, all deterministic and reading only from the schema already in hand:

Format-aware string generation — when a string schema node declares a standard JSON Schema Draft 7 format (date-time, date, email, uuid, uri/url, ipv4), emit a valid representative value for that format instead of \"\".
Generic key-based string fallback — when a string node has no format/enum/const, emit f\"sample_{property_key}\" instead of \"\". No property-name semantics, no hardcoded business assumptions — just the property's own key, mechanically.
example/default honoring — if a schema node declares example or default, prefer that literal value over synthesis. Note for scoping: schema_shape is LLM-generated during specprobe generate, not copied mechanically from the source OpenAPI schema, so these keys may often be absent — this is a \"use it when present\" enhancement, not a fix expected to fire on most responses.

Explicit non-goals (considered and rejected, don't reopen):

Property-name-based semantic guessing (e.g. inferring a status field should be \"active\", or an id field should be 1). Arbitrary domain assumptions with no principled stopping point.
Path-parameter or request-body correlation into the response (e.g. injecting a matched petId path param into a response id field). Requires an unspecified field-matching heuristic between path params/body keys and response properties; a wrong match is confidently wrong, worse than the current obviously-fake placeholder.
Emitting all declared properties instead of required-only. Reverses the prior design decision and ignores Draft 7 conditional keywords (dependencies, if/then/else) that required-only synthesis currently sidesteps entirely."

## Clarifications

### Session 2026-09-22

- Q: When a plain string (no format/enum/const) is being synthesized as an array's item schema or as a schema with no enclosing object property, where does `sample_<property_key>` get its key from? → A: Thread the nearest enclosing object property's key down through arrays/nesting so array items inherit it; use a fixed generic key (`sample_value`) only when no enclosing key exists at all (e.g. a bare root-level string schema).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recognizable placeholder values for well-known string formats (Priority: P1)

A developer runs `specprobe mock` against a fixture whose schema marks string fields with a standard format (`date-time`, `date`, `email`, `uuid`, `uri`/`url`, `ipv4`). When they call the mock endpoint, those fields come back holding a valid, plausible sample value for that format instead of an empty string, so the response reads as data rather than as a placeholder that looks broken.

**Why this priority**: This is the most common source of the "is this a bug or a mock?" confusion the feature description calls out — format-carrying fields (timestamps, emails, IDs-as-UUIDs, links) are extremely common in real API schemas, and an empty string in a `date-time` field is the most jarring case of an unreadable body.

**Independent Test**: Can be fully tested by pointing `specprobe mock` at a fixture whose schema includes a string field with each supported `format` value, requesting the mocked endpoint, and confirming each field holds a valid representative value for its declared format rather than `""`.

**Acceptance Scenarios**:

1. **Given** a required string property with `"format": "date-time"` and no `example`/`default`/`enum`/`const`, **When** the mock server synthesizes the response body, **Then** the property holds a syntactically valid RFC 3339 date-time value (e.g. `"2024-01-01T00:00:00Z"`), not `""`.
2. **Given** a required string property with `"format": "email"`, **When** the response body is synthesized, **Then** the property holds a syntactically valid email address, not `""`.
3. **Given** a required string property with `"format": "uuid"`, **When** the response body is synthesized, **Then** the property holds a syntactically valid UUID, not `""`.
4. **Given** the same fixture is used to synthesize a response body multiple times (repeated requests, repeated server runs), **When** comparing the resulting bodies, **Then** every format-aware value is byte-identical across runs (no randomness, no wall-clock-derived values).
5. **Given** a required string property whose `format` value is not one of the supported formats (e.g. `"hostname"`), **When** the response body is synthesized, **Then** the property falls back to the generic key-based value from User Story 2 rather than `""`.

---

### User Story 2 - Self-identifying placeholder values for unformatted strings (Priority: P2)

A developer looks at a mocked response body for a string field that has no format, enum, or const in its schema (e.g. a free-text `name` or `description`). Instead of an empty string, the field holds a value that visibly ties back to the field itself, so it's immediately obvious the value is synthesized mock data for that specific property rather than a bug that dropped the value.

**Why this priority**: This covers the majority of "plain" string fields that User Story 1's format list doesn't reach, and is the most direct fix for the `{"id": 0, "name": ""}` unreadability example in the problem statement. It's second priority because format-aware values (US1) are the higher-value, more recognizable win where they apply.

**Independent Test**: Can be fully tested by pointing `specprobe mock` at a fixture whose schema includes a plain string property (no format/enum/const) and confirming the synthesized value is derived from that property's own key rather than being empty or generic.

**Acceptance Scenarios**:

1. **Given** a required string property `"name"` with no `format`, `enum`, or `const`, **When** the response body is synthesized, **Then** the property holds the value `"sample_name"`, not `""`.
2. **Given** two different required string properties, e.g. `"description"` and `"notes"`, both with no `format`/`enum`/`const`, **When** the response body is synthesized, **Then** each property's value is derived from its own key (`"sample_description"`, `"sample_notes"`) — the two values are not identical to each other.
3. **Given** the same property is synthesized repeatedly, **When** comparing outputs, **Then** the value is identical every time.
4. **Given** a required array property `"tags"` whose `items` schema is a plain string (no `format`/`enum`/`const`), **When** the response body is synthesized, **Then** the array's single synthesized item holds the value `"sample_tags"`, inheriting the enclosing property's key.
5. **Given** a schema node is a plain string with no enclosing object property anywhere above it (e.g. the schema root is itself `{"type": "string"}`), **When** the value is synthesized, **Then** it holds the fixed generic value `"sample_value"`.

---

### User Story 3 - Schema-declared example/default values take priority (Priority: P3)

A developer's schema explicitly declares an `example` or `default` value for a field (however rarely, given that `schema_shape` is LLM-generated rather than copied from the source OpenAPI document). When present, the mock response uses that author-declared value verbatim instead of a synthesized placeholder, since a real declared example is more informative than any synthesized stand-in.

**Why this priority**: Declared examples produce the single highest-fidelity value available, but the feature description is explicit that `schema_shape` will often lack these keys — so this is scoped as lowest priority: a "use it when present" enhancement layered on top of US1/US2, not the primary fix for response readability.

**Independent Test**: Can be fully tested by pointing `specprobe mock` at a fixture whose schema includes a field with an `example` value, another field with only a `default` value, and a third field with both, then confirming each synthesized value matches the expected declared literal.

**Acceptance Scenarios**:

1. **Given** a schema node that declares `"example": "widget-42"`, **When** the response body is synthesized, **Then** the property holds exactly `"widget-42"`, regardless of the property's type, format, or key.
2. **Given** a schema node that declares only `"default": 7` (no `example`), **When** the response body is synthesized, **Then** the property holds exactly `7`.
3. **Given** a schema node that declares both `"example"` and `"default"` with different values, **When** the response body is synthesized, **Then** the property holds the `example` value.
4. **Given** a schema node that declares `"const"` or `"enum"` together with an `"example"` that differs from the `const`/`enum` value, **When** the response body is synthesized, **Then** the property holds the `const`/`enum` value, not the `example` — the response must remain schema-valid.

---

### Edge Cases

- A string node declares a `format` that duplicates one already covered by `enum`/`const` handling (e.g. `format: "email"` plus an `enum`): existing `enum`/`const` precedence is unchanged — those constraints are checked first, exactly as today.
- A string node's `format` value is recognized but capitalized or spaced differently than expected (e.g. `"Date-Time"`): treated as unsupported/unrecognized and falls back to the key-based rule (User Story 2), since format matching is exact/case-sensitive per the schema's own declared string.
- A property key contains unusual characters (spaces, unicode, punctuation): the key-based fallback still uses it mechanically (e.g. `f"sample_{property_key}"`) with no sanitization, since the result is a JSON string value, not an identifier.
- An `example` or `default` value's JSON type doesn't match the node's declared `type` (a malformed or inconsistent schema): the literal is still emitted as-is; the synthesizer does not validate `example`/`default` against the rest of the node.
- An `example`/`default` value appears on an object- or array-typed node: the literal replaces the entire synthesized subtree for that node (nested defaults inside an object's own properties are not separately merged in).
- A number/integer node has no `example`, `default`, or `minimum`: behavior is unchanged — synthesizes to `0`, since this feature does not add a generic numeric fallback (that remains a rejected non-goal-adjacent scope: no property-name-based guessing, no fabricated business values).
- A plain string node (no format/enum/const) is nested inside an array, or otherwise has no enclosing object property key: the key-based fallback inherits the nearest enclosing object property's key through any array/`items` nesting; if there is no enclosing property key at all, it emits the fixed generic value `sample_value` rather than reverting to `""` or erroring.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST, when synthesizing a string-typed schema node whose declared `format` is one of `date-time`, `date`, `email`, `uuid`, `uri`, `url`, or `ipv4`, emit a valid representative literal value for that format instead of an empty string.
- **FR-002**: System MUST emit the same format-aware value every time the same schema node is synthesized (no randomness, no current-timestamp or environment-derived values), preserving the synthesizer's existing determinism guarantee.
- **FR-003**: System MUST, when a string-typed schema node declares a `format` outside the supported set in FR-001, fall back to the generic key-based rule in FR-004 rather than emitting an empty string.
- **FR-004**: System MUST, when a string-typed schema node has no `format`, `enum`, or `const`, emit the value `sample_<property_key>`, where `<property_key>` is the key of the nearest enclosing object property — threaded through any intermediate array/`items` nesting — used mechanically and without semantic interpretation.
- **FR-004a**: System MUST emit the fixed generic value `sample_value` for a string-typed schema node meeting the FR-004 fallback condition when no enclosing object property key exists at all (e.g. a root-level string schema with no wrapping object).
- **FR-005**: System MUST, when a schema node of any type declares an `example` key, use that literal value in place of any synthesized value for that node.
- **FR-006**: System MUST, when a schema node of any type declares a `default` key and does not declare `example`, use that literal `default` value in place of any synthesized value for that node.
- **FR-007**: System MUST prefer `example` over `default` when a schema node declares both.
- **FR-008**: System MUST continue to prefer `const` and `enum` over format-aware synthesis (FR-001), key-based synthesis (FR-004), and `example`/`default` honoring (FR-005–FR-007), so that responses remain valid against schema constraints that bind the instance value.
- **FR-009**: System MUST leave synthesis of unconstrained numbers (no `minimum`, `example`, or `default`) unchanged, continuing to emit `0`.
- **FR-010**: System MUST NOT change which properties appear in a synthesized object — the required-properties-only response shape is unaffected by this feature.
- **FR-011**: System MUST NOT infer values from a property's name beyond the mechanical `sample_<property_key>` fallback (e.g. MUST NOT special-case a property named `status` or `id`).
- **FR-012**: System MUST NOT read or correlate values from request path parameters or request bodies when synthesizing response values.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every response field backed by a string schema node with a supported format (`date-time`, `date`, `email`, `uuid`, `uri`/`url`, `ipv4`), the mocked value is a syntactically valid instance of that format, in 100% of such fields across the fixture set used for testing.
- **SC-002**: For every response field backed by a plain string schema node (no format/enum/const), the mocked value visibly incorporates that field's own property key — or, for array items, the nearest enclosing property's key — in 100% of such fields.
- **SC-003**: For every response field backed by a schema node declaring `example` or `default`, the mocked value exactly matches that declared literal, in 100% of such fields.
- **SC-004**: Synthesizing the same schema any number of times in succession produces byte-identical response bodies every time — zero observed variation.
- **SC-005**: A person unfamiliar with the fixture can visually distinguish a synthesized mock response from an empty/zeroed placeholder body without reading the source schema, for fixtures exercising all three additions above.

## Assumptions

- The supported `format` set is fixed to the six values named in the feature description (`date-time`, `date`, `email`, `uuid`, `uri`/`url` treated as one case, `ipv4`); other Draft 7 format values (e.g. `hostname`, `ipv6`, `time`, `regex`) are treated as unsupported and use the key-based fallback (FR-003/FR-004).
- Format-aware sample values are fixed, static literals per format (not derived from other fields on the schema or from the request), consistent with the existing zero-LLM/deterministic design.
- `example` and `default` are honored as opaque literals with no validation against the rest of the schema node — if `schema_shape` supplies an inconsistent or malformed value there, it is echoed as-is, consistent with the synthesizer already treating `schema_shape` as trusted input.
- `const`/`enum` continue to take precedence over `example`/`default` because they are schema constraints that bind the instance value, whereas `example`/`default` are non-binding annotations; honoring an `example` that conflicts with `const`/`enum` would produce a schema-invalid mock body.
- This feature is scoped entirely to `src/specprobe/mock/synth.py` (and its tests); it does not change `specprobe generate`, the OpenAPI parsing/chunking pipeline, the exporter, or the mock router/server request-handling code.
