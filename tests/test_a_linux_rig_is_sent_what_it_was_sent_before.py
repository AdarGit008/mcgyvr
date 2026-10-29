"""A Linux rig is sent, byte for byte, what it was sent before Mac and Windows rigs.

Whether its rig file records Linux, or it has no rig file at all (a door run
reads none then, and asks nothing), a rig over ssh is sent the same commands
and stdins as it always was: the lease's five bash scripts on ``bash -s --
lease``, ``rig-units.sh`` whole on ``bash -s``, the shipped reader on the
``echo <base64> | base64 -d | python3 -I -B -`` line (``--cards`` for the card
read), the header read and the ``find`` discovery, the fetcher on ``python3 -
mcgyvr-fetch``, and the health probe's ``curl``. No question is asked of it
first, and nothing it is sent carries a stdin it did not carry. The reader's
program inside the line is the reader as it now stands, assembled.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.serving import gatelib, rigread, servelib
from tests.remote_rigs import record_rig

#: The sha256 of rig-units.sh as a Linux rig has always been sent it.
RIG_UNITS_SHA256 = "9181c7c90cae4b1ba864c37d695d6a0d98c9aad486e1d5b603bf1d28029923c3"
LINE = "lease_id=0123456789abcdef holder=me@door machine=m pid=1 pid_start=none "
LINE += "started_at=2026-10-29T00:00:00Z step=up run_id=none"
#: The five lease scripts, as the rig's bash has always read them.
SCRIPTS = {
    "read": "cat ~/.mcgyvr/lease 2>/dev/null || true\n",
    "take_free": (
        "mkdir -p ~/.mcgyvr || exit 4\nset -C\n"
        f"printf '%s\\n' '{LINE}' > ~/.mcgyvr/lease\n"
    ),
    "take_stale": (
        "mkdir -p ~/.mcgyvr || exit 4\nf=~/.mcgyvr/lease\n"
        "if [ -z 'feedfacefeedface' ]; then grep -qs -- '[^[:space:]]' \"$f\" "
        "&& exit 3; else grep -qs -- 'lease_id=feedfacefeedface ' \"$f\" || exit 3; "
        "fi\n"
        f'printf \'%s\\n\' \'{LINE}\' > "$f.$$" && mv -f "$f.$$" "$f"\n'
    ),
    "stamp": (
        "f=~/.mcgyvr/lease\n"
        "grep -qs -- 'lease_id=0123456789abcdef ' \"$f\" || exit 3\n"
        f'printf \'%s\\n\' \'{LINE}\' > "$f.$$" && mv -f "$f.$$" "$f"\n'
    ),
    "release": (
        "f=~/.mcgyvr/lease\n"
        'grep -qs -- \'lease_id=0123456789abcdef \' "$f" && rm -f "$f"\ntrue\n'
    ),
}
FIELDS = {
    "read": {},
    "take_free": {"line": LINE},
    "take_stale": {"held": "feedfacefeedface", "line": LINE},
    "stamp": {"held": "0123456789abcdef", "line": LINE},
    "release": {"held": "0123456789abcdef"},
}
READER_LINE = re.compile(r"echo [A-Za-z0-9+/=]+ \| base64 -d \| python3 -I -B -")


class Rig:
    """The far side of ssh: records what it is sent, exactly as it is called."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(["ssh"], 0, "", "")


@pytest.fixture(params=["recorded", "unrecorded"])
def host(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> str:
    if request.param == "recorded":
        record_rig(monkeypatch, tmp_path, "box1", "linux-one-card")
        assert gatelib.recorded_os("box1") == "linux"
    else:
        monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))
    monkeypatch.setenv("RUN_HOST", "box1")
    return "box1"


@pytest.mark.parametrize("op", sorted(SCRIPTS))
def test_each_lease_operation_is_its_bash_script(
    monkeypatch: pytest.MonkeyPatch, host: str, op: str
) -> None:
    rig = Rig()
    monkeypatch.setattr(gatelib, "ssh", rig)
    gatelib._lease_op(host, op, **cast(Any, FIELDS[op]))
    assert rig.calls == [((host, "bash -s -- lease"), {"input": SCRIPTS[op]})]


def test_what_holds_the_rig_is_rig_units_sh_on_bash(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    rig = Rig()
    monkeypatch.setattr(rigread, "ssh", rig)
    monkeypatch.delenv("RUN_LAUNCHER", raising=False)
    rigread.held(host)
    ((args, kwargs),) = rig.calls
    assert args == (host, "bash -s")
    assert kwargs.keys() == {"timeout", "input"}
    assert hashlib.sha256(kwargs["input"].encode()).hexdigest() == RIG_UNITS_SHA256


def test_the_reading_and_the_card_read_are_the_reader_line(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    rig = Rig()
    monkeypatch.setattr(rigread, "ssh", rig)
    monkeypatch.setattr(servelib, "ssh", rig)
    with pytest.raises(SystemExit):
        rigread.reading(host)  # the fake rig prints no reading
    servelib.card(host)
    (reading, card) = rig.calls
    assert reading == ((host, gatelib.scan_read_command()), {"timeout": 180})
    assert card == ((host, gatelib.cards_read_command()), {"timeout": 60})
    assert READER_LINE.fullmatch(gatelib.scan_read_command())
    assert gatelib.cards_read_command() == gatelib.scan_read_command() + " --cards"


def test_the_shipments_of_a_linux_rig_are_the_posix_lines(host: str) -> None:
    assert gatelib.shipping_os(host) == gatelib.LINUX
    assert gatelib.scan_read(gatelib.shipping_os(host)) == gatelib.Shipped(
        gatelib.scan_read_command()
    )
    header = gatelib.header_read(gatelib.shipping_os(host), "/m/x.gguf")
    assert header == gatelib.Shipped(gatelib.header_read_command("/m/x.gguf"))
    assert header.command.endswith(" | base64 -d | python3 - '/m/x.gguf'")


def test_the_health_probe_and_the_fetch_are_the_commands_they_were(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    from mcgyvr.serving import fetchlist

    rig = Rig()
    monkeypatch.setattr(servelib, "ssh", rig)
    monkeypatch.setenv("RUN_LAUNCHER", "docker")
    servelib.models_served(host, 8080)
    assert rig.calls == [
        ((host, "curl -sf http://localhost:8080/v1/models"), {"timeout": 30})
    ]
    assert fetchlist.REMOTE_COMMAND == "python3 - mcgyvr-fetch"
