"""The seam the one-door tests drive ``python -m mcgyvr.serving.run`` through.

``src/mcgyvr/serving/run.py`` is the one access point to the rigs. A test may
not touch a rig, and the door has no variable that names a substitute for a
reading — the archived door's three seam variables left with it, because a variable
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

* a copy of ``src/mcgyvr/serving/`` (the door, its gates and its shims) and
  nothing else of a checkout: it is no lab checkout, so the door runs in
  user mode. The rigs are described by user rig files under
  ``$MCGYVR_RIGS/<rig>.json``, written for this tree from the same
  ``RIG``/``LIVE`` readings the stubs answer, and a run is filed under
  ``--out-root out`` (a folder the fixture makes);
* ``stubs/``, first on the PATH :func:`door_env` builds: the ``ssh`` reads the
  shipped reader off its command line and answers from ``rigscan.json`` and
  ``snapshot.txt`` (or ``snapshot-moved.txt`` once a flag file the test names
  exists — the reading box1 gave after a hard lock wiped its BIOS profile), the
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

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests._paths import REPO as REPO

#: The door and everything it spawns. Copied whole into a fixture.
SERVING_SRC = REPO / "src" / "mcgyvr" / "serving"
#: The door's shim directory — what it exports as ``RUN_BIN``, and where a
#: step run bare under a fake door is told to find the shims.
BIN = SERVING_SRC / "gate-scripts" / "bin"
DOOR_REL = Path("src") / "mcgyvr" / "serving" / "run.py"
MODEL = "/models/moe/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf"
#: Where a step run files its envelope, relative to the throw-away fixture.
OUT_ROOT = "out"

RUN_DATE = "2026-09-05"
#: Digests the docker stub knows. ``vllm/vllm-openai:v0.26.0`` has a registry
#: digest; ``llamacpp:b10644-L3`` is a local build and has only an image id.
REPO_DIGEST_HEX = "9d2b5e1c7a4f3b8e6c0d1a2f5b7c9e3d4a6b8c0e2f4a6c8e0b2d4f6a8c0e2b4d"
IMAGE_ID_HEX = "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b"
LOCAL_ID_HEX = "c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00"
VLLM_TAG = "vllm/vllm-openai:v0.26.0"
VLLM_DIGEST = f"vllm/vllm-openai@sha256:{REPO_DIGEST_HEX}"
LOCAL_TAG = "llamacpp:b10644-L3"
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

#: The rig's facts the fixture's snapshot and its rig file carry. Strings,
#: because that is what a ``k=v`` line carries.
RIG: dict[str, dict[str, str]] = {
    "box1": {
        "cpu_max_mhz": "4600",
        "cpu_model": "Intel(R)_Core(TM)_i5-9600K_CPU_@_3.70GHz",
        "ram_mt_s": "3600",
        "pl1_uw": "95000000",
        "pl2_uw": "120000000",
        "gpu_name": "NVIDIA_GeForce_RTX_3060",
        "gpu_vram_mib": "12288",
        "gpu_cc": "8.6",
        "gpu_slot": "00000000:01:00.0",
        "driver": "580.178.04",
        "gpu_reserve_mib": "381",
        "docker": "29.7.2",
    },
    "box2": {
        "cpu_max_mhz": "5200",
        "cpu_model": "Intel(R)_Core(TM)_i9-10900F_CPU_@_2.80GHz",
        "ram_mt_s": "3200",
        "pl1_uw": "4095000000",
        "pl2_uw": "4095000000",
        "gpu_name": "NVIDIA_GeForce_GTX_1660_SUPER",
        "gpu_vram_mib": "6144",
        "gpu_cc": "7.5",
        "gpu_slot": "00000000:02:00.0",
        "driver": "580.178.04",
        "gpu_reserve_mib": "399",
        "docker": "29.7.2",
    },
}
RIG_KEYS = frozenset(RIG["box1"])
RIG_READ_ON = "2026-09-26"
#: What the snapshot holds beyond the declared keys: the two VRAM
#: figures a placement spends, the host memory, the thread count, the name
#: the daemon must answer to (gate 3), and the two idle readings gate 2 holds
#: to ``none``. box1's are a recorded scan. The kernel, MemTotal, swap and
#: swappiness values here are placeholders: the rig file declares none of them,
#: so the door does not compare them.
LIVE: dict[str, dict[str, str]] = {
    "box1": {
        "gpu_used_mib": "17",
        "gpu_free_mib": "5727",
        "mem_available_kib": "14835712",
        "mem_total_kib": "15700000",
        "kernel": "6.8.0-139-generic",
        "swap_total_kib": "8388604",
        "swappiness": "60",
        "nproc": "6",
        "hostname": "box1",
        "gpu_procs": "none",
        "containers": "none",
    },
    "box2": {
        "gpu_used_mib": "0",
        "gpu_free_mib": "11911",
        "mem_available_kib": "26214400",
        "mem_total_kib": "33554432",
        "kernel": "6.8.0-139-generic",
        "swap_total_kib": "8388608",
        "swappiness": "60",
        "nproc": "20",
        "hostname": "box2",
        "gpu_procs": "none",
        "containers": "none",
    },
}


def snapshot_lines(host: str, **override: str) -> str:
    """One snapshot of ``host`` as ``key=value`` lines: the one reader's
    snapshot, and the two idle readings the runtime reader gives."""
    values = {"uptime_since": UPTIME, **RIG[host], **LIVE[host], **override}
    return "".join(f"{k}={v}\n" for k, v in values.items())


#: The rows the runtime reader (``rig-units.sh``) prints; every other line of a
#: test's reading text is the one reader's snapshot.
RUNTIME_ROWS = ("container", "gpu_app", "sleeping", "status", "backend", "backend_line")


def machine_reading(snapshot: dict[str, str]) -> dict[str, object]:
    """The one reader's document of a rig whose snapshot is ``snapshot``.

    Its machine id is the snapshot's ``os_machine_id`` (else one derived from
    the host name, as the reader derives it), and its one card is the
    snapshot's first card, so :func:`mcgyvr.fleet.ids.rig_id` names it as the
    reader's own document would.
    """
    import hashlib

    host = snapshot.get("hostname", "box")
    machine_id = (
        snapshot.get("os_machine_id")
        or hashlib.sha256(f"host:{host}".encode()).hexdigest()[:16]
    )
    cards = []
    if snapshot.get("gpu_name") and str(snapshot.get("gpu_vram_mib", "")).isdigit():
        total = int(snapshot["gpu_vram_mib"])
        used = int(snapshot.get("gpu_used_mib", "0") or 0)
        cards.append(
            {
                "vendor": "nvidia",
                "index": 0,
                "name": snapshot["gpu_name"].replace("_", " "),
                "total_mib": total,
                "used_mib": used,
                "free_mib": max(total - used, 0),
            }
        )
    return {
        "machine": {"id": machine_id, "id_from": "/etc/machine-id", "host": host},
        "cards": cards,
        "card_sources": ["nvidia-smi"] if cards else [],
        "unsized": [],
        "unread": [],
        "snapshot": dict(snapshot),
    }


def split_reading(text: str) -> tuple[dict[str, object], str]:
    """A test's one reading text as the door takes it: the one reader's
    document (its snapshot lines) and the runtime reader's rows."""
    snapshot: dict[str, str] = {}
    rows: list[str] = []
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        if key in RUNTIME_ROWS:
            rows.append(line)
        elif key not in ("containers", "gpu_procs"):
            snapshot[key] = value
    return machine_reading(snapshot), "".join(f"{row}\n" for row in rows)


def rig_id_of_text(text: str) -> str:
    """The rig id a reading text names, as the door's read names it."""
    from mcgyvr.fleet.ids import rig_id

    return rig_id(split_reading(text)[0])


def executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


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
  # The runtime reader (rig-units.sh) on stdin: what holds the rig, from the
  # same snapshot file the shipped reader answers from.
  "bash -s")
    cat >/dev/null
    python3 "$STUBS/rig-answer.py" units "$STUBS" ;;
  # The lock's own harness, shipped to the rig by a `read --probe`: the test
  # writes what it measured at 127.0.0.1 into harness.json.
  *"mcgyvr-harness"*) cat >/dev/null; cat "$STUBS/harness.json" ;;
  # The link timer, shipped by a `link` run: the stub keeps the command and
  # the source it was handed, and answers with what linktime.json says.
  *"mcgyvr-linktime"*)
    printf '%s\\n' "$cmd" > "$STUBS/linktime-cmd.txt"
    cat > "$STUBS/linktime-source.txt"
    cat "$STUBS/linktime.json" ;;
  # The one reader, shipped whole (`mcgyvr scan --rig`, gate 2, gate 7, a
  # `read`): rigscan.json with the snapshot of snapshot.txt folded in.
  *"| base64 -d | python3 -I -B -") python3 "$STUBS/rig-answer.py" whole "$STUBS" ;;
  # Its short reading (`--cards`), which a serve step files of the card.
  *"| base64 -d | python3 -I -B - --cards")
    python3 "$STUBS/rig-answer.py" cards "$STUBS" ;;
  # The weights fetcher a `serve fetch` ships, with its job, on stdin: run
  # as written, by this machine's python3, under a HOME of the stub's own,
  # so its weights folder is `rig-home/.cache/mcgyvr/weights`.
  *"mcgyvr-fetch"*)
    mkdir -p "$STUBS/rig-home"
    HOME=$STUBS/rig-home MCGYVR_WEIGHTS= python3 - ;;
  *"python3 -"*) cat "$STUBS/geometry.json" ;;
  # The rig's lease (`~/.mcgyvr/lease` ON the rig): the remote command is
  # run as written, by a real bash, under a HOME of the stub's own — so
  # `set -C` and `>` mean what they mean on the rig, and a test reads or
  # plants the file at `rig-home/.mcgyvr/lease`.
  *".mcgyvr/lease"*)
    mkdir -p "$STUBS/rig-home"
    HOME=$STUBS/rig-home bash -c "$cmd" ;;
  "bash -s -- lease")
    mkdir -p "$STUBS/rig-home"
    HOME=$STUBS/rig-home bash -s ;;
  *'echo $HOME'*) echo "$STUB_RIG_HOME" ;;
  *"cat >>"*) cat >/dev/null ;;
  *mkdir*) : ;;
  *"memory.used,memory.free"*) echo "$STUB_USED, $STUB_FREE" ;;
  *memory.free*) echo "$STUB_FREE" ;;
  *memory.used*) echo "$STUB_USED" ;;
  *constraint_0_power_limit_uw*) echo 95000000 ;;
  *constraint_1_power_limit_uw*) echo 120000000 ;;
  *query-compute-apps*) : ;;
  # vLLM's sleep routes, present only once `sleep-route` exists (a unit run
  # with sleep mode and the dev routes); `asleep-<port>` is each unit's state.
  *"/sleep?level="*)
    [ -e "$STUBS/sleep-route" ] || exit 22
    port=$(printf '%s' "$cmd" | sed -n 's/.*localhost:\\([0-9]*\\).*/\\1/p')
    touch "$STUBS/asleep-$port" ;;
  *"/wake_up?tags=kv_cache"*)
    [ -e "$STUBS/sleep-route" ] || exit 22
    port=$(printf '%s' "$cmd" | sed -n 's/.*localhost:\\([0-9]*\\).*/\\1/p')
    rm -f "$STUBS/asleep-$port" ;;
  *"/wake_up"*|*"/collective_rpc"*)
    [ -e "$STUBS/sleep-route" ] || exit 22 ;;
  # No sleep route, as a unit without one answers (owner ruling, FLT-02): 404.
  *"is_sleeping"*)
    port=$(printf '%s' "$cmd" | sed -n 's/.*localhost:\\([0-9]*\\).*/\\1/p')
    if [ ! -e "$STUBS/sleep-route" ]; then
      printf '{"error":"Not Found"}\n404'
    elif [ -e "$STUBS/asleep-$port" ]; then
      printf '{"is_sleeping": true}\n200'
    else
      printf '{"is_sleeping": false}\n200'
    fi ;;
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
    if [ -s "$STUBS/serving-names" ]; then
      n=10
      while read -r name; do
        [ -n "$name" ] || continue
        n=$((n + 1))
        row "c0ffee0000$n" "$name"
      done < "$STUBS/serving-names"
    fi
    exit 0 ;;
  rm)
    # `docker rm -f NAME...` takes a unit off the daemon's list, so what
    # `ps` and the rig's snapshot say next is what a removed container is.
    shift
    for name in "$@"; do
      case $name in -*) continue ;; esac
      if [ -f "$STUBS/serving-names" ]; then
        grep -vx -- "$name" "$STUBS/serving-names" > "$STUBS/serving-names.new" || true
        mv "$STUBS/serving-names.new" "$STUBS/serving-names"
      fi
    done
    exit 0 ;;
  compose)
    # `compose ... up -d` brings up what a test queued (serving-pending
    # becomes serving-names, which `ps` and the rig's snapshot then list);
    # `down` removes what Docker's does: the containers the file names, and
    # with --remove-orphans every other container of the project too (here,
    # every `mcgyvr-` name) — unless a test pinned the names in place
    # (compose-down-sticks). `up` and `rm` that name services act on those
    # services' containers alone: `up` moves the queued ones to the list,
    # `rm` takes them off it.
    file= ; prev= ; services= ; seen=
    for arg in "$@"; do
      [ "$prev" = -f ] && file=$arg
      case $arg in
        up | rm) seen=1 ;;
        -*) ;;
        *) [ -n "$seen" ] && services="$services $arg" ;;
      esac
      prev=$arg
    done
    named=
    if [ -n "$services" ]; then
      named=$(python3 -c 'import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
for s in sys.argv[2:]: print(doc["services"][s]["container_name"])' "$file" $services)
    fi
    case " $* " in
      *" up "*)
        if [ -z "$named" ]; then
          [ -f "$STUBS/serving-pending" ] &&
            mv "$STUBS/serving-pending" "$STUBS/serving-names"
        else
          for name in $named; do
            if [ -f "$STUBS/serving-pending" ] &&
               grep -qx -- "$name" "$STUBS/serving-pending"; then
              printf '%s\\n' "$name" >> "$STUBS/serving-names"
              grep -vx -- "$name" "$STUBS/serving-pending" > "$STUBS/pending.new" ||
                true
              mv "$STUBS/pending.new" "$STUBS/serving-pending"
            fi
          done
        fi ;;
      *" rm "*)
        [ -e "$STUBS/compose-down-sticks" ] && exit 0
        [ -f "$STUBS/serving-names" ] || exit 0
        for name in $named; do
          grep -vx -- "$name" "$STUBS/serving-names" > "$STUBS/names.new" ||
            true
          mv "$STUBS/names.new" "$STUBS/serving-names"
        done ;;
      *" down "*)
        [ -e "$STUBS/compose-down-sticks" ] && exit 0
        [ -f "$STUBS/serving-names" ] || exit 0
        : > "$STUBS/serving-names.new"
        while read -r name; do
          [ -n "$name" ] || continue
          case " $* " in
            *" --remove-orphans "*) case $name in mcgyvr-*) continue ;; esac ;;
          esac
          if [ -n "$file" ] && grep -q "container_name: $name\\$" "$file"; then
            continue
          fi
          printf '%s\\n' "$name" >> "$STUBS/serving-names.new"
        done < "$STUBS/serving-names"
        mv "$STUBS/serving-names.new" "$STUBS/serving-names" ;;
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


#: How the ssh stub answers the two readers the door ships, from the files a
#: test writes: ``snapshot.txt`` (or ``snapshot-moved.txt`` once the moved flag
#: exists) and ``rigscan.json``. ``whole`` is the one reader's document, its
#: snapshot read off the snapshot file; ``cards`` its short reading, the first
#: card's used and free MiB from ``STUB_USED`` and ``STUB_FREE``; ``units`` is
#: the runtime reader: a container row per id the snapshot file's
#: ``containers=`` names and per serving unit, and a card holder per process
#: its ``gpu_procs=`` names (or the one a serving rig has). The snapshot file's
#: own runtime rows (``container=``, ``gpu_app=``, ``sleeping=``, ...) pass
#: through as they are.
RIG_ANSWER = """\
import hashlib, json, os, re, sys

how, stubs = sys.argv[1], sys.argv[2]
flag = os.path.join(stubs, "moved-flag")
name = "snapshot.txt"
if os.path.isfile(flag) and os.path.exists(open(flag).read().strip()):
    name = "snapshot-moved.txt"
lines = []
if os.path.isfile(os.path.join(stubs, name)):
    lines = open(os.path.join(stubs, name)).read().splitlines()
pairs = [line.split("=", 1) for line in lines if "=" in line]
runtime = ("container", "gpu_app", "sleeping", "status", "backend", "backend_line")
snapshot = {k: v for k, v in pairs if k not in runtime + ("containers", "gpu_procs")}
serving = []
names = os.path.join(stubs, "serving-names")
if os.path.isfile(names):
    serving = [n.strip() for n in open(names) if n.strip()]
if how == "units":
    said = dict(p for p in pairs if p[0] in ("containers", "gpu_procs"))
    for number, ident in enumerate(
        i for i in said.get("containers", "none").split(";") if i and i != "none"
    ):
        print(f"container=stranger-{number},{ident},-,0")
    for number, unit in enumerate(serving, start=11):
        print(f"container={unit},c0ffee0000{number},mcgyvr,0")
    procs = [p for p in said.get("gpu_procs", "none").split(";") if p and p != "none"]
    if serving:
        procs = ["4242,llama-server,5584MiB"]
    for proc in procs:
        pid, process, mib = proc.split(",")
        print(f"gpu_app={pid},{mib.removesuffix('MiB')},none,{process}")
    for key, value in pairs:
        if key in runtime:
            print(f"{key}={value}")
    raise SystemExit(0)
document = json.load(open(os.path.join(stubs, "rigscan.json")))
if how == "cards":
    used, free = os.environ.get("STUB_USED", ""), os.environ.get("STUB_FREE", "")
    document["cards"] = [
        {
            "vendor": "nvidia",
            "index": 0,
            "name": snapshot.get("gpu_name", "Example Card"),
            "total_mib": int(snapshot.get("gpu_vram_mib", "0") or 0),
            "used_mib": int(used) if used.isdigit() else None,
            "free_mib": int(free) if free.isdigit() else None,
        }
    ]
    document["unread"] = [] if used.isdigit() and free.isdigit() else [
        {"field": "card.nvidia.0.used", "why": "the stub card answered nothing"}
    ]
else:
    # A snapshot file that names no card reads the card off the scan, as the
    # reader's own snapshot is read off the same card call.
    first = (document.get("gpus") or [None])[0]
    if first is not None and "gpu_name" not in snapshot:
        vram = first["vram"]
        snapshot = {
            "gpu_name": "_".join(first["name"].split()),
            "gpu_vram_mib": str(vram["total_mib"]),
            "gpu_cc": "8.6",
            "gpu_slot": "00000000:01:00.0",
            "driver": "580.178.04",
            "gpu_reserve_mib": str(vram.get("reserved_mib", 0)),
            "gpu_used_mib": str(vram["used_mib"]),
            "gpu_free_mib": str(vram["free_mib"]),
            **snapshot,
        }
    document["snapshot"] = {"gpu_others": "", **snapshot}
    document.setdefault("unread", [])
    # The machine and its card as the reader names them, so the rig id this
    # reading names is the one tests.onedoor.machine_reading names.
    machine = dict(document.get("machine") or {})
    if snapshot.get("os_machine_id"):
        machine["id"] = snapshot["os_machine_id"]
    elif not re.fullmatch("[0-9a-f]{16}", str(machine.get("id", ""))):
        host = snapshot.get("hostname", machine.get("host", "box"))
        machine["id"] = hashlib.sha256(f"host:{host}".encode()).hexdigest()[:16]
    document["machine"] = machine
    if "cards" not in document and snapshot.get("gpu_vram_mib", "").isdigit():
        document["cards"] = [
            {
                "vendor": "nvidia",
                "index": 0,
                "name": snapshot.get("gpu_name", "").replace("_", " "),
                "total_mib": int(snapshot["gpu_vram_mib"]),
                "used_mib": 0,
                "free_mib": int(snapshot["gpu_vram_mib"]),
            }
        ]
print(json.dumps(document))
"""


def ssh_stub(where: Path) -> Path:
    """The ``ssh`` that stands behind the shim in ``where``. Reaches nothing."""
    (where / "rig-answer.py").write_text(RIG_ANSWER, encoding="utf-8")
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
    applied. Once ``moved_flag`` exists it reads PL1 at 4095 W instead: a rig
    whose power limit moved away from what it declares."""
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


def rig_lease(root: Path) -> Path:
    """Where the stub rig keeps ``~/.mcgyvr/lease``: the file a door takes
    at gate 2 and releases when it is done, as the ssh stub answers it."""
    return stubs_dir(root) / "rig-home" / ".mcgyvr" / "lease"


def plant_lease(root: Path, line: str) -> Path:
    """A lease already on the rig before the door opens, as another run
    (or a dead one) would have left it."""
    path = rig_lease(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(line.rstrip("\n") + "\n", encoding="utf-8")
    return path


def read_lease(root: Path) -> str | None:
    """The lease on the stub rig now, or ``None`` when it is released."""
    path = rig_lease(root)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def containers_up(root: Path, *names: str) -> None:
    """Make the stub daemon list ``names`` as up (and the rig read busy)."""
    (stubs_dir(root) / "serving-names").write_text(
        "".join(f"{n}\n" for n in names), encoding="utf-8"
    )


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


def scan_payload(host: str) -> dict[str, object]:
    """What the shipped rig scanner answers for ``host``, matching its rig file."""
    rig = RIG[host]
    total = int(rig["gpu_vram_mib"])
    reserve = int(rig["gpu_reserve_mib"])
    used = int(LIVE[host]["gpu_used_mib"])
    return {
        "machine": {
            "id": f"machine-{host}",
            "host": host,
            "kernel": "6.8.0-invented",
        },
        "gpus": [
            {
                "index": 0,
                "name": rig["gpu_name"],
                "vram": {
                    "total_mib": total,
                    "used_mib": used,
                    "free_mib": total - reserve - used,
                    "reserved_mib": reserve,
                },
            }
        ],
        "memory": {"total_gb": 15.7, "available_gb": 14.2},
        "cpu": {"cores": 6, "threads": 6},
        "disk": {"path": "/home/user/.cache/mcgyvr/weights", "free_gb": 400.0},
        "docker": rig["docker"],
        "notes": [],
        "facts": [],
    }


def rig_file(host: str) -> dict[str, object]:
    """The user's rig file for ``host``, as ``mcgyvr scan --rig`` writes it."""
    rig = RIG[host]
    return {
        "rig": host,
        "read_at": "2026-09-26T00:00:00Z",
        "hostname": host,
        "machine_id": f"machine-{host}",
        "cards": [
            {
                "index": 0,
                "name": rig["gpu_name"],
                "total_mib": int(rig["gpu_vram_mib"]),
            }
        ],
        "ram_total_gb": 15.7,
        "disk": {"path": "/home/user/.cache/mcgyvr/weights", "free_gb": 400.0},
        "docker": rig["docker"],
        "private_ipv4": None,
        "private_ipv4_how": "the scan read no network (an invented rig)",
        "notes": [],
    }


def rigs_home(root: Path) -> Path:
    """The folder that holds the fixture's rig files, named by ``MCGYVR_RIGS``."""
    return root / "mcgyvr-home"


def fixture_repo(tmp_path: Path, *, host: str = "box1") -> Path:
    """A throw-away checkout the door can be run from and write into.

    The machine behind the stubs reads as ``host``'s declaration (box1 unless
    said otherwise); :func:`rig_stub` changes that. The checkout is no lab
    checkout, so the door runs in user mode against the rig files under
    :func:`rigs_home`.
    """
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy(REPO / name, root / name)
    os.symlink(REPO / ".venv", root / ".venv")
    for name in ("__init__.py",):
        shutil.copy(REPO / "tests" / name, root / "tests" / name)
    shutil.copytree(
        SERVING_SRC,
        root / "src" / "mcgyvr" / "serving",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # A step run files under --out-root; the folder must exist, as the door
    # never makes it.
    (root / OUT_ROOT).mkdir(parents=True, exist_ok=True)
    for name in ("box1", "box2"):
        folder = rigs_home(root) / "rigs"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.json").write_text(
            json.dumps(rig_file(name)) + "\n", encoding="utf-8"
        )
    stubs = stubs_dir(root)
    stubs.mkdir()
    ssh_stub(stubs)
    docker_stub(stubs)
    rig_stub(stubs, host)
    (stubs / "rigscan.json").write_text(
        json.dumps(scan_payload(host)), encoding="utf-8"
    )
    return root


def add_step(root: Path, campaign: str, filename: str, body: str) -> Path:
    path = root / "steps" / campaign / filename
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
    rig = " ".join(f"{k}={v}" for k, v in RIG["box1"].items())
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
    ``steps/<campaign>/``, a path relative to the fixture root (or absolute),
    or ``""`` for the shipped default step. An empty ``host`` leaves
    ``--host`` out, for the test that asks what the door does then."""

    campaign: str
    step: str
    host: str = "box1"
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
        return root / "steps" / scenario.campaign / step
    return root / step


def _command(root: Path, scenario: Scenario | None) -> list[str]:
    """The ONLY place the door's path and argv shape are known."""
    argv = [sys.executable, str(root / DOOR_REL)]
    if scenario is None:
        return [*argv, "--help"]
    argv += ["step"]
    if scenario.host:
        argv += ["--host", scenario.host]
    # The fixture is no lab checkout, so the door runs in user mode.
    argv += ["--campaign", scenario.campaign]
    if scenario.step:
        argv += ["--step", str(_step_path(root, scenario))]
    argv += ["--out-root", OUT_ROOT]
    argv += ["--model", scenario.model]
    argv += ["--date", scenario.date]
    argv += ["--parallel", str(scenario.parallel)]
    argv += ["--ctx-per-slot", str(scenario.ctx_per_slot)]
    argv += ["--ubatch", str(scenario.ubatch)]
    if scenario.suffix:
        argv += ["--suffix", scenario.suffix]
    if scenario.step_args:
        argv += ["--", *scenario.step_args]
    return argv


def door_env(root: Path) -> dict[str, str]:
    """The environment a door invocation runs under: no ``RUN_*`` or
    ``DOCKER_*`` inherited (the door refuses them by name), no image variable
    from the developer's shell, and the fixture's stubs first on PATH — the
    door puts its own shims ahead of them. ``MCGYVR_RIGS`` names the fixture's
    rig files, and ``MCGYVR_DATA`` keeps the user-mode door log in the tree."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("RUN_", "DOCKER_")) and k not in ("LCP_IMG", "VLLM_IMG")
    }
    parts = [str(stubs_dir(root)), str(Path(sys.executable).parent)]
    parts += (env.get("PATH") or os.defpath).split(os.pathsep)
    env["PATH"] = os.pathsep.join(parts)
    env["STUB_RIG_HOME"] = RIG_HOME
    env["STUB_FREE"] = LIVE["box1"]["gpu_free_mib"]
    env["STUB_USED"] = LIVE["box1"]["gpu_used_mib"]
    env["MCGYVR_RIGS"] = str(rigs_home(root) / "rigs")
    env["MCGYVR_DATA"] = str(root / "data")
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
    """The envelope a step run's ``--out-root`` names in the fixture."""
    return root / OUT_ROOT / f"{date}-{campaign}"


def serve_envelope(
    root: Path,
    step: str,
    campaign: str,
    date: str = RUN_DATE,
    suffix: str = "",
) -> Path:
    """The door-log envelope a user-mode serve run files ``step`` under."""
    run_id = f"{date}-{campaign}-{step}" + (f"-{suffix}" if suffix else "")
    return root / "data" / "door" / date / run_id


def written_under_records(root: Path) -> list[str]:
    out = root / OUT_ROOT
    if not out.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in out.rglob("*") if p.is_file())


def is_claim(name: str) -> bool:
    """Whether ``name`` is gate 5's claim on a RUN_ID (``.<RUN_ID>.running``),
    which exists only while a run is in progress and is the door's, not a
    step's."""
    return name.startswith(".") and name.endswith(".running")


def claims(root: Path) -> list[str]:
    """Every claim marker under the out root right now. Empty after any run
    the door finished, however it ended."""
    return [p for p in written_under_records(root) if is_claim(Path(p).name)]


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        out[key] = value
    return out


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


def sleep_route(where: Path, *, asleep: tuple[int, ...] = ()) -> None:
    """Give the stubbed units vLLM's sleep routes; those on ``asleep`` ports sleep."""
    (where / "sleep-route").touch()
    for flag in where.glob("asleep-*"):
        flag.unlink()
    for port in asleep:
        (where / f"asleep-{port}").touch()


def asleep_ports(where: Path) -> list[int]:
    """The ports of the stubbed units that say they are asleep, sorted."""
    return sorted(int(flag.name.split("-", 1)[1]) for flag in where.glob("asleep-*"))


def serve_door(
    root: Path,
    mode: str,
    compose: Path,
    *,
    host: str = "box1",
    date: str = RUN_DATE,
    suffix: str = "",
    env_extra: dict[str, str] | None = None,
    extra: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """One `serve up|down|sleep|wake` invocation from the fixture, to completion."""
    argv = [sys.executable, str(root / DOOR_REL), "serve", mode]
    argv += ["--host", host, "--compose", str(compose), "--date", date]
    if suffix:
        argv += ["--suffix", suffix]
    argv += extra or []
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
