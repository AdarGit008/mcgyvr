"""The models on disk are listed four ways, each by its own stated rule.

Four listers walk a models folder, and their protocols differ on purpose:

- the scan (:func:`mcgyvr.serving.rigscan._models_on_disk`) lists every
  ``.gguf`` and ``.safetensors`` file at any depth, each part of a split model
  among them, so the reading says what the disk holds;
- the rig agent (:func:`mcgyvr.rig.inventory.read`) names to the hub the
  ``.gguf`` files no more than four folders down, a split model by its first
  part alone, as a head is started on that part;
- recommend's discovery (:func:`mcgyvr.recommend.discover_command`) asks the rig
  for the ``*.gguf`` entries directly in the folder, through the one ``find``
  shape the gate library admits, which matches the suffix case-sensitively and
  does not pass over a hidden name;
- the local-rig emulator (:func:`mcgyvr.serving.localrig.run`) answers that
  ``find`` as ``find`` does, on this machine.

All four skip what is not a model file, and the three that walk skip hidden
folders. One invented tree is listed by all four here, so a change to one
lister's rule is seen against the others' and has to be stated in this file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr import recommend
from mcgyvr.rig import inventory
from mcgyvr.serving import localrig, rigscan

#: The invented tree: every file holds a few bytes, so each has a size.
TREE = (
    "coder-7b-Q4_K_M.gguf",
    "SHOUTED-Q8_0.GGUF",
    "weights.safetensors",
    "readme.txt",
    ".hidden-Q4_0.gguf",
    "big-Q4_K_M-00001-of-00002.gguf",
    "big-Q4_K_M-00002-of-00002.gguf",
    ".cache/cached-Q4_0.gguf",
    "family/nested-Q5_K_M.gguf",
    "family/nested.safetensors",
    "a/b/c/d/four-down-Q4_0.gguf",
    "a/b/c/d/e/five-down-Q4_0.gguf",
)

#: What the scan lists: both formats, any depth, every split part, nothing
#: hidden.
SCAN = {
    "coder-7b-Q4_K_M.gguf",
    "SHOUTED-Q8_0.GGUF",
    "weights.safetensors",
    "big-Q4_K_M-00001-of-00002.gguf",
    "big-Q4_K_M-00002-of-00002.gguf",
    "family/nested-Q5_K_M.gguf",
    "family/nested.safetensors",
    "a/b/c/d/four-down-Q4_0.gguf",
    "a/b/c/d/e/five-down-Q4_0.gguf",
}
#: What the agent names: .gguf only (any case), at most four folders down, a
#: split model by its first part, nothing hidden.
AGENT = {
    "coder-7b-Q4_K_M.gguf",
    "SHOUTED-Q8_0.GGUF",
    "big-Q4_K_M-00001-of-00002.gguf",
    "family/nested-Q5_K_M.gguf",
    "a/b/c/d/four-down-Q4_0.gguf",
}
#: What recommend's discovery finds: ``*.gguf`` directly in the folder, the
#: suffix matched case-sensitively, hidden names and split parts kept.
DISCOVERY = {
    "coder-7b-Q4_K_M.gguf",
    ".hidden-Q4_0.gguf",
    "big-Q4_K_M-00001-of-00002.gguf",
    "big-Q4_K_M-00002-of-00002.gguf",
}


@pytest.fixture
def models(tmp_path: Path) -> Path:
    folder = tmp_path / "models"
    for relative in TREE:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GGUF-invented")
    return folder


def _relative(paths: list[str], folder: Path) -> set[str]:
    return {Path(p).relative_to(folder).as_posix() for p in paths}


def test_the_scan_lists_both_formats_at_any_depth_and_every_split_part(
    models: Path,
) -> None:
    found, _facts = rigscan._models_on_disk([str(models)])
    assert _relative([row["path"] for row in found], models) == SCAN


def test_the_agent_names_gguf_four_folders_down_and_a_split_by_its_first_part(
    models: Path,
) -> None:
    held = inventory.read(str(models), scan=lambda path: {"error": "invented"})
    assert set(held.files.values()) == AGENT
    assert {m.name for m in held.models} == {Path(p).name for p in AGENT}


def test_recommends_discovery_finds_gguf_directly_in_the_folder(
    models: Path,
) -> None:
    command = recommend.discover_command(str(models))
    done = localrig.run(command, input=None, timeout=10)
    assert done.returncode == 0, done.stderr
    assert _relative(done.stdout.split(), models) == DISCOVERY


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("find") is None,
    reason="the POSIX find a rig runs",
)
def test_the_emulator_answers_the_discovery_as_find_does(models: Path) -> None:
    command = recommend.discover_command(str(models))
    real = subprocess.run(
        ["/bin/sh", "-c", command], capture_output=True, text=True, check=True
    )
    emulated = localrig.run(command, input=None, timeout=10)
    assert sorted(emulated.stdout.split()) == sorted(real.stdout.split())


def test_every_lister_keeps_to_its_own_rule_and_none_lists_what_is_no_model(
    models: Path,
) -> None:
    """The rules side by side: the agent names only what the scan lists, the
    discovery is the folder's own level, and no lister takes the text file."""
    assert AGENT <= SCAN
    assert all("/" not in p for p in DISCOVERY)
    assert {
        "weights.safetensors",
        "family/nested.safetensors",
        "big-Q4_K_M-00002-of-00002.gguf",
        "a/b/c/d/e/five-down-Q4_0.gguf",
    } == SCAN - AGENT
    for listed in (SCAN, AGENT, DISCOVERY):
        assert "readme.txt" not in listed
        assert ".cache/cached-Q4_0.gguf" not in listed
