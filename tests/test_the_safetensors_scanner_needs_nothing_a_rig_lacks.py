"""``safetensorscan`` is shipped to the machine holding the weights as bytes.

Like ``ggufscan`` it is run there as ``python3 -`` or as
``python -m mcgyvr.serving.safetensorscan <model dir>``: the interpreter has no
venv, no ``mcgyvr`` and no ``PYTHONPATH``. An import added to the file fails on
that machine and nowhere else, so this suite refuses one, keeps the command
line guarded so that importing the module prints nothing, and runs the file the
way it is shipped over a checkpoint it reads.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from tests import safetensors_checkpoint as ckpt

REPO = Path(__file__).resolve().parents[1]
SCANNER = REPO / "src" / "mcgyvr" / "serving" / "safetensorscan.py"

#: What a bare ``python3`` is guaranteed to have, and nothing that has ever
#: been added to the file's import lines (``__future__`` is the interpreter's).
STDLIB_ONLY = {"__future__", "json", "os", "struct", "sys", "typing"}


def _tree() -> ast.Module:
    return ast.parse(SCANNER.read_text(encoding="utf-8"), filename=str(SCANNER))


def _imported_names(tree: ast.Module) -> set[str]:
    """Top-level names of every import, at any depth -- a lazy one counts too."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module name; the empty string is not
            # in the allowed set, so it is refused the same way.
            names.add((node.module or "").split(".")[0])
    return names


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    left = node.test.left
    right = node.test.comparators
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and len(right) == 1
        and isinstance(right[0], ast.Constant)
        and right[0].value == "__main__"
    )


def test_the_scanner_imports_nothing_a_rig_lacks() -> None:
    extra = sorted(_imported_names(_tree()) - STDLIB_ONLY)
    assert not extra, (
        f"{SCANNER.relative_to(REPO)} imports {extra}; it runs on the machine "
        f"holding the weights as `python3 -` with nothing installed, so only "
        f"{sorted(STDLIB_ONLY)} are available there"
    )


def test_the_scanner_keeps_its_main_guard() -> None:
    assert any(_is_main_guard(node) for node in _tree().body), (
        f'{SCANNER.relative_to(REPO)} has no `if __name__ == "__main__":` guard'
    )


def test_the_scanner_runs_isolated_from_stdin_and_reports_no_directories() -> None:
    """The transport the gates use, with no argument: `[]`, exit 0.

    ``-I`` isolates the child from this environment, so a dependency the AST
    walk somehow missed fails here rather than on the rig.
    """
    done = subprocess.run(
        [sys.executable, "-I", "-"],
        input=SCANNER.read_bytes(),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout.strip() == b"[]", done.stdout.decode("utf-8", "replace")


def test_the_shipped_scanner_prints_one_row_per_directory_and_an_error_row(
    tmp_path: Path,
) -> None:
    good = ckpt.make(tmp_path / "box-a-model", ckpt.decoder_spec(2), ckpt.base_config())
    missing = tmp_path / "no-such-directory"
    done = subprocess.run(
        [sys.executable, "-I", "-", str(good), str(missing)],
        input=SCANNER.read_bytes(),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    rows = json.loads(done.stdout)
    assert [r["file"] for r in rows] == [str(good), str(missing)]
    assert rows[0]["n_layer"] == 2
    assert rows[0]["bytes_total_tensors"] > 0
    assert "error" in rows[1] and "not a directory" in rows[1]["error"]
