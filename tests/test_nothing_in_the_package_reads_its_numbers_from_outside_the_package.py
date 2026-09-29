"""Nothing in the package reads its numbers from outside the package.

A stranger's install has the package and its data and nothing else of this
repository. So the package's source and its ``data/`` folder are copied to a
fresh folder with nothing beside them, and a separate interpreter importing
mcgyvr from there answers the class tolerances and the runtime figure, the same
answers this checkout gives. Without the ``data/`` folder the same interpreter
refuses them by name: there is no other place they are read from.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mcgyvr import derived

REPO = Path(__file__).resolve().parent.parent

_ASK = """
import json
import mcgyvr
from mcgyvr import derived
try:
    answer = {
        "tolerances": derived.class_tolerances(),
        "runtime": derived.runtime_resident_gb(),
    }
except derived.DerivedNumbersError as exc:
    answer = {"refused": str(exc)}
answer["package"] = mcgyvr.__file__
print(json.dumps(answer))
"""


def _stranger(root: Path, *, with_data: bool) -> dict[str, object]:
    """What an interpreter importing mcgyvr from a bare copy under ``root`` answers."""
    shutil.copytree(
        REPO / "src" / "mcgyvr",
        root / "src" / "mcgyvr",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    if with_data:
        shutil.copytree(REPO / "data", root / "data")
    (root / "home").mkdir()
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "HOME": str(root / "home")}
    done = subprocess.run(
        [sys.executable, "-c", _ASK],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout)
    assert isinstance(answer, dict)
    assert Path(str(answer["package"])).is_relative_to(root / "src"), answer
    return answer


def test_a_bare_copy_of_the_package_and_its_data_answers_the_numbers(
    tmp_path: Path,
) -> None:
    answer = _stranger(tmp_path, with_data=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data", "home", "src"]
    assert "refused" not in answer, answer
    assert answer["tolerances"] == derived.class_tolerances()
    assert answer["runtime"] == derived.runtime_resident_gb()


def test_a_bare_copy_without_its_data_refuses_the_numbers_by_name(
    tmp_path: Path,
) -> None:
    answer = _stranger(tmp_path, with_data=False)
    assert derived.NUMBERS_FILENAME in str(answer.get("refused")), answer
