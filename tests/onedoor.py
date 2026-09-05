"""The seams the one-door tests drive ``tools/runs/run.sh`` through.

``run.sh`` is the one executable allowed to start a container or open an ssh
pipe to a rig (BRIEF "Target design"). A test may not touch a rig, so every
place the door would read the machine or the daemon is a named seam the brief
lists — ``RUN_RIG_SNAPSHOT_CMD``, ``RUN_DOCKER``, ``RUN_SSH``, ``RUN_DATE``,
``RUN_REPO``, ``RUN_PRODUCT_CHECK`` — and this module builds the stubs that
stand behind them, plus a throw-away copy of the repository for the door to
work in, so an assertion like "exit 2 having written nothing" is a statement
about a filesystem nobody else is writing to.

``tools/runs/rows.py`` is imported as ``tools.runs.rows`` (``rows_module``):
``tools/`` is a namespace package from the repo root, which is how the shim
``tests/sweeprows.py`` re-exports it and how ``tests/test_one_door.py`` reads
it, so every test in one process holds the one module object rather than a
by-path second copy.

The contract these helpers assume — every name below is one the implementer
must honour, and the test that pins it says so in its docstring:

* ``tools/runs/run.sh <campaign> <step> --host srv1|srv2 [-- STEP ARGS...]``;
  no arguments or ``--help`` exit 2 and list the campaigns found under
  ``$RUN_REPO/tools/runs/campaigns/``.
* a campaign is a directory ``tools/runs/campaigns/<campaign>/``; a step is a
  file ``<n>-<name>.sh`` in it, addressed by ``<n>`` or by ``<name>``.
* a step declares what it writes on one comment line, ``# RUN_ARTIFACTS: a.tsv
  [b.tsv ...]``, relative to the envelope; the door refuses to start a step
  whose declared artifact already exists. A step that runs twice over one file
  declares it under ``# RUN_REWRITES:`` instead: the door admits an existing
  file only if its ``### START run_id=`` names this same step, and moves it to
  ``<name>.superseded-<run_id>.<ext>`` before the step starts.
* the door exports ``RUN_ID``, ``RUN_OUT_DIR`` (the envelope
  ``records/evidence/<RUN_DATE>-<campaign>``), ``RUN_HOST``, ``RUN_ROUND`` and
  ``RUN_PRODUCT_SHA256`` (the two words ``RUN_PRODUCT_CHECK`` printed) to the
  step. ``RUN_ID`` is ``<RUN_DATE>-<campaign>-<step name>`` with an optional
  ``-<suffix>``, whitespace-free and legal as a docker container-name prefix.
* ``RUN_PRODUCT_CHECK`` prints ``round=<id> product_sha256=<hex>`` on success
  and exits non-zero with its reason on stderr otherwise.
* ``RUN_RIG_SNAPSHOT_CMD`` prints ``k=v`` lines in ``rig_snapshot``'s shape.
* ``RUN_DOCKER`` is invoked in place of ``docker`` by ``_common.sh``, ``run.sh``
  and the three drivers, with docker's own argv.
"""

from __future__ import annotations

import importlib
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "tools" / "runs"

#: ARCHIVED 2026-09-05, round r3. `run.sh` and `_common.sh` moved to
#: `archive/runs/` when `src/mcgyvr/serving/run.py` became the one access point.
#:
#: The tests that drive them are kept, pointed here, and are no longer a
#: statement about what runs — they are the SPEC the Python door has to meet.
#: Each one is a rule that cost rig time to learn (an artifact overwritten, a
#: rig that moved mid-run, a parser that only ran in CI), and deleting them
#: with the file would throw away the reasons along with the implementation.
#:
#: What run.py already reproduces, verified 2026-09-05 by mutation: gate 5
#: write-once, gate 5's refusal of a step that declares nothing, gate 8's
#: parse-and-prefix read-back, gate 7's teardown, and a refusal when a gate
#: script is missing. What is NOT yet ported: the interrupt path's stamping,
#: the RUN_REWRITES supersede-move, and the driver seams below.
ARCHIVED_RUNS = REPO / "archive" / "runs"
RUN_SH = ARCHIVED_RUNS / "run.sh"
#: NOT archived with it. `_common.sh` is the emitter LIBRARY the campaign steps
#: source (stamps, rig readings, image digests) — the steps are callers and go
#: on working; only the door itself moved.
COMMON_SH = RUNS / "_common.sh"
ROWS_PY = RUNS / "rows.py"
WORKLOAD_PY = RUNS / "workload.py"
HOSTS_JSON = RUNS / "hosts.json"
DRIVERS = RUNS / "drivers"
CAMPAIGNS = RUNS / "campaigns"
KERNEL_ARMS = CAMPAIGNS / "srv1-kernel-arms"

DRIVER_NAMES = ("lcp_sweep.py", "vllm_sweep.py", "vllm_cores.py")
#: The image variable each driver reads (``tools/runs/drivers/lcp_sweep.py:51``,
#: ``tools/runs/drivers/vllm_sweep.py:58``, ``tools/runs/drivers/vllm_cores.py:90``).
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
#: The eight ``srv1-*.sh`` steps, by the name that follows ``<n>-`` after the
#: move (BRIEF layout: ``tools/runs/campaigns/srv1-kernel-arms/<n>-<name>.sh``).
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

RUN_DATE = "2026-09-02"
ROUND_ID = "r9-onedoor"
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

#: BRIEF "Rig values read live on 2026-09-02". Strings, because that is what a
#: ``k=v`` line carries and what ``hosts.json`` is compared against.
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


def rows_module() -> ModuleType:
    """``tools.runs.rows`` — the parser at its new home. Raises if it is not there.

    The existence check comes first so the RED failure names the move rather
    than reading as a broken import.
    """
    if not ROWS_PY.is_file():
        raise FileNotFoundError(
            f"{ROWS_PY.relative_to(REPO)} does not exist; tests/sweeprows.py "
            "has not moved to tools/runs/rows.py (BRIEF layout)"
        )
    return importlib.import_module("tools.runs.rows")


def snapshot_lines(host: str, **override: str) -> str:
    """One ``rig_snapshot`` reading for ``host``, as the seam prints it."""
    values = {"uptime_since": UPTIME, **RIG[host], **override}
    return "".join(f"{k}={v}\n" for k, v in values.items())


def executable(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def rig_stub(where: Path, host: str, *, moved_flag: Path | None = None) -> Path:
    """A ``RUN_RIG_SNAPSHOT_CMD`` that reads ``host``'s declared values.

    Once ``moved_flag`` exists it reads PL1 at 4095 W instead — the reading
    srv1 gave at 05:57 after a hard lock wiped its BIOS profile.
    """
    normal = snapshot_lines(host)
    moved = snapshot_lines(host, pl1_uw="4095000000")
    flag = str(moved_flag) if moved_flag else "/nonexistent/never"
    return executable(
        where / "rig-snapshot",
        "#!/usr/bin/env bash\n"
        f"if [ -e '{flag}' ]; then\n"
        f"printf '%s' '{moved}'\n"
        "else\n"
        f"printf '%s' '{normal}'\n"
        "fi\n",
    )


def docker_stub(
    where: Path, *, leftover_flag: Path | None = None, daemon_down: bool = False
) -> Path:
    """A ``RUN_DOCKER`` that logs every argv line to ``docker.log`` beside it.

    ``ps`` prints nothing until ``leftover_flag`` exists, then names a container
    that carries this run's ``RUN_ID`` prefix. ``image inspect`` answers for
    the two tags the tests use and refuses any other, honouring ``--format``
    for the two fields the brief names (``RepoDigests``, ``Id``); the plain
    JSON it prints has the real document's shape — ``RepoDigests`` first, then
    a ``Config.Labels`` block whose toolkit label carries ``TOOLKIT_DIGEST``.
    ``daemon_down`` makes ``info`` fail the way a CLI with no daemon does.
    """
    flag = str(leftover_flag) if leftover_flag else "/nonexistent/never"
    log = where / "docker.log"
    info = (
        "    echo 'Cannot connect to the Docker daemon at "
        "unix:///var/run/docker.sock' >&2\n"
        "    exit 1 ;;\n"
        if daemon_down
        else "    exit 0 ;;\n"
    )
    return executable(
        where / "docker",
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{log}'\n"
        'case "${1:-}" in\n'
        "  info)\n" + info + "  ps)\n"
        f"    [ -e '{flag}' ] && printf '%s-lcps\\n' \"${{RUN_ID:-norunid}}\"\n"
        "    exit 0 ;;\n"
        "  image | inspect) ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
        "tag= ; fmt=\n"
        'while [ "$#" -gt 0 ]; do\n'
        "  case $1 in\n"
        "    --format | -f) fmt=$2; shift ;;\n"
        "    --format=*) fmt=${1#--format=} ;;\n"
        "    image | inspect) ;;\n"
        "    -*) ;;\n"
        "    *) tag=$1 ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        'case "$tag" in\n'
        f"  {VLLM_TAG}) id={IMAGE_ID_HEX}; rd='{VLLM_DIGEST}' ;;\n"
        f"  {LOCAL_TAG}) id={LOCAL_ID_HEX}; rd= ;;\n"
        '  *) printf "Error response from daemon: No such image: %s\\n" '
        '"$tag" >&2; exit 1 ;;\n'
        "esac\n"
        'if [ -n "$fmt" ]; then\n'
        '  case "$fmt" in\n'
        '    *RepoDigests*) [ -n "$rd" ] && { printf "%s\\n" "$rd"; exit 0; }\n'
        '      case "$fmt" in *Id*) printf "sha256:%s\\n" "$id" ;; esac\n'
        "      exit 0 ;;\n"
        '    *Id*) printf "sha256:%s\\n" "$id"; exit 0 ;;\n'
        "  esac\n"
        "fi\n"
        'printf \'[\\n    {\\n        "Id": "sha256:%s",\\n'
        '        "RepoTags": [\\n            "%s"\\n        ],\\n'
        '        "RepoDigests": [%s],\\n'
        '        "Config": {\\n            "Labels": {\\n'
        f'                "org.mcgyvr.build.toolkit": "{TOOLKIT_DIGEST}"\\n'
        "            }\\n        }\\n    }\\n]\\n' "
        '"$id" "$tag" "${rd:+\\"$rd\\"}"\n',
    )


def docker_log(stub: Path) -> list[str]:
    log = stub.parent / "docker.log"
    if not log.is_file():
        return []
    return log.read_text(encoding="utf-8").splitlines()


def ssh_stub(where: Path) -> Path:
    """A ``RUN_SSH`` that records the attempt and refuses: no test reaches a rig."""
    marker = where / "ssh.reached"
    return executable(
        where / "ssh",
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{marker}'\n"
        "echo 'ssh reached from a test' >&2\n"
        "exit 1\n",
    )


def product_stub(where: Path, *, pinned: bool, moved_from: str = "r8-prior") -> Path:
    """A ``RUN_PRODUCT_CHECK``: the open round and its digest, or the refusal
    ``tools/bench/product.require_pinned`` raises (``product.py:274``)."""
    if pinned:
        body = f"printf 'round=%s product_sha256=%s\\n' {ROUND_ID} {PRODUCT_SHA256}\n"
    else:
        body = (
            f"echo 'the product has moved off round `{moved_from}`: it pins "
            "deadbeef and this tree is cafef00d' >&2\n"
            "exit 1\n"
        )
    return executable(where / "product-check", "#!/usr/bin/env bash\n" + body)


def fixture_repo(tmp_path: Path) -> Path:
    """A throw-away checkout the door can write into.

    ``tools/runs`` is copied whole (minus any campaign, so the tests own the
    campaign list), ``tests/sweeprows.py`` and ``tests/__init__.py`` come along
    so ``_repo_root`` recognises it, ``pyproject.toml``/``uv.lock`` with a
    symlinked ``.venv`` let ``uv run --no-sync`` work inside it, and
    ``tools/runs/hosts.json`` is written from the brief's rig table.
    """
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tools").mkdir()
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
    # `run.sh` is no longer under RUNS to be copied by the copytree above — it
    # was archived when src/mcgyvr/serving/run.py became the door. These tests
    # still drive it, as the spec the Python door has to meet, so the archived
    # copy is placed at the path they invoke.
    shutil.copy(RUN_SH, root / "tools" / "runs" / "run.sh")
    (root / "tools" / "runs" / "run.sh").chmod(0o755)
    (root / "tools" / "runs" / "hosts.json").write_text(
        hosts_document(), encoding="utf-8"
    )
    return root


def hosts_document() -> str:
    import json

    doc: dict[str, object] = {"hosts": ["srv1", "srv2"]}
    for host, rig in RIG.items():
        doc[host] = {"rig": dict(rig), "read_on": RIG_READ_ON}
    return json.dumps(doc, indent=2) + "\n"


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
    twice over it).
    """
    end = end_line or (
        f"### END uptime_since={UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "cpu_max_mhz=4600 ram_mt_s=3600"
    )
    rig = " ".join(f"{k}={v}" for k, v in RIG["srv1"].items())
    return (
        "#!/usr/bin/env bash\n"
        f"# {directive}: probe.tsv\n"
        "set -euo pipefail\n"
        '[ -n "${RUN_ID:-}" ] || { echo "probe: RUN_ID is unset; start me '
        'through tools/runs/run.sh" >&2; exit 2; }\n'
        f"printf 'RUN_ID=%s\\nRUN_OUT_DIR=%s\\nRUN_HOST=%s\\nRUN_ROUND=%s\\n"
        "RUN_PRODUCT_SHA256=%s\\n' "
        '"$RUN_ID" "${RUN_OUT_DIR:-}" "${RUN_HOST:-}" "${RUN_ROUND:-}" '
        f"\"${{RUN_PRODUCT_SHA256:-}}\" > '{env_file}'\n"
        'out="${RUN_OUT_DIR:?}/probe.tsv"\n'
        "{\n"
        "printf '### WORKLOAD digest=none comparable_with=microbenchmark-only\\n'\n"
        f"printf '### START uptime_since={UPTIME} pl1_uw=95000000 "
        "pl2_uw=120000000 pl1_source=constraint_0_power_limit_uw "
        'cpu_max_mhz=4600 ram_mt_s=3600 run_id=%s\\n\' "$RUN_ID"\n'
        f"printf '### ROUND id={ROUND_ID} product_sha256={PRODUCT_SHA256}\\n'\n"
        f"printf '### RIG {rig}\\n'\n"
        "printf '%s\\tprobe\\tCONFIG\\timg=sha256:%s\\n' "
        f'"${{RUN_HOST:-nohost}}" {LOCAL_ID_HEX}\n'
        f"printf '{end}\\n'\n"
        '} > "$out"\n' + after + "\n"
    )


def door_env(
    root: Path,
    stubs: Path,
    *,
    host: str = "srv1",
    pinned: bool = True,
    rig: Path | None = None,
    docker: Path | None = None,
) -> dict[str, str]:
    """The environment a door invocation runs under: every seam set, no
    ``RUN_*`` or image variable inherited from the developer's shell."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("RUN_") and k not in ("LCP_IMG", "VLLM_IMG")
    }
    env["RUN_REPO"] = str(root)
    env["RUN_DATE"] = RUN_DATE
    env["RUN_PRODUCT_CHECK"] = str(product_stub(stubs, pinned=pinned))
    env["RUN_RIG_SNAPSHOT_CMD"] = str(rig or rig_stub(stubs, host))
    env["RUN_DOCKER"] = str(docker or docker_stub(stubs))
    env["RUN_SSH"] = str(ssh_stub(stubs))
    return env


def door(
    root: Path, argv: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run the fixture's copy of the ARCHIVED ``run.sh``; it must exist to copy."""
    assert RUN_SH.is_file(), f"{RUN_SH.relative_to(REPO)} does not exist"
    assert os.access(RUN_SH, os.X_OK), f"{RUN_SH.relative_to(REPO)} is not executable"
    # A throw-away tree has the door copied into it at the path these tests
    # drive; the REAL checkout no longer has one there, because it was
    # archived. Reach for the archived copy in that case rather than a path
    # that has not existed since round r3.
    door_path = RUN_SH if root == REPO else root / "tools" / "runs" / "run.sh"
    return subprocess.run(
        [str(door_path), *argv],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def envelope(root: Path, campaign: str) -> Path:
    return root / "records" / "evidence" / f"{RUN_DATE}-{campaign}"


def written_under_records(root: Path) -> list[str]:
    records = root / "records"
    if not records.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in records.rglob("*") if p.is_file())


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        out[key] = value
    return out


def driver(
    name: str,
    env: dict[str, str],
    *,
    argv: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``tools/runs/drivers/<name>`` with the interpreter the tests use.

    The file must exist first: ``python missing.py`` exits 2 on its own, which
    would read exactly like the refusal these tests are looking for.
    """
    path = DRIVERS / name
    assert path.is_file(), f"{path.relative_to(REPO)} does not exist"
    return subprocess.run(
        [sys.executable, str(path), *(argv if argv is not None else DRIVER_ARGV[name])],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def bare_env(stubs: Path, **extra: str) -> dict[str, str]:
    """An environment with no ``RUN_*`` in it, plus a docker stub and ``extra``."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("RUN_") and k not in ("LCP_IMG", "VLLM_IMG")
    }
    env["RUN_DOCKER"] = str(docker_stub(stubs))
    env.update(extra)
    return env


def bash(
    script: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
