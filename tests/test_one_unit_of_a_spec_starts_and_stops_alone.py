"""One unit of a compose file starts and stops alone, through the door.

Plan 2026-10-07, §6.2 (approved): the stronger rung on a full rig is a
SWAP, and for llama.cpp a "sleep" is a stop of the unit's container and a
"wake" is a start. So the door's ``serve up --unit C`` and ``serve down
--unit C`` act on that container of the compose file alone: ``up`` starts it
without its compose neighbours (``--no-deps``), ``down`` stops and removes it,
and the file's other units are left as they are, up or not. Gate 7 judges the
named units only: an ``up`` expects each of them serving, a ``down`` expects
each of them gone. Anything else the run leaves is still named.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile
from tests import onedoor, usermode

FAST, STRONG = usermode.UNITS
#: The compose service each invented unit is (``usermode.compose_file``).
SERVICE = {FAST: "unit0", STRONG: "unit1"}


def _rig() -> None:
    rigfile.write(
        rigfile.from_scan(
            usermode.RIG, Scan.from_json(json.dumps(usermode.scan_payload()))
        )
    )


def _serving(stubs: Path, *, up: tuple[str, ...], pending: tuple[str, ...]) -> None:
    """The daemon lists ``up`` now; a compose up of ``pending`` would start them."""
    for name, names in (("serving-names", up), ("serving-pending", pending)):
        path = stubs / name
        path.unlink(missing_ok=True)
        if names:
            path.write_text("".join(f"{n}\n" for n in names), encoding="utf-8")


def _listed(stubs: Path) -> list[str]:
    path = stubs / "serving-names"
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def _door(tmp_path: Path, stubs: Path, direction: str, *units: str) -> tuple[int, str]:
    extra = tuple(part for unit in units for part in ("--unit", unit))
    done = usermode.door(
        usermode.serve(direction, usermode.compose_file(tmp_path), extra=extra),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path))},
    )
    return done.returncode, done.stdout + done.stderr


def _compose(stubs: Path) -> list[str]:
    return [line for line in onedoor.docker_log(stubs) if line.startswith("compose")]


def _end(home: Path) -> dict[str, object]:
    [run] = usermode.door_logs(home)
    end: dict[str, object] = json.loads(
        (run / f"{run.name}.end.json").read_text(encoding="utf-8")
    )
    return end


def test_up_of_one_unit_starts_it_alone_and_leaves_its_neighbour_running(
    tmp_path: Path,
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    _serving(stubs, up=(FAST,), pending=(STRONG,))

    code, said = _door(tmp_path, stubs, "up", STRONG)

    assert code == 0, said
    [started] = _compose(stubs)
    assert " up " in f" {started} ", started
    assert "--no-deps" in started.split(), started
    assert started.split()[-1] == SERVICE[STRONG], started
    assert "--remove-orphans" not in started, "a one-unit up touched the project"
    assert _listed(stubs) == [FAST, STRONG]
    end = _end(usermode.home())
    assert end["serving"] == [STRONG]
    assert end["missing"] == []
    assert end["left"] == []


def test_down_of_one_unit_stops_it_alone_and_leaves_its_neighbour_running(
    tmp_path: Path,
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    _serving(stubs, up=(FAST, STRONG), pending=())

    code, said = _door(tmp_path, stubs, "down", FAST)

    assert code == 0, said
    [stopped] = _compose(stubs)
    assert " down " not in f" {stopped} ", "a one-unit down took the file down"
    assert " rm " in f" {stopped} ", stopped
    assert stopped.split()[-1] == SERVICE[FAST], stopped
    assert _listed(stubs) == [STRONG]
    end = _end(usermode.home())
    assert end["left"] == []
    up = end["containers_up"]
    assert isinstance(up, list) and STRONG in up


def test_a_unit_that_stays_up_after_its_down_is_named_and_the_run_is_not_green(
    tmp_path: Path,
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    _serving(stubs, up=(FAST, STRONG), pending=())
    (stubs / "compose-down-sticks").touch()

    code, said = _door(tmp_path, stubs, "down", FAST)

    assert code == 1, said
    assert FAST in said
    assert _end(usermode.home())["left"] == [FAST]


def test_up_of_one_unit_that_never_answers_is_missing_and_not_green(
    tmp_path: Path,
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    # The compose up starts nothing: the strong unit is not queued.
    _serving(stubs, up=(FAST,), pending=())

    code, said = _door(tmp_path, stubs, "up", STRONG)

    assert code == 1, said
    end = _end(usermode.home())
    assert end["missing"] == [STRONG], "a unit the run did not name was judged"


def test_a_fetch_takes_no_unit(tmp_path: Path) -> None:
    stubs = usermode.machine(tmp_path)
    listed = tmp_path / "weights.json"
    listed.write_text(json.dumps({"files": []}), encoding="utf-8")

    done = usermode.door(
        [
            "serve",
            "fetch",
            "--host",
            usermode.RIG,
            "--weights",
            str(listed),
            "--unit",
            FAST,
        ],
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stdout + done.stderr
    assert "--unit" in done.stderr
    assert onedoor.ssh_log(stubs) == []


@pytest.mark.parametrize("direction", ["up", "down"])
def test_a_unit_the_compose_file_does_not_name_is_refused_before_any_gate(
    tmp_path: Path, direction: str
) -> None:
    stubs = usermode.machine(tmp_path)

    code, said = _door(tmp_path, stubs, direction, "not-a-container")

    assert code == 2, said
    assert "names no container" in said
    assert onedoor.ssh_log(stubs) == []
