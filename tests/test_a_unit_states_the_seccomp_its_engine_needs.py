"""A unit states the seccomp profile its engine needs, and both launch paths apply it.

Owner ruling: allow io_uring. The Lidenburg llama.cpp fork's MoE expert cache
calls ``abort()`` when ``io_uring_queue_init`` fails
(``ggml/src/ggml-backend.cpp``) — there is no fallback and no env var disables
the tier — and docker's default seccomp profile blocks the io_uring syscalls,
so under a plain ``docker run`` the call returns EPERM and a unit on that image
(``srv2_35b_256k``) dies at start with exit 139
(``records/evidence/2026-09-15-lock-fleets/``
``rig-id-relock-srv2-c1-srv2_35b_256k-diag1.json``).

* A unit's ``launch`` may state ``seccomp:``, a profile file beside the fleet
  file. The stated profile is docker's default plus only the io_uring
  syscalls — never ``unconfined``, never ``--privileged``.
* Both launch paths apply it: lock-fleets' ``_unit.sh`` (``run_args``) and the
  product's live path (``mcgyvr emit``, which renders ``security_opt`` and
  writes the profile beside the compose file it names).
* A unit that states none launches with no profile of its own, and a stated
  profile that is not there is refused by name before any rig is touched.
* A unit whose LAUNCH changed gets ONE fresh cold start, ``plan.py relaunch``,
  after its failed diagnostic start.

No rig is reached: every profile here is a file in a throw-away tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import LockedLaunchError, emit_locked
from tests.lockfleets_window import (
    REPO,
    fleet_doc,
    make_tree,
    steps_module,
)

#: Where a unit's profile sits, as its ``launch.seccomp`` spells it: a path
#: relative to the directory holding fleet.yaml.
PROFILE = "seccomp/io-uring.json"
#: The committed profile of the fleet this repo locks.
COMMITTED = REPO / "fleet-setup" / PROFILE


# --------------------------------------------------------------------------
# the profile itself
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# the fixture fleet
# --------------------------------------------------------------------------


def _doc() -> dict[str, Any]:
    """The committed profile, as a fixture tree may copy it."""
    doc: dict[str, Any] = json.loads(COMMITTED.read_text(encoding="utf-8"))
    return doc


def _fleet(profile: str = PROFILE) -> dict[str, Any]:
    fleet = fleet_doc()
    fleet["units"]["a_pair"]["launch"]["seccomp"] = profile
    return fleet


def _tree(
    tmp_path: Path, *, profile: str = PROFILE, written: bool = True, doc: Any = None
) -> Path:
    """A throw-away tree whose ``a_pair`` states ``profile``."""
    root = make_tree(tmp_path, fleet=_fleet(profile))
    if written:
        path = root / "fleet-setup" / profile
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(_doc() if doc is None else doc, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# lock-fleets: the unit run
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# the product's live path: the emitted compose
# --------------------------------------------------------------------------


def _emit(root: Path, out: Path) -> dict[str, Any]:
    fleet = steps_module().load(root)
    emit_locked(fleet, out, root / "fleet-setup")
    doc = yaml.safe_load((out / "compose.alpha.two.yml").read_text("utf-8"))
    return dict(doc["services"])


def test_the_emitted_compose_carries_the_profile_and_the_file_beside_it(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "compose"
    services = _emit(root, out)
    assert services["a_pair"]["security_opt"] == ["seccomp=io-uring.json"]
    # Compose resolves the path against the project directory — the compose
    # file's own — and reads it itself, so the profile is written beside it.
    beside = out / "io-uring.json"
    assert beside.is_file()
    assert json.loads(beside.read_text("utf-8")) == _doc()
    assert beside.read_text("utf-8") == (root / "fleet-setup" / PROFILE).read_text(
        "utf-8"
    )


def test_a_unit_that_states_none_renders_no_security_opt(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    out = tmp_path / "compose"
    _emit(root, out)
    solo = yaml.safe_load((out / "compose.alpha.one.yml").read_text("utf-8"))
    assert "security_opt" not in solo["services"]["a_solo"]
    # A fleet where nobody states one writes the same bytes as before and no
    # profile beside it.
    bare = make_tree(tmp_path / "bare")
    plain = tmp_path / "plain"
    emit_locked(steps_module().load(bare), plain, bare / "fleet-setup")
    assert sorted(p.name for p in plain.iterdir()) == [
        "compose.alpha.one.yml",
        "compose.alpha.two.yml",
        "compose.beta.one.yml",
        "compose.beta.two.yml",
    ]


def test_emit_refuses_a_stated_profile_that_is_not_there(tmp_path: Path) -> None:
    root = _tree(tmp_path, written=False)
    out = tmp_path / "compose"
    with pytest.raises(LockedLaunchError, match="seccomp"):
        emit_locked(steps_module().load(root), out, root / "fleet-setup")
    # Every refusal is raised before the first file is written.
    assert not out.exists() or not any(out.iterdir())


# --------------------------------------------------------------------------
# the fresh start a changed launch gets
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# what the repo commits
# --------------------------------------------------------------------------
