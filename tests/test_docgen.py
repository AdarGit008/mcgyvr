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

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr import docgen
from mcgyvr.config import SCHEMA, Field

#: The name the inner run loads the redirect plugin under, and the variable it
#: reads the throwaway document directory from.
_REDIRECT_MODULE = "docgen_output_redirect"
_OUTPUTS_ENV = "MCGYVR_DOCGEN_TEST_OUTPUTS"

#: The redirect plugin, as source. docgen's default output paths are module
#: constants joined to ``REPO_ROOT`` (docgen.py:74-77, :923-937), and an
#: absolute path put in their place moves every defaulted write into the outer
#: test's ``tmp_path``. ``REPO_ROOT`` itself is left alone, so the inner run's
#: own git calls and imports are exactly what they were. It is written out at
#: run time rather than kept as a file in ``tests/`` because pytest must import
#: it by name for ``-p`` and must never collect it as a test module.
_REDIRECT_PLUGIN = f'''\
"""Point docgen's default outputs at a throwaway copy of the documents."""

from __future__ import annotations

import os
from pathlib import Path

from mcgyvr import docgen

_root = Path(os.environ["{_OUTPUTS_ENV}"])
docgen.SKILL_PATH = _root / "SKILL.md"
docgen.SETUP_PATH = _root / "SETUP.md"
docgen.EXAMPLES_PATH = _root / "examples.md"
'''


def _outputs(tmp_path: Path, *, skill: Path | None = None) -> list[str]:
    """All four output flags, every one of them inside ``tmp_path``.

    ``--skill-output``, ``--setup-output`` and ``--examples-output`` default
    to the committed copies (docgen.py:868-880), so a write-mode run that
    overrides only some of them regenerates the rest of the checkout in
    place. A test that did that would erase, from the working tree, exactly
    the drift ``make docs-check`` exists to catch: set SETUP.md to "STALE",
    run this file, and the file comes back regenerated, after which nothing
    can tell it had drifted. Every ``docgen.main()`` call in this file passes
    these, and
    ``test_running_the_docgen_tests_does_not_rewrite_the_committed_documents``
    holds them to it.
    """
    return [
        "--output",
        str(tmp_path / "config-reference.md"),
        "--skill-output",
        str(skill if skill is not None else tmp_path / "SKILL.md"),
        "--setup-output",
        str(tmp_path / "SETUP.md"),
        "--examples-output",
        str(tmp_path / "examples.md"),
    ]


def _render_the_kept_documents(tmp_path: Path) -> None:
    """The two documents `--check` compares that this file is not about.

    Written current, so a check-mode run in here reports drift in the skill
    and nothing else.
    """
    (tmp_path / "SETUP.md").write_text(docgen.render_setup(), encoding="utf-8")
    (tmp_path / "examples.md").write_text(docgen.render_examples(), encoding="utf-8")


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
    # `units` is required, `sandbox` is not — a reader must be able to tell.
    assert "| `units` | block map | **yes** |" in rendered
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
    common = _outputs(tmp_path, skill=skill)

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

    argv = _outputs(tmp_path, skill=skill)
    assert docgen.main(argv) == 1
    assert not reference.exists()
    err = capsys.readouterr().err
    assert "`units`" in err  # a required key the empty document does not name


def test_check_mode_treats_a_missing_skill_as_drift(tmp_path: Path) -> None:
    _render_the_kept_documents(tmp_path)
    argv = ["--check", *_outputs(tmp_path, skill=tmp_path / "absent.md")]
    assert docgen.main(argv) == 1


def test_check_mode_names_the_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("stale\n", encoding="utf-8")
    _render_the_kept_documents(tmp_path)
    argv = ["--check", *_outputs(tmp_path, skill=skill)]
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


def test_running_the_docgen_tests_does_not_rewrite_the_committed_documents(
    tmp_path: Path,
) -> None:
    """A sentinel planted where the inner run's defaults point survives it.

    `--skill-output`, `--setup-output` and `--examples-output` default to the
    checkout's own copies (docgen.py:923-937), so a write-mode `docgen.main()`
    call that overrides only some of them regenerates the others in place.
    That is not a stray write: it silently repairs, in the working tree, the
    very drift `make docs-check` exists to fail on (plan actions 2 and 3), so
    a run of the suite would leave a stale committed document looking current.

    A digest taken before and after would not see it — the rewrite produces
    the bytes the file is supposed to have. A sentinel does: it is the one
    thing regeneration cannot reproduce.

    The sentinel does not go in the committed file. Planting it there left
    `skills/mcgyvr/SETUP.md` carrying a comment line for the length of the
    inner run — up to 600 s — while `addopts = "-q -n auto"`
    (pyproject.toml:212) had the rest of the suite reading that file in other
    processes; the two tests that read it failed whenever they landed in the
    window, and only ever passed by scheduling luck
    (`tests/test_the_docgen_guard_never_writes_the_committed_setup.py`).
    Instead the three kept documents are copied into `tmp_path`, the sentinel
    goes into the copy, and the inner run is handed a `-p` plugin that points
    docgen's defaults at the copies. A defaulting write in this file lands on
    the copy and destroys the sentinel there, which is the same detection with
    none of the checkout at stake. The committed file is asserted untouched as
    well, so a redirect that did not take hold cannot pass this quietly.

    The inner run is `-n 0`: it is one file, and one process is where the
    plugin redirecting the defaults has to be. This test is deselected from
    that run, or it would drive itself.
    """
    skills = docgen.REPO_ROOT / "skills" / "mcgyvr"
    committed = skills / "SETUP.md"
    assert committed.exists(), "skills/mcgyvr/SETUP.md must exist"
    untouched = committed.read_bytes()

    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "SKILL.md").write_bytes((skills / "SKILL.md").read_bytes())
    (documents / "examples.md").write_bytes(
        (skills / "references" / "examples.md").read_bytes()
    )
    sentinel = b"\n<!-- a docgen test rewrote the committed SETUP.md -->\n"
    planted = untouched + sentinel
    (documents / "SETUP.md").write_bytes(planted)
    (tmp_path / f"{_REDIRECT_MODULE}.py").write_text(_REDIRECT_PLUGIN, encoding="utf-8")

    here = Path(__file__)
    myself = (
        f"tests/{here.name}::"
        f"{test_running_the_docgen_tests_does_not_rewrite_the_committed_documents.__name__}"
    )
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-n",
            "0",
            "-p",
            "no:cacheprovider",
            "-p",
            _REDIRECT_MODULE,
            f"tests/{here.name}",
            "--deselect",
            myself,
        ],
        cwd=docgen.REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (str(tmp_path), os.environ.get("PYTHONPATH", ""))
                if part
            ),
            _OUTPUTS_ENV: str(documents),
        },
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert (documents / "SETUP.md").read_bytes() == planted, (
        "a docgen test wrote the document `--setup-output` defaults to: every "
        "main() call that writes must point all four outputs at a tmp_path"
    )
    assert committed.read_bytes() == untouched, (
        "a docgen test wrote the committed skills/mcgyvr/SETUP.md, which the "
        "inner run's defaults do not point at: either the redirect plugin did "
        "not load or something reaches the checkout's copy by its own path"
    )


def test_table_cells_escape_pipes() -> None:
    field = Field("demo", "str", "a doc with a | pipe in it")
    assert "\\|" in "\n".join(docgen._table((field,), ""))
