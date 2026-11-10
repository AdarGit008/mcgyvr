"""A Linux rig is sent, byte for byte, what it was sent before Mac and Windows rigs.

Whether its rig file records Linux, or it has no rig file at all (a door run
reads none then, and asks nothing), a rig over ssh is sent the same commands
and stdins as it always was: ``rig-units.sh`` whole on ``bash -s``, the
shipped reader on the ``echo <base64> | base64 -d | python3 -I -B -`` line
(``--cards`` for the card read), the header read and the ``find`` discovery,
the fetcher on ``python3 - mcgyvr-fetch``, and the health probe's ``curl``.
No question is asked of it first, and nothing it is sent carries a stdin it
did not carry. The programs inside the lines (the reader, the fetcher) are
the ones this checkout assembles (``mcgyvr.serving.shipped``), as a program's
bytes always were the checkout's; they now refuse a Python older than 3.9
with a sentence, where the reader needed 3.11 before and the fetcher alone
ran on older ones.

The lease is the one exception: a Linux rig is no longer sent five bash
scripts on ``bash -s -- lease`` but the one Python lease every other rig is
sent (``shipped.lease``), on the reader's line with the operation, the lease
folder and its fields after the ``-``, and no stdin; what each operation
answers and leaves on the rig is the scripts' own
(``test_the_one_lease_answers_every_state_as_the_bash_scripts_did``).
"""

from __future__ import annotations

import base64
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.serving import gatelib, rigread, servelib, shipped
from tests.remote_rigs import record_rig

#: The sha256 of rig-units.sh as a Linux rig has always been sent it.
RIG_UNITS_SHA256 = "9181c7c90cae4b1ba864c37d695d6a0d98c9aad486e1d5b603bf1d28029923c3"
LINE = "lease_id=0123456789abcdef holder=me@door machine=m pid=1 pid_start=none "
LINE += "started_at=2026-10-29T00:00:00Z step=up run_id=none"
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


#: Each lease operation's arguments after the shipped program's ``-``.
ARGS = {
    "read": " read '~/.mcgyvr'",
    "take_free": f" take_free '~/.mcgyvr' 'line={LINE}'",
    "take_stale": f" take_stale '~/.mcgyvr' held=feedfacefeedface 'line={LINE}'",
    "stamp": f" stamp '~/.mcgyvr' held=0123456789abcdef 'line={LINE}'",
    "release": " release '~/.mcgyvr' held=0123456789abcdef",
}


@pytest.mark.parametrize("op", sorted(FIELDS))
def test_each_lease_operation_is_the_shipped_python_lease(
    monkeypatch: pytest.MonkeyPatch, host: str, op: str
) -> None:
    rig = Rig()
    monkeypatch.setattr(gatelib, "ssh", rig)
    gatelib._lease_op(host, op, **cast(Any, FIELDS[op]))
    program = shipped.packed(shipped.lease())
    line = f"echo {base64.b64encode(program).decode()} | base64 -d | python3 -I -B -"
    assert rig.calls == [((host, line + ARGS[op]), {"input": None})]


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


def test_first_contact_and_the_model_reads_are_one_line_each(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    from mcgyvr import recommend
    from mcgyvr import scan as scan_module

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def ssh_read_only(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(["ssh"], 0, "{}", "")

    monkeypatch.setattr(gatelib, "ssh_read_only", ssh_read_only)
    monkeypatch.setattr(scan_module, "_WINDOWS_FOUND", set())
    scan_module.read_over(scan_module.Reach.ssh(host))
    recommend._discover(host, "/m")
    with pytest.raises(recommend.RecommendError):
        recommend._read_header(host, "/m/x.gguf")  # the fake prints no header
    timeout = {"timeout": scan_module.SSH_TIMEOUT_S}
    assert calls == [
        ((host, gatelib.scan_read_command()), timeout),
        ((host, "find '/m' -maxdepth 1 -name '*.gguf' -print"), timeout),
        ((host, gatelib.header_read_command("/m/x.gguf")), timeout),
    ]
