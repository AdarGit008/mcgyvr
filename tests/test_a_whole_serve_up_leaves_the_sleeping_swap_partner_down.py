"""A whole ``serve up`` leaves a sleeping swap partner down, and a whole down takes it.

Plan 2026-10-07, §6.2, with the owner's P10 ruling: swap partners share one
launch spec, and the unit that starts asleep (``role: sleeps-until-needed``)
is written under a compose profile, so ``docker compose up`` does not start
it and the card's awake set still fits. The door reads that from the file
like everything else it expects:

* a whole ``serve up`` waits for, and gate 7 judges, the awake units only;
  the sleeper is neither expected up nor named as missing;
* ``serve up --unit`` of the sleeper starts it (the swap's wake);
* a whole ``serve down`` takes the sleeper too, if a swap left it running,
  by naming its service: a profile is not something ``down`` is promised to
  reach.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.scan import Scan
from mcgyvr.serving import SLEEPER_PROFILE, rigfile, servelib
from tests import onedoor, usermode

FAST, STRONG = usermode.UNITS
#: The compose service each invented unit is.
SERVICE = {FAST: "unit0", STRONG: "unit1"}


def _rig() -> None:
    rigfile.write(
        rigfile.from_scan(
            usermode.RIG, Scan.from_json(json.dumps(usermode.scan_payload()))
        )
    )


def _compose_file(tmp_path: Path) -> Path:
    """The invented units' one spec, the strong unit under the sleeper profile."""
    path = usermode.compose_file(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["services"][SERVICE[STRONG]]["profiles"] = [SLEEPER_PROFILE]
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _serving(stubs: Path, *, up: tuple[str, ...], pending: tuple[str, ...]) -> None:
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
        usermode.serve(direction, _compose_file(tmp_path), extra=extra),
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


def test_the_door_reads_which_service_starts_asleep(tmp_path: Path) -> None:
    by_container = {
        service.container: service
        for service in servelib.services(_compose_file(tmp_path))
    }

    assert by_container[STRONG].asleep is True
    assert by_container[FAST].asleep is False


def test_a_whole_up_starts_the_awake_units_and_expects_no_more(
    tmp_path: Path,
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    # What Docker does with the file: the profiled service is not started.
    _serving(stubs, up=(), pending=(FAST,))

    code, said = _door(tmp_path, stubs, "up")

    assert code == 0, said
    assert _listed(stubs) == [FAST]
    end = _end(usermode.home())
    assert end["serving"] == [FAST]
    assert end["missing"] == [], "the sleeper was expected up by a whole up"
    assert end["left"] == []


def test_the_sleeper_is_started_by_naming_it(tmp_path: Path) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    _serving(stubs, up=(), pending=(STRONG,))

    code, said = _door(tmp_path, stubs, "up", STRONG)

    assert code == 0, said
    [started] = _compose(stubs)
    assert started.split()[-1] == SERVICE[STRONG], started
    assert _end(usermode.home())["serving"] == [STRONG]


def test_a_whole_down_takes_a_sleeper_a_swap_left_running(tmp_path: Path) -> None:
    _rig()
    stubs = usermode.machine(tmp_path)
    _serving(stubs, up=(STRONG,), pending=())

    code, said = _door(tmp_path, stubs, "down")

    assert code == 0, said
    removed = [line for line in _compose(stubs) if " rm " in f" {line} "]
    assert removed and removed[-1].split()[-1] == SERVICE[STRONG], _compose(stubs)
    assert _listed(stubs) == []
    assert _end(usermode.home())["left"] == []
