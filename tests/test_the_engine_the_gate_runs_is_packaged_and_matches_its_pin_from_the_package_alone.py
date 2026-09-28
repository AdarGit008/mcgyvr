"""The engine the semantic gate runs ships inside the package and matches its pin.

The semantic rung stages a small third-party resolver into the sandbox and
refuses to run it unless every file matches the digest pinned in
``gate/semantic.py``. A stranger installs a wheel and nothing else, so the
engine has to be found in the package, and found in the same place whether the
code runs from a checkout or from an install: one place to read it from, one
set of bytes that is checked.

What must be observably true:

* a checkout reads the engine from inside the package, and those bytes satisfy
  the pin;
* the package holds exactly the pinned engine files and their licence, nothing
  more;
* a wheel built from the package's own sources, with nothing else of the tree
  beside them, installs an engine the gate finds and whose bytes satisfy the
  pin.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import mcgyvr.gate.semantic as semantic
from mcgyvr.gate.semantic import ENGINE_DIGESTS, engine_dir, verify_engine

REPO = Path(__file__).resolve().parents[1]
PACKAGED = Path(semantic.__file__).resolve().parent / "_engine" / "ghostcall"

#: The only inputs a wheel build is given: the package's sources, the data it
#: ships, and the project metadata.
PRODUCT_ALONE = ("pyproject.toml", "LICENSE", "src", "data")


def test_a_checkout_reads_the_engine_from_inside_the_package() -> None:
    engine = engine_dir().resolve()
    assert engine == PACKAGED, f"the gate reads its engine from {engine}"
    assert verify_engine(engine) is None


def test_the_package_holds_exactly_the_pinned_engine_files() -> None:
    assert PACKAGED.is_dir(), f"{PACKAGED} does not exist"
    held = {p.name for p in PACKAGED.iterdir() if p.is_file() and p.suffix != ".pyc"}
    assert held == {*ENGINE_DIGESTS, "LICENSE"}, held


def _uv() -> str:
    found = shutil.which("uv")
    if found is None:
        pytest.fail("uv is not on PATH; the release builds with `uv build`")
    return found


def _git(where: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(where), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
    )


def _product_alone(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    for entry in PRODUCT_ALONE:
        source, target = REPO / entry, tree / entry
        if source.is_dir():
            shutil.copytree(
                source, target, ignore=shutil.ignore_patterns("__pycache__")
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    _git(tree, "init", "-q")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-qm", "the product alone")
    return tree


_PROBE = """
import sys
from pathlib import Path
import mcgyvr.gate.semantic as semantic
site = Path(sys.argv[1]).resolve()
here = Path(semantic.__file__).resolve()
assert site in here.parents, f"imported {here}, not the installed wheel"
engine = semantic.engine_dir().resolve()
assert site in engine.parents, f"the engine was read from {engine}"
issue = semantic.verify_engine(engine)
assert issue is None, issue
print("engine", engine.relative_to(site))
"""


def test_a_wheel_built_from_the_product_alone_runs_the_pinned_engine(
    tmp_path: Path,
) -> None:
    tree = _product_alone(tmp_path)
    out = tmp_path / "dist"
    built = subprocess.run(
        [_uv(), "build", "--wheel", "--out-dir", str(out)],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert built.returncode == 0, built.stderr[-2000:]
    (wheel,) = sorted(out.glob("*.whl"))

    site = tmp_path / "site"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(site)
    ran = subprocess.run(
        [sys.executable, "-c", _PROBE, str(site)],
        cwd=site,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, "PYTHONPATH": str(site)},
    )
    assert ran.returncode == 0, ran.stderr[-2000:]
    assert ran.stdout.strip() == "engine mcgyvr/gate/_engine/ghostcall", ran.stdout
