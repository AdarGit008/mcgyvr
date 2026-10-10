"""``serve fetch`` downloads weights on the rig, resumes, and keeps only what hashes.

Owner, 2026-10-07 (Round 5, the door's user mode, approved as drafted): the
door gets ``serve fetch``, stdlib only and run on the rig, which resumes from
a ``.part`` file, checks the Hub's sha256 and renames into place only on a
match. Downloads have no cap, and the total is shown before (Round 3, OQ3). A
Hugging Face token comes from a variable the caller names and goes only to the
fetch step: never on a command line, never into a file.

What a fetch is asked for is a list of files, each with the repository, the
revision, the file, its sha256 and its size, as the model knowledge records
them (:class:`mcgyvr.knowledge.record.Weights`, ``size_bytes``).

The Hub here is a server on this machine's loopback, named to the door by
``HF_ENDPOINT``; the rig is the invented one of :mod:`tests.usermode`, whose
ssh runs the shipped fetcher with a home folder of its own.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from mcgyvr.knowledge.record import Number, Weights
from mcgyvr.scan import Scan
from mcgyvr.serving import fetchlist, rigfile, rigscan
from tests import onedoor, usermode

REPO = "invented-org/Invented-Coder-GGUF"
REVISION = "0123456789abcdef0123456789abcdef01234567"
#: Not a real token; what the test hands the door under the variable it names.
TOKEN = "hf_invented_test_token_0000"


def _blob(seed: int, size: int) -> bytes:
    return bytes((seed + index * 7) % 251 for index in range(size))


SMALL = _blob(3, 300_000)
LARGE = _blob(11, 1_200_000)
FILES = {"coder-s-Q4_K_M.gguf": SMALL, "coder-m-Q4_K_M.gguf": LARGE}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Hub:
    """A Hub on loopback: ``/<repo>/resolve/<rev>/<file>`` redirects to
    ``/cdn/<file>``, which honours ``Range: bytes=N-``.

    ``cut_after`` ends a body after that many bytes, as a dropped connection
    does; ``refuse`` answers that status to the resolve URL; ``serve`` stands in
    other bytes for a file.
    """

    url: str = ""
    asked: list[dict[str, str | None]] = field(default_factory=list)
    cut_after: int | None = None
    refuse: int | None = None
    serve: dict[str, bytes] = field(default_factory=lambda: dict(FILES))


@pytest.fixture
def hub() -> Iterator[Hub]:
    state = Hub()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def do_GET(self) -> None:
            state.asked.append(
                {
                    "path": self.path,
                    "range": self.headers.get("Range"),
                    "authorization": self.headers.get("Authorization"),
                }
            )
            prefix = f"/{REPO}/resolve/{REVISION}/"
            if self.path.startswith(prefix):
                if state.refuse is not None:
                    self.send_error(state.refuse)
                    return
                self.send_response(302)
                self.send_header("Location", "/cdn/" + self.path[len(prefix) :])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            name = self.path.removeprefix("/cdn/")
            if not self.path.startswith("/cdn/") or name not in state.serve:
                self.send_error(404)
                return
            data = state.serve[name]
            start = 0
            asked = self.headers.get("Range")
            if asked and asked.startswith("bytes=") and asked.endswith("-"):
                start = int(asked[len("bytes=") : -1])
                if start >= len(data):
                    self.send_error(416)
                    return
                self.send_response(206)
                self.send_header(
                    "Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}"
                )
            else:
                self.send_response(200)
            body = data[start:]
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if state.cut_after is not None:
                self.wfile.write(body[: state.cut_after])
                self.wfile.flush()
                self.close_connection = True
                return
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def _rig() -> None:
    rigfile.write(
        rigfile.from_scan(
            usermode.RIG, Scan.from_json(json.dumps(usermode.scan_payload()))
        )
    )


def _wanted(tmp_path: Path, files: dict[str, bytes] = FILES) -> Path:
    path = tmp_path / "weights.json"
    path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "repo": REPO,
                        "revision": REVISION,
                        "file": name,
                        "sha256": _sha(data),
                        "bytes": len(data),
                    }
                    for name, data in files.items()
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _weights(stubs: Path) -> Path:
    """The weights folder on the invented rig: its home's default."""
    return stubs / "rig-home" / ".cache" / "mcgyvr" / "weights"


def _fetch(
    tmp_path: Path,
    stubs: Path,
    hub: Hub,
    *extra: str,
    wanted: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    listed = wanted if wanted is not None else _wanted(tmp_path)
    done = usermode.door(
        [
            "serve",
            "fetch",
            "--host",
            usermode.RIG,
            "--weights",
            str(listed),
            "--date",
            usermode.RUN_DATE,
            *extra,
        ],
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={
            "MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path)),
            "HF_ENDPOINT": hub.url,
            "HF_TOKEN": TOKEN,
            **(env or {}),
        },
    )
    return done.returncode, done.stdout + done.stderr


def _record(home: Path) -> dict[str, object]:
    runs = usermode.door_logs(home)
    record: dict[str, object] = json.loads(
        (runs[-1] / "serve-fetch.json").read_text(encoding="utf-8")
    )
    return record


def _states(home: Path) -> dict[str, str]:
    rows = _record(home)["files"]
    assert isinstance(rows, list)
    return {row["file"]: row["state"] for row in rows}


def _everything_written(*roots: Path) -> str:
    text = []
    for root in roots:
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix != ".gguf"
                and "rig-home" not in path.parts
            ):
                text.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(text)


def test_a_fetch_says_the_total_first_then_files_each_weight_whose_hash_matches(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())

    code, said = _fetch(tmp_path, stubs, hub)

    assert code == 0, said
    total = len(SMALL) + len(LARGE)
    first = said.index(f"{total} bytes")
    assert first < said.index("fetched"), said
    for name, data in FILES.items():
        assert (_weights(stubs) / name).read_bytes() == data
    assert not list(_weights(stubs).glob("*.part"))
    assert _states(usermode.home()) == dict.fromkeys(FILES, "fetched")
    assert _record(usermode.home())["total_bytes"] == total


def test_the_token_goes_to_the_hub_only_and_is_written_nowhere(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())

    code, said = _fetch(tmp_path, stubs, hub)

    assert code == 0, said
    resolves = [row for row in hub.asked if "/resolve/" in str(row["path"])]
    downloads = [row for row in hub.asked if str(row["path"]).startswith("/cdn/")]
    assert resolves and downloads
    assert all(row["authorization"] == f"Bearer {TOKEN}" for row in resolves)
    assert all(row["authorization"] is None for row in downloads), (
        "the token followed a redirect"
    )
    assert TOKEN not in said
    assert TOKEN not in "\n".join(onedoor.ssh_log(stubs))
    assert TOKEN not in _everything_written(usermode.home(), stubs, tmp_path)


def test_a_cut_download_keeps_its_part_and_the_next_fetch_resumes_it(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())
    one = {"coder-m-Q4_K_M.gguf": LARGE}
    wanted = _wanted(tmp_path, one)
    hub.cut_after = 400_000

    code, said = _fetch(tmp_path, stubs, hub, wanted=wanted)

    assert code == 1, said
    part = _weights(stubs) / "coder-m-Q4_K_M.gguf.part"
    assert part.read_bytes() == LARGE[:400_000]
    assert not (_weights(stubs) / "coder-m-Q4_K_M.gguf").exists()
    assert _states(usermode.home()) == {"coder-m-Q4_K_M.gguf": "incomplete"}

    hub.cut_after = None
    hub.asked.clear()
    code, said = _fetch(tmp_path, stubs, hub, "--suffix", "again", wanted=wanted)

    assert code == 0, said
    assert (_weights(stubs) / "coder-m-Q4_K_M.gguf").read_bytes() == LARGE
    assert not part.exists()
    ranges = [row["range"] for row in hub.asked if str(row["path"]).startswith("/cdn/")]
    assert ranges == ["bytes=400000-"], ranges
    assert _states(usermode.home()) == {"coder-m-Q4_K_M.gguf": "resumed"}


def test_a_download_whose_hash_does_not_match_leaves_no_file(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())
    hub.serve["coder-s-Q4_K_M.gguf"] = _blob(99, len(SMALL))

    code, said = _fetch(tmp_path, stubs, hub)

    assert code == 1, said
    assert not (_weights(stubs) / "coder-s-Q4_K_M.gguf").exists()
    assert not (_weights(stubs) / "coder-s-Q4_K_M.gguf.part").exists()
    assert (_weights(stubs) / "coder-m-Q4_K_M.gguf").read_bytes() == LARGE
    assert _states(usermode.home()) == {
        "coder-s-Q4_K_M.gguf": "mismatch",
        "coder-m-Q4_K_M.gguf": "fetched",
    }
    assert "sha256" in said


def test_a_part_whose_start_is_not_the_files_is_resumed_then_thrown_away(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())
    one = {"coder-s-Q4_K_M.gguf": SMALL}
    folder = _weights(stubs)
    folder.mkdir(parents=True)
    (folder / "coder-s-Q4_K_M.gguf.part").write_bytes(b"\0" * 1000)

    code, said = _fetch(tmp_path, stubs, hub, wanted=_wanted(tmp_path, one))

    assert code == 1, said
    assert list(folder.iterdir()) == []
    assert _states(usermode.home()) == {"coder-s-Q4_K_M.gguf": "mismatch"}


def test_a_file_already_there_that_matches_is_not_fetched_again(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())
    folder = _weights(stubs)
    folder.mkdir(parents=True)
    (folder / "coder-s-Q4_K_M.gguf").write_bytes(SMALL)

    code, said = _fetch(tmp_path, stubs, hub)

    assert code == 0, said
    assert not any("coder-s" in str(row["path"]) for row in hub.asked)
    assert _states(usermode.home()) == {
        "coder-s-Q4_K_M.gguf": "present",
        "coder-m-Q4_K_M.gguf": "fetched",
    }


def test_a_different_file_of_the_same_name_is_left_as_it_is(
    tmp_path: Path, hub: Hub
) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())
    one = {"coder-s-Q4_K_M.gguf": SMALL}
    folder = _weights(stubs)
    folder.mkdir(parents=True)
    theirs = b"someone else's file"
    (folder / "coder-s-Q4_K_M.gguf").write_bytes(theirs)

    code, said = _fetch(tmp_path, stubs, hub, wanted=_wanted(tmp_path, one))

    assert code == 1, said
    assert (folder / "coder-s-Q4_K_M.gguf").read_bytes() == theirs
    assert hub.asked == []
    assert _states(usermode.home()) == {"coder-s-Q4_K_M.gguf": "refused"}


def test_a_gated_answer_names_the_token_variable(tmp_path: Path, hub: Hub) -> None:
    _rig()
    stubs = usermode.machine(tmp_path, pending=())
    hub.refuse = 401

    code, said = _fetch(tmp_path, stubs, hub)

    assert code == 1, said
    assert "HF_TOKEN" in said
    assert "401" in said


def test_a_token_variable_named_and_empty_is_refused_before_any_gate(
    tmp_path: Path, hub: Hub
) -> None:
    stubs = usermode.machine(tmp_path, pending=())

    code, said = _fetch(
        tmp_path,
        stubs,
        hub,
        "--hf-token-env",
        "MY_HUB_TOKEN",
        env={"MY_HUB_TOKEN": ""},
    )

    assert code == 2, said
    assert "MY_HUB_TOKEN" in said
    assert onedoor.ssh_log(stubs) == []
    assert hub.asked == []


@pytest.mark.parametrize(
    "bad",
    [
        {"sha256": "abc"},
        {"revision": "main"},
        {"file": "../escape.gguf"},
        {"bytes": 0},
        {"extra": 1},
    ],
)
def test_a_list_the_door_cannot_hold_to_a_hash_is_refused_before_any_gate(
    tmp_path: Path, hub: Hub, bad: dict[str, object]
) -> None:
    stubs = usermode.machine(tmp_path, pending=())
    row: dict[str, object] = {
        "repo": REPO,
        "revision": REVISION,
        "file": "coder-s-Q4_K_M.gguf",
        "sha256": _sha(SMALL),
        "bytes": len(SMALL),
        **bad,
    }
    wanted = tmp_path / "bad.json"
    wanted.write_text(json.dumps({"files": [row]}), encoding="utf-8")

    code, said = _fetch(tmp_path, stubs, hub, wanted=wanted)

    assert code == 2, said
    assert onedoor.ssh_log(stubs) == []


def test_a_plain_http_hub_is_refused_unless_it_is_this_machine(
    tmp_path: Path, hub: Hub
) -> None:
    stubs = usermode.machine(tmp_path, pending=())

    code, said = _fetch(
        tmp_path, stubs, hub, env={"HF_ENDPOINT": "http://mirror.invalid"}
    )

    assert code == 2, said
    assert "HF_ENDPOINT" in said
    assert onedoor.ssh_log(stubs) == []


def test_the_list_is_what_the_model_knowledge_records() -> None:
    weights = Weights(
        repo=REPO, revision=REVISION, file="coder-s-Q4_K_M.gguf", sha256=_sha(SMALL)
    )
    size = Number(len(SMALL), "fact", f"hub-api:{REPO}@{REVISION}", date(2026, 10, 7))

    [want] = fetchlist.from_weights([(weights, size)])

    assert fetchlist.parse(fetchlist.dump([want])) == (want,)
    assert (want.repo, want.revision, want.file) == (REPO, REVISION, weights.file)
    assert (want.sha256, want.bytes) == (_sha(SMALL), len(SMALL))


def test_the_fetcher_and_the_rig_scan_name_the_same_weights_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr.serving import fetcher

    monkeypatch.delenv("MCGYVR_WEIGHTS", raising=False)
    assert fetcher.weights_dir() == rigscan._default_weights_dir()
    monkeypatch.setenv("MCGYVR_WEIGHTS", str(tmp_path / "w"))
    assert fetcher.weights_dir() == rigscan._default_weights_dir()
    assert os.fspath(tmp_path / "w") == fetcher.weights_dir()
