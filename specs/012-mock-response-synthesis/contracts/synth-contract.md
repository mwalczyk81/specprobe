# Contract: `synthesize_sample_from_schema`

**Feature**: `012-mock-response-synthesis` | **Module**: `src/specprobe/mock/synth.py`

This is the internal library contract the `specprobe mock` HTTP server (and any other future caller) relies on. The public function signature is unchanged by this feature; only its value-selection behavior is extended.

---

## Signature

```python
def synthesize_sample_from_schema(schema: dict[str, Any] | None) -> Any:
    """Synthesize a minimal JSON-serializable value conforming to `schema`.

    Returns `None` if `schema` is `None`.
    """
```

No parameters are added or removed. Callers (e.g. `MockRequestHandler._handle` via `MockRouter`) are unaffected — they still pass a single JSON Schema Draft 7 `dict` and receive a JSON-serializable value back.

---

## Guarantees (unchanged from before this feature)

- Given `schema is None`, returns `None`.
- Given an `object` schema, the returned `dict` contains **only** the keys listed in `required` (or is `{}`/absent-key-omitted if `required` is missing) — this feature does not add non-required properties.
- Given an `array` schema, the returned `list` contains exactly one synthesized item (or `[]` if `items` is absent).
- Given a node with `const`, returns that literal. Given a node with `enum`, returns its first element. These win over every other rule, including the new ones below.
- Given the **same** `schema` dict, calling the function any number of times returns byte-identical output every time (no randomness, no wall-clock or environment reads).

---

## Guarantees (new, added by this feature)

- Given a node with an `example` key, returns that literal verbatim (any JSON type), unless `const`/`enum` is also present on that node (those still win).
- Given a node with a `default` key and no `example` key, returns that literal verbatim, unless `const`/`enum` is also present.
- Given a `string`-typed node (no `const`/`enum`/`example`/`default`) whose `format` is one of `date-time`, `date`, `email`, `uuid`, `uri`, `url`, `ipv4`, returns the fixed representative literal for that format (see [data-model.md §1](../data-model.md#1-format--representative-value-table)) — never `""`.
- Given any other `string`-typed node (no `const`/`enum`/`example`/`default`/recognized `format`), returns `sample_<key>` where `<key>` is the nearest enclosing object property's name (inherited through any array/`items` nesting), or the fixed literal `sample_value` if there is no enclosing property at all — never `""`.
- Given an `integer`/`number`-typed node with none of `const`/`enum`/`example`/`default`/`minimum`, still returns `0` — **unchanged**, no generic numeric fallback is introduced.

---

## Non-Goals (the caller MUST NOT rely on any of the following — they are explicitly out of scope)

- The function does not infer values from a property's *name* beyond the mechanical `sample_<key>` string (e.g. it will never special-case a property literally named `status` or `id`).
- The function does not read or accept the request's path parameters or request body — it has no such parameters, and callers MUST NOT attempt to correlate response values with request data through this function.
- The function does not validate `example`/`default` values against the rest of the node (type, `format`, etc.) — a malformed `schema_shape` is echoed as-is, not rejected.
