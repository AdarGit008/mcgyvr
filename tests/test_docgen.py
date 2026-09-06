"""The config reference is a projection of the schema, and is never kept.

The schema is the reference. A rendered copy that outlives its check becomes
a second description of the config, so the owner's ruling (2026-09-05) is
that every ``docgen`` run renders the reference, checks it and deletes it —
no copy is committed and ``make docs-check`` cannot find one to compare.
What is tested here are the properties of the generator itself: that it is
deterministic, that it reaches every key, that the things the loader treats
as load-bearing survive the rendering, and that the rendered file is gone
when the run returns, whatever the verdict.
"""

from __future__ import annotations

import subprocess
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
    assert "one of `llama.cpp`, `vllm`" in rendered
    assert "one of `branch`, `none`" in rendered


def test_credential_keys_are_documented_as_names_not_values() -> None:
    # The single most consequential thing a reader can get wrong about this
    # config: these keys take the NAME of an environment variable.
    rendered = docgen.render_reference()
    for path, field in _walk(SCHEMA):
        if field.kind == "env_name":
            assert "env var name" in rendered, path
            assert "never the value" in rendered


def test_the_reference_is_rendered_checked_and_deleted_on_every_run(
    tmp_path: Path,
) -> None:
    # Both modes: the reference exists only for the length of its check. The
    # skill is pre-rendered so that `--check` has nothing else to refuse.
    reference = tmp_path / "config-reference.md"
    skill = tmp_path / "SKILL.md"
    skill.write_text(docgen.render_skill(), encoding="utf-8")
    common = ["--output", str(reference), "--skill-output", str(skill)]

    assert docgen.main(common) == 0
    assert not reference.exists()
    assert docgen.main(["--check", *common]) == 0
    assert not reference.exists()


def test_a_reference_that_drops_a_key_fails_its_check_and_is_still_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference = tmp_path / "config-reference.md"
    skill = tmp_path / "SKILL.md"
    skill.write_text(docgen.render_skill(), encoding="utf-8")
    monkeypatch.setattr(docgen, "render_reference", lambda: docgen.MARKER + "\n")

    argv = ["--output", str(reference), "--skill-output", str(skill)]
    assert docgen.main(argv) == 1
    assert not reference.exists()
    err = capsys.readouterr().err
    assert "`version`" in err  # a required key the empty document does not name


def test_check_mode_treats_a_missing_skill_as_drift(tmp_path: Path) -> None:
    argv = [
        "--check",
        "--output",
        str(tmp_path / "config-reference.md"),
        "--skill-output",
        str(tmp_path / "absent.md"),
    ]
    assert docgen.main(argv) == 1


def test_check_mode_names_the_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("stale\n", encoding="utf-8")
    argv = [
        "--check",
        "--output",
        str(tmp_path / "config-reference.md"),
        "--skill-output",
        str(skill),
    ]
    docgen.main(argv)
    assert "make docs" in capsys.readouterr().err


def test_no_rendered_reference_is_committed() -> None:
    # The schema is the reference. A committed rendering is a second one,
    # and the generator no longer has a checkout path to write it to.
    tracked = subprocess.run(
        ["git", "ls-files", "--", "*config-reference.md"],
        cwd=docgen.REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tracked == [], tracked
    assert not hasattr(docgen, "REFERENCE_PATH")


def test_table_cells_escape_pipes() -> None:
    field = Field("demo", "str", "a doc with a | pipe in it")
    assert "\\|" in "\n".join(docgen._table((field,), ""))
