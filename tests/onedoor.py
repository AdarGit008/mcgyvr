"""The seam the one-door tests drive ``python -m mcgyvr.serving.run`` through.

``src/mcgyvr/serving/run.py`` is the one access point to the rigs. A test may
not touch a rig, and the door has no variable that names a substitute for a
reading — the archived door's three seam variables left with it
(``tests/test_no_retired_door_names.py`` spells them), because a variable
that replaces a reading is a variable that skips one. What the door DOES have
is a PATH: it puts its own ``ssh`` and ``docker`` shims first, and each shim,
having admitted the host, execs the NEXT binary of that name on PATH. So a
test stands an ``ssh`` and a ``docker`` of its own behind the shims, in a
directory the door's environment leads with, and answers by the remote
command it is handed.

Everything here is built around one idea: a :class:`Scenario` is what an
operator would type, and :func:`door` is the only code that knows how that
becomes an argv. A test never spells ``--host`` itself.

The fixture (:func:`fixture_repo`) is a throw-away checkout the door can be
run FROM — it is invoked as ``python <fixture>/src/mcgyvr/serving/run.py``,
because the door derives its repo root from its own file — holding:

* a copy of ``src/mcgyvr/serving/`` (the door, its gates and its shims) and of
  ``tools/bench/product.py``; every other entry of ``product.SURFACE`` exists
  as a stub so gate 1's digest can be taken; ``rounds.json`` is written LAST,
  pinning that digest, so gate 1 admits the tree as built;
* ``tools/runs/`` minus the campaigns (``hosts.json``, ``rows.py``,
  ``workload.py``, ``_common.sh``, the drivers), so the tests own the campaign
  list; the tree is ``git init``ed because ``_common.sh`` locates the repo
  with ``git rev-parse`` when ``RUN_REPO`` is unset — and the door refuses
  ``RUN_REPO`` from the calling shell like every other ``RUN_*``;
* ``stubs/``, first on the PATH :func:`door_env` builds: the ``ssh`` reads the
  rig-snapshot request off its command line and answers from
  ``snapshot.txt`` (or ``snapshot-moved.txt`` once a flag file the test names
  exists — the reading srv1 gave after a hard lock wiped its BIOS profile), the
  geometry read from ``geometry.json`` (one row seeded from a recorded
  envelope), and the rest with canned lines; the ``docker`` logs every argv it
  is handed and answers ``info``, ``version``, ``image inspect`` and ``ps``.

The driver-seam tests do not go through the door: :func:`bare_env` puts the
same two stubs on PATH with ``RUN_HOST`` set. A driver and the emitter's two
rig-reaching functions prove the door before anything else, though, so a
test that must get PAST that proof runs them under :func:`fake_door` — a
stand-in whose path ends in ``mcgyvr/serving/run.py``, which is what
``gatelib.under_door`` reads off /proc — with ``RUN_ROOT`` naming this tree
and ``RUN_BIN`` its shim directory, where the emitter finds the real shims by
path.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "tools" / "runs"
#: The door and everything it spawns. Copied whole into a fixture.
SERVING_SRC = REPO / "src" / "mcgyvr" / "serving"
#: The door's shim directory — what it exports as ``RUN_BIN``, and where a
#: step run bare under a fake door is told to find the shims.
BIN = SERVING_SRC / "gate-scripts" / "bin"
DOOR_REL = Path("src") / "mcgyvr" / "serving" / "run.py"
PRODUCT_PY = REPO / "tools" / "bench" / "product.py"
COMMON_SH = RUNS / "_common.sh"
ROWS_PY = RUNS / "rows.py"
WORKLOAD_PY = RUNS / "workload.py"
HOSTS_JSON = RUNS / "hosts.json"
DRIVERS = RUNS / "drivers"
CAMPAIGNS = RUNS / "campaigns"
KERNEL_ARMS = CAMPAIGNS / "srv1-kernel-arms"
#: One geometry the door once read on srv1, so the placement the fixture's
#: run derives is derived from a real tensor table and not from a number
#: invented to fit.
GEOMETRY_JSON = (
    REPO
    / "records"
    / "evidence"
    / "2026-09-05-e2e-srv1-gemma-4-26b-a4b-it-ud-iq3xxs"
    / "geometry.json"
)
MODEL = "/models/moe/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf"

DRIVER_NAMES = ("lcp_sweep.py", "vllm_sweep.py", "vllm_cores.py")
#: The image variable each driver reads.
DRIVER_IMG_VAR = {
    "lcp_sweep.py": "LCP_IMG",
    "vllm_sweep.py": "VLLM_IMG",
    "vllm_cores.py": "VLLM_IMG",
}
#: Argument lists that get each driver past ``sys.argv`` and to its first
#: docker call, and no further: the cell is legal but the container never
#: comes up, so the driver records a refusal and returns.
DRIVER_ARGV = {
    "lcp_sweep.py": ["model.gguf", "/nonexistent/models", "T", "1:2048:0:1"],
    "vllm_sweep.py": ["T", "org/model", "0.9:2048:8:auto:1"],
    "vllm_cores.py": ["pair", "0.45", "2048", "128", "auto", "1", "a=org/model"],
}
#: The nine steps of the kernel-arms campaign, by the name that follows ``<n>-``.
STEP_NAMES = frozenset(
    {
        "aa-null",
        "build-ladder",
        "correctness",
        "crash",
        "kernel-arms",
        "llama-bench",
        "moe-slots",
        "ncmoe-floor",
        "vllm-arms",
    }
)

RUN_DATE = "2026-09-05"
ROUND_ID = "r9-onedoor"
#: A digest-shaped value for artifacts a test writes BY HAND to stand for an
#: earlier run. The digest the door itself stamps is the fixture's own —
#: :func:`pinned` reads it back — and is never this constant.
PRODUCT_SHA256 = "3f9c1a7e5b2d4c6f8a0e1b3d5f7a9c2e4b6d8f0a1c3e5b7d9f2a4c6e8b0d1f3a"
#: Digests the docker stub knows. ``vllm/vllm-openai:v0.26.0`` has a registry
#: digest; ``llamacpp:b10644-L3`` is a local build and has only an image id.
REPO_DIGEST_HEX = "9d2b5e1c7a4f3b8e6c0d1a2f5b7c9e3d4a6b8c0e2f4a6c8e0b2d4f6a8c0e2b4d"
IMAGE_ID_HEX = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b"
LOCAL_ID_HEX = "c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00"
VLLM_TAG = "vllm/vllm-openai:v0.26.0"
VLLM_DIGEST = f"vllm/vllm-openai@sha256:{REPO_DIGEST_HEX}"
LOCAL_TAG = "llamacpp:b10644-L3"
LCP_TAG = "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644"
LCP_DIGEST = f"ghcr.io/ggml-org/llama.cpp@sha256:{REPO_DIGEST_HEX}"
#: A label value that LOOKS like a digest. ``1-build-ladder.sh`` labels every
#: rung ``org.mcgyvr.build.toolkit=$RUN_CUDA_DEVEL`` and that base image may be
#: pinned by digest; ``docker image inspect`` prints ``Config.Labels`` after
#: ``RepoDigests``, so a resolver that greps the whole document for the first
#: ``@sha256:`` would hand a driver the toolkit instead of the rung.
TOOLKIT_DIGEST = "nvidia/cuda@sha256:" + "a" * 64

UPTIME = "2026-09-01T08:11:08Z"
#: The rig's own ``$HOME`` as the ssh stub answers it.
RIG_HOME = "/home/x"
#: What ``bare_env`` names as the rig. RFC 6761 reserves ``.invalid``: it never
#: resolves, so a driver's health probe fails at once and no real machine is
#: touched by a test that runs a driver bare.
BARE_HOST = "rig.invalid"

#: The declared keys — ``tools/runs/hosts.json[host].rig``, what gate 2
#: compares. Strings, because that is what a ``k=v`` line carries.
RIG: dict[str, dict[str, str]] = {
    "srv1": {
        "cpu_max_mhz": "4600",
        "cpu_model": "Intel(R)_Core(TM)_i5-9600K_CPU_@_3.70GHz",
        "ram_mt_s": "3600",
        "pl1_uw": "95000000",
        "pl2_uw": "120000000",
        "gpu_name": "NVIDIA_GeForce_GTX_1660_SUPER",
        "gpu_vram_mib": "6144",
        "gpu_cc": "7.5",
        "driver": "580.173.02",
        "gpu_reserve_mib": "401",
        "docker": "29.7.2",
    },
    "srv2": {
        "cpu_max_mhz": "5200",
        "cpu_model": "Intel(R)_Core(TM)_i9-10900F_CPU_@_2.80GHz",
        "ram_mt_s": "2933",
        "pl1_uw": "65000000",
        "pl2_uw": "0",
        "gpu_name": "NVIDIA_GeForce_RTX_3060",
        "gpu_vram_mib": "12288",
        "gpu_cc": "8.6",
        "driver": "595.84",
        "gpu_reserve_mib": "377",
        "docker": "29.7.2",
    },
}
RIG_KEYS = frozenset(RIG["srv1"])
RIG_READ_ON = "2026-09-03"
#: What ``rig-snapshot.sh`` prints beyond the declared keys: the two VRAM
#: figures a placement spends, the host memory, the thread count, the name
#: the daemon must answer to (gate 3), and the two idle readings gate 2 holds
#: to ``none``. srv1's are the recorded 2026-09-05 scan.
LIVE: dict[str, dict[str, str]] = {
    "srv1": {
        "gpu_used_mib": "17",
        "gpu_free_mib": "5727",
        "mem_available_kib": "14835712",
        "nproc": "6",
        "hostname": "srv1",
        "gpu_procs": "none",
        "containers": "none",
    },
    "srv2": {
        "gpu_used_mib": "0",
        "gpu_free_mib": "11911",
        "mem_available_kib": "26214400",
        "nproc": "20",
        "hostname": "srv2",
        "gpu_procs": "none",
        "containers": "none",
    },
}


def rows_module() -> ModuleType:
    """``tools.runs.rows`` — the parser gate 8 reads an artifact with."""
    if not ROWS_PY.is_file():
        raise FileNotFoundError(f"{ROWS_PY.relative_to(REPO)} does not exist")
    return importlib.import_module("tools.runs.rows")


def _product() -> ModuleType:
    return importlib.import_module("tools.bench.product")


def snapshot_lines(host: str, **override: str) -> str:
    """One ``rig-snapshot.sh`` reading for ``host``, as the rig prints it."""
    values = {"uptime_since": UPTIME, **RIG[host], **LIVE[host], **override}
    return "".join(f"{k}={v}\n" for k, v in values.items())


def executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


#: A stand-in for the door: a file whose path ends in mcgyvr/serving/run.py —
#: as a copy of the door in a fixture tree does — that runs its arguments as
#: a child. What the child reads in /proc is exactly what a gate, a step or a
#: driver reads under the real door: ``gatelib.is_door`` matches the suffix.
FAKE_DOOR = (
    "import subprocess, sys\n"
    "raise SystemExit(subprocess.run(sys.argv[1:]).returncode)\n"
)


def fake_door(tmp_path: Path) -> Path:
    return executable(tmp_path / "door" / "mcgyvr" / "serving" / "run.py", FAKE_DOOR)


# --------------------------------------------------------------------------
# the stubs behind the shims
# --------------------------------------------------------------------------

#: The ``ssh`` the door's shim execs. The shim has already admitted the host
#: and prepended ``-o BatchMode=yes -o ConnectTimeout=10``; what is left is
#: ``[-o X ...] HOST COMMAND...``, and the answer depends on COMMAND alone.
#: stdin is read only where the caller is known to pipe something (the
#: reader shipped to ``bash -s``, a line teed with ``cat >>``): a stub that
#: read an inherited stdin would hang a door run under a terminal.
SSH_STUB = """\
#!/usr/bin/env bash
set -u
STUBS=$(cd "$(dirname "$0")" && pwd)
printf '%.200s\\n' "$*" >> "$STUBS/ssh.log"
while [ $# -gt 0 ]; do
  case $1 in
    -o) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
host=${1:-}; shift || true
cmd="$*"
if [ -e "$STUBS/ssh-down" ]; then
  echo "ssh: connect to host $host port 22: Connection refused" >&2
  exit 255
fi
case $cmd in
  "bash -s")
    cat >/dev/null
    if [ -f "$STUBS/moved-flag" ] && [ -e "$(cat "$STUBS/moved-flag")" ]; then
      f="$STUBS/snapshot-moved.txt"
    else
      f="$STUBS/snapshot.txt"
    fi
    # While the daemon lists serving units (serving-names), the rig reads
    # busy: the card is held and containers are up, as a serving rig is.
    if [ -f "$STUBS/serving-names" ]; then
      sed -e 's/^containers=.*/containers=c0ffee000011;c0ffee000012/' \
          -e 's/^gpu_procs=.*/gpu_procs=4242,llama-server,5584MiB/' "$f"
    else
      cat "$f"
    fi ;;
  *"python3 -"*) cat "$STUBS/geometry.json" ;;
  *'echo $HOME'*) echo "$STUB_RIG_HOME" ;;
  *"cat >>"*) cat >/dev/null ;;
  *mkdir*) : ;;
  *"memory.used,memory.free"*) echo "$STUB_USED, $STUB_FREE" ;;
  *memory.free*) echo "$STUB_FREE" ;;
  *memory.used*) echo "$STUB_USED" ;;
  *constraint_0_power_limit_uw*) echo 95000000 ;;
  *constraint_1_power_limit_uw*) echo 120000000 ;;
  *query-compute-apps*) : ;;
  *"v1/models"*) echo '{"data":[{"id":"stub-model"}]}' ;;
  *health*) : ;;
  *completion*) echo '{"content":"hi"}' ;;
  *) echo "ssh stub: no answer for: ${cmd:0:120}" >&2; exit 1 ;;
esac
"""

#: What every ``docker`` stub starts with. Under the door the shim prepends
#: ``-H ssh://RUN_HOST``; the prologue checks it names the door's host and
#: drops it, logs docker's own argv, and answers the two questions gate 3
#: asks — ``info`` (the daemon's name, which must be the machine gate 2 read)
#: and ``version`` — from the same snapshot the ssh stub serves, unless a
#: test has written ``docker-name`` / ``docker-version`` beside it.
DOCKER_PROLOGUE = """\
#!/usr/bin/env bash
set -u
STUBS=$(cd "$(dirname "$0")" && pwd)
if [ "${1:-}" = -H ]; then
  if [ "${2:-}" != "ssh://${RUN_HOST:-}" ]; then
    echo "docker stub: -H ${2:-} is not the door's host ssh://${RUN_HOST:-}" >&2
    exit 1
  fi
  shift 2
fi
printf '%s\\n' "$*" >> "$STUBS/docker.log"
case "${1:-}" in
  info)
    if [ -e "$STUBS/daemon-down" ]; then
      echo "Cannot connect to the Docker daemon at ssh://${RUN_HOST:-}" >&2
      exit 1
    fi
    if [ -f "$STUBS/docker-name" ]; then cat "$STUBS/docker-name"
    else sed -n 's/^hostname=//p' "$STUBS/snapshot.txt"; fi
    exit 0 ;;
  version)
    if [ -f "$STUBS/docker-version" ]; then cat "$STUBS/docker-version"
    else sed -n 's/^docker=//p' "$STUBS/snapshot.txt"; fi
    exit 0 ;;
esac
"""

_DOCKER_BODY = """\
case "${1:-}" in
  ps)
    if [ -f "$STUBS/ps-sleep" ]; then sleep "$(cat "$STUBS/ps-sleep")"; fi
    case "$*" in *ID*) with_id=1 ;; *) with_id=0 ;; esac
    row() {
      if [ "$with_id" = 1 ]; then printf '%s\\t%s\\n' "$1" "$2"
      else printf '%s\\n' "$2"; fi
    }
    if [ -f "$STUBS/leftover-flag" ] && [ -e "$(cat "$STUBS/leftover-flag")" ]; then
      row c0ffee000001 "${RUN_ID:-norunid}-lcps"
    fi
    if [ -f "$STUBS/stray-flag" ] && [ -e "$(cat "$STUBS/stray-flag")" ]; then
      row c0ffee000002 "STRAY_NAME"
    fi
    if [ -f "$STUBS/serving-names" ]; then
      n=10
      while read -r name; do
        [ -n "$name" ] || continue
        n=$((n + 1))
        row "c0ffee0000$n" "$name"
      done < "$STUBS/serving-names"
    fi
    exit 0 ;;
  compose)
    # `compose ... up -d` brings up what a test queued (serving-pending
    # becomes serving-names, which `ps` and the rig's snapshot then list);
    # `down` clears it, unless a test pinned the names in place
    # (compose-down-sticks).
    case " $* " in
      *" up "*)
        [ -f "$STUBS/serving-pending" ] &&
          mv "$STUBS/serving-pending" "$STUBS/serving-names" ;;
      *" down "*) [ -e "$STUBS/compose-down-sticks" ] || rm -f "$STUBS/serving-names" ;;
    esac
    exit 0 ;;
  image | inspect) ;;
  *) exit 0 ;;
esac
tag= ; fmt=
while [ "$#" -gt 0 ]; do
  case $1 in
    --format | -f) fmt=$2; shift ;;
    --format=*) fmt=${1#--format=} ;;
    image | inspect) ;;
    -*) ;;
    *) tag=$1 ;;
  esac
  shift
done
case "$tag" in
  VLLM_TAG) id=IMAGE_ID_HEX; rd='VLLM_DIGEST' ;;
  LOCAL_TAG) id=LOCAL_ID_HEX; rd= ;;
  *) printf "Error response from daemon: No such image: %s\\n" "$tag" >&2; exit 1 ;;
esac
if [ -n "$fmt" ]; then
  case "$fmt" in
    *RepoDigests*) [ -n "$rd" ] && { printf "%s\\n" "$rd"; exit 0; }
      case "$fmt" in *Id*) printf "sha256:%s\\n" "$id" ;; esac
      exit 0 ;;
    *Id*) printf "sha256:%s\\n" "$id"; exit 0 ;;
  esac
fi
printf '[\\n    {\\n        "Id": "sha256:%s",\\n\
        "RepoTags": [\\n            "%s"\\n        ],\\n\
        "RepoDigests": [%s],\\n\
        "Config": {\\n            "Labels": {\\n\
                "org.mcgyvr.build.toolkit": "TOOLKIT_DIGEST"\\n\
            }\\n        }\\n    }\\n]\\n' "$id" "$tag" "${rd:+\\"$rd\\"}"
"""


def docker_stub_text(body: str) -> str:
    """A complete ``docker`` stub: :data:`DOCKER_PROLOGUE`, then ``body``,
    which sees docker's own argv in ``$@`` and the stub directory in ``$STUBS``."""
    return DOCKER_PROLOGUE + body


def ssh_stub(where: Path) -> Path:
    """The ``ssh`` that stands behind the shim in ``where``. Reaches nothing."""
    return executable(where / "ssh", SSH_STUB)


#: What the docker stub calls a container the run did NOT name: no ``RUN_ID-``
#: prefix, the shape a driver's own ``--name`` or a hand-started server has.
STRAY_NAME = "vllm-someone-elses"


def docker_stub(
    where: Path,
    *,
    leftover_flag: Path | None = None,
    stray_flag: Path | None = None,
    daemon_down: bool = False,
    ps_sleep: float | None = None,
) -> Path:
    """The default ``docker`` in ``where``; every argv line lands in ``docker.log``.

    ``ps`` prints nothing until ``leftover_flag`` exists, then lists (id and
    name, tab-separated, as ``--format '{{.ID}}\\t{{.Names}}'`` does) a
    container that carries the run's ``RUN_ID`` prefix; once ``stray_flag``
    exists it lists :data:`STRAY_NAME` too, a container with no such prefix.
    ``ps_sleep`` makes every ``ps`` take that many seconds first, after the
    argv is logged — for a test that must catch the door inside gate 7.
    ``image inspect`` answers for the two tags the tests use and refuses any
    other, honouring ``--format`` for ``RepoDigests`` and ``Id``; the plain
    JSON it prints has the real document's shape — ``RepoDigests`` first,
    then a ``Config.Labels`` block whose toolkit label carries
    :data:`TOOLKIT_DIGEST`. ``daemon_down`` makes ``info`` fail the way a CLI
    with no daemon behind it does.
    """
    body = (
        _DOCKER_BODY.replace("VLLM_TAG", VLLM_TAG)
        .replace("VLLM_DIGEST", VLLM_DIGEST)
        .replace("IMAGE_ID_HEX", IMAGE_ID_HEX)
        .replace("LOCAL_TAG", LOCAL_TAG)
        .replace("LOCAL_ID_HEX", LOCAL_ID_HEX)
        .replace("TOOLKIT_DIGEST", TOOLKIT_DIGEST)
        .replace("STRAY_NAME", STRAY_NAME)
    )
    for filename, value in (
        ("leftover-flag", leftover_flag),
        ("stray-flag", stray_flag),
    ):
        flag = where / filename
        if value is None:
            flag.unlink(missing_ok=True)
        else:
            flag.write_text(str(value), encoding="utf-8")
    down = where / "daemon-down"
    if daemon_down:
        down.touch()
    else:
        down.unlink(missing_ok=True)
    delay = where / "ps-sleep"
    if ps_sleep is None:
        delay.unlink(missing_ok=True)
    else:
        delay.write_text(str(ps_sleep), encoding="utf-8")
    return executable(where / "docker", docker_stub_text(body))


def rig_stub(
    where: Path, host: str, *, moved_flag: Path | None = None, **override: str
) -> Path:
    """What the rig answers ``bash -s`` with: ``host``'s reading, ``override``
    applied. Once ``moved_flag`` exists it reads PL1 at 4095 W instead — the
    reading srv1 gave at 05:57 after a hard lock wiped its BIOS profile."""
    (where / "snapshot.txt").write_text(
        snapshot_lines(host, **override), encoding="utf-8"
    )
    (where / "snapshot-moved.txt").write_text(
        snapshot_lines(host, **override, pl1_uw="4095000000"), encoding="utf-8"
    )
    flag = where / "moved-flag"
    if moved_flag is None:
        flag.unlink(missing_ok=True)
    else:
        flag.write_text(str(moved_flag), encoding="utf-8")
    return where / "snapshot.txt"


def rig_unreadable(where: Path) -> None:
    """Every ssh fails the way a rig that is down does."""
    (where / "ssh-down").touch()


def stub_sleep(where: Path) -> Path:
    """A ``sleep`` that returns at once, for a step whose retry loop would
    otherwise wait real seconds between attempts a stub decides."""
    return executable(where / "sleep", "#!/usr/bin/env bash\nexit 0\n")


def stubs_dir(root: Path) -> Path:
    return root / "stubs"


def _log(where: Path, name: str) -> list[str]:
    directory = where if where.is_dir() else where.parent
    if (directory / "stubs").is_dir():
        directory = directory / "stubs"
    path = directory / name
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def docker_log(where: Path) -> list[str]:
    """Every argv the docker stub saw, one line each. ``where`` is the fixture
    root, the stub directory, or the stub itself."""
    return _log(where, "docker.log")


def ssh_log(where: Path) -> list[str]:
    return _log(where, "ssh.log")


# --------------------------------------------------------------------------
# the fixture
# --------------------------------------------------------------------------


def hosts_document() -> str:
    doc: dict[str, object] = {"hosts": ["srv1", "srv2"]}
    for host, rig in RIG.items():
        doc[host] = {"rig": dict(rig), "read_on": RIG_READ_ON}
    return json.dumps(doc, indent=2) + "\n"


def pin(root: Path) -> str:
    """Write ``rounds.json`` for the tree as it stands NOW, and return the digest.

    Called last by :func:`fixture_repo`; a test that changes a file under
    ``product.SURFACE`` afterwards calls it again, or gate 1 refuses.
    """
    digest: str = _product().digest(root)
    rounds = {
        "rounds": [
            {
                "id": ROUND_ID,
                "opened": RUN_DATE,
                "product_sha256": digest,
                "why": "the one-door fixture, pinned as built",
                "adopted": [],
            }
        ]
    }
    (root / "tools" / "bench" / "rounds.json").write_text(
        json.dumps(rounds, indent=1) + "\n", encoding="utf-8"
    )
    return digest


def unpin(root: Path) -> None:
    """Pin a digest this tree does not have: gate 1 must refuse."""
    pin(root)
    path = root / "tools" / "bench" / "rounds.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["rounds"][-1]["product_sha256"] = "deadbeef" * 8
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


def pinned(root: Path) -> tuple[str, str]:
    """The round id and digest the fixture's ``rounds.json`` declares."""
    doc = json.loads(
        (root / "tools" / "bench" / "rounds.json").read_text(encoding="utf-8")
    )
    last = doc["rounds"][-1]
    return str(last["id"]), str(last["product_sha256"])


def fixture_repo(tmp_path: Path, *, host: str = "srv1") -> Path:
    """A throw-away checkout the door can be run from and write into.

    The machine behind the stubs reads as ``host``'s declaration (srv1 unless
    said otherwise); :func:`rig_stub` changes that.
    """
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy(REPO / name, root / name)
    os.symlink(REPO / ".venv", root / ".venv")
    for name in ("__init__.py", "sweeprows.py"):
        shutil.copy(REPO / "tests" / name, root / "tests" / name)
    shutil.copytree(
        RUNS,
        root / "tools" / "runs",
        ignore=shutil.ignore_patterns("__pycache__", "campaigns"),
    )
    (root / "tools" / "runs" / "campaigns").mkdir()
    shutil.copytree(
        SERVING_SRC,
        root / "src" / "mcgyvr" / "serving",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (root / "tools" / "bench").mkdir(parents=True)
    shutil.copy2(PRODUCT_PY, root / "tools" / "bench" / "product.py")
    # Every other entry of the product surface, so the digest can be taken:
    # a declared entry that is missing is a refusal in surface_files.
    for entry in _product().SURFACE:
        target = root / entry
        if target.exists():
            continue
        if (REPO / entry).is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {entry}: a stub for the surface digest\n")
    subprocess.run(
        ["git", "init", "-q"],
        cwd=root,
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
    )
    stubs = stubs_dir(root)
    stubs.mkdir()
    ssh_stub(stubs)
    docker_stub(stubs)
    rig_stub(stubs, host)
    geometry = json.loads(GEOMETRY_JSON.read_text(encoding="utf-8"))
    (stubs / "geometry.json").write_text(json.dumps([geometry]), encoding="utf-8")
    pin(root)
    return root


def add_step(root: Path, campaign: str, filename: str, body: str) -> Path:
    path = root / "tools" / "runs" / "campaigns" / campaign / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return executable(path, body)


def probe_step(
    env_file: Path,
    *,
    after: str = "",
    end_line: str | None = None,
    directive: str = "RUN_ARTIFACTS",
) -> str:
    """A step that writes a conforming ``probe.tsv`` by hand and records the
    environment the door handed it in ``env_file``.

    It hand-writes every stamp, so it depends on nothing in ``_common.sh``:
    the gates around the step are what these tests are about. ``after`` runs
    once the artifact is complete (a flag for a stub); ``end_line`` replaces
    the ``### END`` line, for the parse gate; ``directive`` is the comment
    line the file is declared under (``RUN_REWRITES`` for a step that may run
    twice over it). The round it stamps is the one the door handed it, and
    both START and END name the run it was handed (``end_line`` may carry a
    ``%s`` for it, or not).
    """
    # `%s` is filled with "$RUN_ID" by the printf below: END names the run it
    # closes, as START names the one it opens, and gate 8 reads both.
    end = end_line or (
        f"### END uptime_since={UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "cpu_max_mhz=4600 ram_mt_s=3600 run_id=%s"
    )
    rig = " ".join(f"{k}={v}" for k, v in RIG["srv1"].items())
    return (
        "#!/usr/bin/env bash\n"
        f"# {directive}: probe.tsv\n"
        "set -euo pipefail\n"
        '[ -n "${RUN_ID:-}" ] || { echo "probe: RUN_ID is unset; start me '
        'through python -m mcgyvr.serving.run" >&2; exit 2; }\n'
        f"printf 'RUN_ID=%s\\nRUN_OUT_DIR=%s\\nRUN_HOST=%s\\nRUN_ROUND=%s\\n"
        "RUN_PRODUCT_SHA256=%s\\nRUN_STEP=%s\\n' "
        '"$RUN_ID" "${RUN_OUT_DIR:-}" "${RUN_HOST:-}" "${RUN_ROUND:-}" '
        f'"${{RUN_PRODUCT_SHA256:-}}" "${{RUN_STEP:-}}" > \'{env_file}\'\n'
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n'
        "{\n"
        "printf '### WORKLOAD digest=none comparable_with=microbenchmark-only\\n'\n"
        f"printf '### START uptime_since={UPTIME} pl1_uw=95000000 "
        "pl2_uw=120000000 pl1_source=constraint_0_power_limit_uw "
        'cpu_max_mhz=4600 ram_mt_s=3600 run_id=%s\\n\' "$RUN_ID"\n'
        "printf '### ROUND id=%s product_sha256=%s\\n' "
        '"${RUN_ROUND:-}" "${RUN_PRODUCT_SHA256:-}"\n'
        f"printf '### RIG {rig}\\n'\n"
        "printf '%s\\tprobe\\tCONFIG\\timg=sha256:%s\\n' "
        f'"${{RUN_HOST:-nohost}}" {LOCAL_ID_HEX}\n'
        f"printf '{end}\\n' \"$RUN_ID\"\n"
        '} > "$out"\n' + after + "\n"
    )


# --------------------------------------------------------------------------
# the door
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """What an operator types. ``step`` is a file name under
    ``tools/runs/campaigns/<campaign>/``, a path relative to the fixture root
    (or absolute), or ``""`` for the shipped default step. An empty ``host``
    leaves ``--host`` out, for the test that asks what the door does then."""

    campaign: str
    step: str
    host: str = "srv1"
    suffix: str = ""
    step_args: tuple[str, ...] = ()
    model: str = MODEL
    date: str = RUN_DATE
    parallel: int = 8
    ctx_per_slot: int = 2048
    ubatch: int = 512


def _step_path(root: Path, scenario: Scenario) -> Path:
    step = Path(scenario.step)
    if step.is_absolute():
        return step
    if len(step.parts) == 1:
        return root / "tools" / "runs" / "campaigns" / scenario.campaign / step
    return root / step


def _command(root: Path, scenario: Scenario | None) -> list[str]:
    """The ONLY place the door's path and argv shape are known."""
    argv = [sys.executable, str(root / DOOR_REL)]
    if scenario is None:
        return [*argv, "--help"]
    if scenario.host:
        argv += ["--host", scenario.host]
    argv += ["--campaign", scenario.campaign, "--model", scenario.model]
    argv += ["--date", scenario.date]
    argv += ["--parallel", str(scenario.parallel)]
    argv += ["--ctx-per-slot", str(scenario.ctx_per_slot)]
    argv += ["--ubatch", str(scenario.ubatch)]
    if scenario.step:
        argv += ["--step", str(_step_path(root, scenario))]
    if scenario.suffix:
        argv += ["--suffix", scenario.suffix]
    if scenario.step_args:
        argv += ["--", *scenario.step_args]
    return argv


def door_env(root: Path) -> dict[str, str]:
    """The environment a door invocation runs under: no ``RUN_*`` or
    ``DOCKER_*`` inherited (the door refuses them by name), no image variable
    from the developer's shell, and the fixture's stubs first on PATH — the
    door puts its own shims ahead of them."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("RUN_", "DOCKER_")) and k not in ("LCP_IMG", "VLLM_IMG")
    }
    parts = [str(stubs_dir(root)), str(Path(sys.executable).parent)]
    parts += (env.get("PATH") or os.defpath).split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts)
    env["STUB_RIG_HOME"] = RIG_HOME
    env["STUB_FREE"] = LIVE["srv1"]["gpu_free_mib"]
    env["STUB_USED"] = LIVE["srv1"]["gpu_used_mib"]
    return env


def door(
    root: Path, scenario: Scenario, *, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """One door invocation from the fixture, to completion."""
    env = door_env(root)
    env.update(env_extra or {})
    return subprocess.run(
        _command(root, scenario),
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def door_process(root: Path, scenario: Scenario) -> subprocess.Popen[str]:
    """The door started in its own session, for a test that signals it."""
    return subprocess.Popen(
        _command(root, scenario),
        cwd=root,
        env=door_env(root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def door_help(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _command(root, None),
        cwd=root,
        env=door_env(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def envelope(root: Path, campaign: str, date: str = RUN_DATE) -> Path:
    return root / "records" / "evidence" / f"{date}-{campaign}"


def written_under_records(root: Path) -> list[str]:
    records = root / "records"
    if not records.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in records.rglob("*") if p.is_file())


#: What the door files in an envelope before the step, whatever the step does.
DOOR_FACTS = frozenset({"scan.json", "geometry.json", "placement.json"})


def is_claim(name: str) -> bool:
    """Whether ``name`` is gate 5's claim on a RUN_ID (``.<RUN_ID>.running``),
    which exists only while a run is in progress and is the door's, not a
    step's."""
    return name.startswith(".") and name.endswith(".running")


def filed_by_steps(root: Path) -> list[str]:
    """Files under ``records/`` that a STEP wrote — the door's own three facts
    (scan, geometry, placement) and its claim on the RUN_ID left out."""
    return [
        p
        for p in written_under_records(root)
        if Path(p).name not in DOOR_FACTS and not is_claim(Path(p).name)
    ]


def claims(root: Path) -> list[str]:
    """Every claim marker under ``records/`` right now. Empty after any run
    the door finished, however it ended."""
    return [p for p in written_under_records(root) if is_claim(Path(p).name)]


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        out[key] = value
    return out


# --------------------------------------------------------------------------
# the drivers and the emitter, run bare
# --------------------------------------------------------------------------


def driver(
    name: str,
    env: dict[str, str],
    *,
    argv: list[str] | None = None,
    door: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``tools/runs/drivers/<name>`` with the interpreter the tests use.

    The file must exist first: ``python missing.py`` exits 2 on its own, which
    would read exactly like the refusal these tests are looking for. ``door``
    is a :func:`fake_door` to run it under; without one the driver's own
    proof refuses it, which is what a test of that refusal wants.
    """
    path = DRIVERS / name
    assert path.is_file(), f"{path.relative_to(REPO)} does not exist"
    command = [sys.executable, str(path)]
    command += argv if argv is not None else DRIVER_ARGV[name]
    if door is not None:
        command = [sys.executable, str(door), *command]
    return subprocess.run(
        command,
        cwd=REPO,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def bare_env(stubs: Path, **extra: str) -> dict[str, str]:
    """An environment for a driver or the emitter run BARE: no ``RUN_*`` from
    the shell, the two stubs first on PATH, ``RUN_HOST`` naming a machine that
    does not exist, plus ``extra``."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("RUN_", "DOCKER_")) and k not in ("LCP_IMG", "VLLM_IMG")
    }
    stubs.mkdir(parents=True, exist_ok=True)
    docker_stub(stubs)
    ssh_stub(stubs)
    env["PATH"] = f"{stubs}{os.pathsep}{env.get('PATH') or os.defpath}"
    env["RUN_HOST"] = BARE_HOST
    env["STUB_RIG_HOME"] = RIG_HOME
    env["STUB_FREE"] = LIVE["srv1"]["gpu_free_mib"]
    env["STUB_USED"] = LIVE["srv1"]["gpu_used_mib"]
    env.update(extra)
    return env


def bash(
    script: str, env: dict[str, str], cwd: Path, *, door: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """``bash -c script``; under ``door`` (a :func:`fake_door`) when given."""
    command = ["bash", "-c", script]
    if door is not None:
        command = [sys.executable, str(door), *command]
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


# --------------------------------------------------------------------------
# the serve run
# --------------------------------------------------------------------------


def serving(
    where: Path,
    names: tuple[str, ...],
    *,
    already_up: bool = False,
    sticks: bool = False,
) -> None:
    """What ``compose up`` will bring up on the stubbed rig — or, with
    ``already_up``, what its daemon lists right now. Once up, the names stay
    until ``compose down`` clears them, or for good when ``sticks`` says a
    down that does not stop them is the case under test."""
    target = "serving-names" if already_up else "serving-pending"
    for stale in ("serving-names", "serving-pending"):
        (where / stale).unlink(missing_ok=True)
    (where / target).write_text(
        "".join(f"{name}\n" for name in names), encoding="utf-8"
    )
    flag = where / "compose-down-sticks"
    if sticks:
        flag.touch()
    else:
        flag.unlink(missing_ok=True)


def serve_door(
    root: Path,
    mode: str,
    compose: Path,
    *,
    host: str = "srv1",
    date: str = RUN_DATE,
    suffix: str = "",
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """One `serve up|down` invocation from the fixture, to completion."""
    argv = [sys.executable, str(root / DOOR_REL), "serve", mode]
    argv += ["--host", host, "--compose", str(compose), "--date", date]
    if suffix:
        argv += ["--suffix", suffix]
    env = door_env(root)
    env.update(env_extra or {})
    return subprocess.run(
        argv,
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
