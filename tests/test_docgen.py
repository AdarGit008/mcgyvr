"""The config reference is a projection of the schema, and stays one.

Drift between the committed reference and the schema is caught by
``make docs-check`` in CI — that is a property of the repository's state.
What is tested here are the properties of the generator itself, which the
drift check cannot express: that it is deterministic, that it reaches every
key, and that the things the loader treats as load-bearing survive the
rendering.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr import docgen
from mcgyvr.config import SCHEMA, Field


def _walk(fields: tuple[Field, ...], prefix: str = "") -> list[tuple[str, Field]]:
    """Every key in the schema, at every depth, as dotted paths."""
    out: list[tuple[str, Field]] = []
    for field in fields:
        path = f"{prefix}.{field.name}" if prefix else field.name
        out.append((path, field))
        if field.block:
            out.extend(_walk(field.block, path))
    return out


def test_render_is_deterministic() -> None:
    # Byte-identical across calls, or the drift check is unusable: it would
    # fail on runs that changed nothing.
    assert docgen.render_reference() == docgen.render_reference()


def test_carries_the_do_not_edit_marker() -> None:
    # CTX-08's provenance requirement. Without it a generated file gets
    # hand-edited and silently diverges from its source.
    rendered = docgen.render_reference()
    assert rendered.startswith(docgen.MARKER)
    assert "DO NOT EDIT" in rendered


def test_every_schema_key_is_documented() -> None:
    rendered = docgen.render_reference()
    missing = []
    for path, _ in _walk(SCHEMA):
        if f"`{path.split('.')[-1]}`" not in rendered:
            missing.append(path)
    assert not missing, f"schema keys absent from the reference: {missing}"


def test_every_key_carries_its_own_prose() -> None:
    # `doc` has no default in Field for a reason; assert the renderer does
    # not quietly drop it for some kind it does not handle.
    rendered = docgen.render_reference()
    for path, field in _walk(SCHEMA):
        head = field.doc.split(".")[0].replace("|", "\\|")
        assert head in rendered, f"{path}: documentation prose is missing"


def test_required_and_optional_are_distinguishable() -> None:
    rendered = docgen.render_reference()
    # `version` is required, `sandbox` is not — a reader must be able to tell.
    assert "| `version` | number (min 1) | **yes** |" in rendered
    assert "| `sandbox` | block | no |" in rendered


def test_defaults_render_as_values_not_blanks() -> None:
    rendered = docgen.render_reference()
    # A real default is shown as one; an absent one says so. The loader
    # distinguishes "unset" from "empty", so the reference must too.
    assert "| `1` |" in rendered  # max_parallel
    assert "| `900` |" in rendered  # task_timeout_s
    assert "| `false` |" in rendered  # verifier.enabled
    assert "| `docker` |" in rendered  # sandbox.mode
    assert "| unset |" in rendered  # api_key_env and friends


def test_enum_choices_are_named() -> None:
    rendered = docgen.render_reference()
    assert "one of `ollama`, `openai`" in rendered
    assert "one of `pull_request`, `branch`, `none`" in rendered


def test_credential_keys_are_documented_as_names_not_values() -> None:
    # The single most consequential thing a reader can get wrong about this
    # config: these keys take the NAME of an environment variable.
    rendered = docgen.render_reference()
    for path, field in _walk(SCHEMA):
        if field.kind == "env_name":
            assert "env var name" in rendered, path
            assert "never the value" in rendered


def test_check_mode_detects_drift(tmp_path: Path) -> None:
    target = tmp_path / "reference.md"

    assert docgen.main(["--output", str(target)]) == 0
    assert docgen.main(["--check", "--output", str(target)]) == 0

    target.write_text("# hand-edited\n", encoding="utf-8")
    assert docgen.main(["--check", "--output", str(target)]) == 1


def test_check_mode_treats_a_missing_file_as_drift(tmp_path: Path) -> None:
    assert docgen.main(["--check", "--output", str(tmp_path / "absent.md")]) == 1


def test_check_mode_names_the_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "reference.md"
    target.write_text("stale\n", encoding="utf-8")
    docgen.main(["--check", "--output", str(target)])
    assert "make docs" in capsys.readouterr().err


def test_committed_reference_is_where_the_generator_writes() -> None:
    # If this path moves, `make docs-check` silently checks nothing.
    assert (docgen.REPO_ROOT / docgen.REFERENCE_PATH).exists()


def test_table_cells_escape_pipes() -> None:
    field = Field("demo", "str", "a doc with a | pipe in it")
    assert "\\|" in "\n".join(docgen._table((field,), ""))
