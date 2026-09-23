# Quickstart & Verification Guide: Higher-Fidelity Mock Response Synthesis

**Feature**: `012-mock-response-synthesis` | **Date**: 2026-09-22 | **Spec**: [spec.md](file:///C:/Users/mwalc/source/repos/specprobe/.claude/worktrees/fix-stdin-streaming-test/specs/012-mock-response-synthesis/spec.md)

---

## Overview

This guide provides runnable scenarios proving that `specprobe mock` now synthesizes readable, higher-fidelity response bodies for string fields — format-aware where a `format` is declared, self-identifying otherwise — while honoring `example`/`default` when present and leaving required-only object shape and unconstrained numbers unchanged.

---

## Prerequisites

- SpecProbe development environment installed:
  ```powershell
  uv sync
  ```

---

## Scenario 1: Existing Fixture — Key-Based Fallback (no code changes needed to demonstrate)

The existing sample fixture ([`tests/fixtures/generated_tests.jsonl`](file:///C:/Users/mwalc/source/repos/specprobe/tests/fixtures/generated_tests.jsonl)) already has a plain `name` string property (no `format`/`enum`/`const`). Before this feature, `GET /pets/42` returned `{"id": 0, "name": ""}`; after, it must return `{"id": 0, "name": "sample_name"}`.

```powershell
uv run specprobe mock tests/fixtures/generated_tests.jsonl --port 8000
```

In a second terminal:

```powershell
curl -i http://localhost:8000/pets/42
```

**Expected Result**: `200 OK` with body `{"id": 0, "name": "sample_name"}` — the `id` (an unconstrained integer) is still `0`, unchanged.

---

## Scenario 2: New Fixture — Format-Aware Strings, Array Key Inheritance, and `example`/`default`

Create a small fixture exercising all three additions plus the array-item key-inheritance case:

```powershell
@'
{"operation_id":"getWidget","description":"Fetch a widget with format-annotated and example fields","request":{"method":"GET","path":"/widgets/1","path_params":{"id":"1"},"query_params":{},"headers":{},"body":null},"response":{"status_code":200,"headers":{"Content-Type":"application/json"},"schema_shape":{"type":"object","required":["id","createdAt","email","tags","sku"],"properties":{"id":{"type":"integer","example":42},"createdAt":{"type":"string","format":"date-time"},"email":{"type":"string","format":"email"},"tags":{"type":"array","items":{"type":"string"}},"sku":{"type":"string","default":"WIDGET-STANDARD"}}}},"tags":["widgets"]}
'@ | Set-Content -Encoding utf8 tmp_widget_fixture.jsonl
```

```powershell
uv run specprobe mock tmp_widget_fixture.jsonl --port 8001
```

In a second terminal:

```powershell
curl -i http://localhost:8001/widgets/1
```

**Expected Result**: `200 OK` with body:

```json
{
  "id": 42,
  "createdAt": "2024-01-01T00:00:00Z",
  "email": "user@example.com",
  "tags": ["sample_tags"],
  "sku": "WIDGET-STANDARD"
}
```

- `id` comes from its `example` (42), not the unconstrained-number default (0).
- `createdAt` and `email` are format-aware literals, not `""`.
- `tags` is a single-item array whose plain-string item inherits the enclosing `"tags"` property's key.
- `sku` comes from its `default` (no `example` present on that node).

Clean up the temporary fixture afterward:

```powershell
Remove-Item tmp_widget_fixture.jsonl
```

---

## Scenario 3: Unit-Level Verification (fastest feedback loop)

```powershell
uv run pytest tests/unit/test_mock_synth.py -v
```

**Expected Result**: All tests pass, including the updated expectations for the five previously-placeholder assertions (see [research.md §3](research.md#3-precedence-order--existing-test-impact)) and the new tests for format-aware synthesis, key threading, and `example`/`default` precedence against `const`/`enum`.

---

## Scenario 4: Full Regression Pass

```powershell
uv run pytest
```

**Expected Result**: 100% pass — in particular, `tests/integration/test_cli_mock.py` (which exercises the mock server end-to-end) and any other test asserting on synthesized response bodies must still pass with the new values.
