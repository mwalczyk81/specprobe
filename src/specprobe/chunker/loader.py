"""OpenAPI specification loader and validation module."""

from pathlib import Path
import sys
from typing import Any
import yaml
import prance
from prance.util.fs import canonical_filename


class SpecLoadError(Exception):
    """Raised when an OpenAPI specification cannot be loaded or is invalid."""


def load_openapi_spec(spec_path_or_content: str | Path) -> dict[str, Any]:
    """Load, parse, and validate an OpenAPI 3.0 or 3.1 specification.

    Accepts either a filesystem path (str or Path), '-' for stdin, or direct YAML/JSON string.
    Rejects Swagger 2.0 specifications upfront with an explicit error.
    Uses prance.BaseParser to load without recursive inlining.
    """
    path_obj = None
    content: str

    if isinstance(spec_path_or_content, Path) or (
        isinstance(spec_path_or_content, str) and not spec_path_or_content.strip().startswith(("{", "openapi:", "swagger:"))
    ):
        raw_path = str(spec_path_or_content)
        if raw_path == "-":
            content = sys.stdin.read()
            if not content.strip():
                raise SpecLoadError("Standard input provided is empty.")
        else:
            path_obj = Path(raw_path)
            if not path_obj.exists():
                raise SpecLoadError(f"Specification file '{raw_path}' does not exist.")
            try:
                content = path_obj.read_text(encoding="utf-8")
            except Exception as exc:
                raise SpecLoadError(f"Failed to read specification file '{raw_path}': {exc}") from exc
    else:
        content = str(spec_path_or_content)

    # Initial parse with pyyaml to inspect version before full validation
    try:
        raw_dict = yaml.safe_load(content)
    except Exception as exc:
        location = str(path_obj) if path_obj else "content"
        raise SpecLoadError(f"Failed to parse specification '{location}': {exc}") from exc

    if not isinstance(raw_dict, dict):
        raise SpecLoadError("Specification root must be a valid JSON/YAML mapping.")

    # Explicit rejection of Swagger 2.0
    if "swagger" in raw_dict:
        raise SpecLoadError("Swagger 2.0 is not supported. SpecProbe requires OpenAPI 3.0 or 3.1.")

    # Validation of OpenAPI version field
    openapi_version = raw_dict.get("openapi")
    if not openapi_version or not isinstance(openapi_version, str):
        raise SpecLoadError("Missing 'openapi' version field. SpecProbe requires OpenAPI 3.0 or 3.1.")

    if not (openapi_version.startswith("3.0.") or openapi_version.startswith("3.1.")):
        raise SpecLoadError(
            f"Unsupported OpenAPI version '{openapi_version}'. SpecProbe requires OpenAPI 3.0 or 3.1."
        )

    # Validate using prance.BaseParser without inlining references
    try:
        if path_obj and path_obj.exists():
            parser = prance.BaseParser(canonical_filename(str(path_obj)), strict=False)
        else:
            parser = prance.BaseParser(spec_string=content, strict=False)
        return parser.specification
    except SpecLoadError:
        raise
    except prance.ValidationError as exc:
        # Check if validation failed due to unresolvable external references
        cause = getattr(exc, "__cause__", None)
        is_unresolvable = False
        try:
            import referencing.exceptions

            if isinstance(cause, referencing.exceptions.Unresolvable):
                is_unresolvable = True
        except ImportError:
            pass
        if not is_unresolvable and cause and "Unresolvable" in type(cause).__name__:
            is_unresolvable = True

        if is_unresolvable:
            # Allow spec with external references to be processed;
            # SchemaPruner preserves raw $ref and attaches non-fatal warnings
            return raw_dict

        location = str(path_obj) if path_obj else "content"
        raise SpecLoadError(f"Validation failed for specification '{location}': {exc}") from exc
    except Exception as exc:
        location = str(path_obj) if path_obj else "content"
        raise SpecLoadError(f"Validation failed for specification '{location}': {exc}") from exc
