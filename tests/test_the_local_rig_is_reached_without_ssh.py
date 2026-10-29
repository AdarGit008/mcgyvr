"""The rig that is this machine is reached without ssh, where it has no sshd.

`gatelib.local_transport` says when: for this machine's names only, always on
macOS and Windows, on Linux when nothing listens on port 22, or as
``$MCGYVR_LOCAL_TRANSPORT`` says. Then the door's `ssh` runs the step here
(`mcgyvr.serving.localrig`): the shipped machine reader reads the same
invented machine it reads over ssh; a source on stdin runs on this
interpreter; a health probe is made with urllib; the lease is taken, stamped
and released in this machine's own lease file; and anything else is refused.
The ssh on PATH is never reached.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib, localrig
from tests import machine_shapes, machinereader
from tests.hostos_fakes import as_system
from tests.test_serving_gatelib import clean_env, fake_door, ssh_stub, under


@pytest.mark.parametrize(
    ("host", "system", "chosen", "sshd", "expected"),
    [
        ("localhost", "darwin", "", True, True),
        ("127.0.0.1", "windows", "", True, True),
        ("localhost", "linux", "", False, True),
        ("localhost", "linux", "", True, False),
        ("localhost", "linux", "direct", True, True),
        ("localhost", "darwin", gatelib.TRANSPORT_SSH, False, False),
        ("box1", "darwin", "direct", False, False),
    ],
)
def test_which_rigs_are_reached_without_ssh(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    system: str,
    chosen: str,
    sshd: bool,
    expected: bool,
) -> None:
    monkeypatch.setattr(gatelib, "_sshd_listens", lambda: sshd)
    monkeypatch.setenv(gatelib.LOCAL_TRANSPORT_ENV, chosen)
    as_system(monkeypatch, system)
    assert gatelib.local_transport(host) is expected


def test_this_machines_names_are_the_ones_detection_calls_local() -> None:
    from mcgyvr.detect import LOCAL_HOSTS

    assert set(gatelib.LOCAL_RIGS) == set(LOCAL_HOSTS)


def test_the_shipped_reader_reads_the_same_machine_without_ssh(tmp_path: Path) -> None:
    shape = machine_shapes.shapes()[0]
    staged = machinereader.stage(shape)
    code = (
        "import sys\n"
        "from mcgyvr.serving import gatelib, localrig\n"
        "done = localrig.run(gatelib.cards_read_command(), input=None, timeout=60)\n"
        "sys.stdout.write(done.stdout); sys.stderr.write(done.stderr)\n"
        "raise SystemExit(done.returncode)\n"
    )
    local = machinereader.run(
        staged, tmp_path / "local", command=(sys.executable, "-c", code)
    )
    shipped = machinereader.run(staged, tmp_path / "shipped")
    assert local.returncode == 0, local.stderr
    assert not local.unexpected and not local.elevated
    assert machinereader.cards(json.loads(local.stdout)) == machinereader.cards(
        json.loads(shipped.stdout)
    )


def test_the_doors_ssh_to_this_machine_runs_here_and_reaches_no_ssh(
    tmp_path: Path,
) -> None:
    door = fake_door(tmp_path)
    stub = ssh_stub(tmp_path / "stubs")
    env = clean_env(stub.parent)
    env.update(RUN_HOST="localhost", MCGYVR_LOCAL_TRANSPORT="direct")
    code = (
        "from mcgyvr.serving import gatelib\n"
        "done = gatelib.ssh('localhost', 'python3 - word', input='import sys; "
        "print(sys.argv[1:])')\n"
        "print(done.returncode, done.stdout.strip())\n"
    )
    result = under(door, [sys.executable, "-c", code], env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0 ['word']"
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "ssh was reached"


def test_outside_the_door_this_machine_is_refused_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(gatelib.LOCAL_TRANSPORT_ENV, "direct")
    with pytest.raises(SystemExit) as raised:
        gatelib.ssh("localhost", "python3 -", input="print(1)")
    assert raised.value.code == 2


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "python3 -c 'print(1)' -",
        "python3 script.py",
        "curl -sf http://box1:8080/v1/models",
        "curl -sf --data-binary @/etc/passwd http://localhost:8080/",
        "echo !!notbase64!! | base64 -d | python3 -I -B -",
    ],
)
def test_a_command_no_step_makes_is_refused(command: str) -> None:
    done = localrig.run(command, input=None, timeout=10)
    assert done.returncode == localrig.REFUSED
    assert "refused" in done.stderr


@pytest.fixture
def answering() -> Iterator[int]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/v1/models":
                body = b'{"data": [{"id": "m"}]}'
                self.send_response(200)
            else:
                body = b'{"error": "no"}'
                self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield int(server.server_address[1])
    server.shutdown()
    server.server_close()


def test_a_health_probe_is_answered_as_curl_answers(answering: int) -> None:
    port = answering
    ok = localrig.run(
        f"curl -sf http://localhost:{port}/v1/models", input=None, timeout=10
    )
    assert (ok.returncode, json.loads(ok.stdout)) == (0, {"data": [{"id": "m"}]})
    gone = localrig.run(
        f"curl -sf http://localhost:{port}/is_sleeping", input=None, timeout=10
    )
    assert gone.returncode == localrig.CURL_HTTP_ERROR
    coded = localrig.run(
        f"curl -s -w '\\n%{{http_code}}' http://localhost:{port}/is_sleeping",
        input=None,
        timeout=10,
    )
    assert coded.returncode == 0 and coded.stdout.endswith("\n404")


def test_a_redirect_is_not_followed_and_no_proxy_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.2:9/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    try:
        done = localrig.run(
            f"curl -s -w '\\n%{{http_code}}' http://127.0.0.1:{port}/v1/models",
            input=None,
            timeout=10,
        )
    finally:
        server.shutdown()
        server.server_close()
    assert done.returncode == 0, done
    assert done.stdout.endswith("\n302")


def test_nothing_listening_is_curls_no_connection() -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    done = localrig.run(
        f"curl -sf http://127.0.0.1:{port}/v1/models", input=None, timeout=5
    )
    assert done.returncode == localrig.CURL_NO_CONNECTION


def test_the_gguf_discovery_lists_one_folder(tmp_path: Path) -> None:
    (tmp_path / "a.gguf").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"")
    (tmp_path / "deeper").mkdir()
    (tmp_path / "deeper" / "c.gguf").write_bytes(b"")
    done = localrig.run(
        f"find '{tmp_path}' -maxdepth 1 -name '*.gguf' -print", input=None, timeout=5
    )
    assert done.stdout.splitlines() == [str(tmp_path / "a.gguf")]


def test_the_lease_is_taken_stamped_and_released_in_this_machines_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(gatelib.LOCAL_TRANSPORT_ENV, "direct")
    monkeypatch.setattr(gatelib, "_over_ssh", _no_ssh)
    lease_file = Path.home() / ".mcgyvr" / "lease"
    mine = gatelib.new_lease("up", 4242)
    assert gatelib.lease_read("localhost") is None
    assert gatelib.lease_take("localhost", mine, held=None) is None
    assert lease_file.read_text().strip() == mine.line()

    other = gatelib.new_lease("down", 4343)
    assert gatelib.lease_take("localhost", other, held=None) == gatelib.Lease.parse(
        mine.line()
    )

    stamped = gatelib.lease_stamp("localhost", mine, "run-1")
    assert (gatelib.lease_read("localhost") or stamped).run_id == "run-1"
    assert gatelib.lease_release("localhost", other.lease_id) is True
    assert lease_file.exists(), "another run's id released the lease"
    assert gatelib.lease_release("localhost", mine.lease_id) is True
    assert not lease_file.exists()


def _no_ssh(*_a: object) -> object:
    raise AssertionError("the lease went over ssh")
