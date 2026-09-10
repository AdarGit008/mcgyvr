"""SETUP.md is rendered from config.SCHEMA and checked for drift, not deleted.

Plan v4 (2026-09-09): one package, one seam, two documents. `SKILL.md` is what
an agent reads to author a contract; `SETUP.md` is what a machine's owner
reads to stand the ladder up. Action 1 gives `docgen` a `render_setup()` that
renders `skills/mcgyvr/SETUP.md` from `config.SCHEMA` to a committed path —
unlike `render_reference()` (docgen.py:707-723), which renders to a temp
file, checks it, and deletes it, `SETUP.md` is a document that is written and
kept, the same shape `render_skill()` already has for `SKILL.md`. Action 2
gives `docgen --check` a second branch beside the `SKILL.md` one
(docgen.py:769-780) that diffs the committed `SETUP.md` against what
`render_setup()` produces. Action 3 is `make docs-check` covering it, since
CI already runs that target (.github/workflows/ci.yml:51).

Four things hold. `render_setup()` exists and returns text built from
`config.SCHEMA`. The committed `skills/mcgyvr/SETUP.md` is byte-identical to
what it renders. That file is not deleted after rendering, the way the
config reference is — it persists in the checkout the way `SKILL.md` does.
And `python -m mcgyvr.docgen --check` — and therefore `make docs-check` —
exits non-zero when the committed `SETUP.md` has drifted from the schema.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr import docgen
from mcgyvr.config import SCHEMA, Field

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP_PATH = REPO_ROOT / "skills" / "mcgyvr" / "SETUP.md"


def _names(fields: tuple[Field, ...], prefix: str = "") -> list[str]:
    out: list[str] = []
    for field in fields:
        out.append(f"{prefix}{field.name}")
        out += _names(field.block, f"{prefix}{field.name}.")
    return out


def test_render_setup_exists_and_is_built_from_the_config_schema() -> None:
    text = docgen.render_setup()
    assert isinstance(text, str) and text.strip()
    for name in _names(SCHEMA):
        assert f"`{name}`" in text, name


def test_setup_markdown_on_disk_is_byte_identical_to_render_setup() -> None:
    assert SETUP_PATH.exists(), "skills/mcgyvr/SETUP.md must exist"
    assert SETUP_PATH.read_bytes() == docgen.render_setup().encode("utf-8")


def test_setup_markdown_is_not_deleted_after_rendering() -> None:
    # Unlike render_reference()/check_reference() (docgen.py:707-723), which
    # write to a temp path, check it, then target.unlink(missing_ok=True),
    # SETUP.md is a committed document that persists — the render_skill()
    # shape, not the render_reference() shape.
    assert SETUP_PATH.exists(), "skills/mcgyvr/SETUP.md must exist"
    before = SETUP_PATH.read_bytes()
    docgen.render_setup()
    assert SETUP_PATH.exists(), "rendering must not delete the committed SETUP.md"
    assert SETUP_PATH.read_bytes() == before


def test_docgen_check_refuses_a_setup_document_that_drifted(tmp_path: Path) -> None:
    """A second branch beside the SKILL.md one at docgen.py:769-780.

    The stale document is written in ``tmp_path`` and named with
    ``--setup-output``; the committed file is never written. An earlier
    version of this test said it mutated a temp copy and did not: it wrote
    ``b"stale\\n"`` into the committed ``SETUP.md`` and restored it in a
    ``finally``, which leaves the checkout carrying a one-word SETUP.md on
    any crash or interrupt, and races anything else in the suite that reads
    it. The unused ``tmp_path`` it already took is what it should have been
    using.
    """
    assert SETUP_PATH.exists(), "skills/mcgyvr/SETUP.md must exist"
    untouched = SETUP_PATH.read_bytes()
    stale = tmp_path / "SETUP.md"
    stale.write_bytes(b"stale\n")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcgyvr.docgen",
            "--check",
            "--setup-output",
            str(stale),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert str(stale) in result.stdout + result.stderr
    assert SETUP_PATH.read_bytes() == untouched, "the committed SETUP.md was written"


def _docs_check_recipe() -> str:
    """The commands `make docs-check` runs, as the Makefile spells them."""
    lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("docs-check:"))
    recipe = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())
    assert recipe, "the docs-check target must have a recipe"
    return "\n".join(recipe)


def test_make_docs_check_covers_a_stale_setup_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`make docs-check` is what fails, and the committed file is never written.

    Proved as the chain it actually is, because the destructive way to prove
    it — write ``b"stale\\n"`` into the committed ``SETUP.md``, run ``make``,
    restore in a ``finally`` — leaves the repository carrying a one-word
    SETUP.md whenever the run is interrupted, and `make` takes no
    ``--setup-output`` to point somewhere safe.

    Two links. The Makefile's ``docs-check`` recipe runs
    ``python -m mcgyvr.docgen --check`` and overrides no output, so the
    document it checks is the committed one. And that run, with the rendering
    made to differ from what is on disk, reports the committed path and exits
    non-zero — in check mode, which writes nothing at all.
    """
    assert SETUP_PATH.exists(), "skills/mcgyvr/SETUP.md must exist"
    recipe = _docs_check_recipe()
    assert "-m mcgyvr.docgen --check" in recipe, recipe
    assert "--setup-output" not in recipe, recipe

    untouched = SETUP_PATH.read_bytes()
    # The other two kept documents are pointed at current renderings in
    # tmp_path, so the only thing this run can refuse is SETUP.md.
    (tmp_path / "SKILL.md").write_text(docgen.render_skill(), encoding="utf-8")
    (tmp_path / "examples.md").write_text(docgen.render_examples(), encoding="utf-8")
    monkeypatch.setattr(docgen, "render_setup", lambda: "stale\n")

    code = docgen.main(
        [
            "--check",
            "--output",
            str(tmp_path / "config-reference.md"),
            "--skill-output",
            str(tmp_path / "SKILL.md"),
            "--examples-output",
            str(tmp_path / "examples.md"),
        ]
    )

    assert code == 1
    err = capsys.readouterr().err
    assert str(SETUP_PATH) in err, err
    assert SETUP_PATH.read_bytes() == untouched, "the committed SETUP.md was written"
