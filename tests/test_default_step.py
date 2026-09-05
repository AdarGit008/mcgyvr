"""The door's default step walks the derived floor onto the rig and records it.

``src/mcgyvr/serving/gate-scripts/default-step.sh`` is what gate 6 runs when a
caller names no ``--step``. It is model-agnostic by design: it reads the
placement the door derived, launches at the floor, measures the card after one
real completion, then launches one block below the floor and expects a refusal
— the refusal is the measurement (okf/must-read/touching-rigs.md), and a load
below the floor is a RESULT row saying the floor was loose, never an error.

No test here reaches a rig. The script's only way out is the door's ``ssh``
and ``docker`` shims, which it resolves BY PATH under ``RUN_ROOT`` after
proving the door (``gatelib.under_door``, read off /proc). So each :class:`Fake`
runs the step under a stand-in door — a file whose path ends in
``mcgyvr/serving/run.py`` — and puts the answering stubs at the shim path
under a throw-away ``RUN_ROOT``; what PATH offers under the same names are
decoys that log and fail, so a step that took ``ssh`` from PATH would show up
in the log. Every call is logged so the test can say what the step did to
the machine — which containers it started, and that each one was removed.
``sleep`` is stubbed too: the health poll is 120 x 3 s by design, and a test
that waited for it would be a test nobody ran.

The fake envelope is a RECORDED one — ``records/evidence/2026-09-05-e2e-srv2-
deepseek-coder-v2-16b/{scan,geometry,placement}.json`` — so the numbers the
step reads are numbers the door once wrote, not ones invented to fit.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "default-step.sh"
SRV2_ENVELOPE = (
    REPO / "records" / "evidence" / "2026-09-05-e2e-srv2-deepseek-coder-v2-16b"
)
SRV1_ENVELOPE = (
    REPO / "records" / "evidence" / "2026-09-05-e2e-srv1-qwen3-6-35b-a3b-ud-iq3xxs"
)

ROUND_ID = "r3-05-09-2026"
PRODUCT_SHA256 = "247d1386fbe4de0cd674d710f86fb39039643e14902b723d6e6ed198677db333"
DIGEST = "ghcr.io/ggml-org/llama.cpp@sha256:" + "a" * 64
RIG_HOME = "/home/x"
#: hosts.json as the door will carry it: the image a row is valid against, and
#: whether the host survives CPU expert offload (srv1 does not: it hard-locks).
HOSTS = {
    "srv1": {"llamacpp_image": "llamacpp:b10644-L3", "cpu_expert_offload": False},
    "srv2": {
        "llamacpp_image": "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644",
        "cpu_expert_offload": True,
    },
}

#: The stand-in for the door's ssh shim. Refuses any host but STUB_HOST, the
#: way the shim refuses any host but RUN_HOST, and answers the rig-side
#: commands the step issues; ``cat >>`` lands under STUB_RIG so the rig-side
#: copy of the artifact can be compared with the local one.
SSH_STUB = """\
#!/usr/bin/env bash
set -u
printf 'ssh %s\\n' "$*" >> "$STUB_LOG"
while [ "${1:-}" = -o ]; do shift 2; done
host=$1; shift
[ "$host" = "$STUB_HOST" ] || { echo "ssh stub: refusing host $host" >&2; exit 255; }
cmd="$*"
case "$cmd" in
  *'echo $HOME'*) echo "$STUB_RIG_HOME" ;;
  *memory.used*) echo "${STUB_USED:-11700}" ;;
  *memory.free*) echo "${STUB_FREE:-11911}" ;;
  *constraint_0_power_limit_uw*) echo "${STUB_PL1:-65000000}" ;;
  *constraint_1_power_limit_uw*) echo "${STUB_PL2:-0}" ;;
  *health*)
    for f in "$STUB_STATE"/*; do
      [ -e "$f" ] && [ "$(cat "$f")" = alive ] && exit "${STUB_HEALTH_RC:-0}"
    done
    exit 7 ;;
  *completion*) echo '{"content":" there"}' ;;
  *mkdir*|*'cat >>'*) HOME=$STUB_RIG bash -c "$cmd" ;;
  *) echo "ssh stub: no answer for: $cmd" >&2; exit 1 ;;
esac
"""

#: The stand-in for the docker shim. A container is a file under STUB_STATE
#: holding ``alive`` or ``dead``; ``run`` creates it (dead when the placement
#: equals STUB_REFUSE_NCMOE, the way a launch past the memory edge exits),
#: ``ps`` lists the live ones by the same name filter docker takes, ``rm -f``
#: deletes it, and ``logs`` prints the tail an OOM leaves behind.
DOCKER_STUB = """\
#!/usr/bin/env bash
set -u
printf 'docker %s\\n' "$*" >> "$STUB_LOG"
verb=${1:-}; shift || true
case "$verb" in
  image)
    echo "$STUB_DIGEST" ;;
  run)
    name=; ncmoe=
    while [ $# -gt 0 ]; do
      case "$1" in
        --name) name=$2; shift ;;
        --n-cpu-moe) ncmoe=$2; shift ;;
      esac
      shift
    done
    [ -n "$name" ] || { echo "docker stub: run without --name" >&2; exit 125; }
    if [ -n "${STUB_RUN_FAILS:-}" ]; then
      echo "docker: Error response from daemon: port is already allocated." >&2
      exit 125
    fi
    if [ -n "${STUB_REFUSE_NCMOE:-}" ] && [ "$ncmoe" = "$STUB_REFUSE_NCMOE" ]; then
      echo dead > "$STUB_STATE/$name"
    else
      echo alive > "$STUB_STATE/$name"
    fi
    echo "cid-$name" ;;
  ps)
    pat=
    while [ $# -gt 0 ]; do
      case "$1" in --filter) pat=${2#name=}; shift ;; esac
      shift
    done
    pat=${pat#^}
    for f in "$STUB_STATE"/*; do
      [ -e "$f" ] || continue
      n=$(basename "$f")
      case "$pat" in
        *'$') [ "$n" = "${pat%\\$}" ] || continue ;;
        *) [ "${n#"$pat"}" != "$n" ] || continue ;;
      esac
      [ "$(cat "$f")" = alive ] && echo "cid-$n"
    done
    exit 0 ;;
  rm)
    [ "${1:-}" = -f ] && shift
    rm -f "$STUB_STATE/$1" ;;
  logs)
    echo "ggml_backend_cuda_buffer_type_alloc_buffer: allocating 5940.00 MiB"
    echo "cudaMalloc failed: out of memory" ;;
  *)
    echo "docker stub: no answer for verb '$verb'" >&2; exit 1 ;;
esac
"""

SLEEP_STUB = "#!/usr/bin/env bash\nexit 0\n"

#: What PATH offers as ``ssh`` and ``docker``: never the right answer. The
#: step resolves the shims by path under RUN_ROOT, and a decoy line in the
#: log means it took one from PATH instead.
DECOY_STUB = """\
#!/usr/bin/env bash
printf 'decoy %s %s\\n' "$(basename "$0")" "$*" >> "$STUB_LOG"
exit 1
"""

#: The stand-in door: runs its arguments as a child, from a path that ends in
#: mcgyvr/serving/run.py — which is what the step's proof reads off /proc.
FAKE_DOOR = (
    "import subprocess, sys\n"
    "raise SystemExit(subprocess.run(sys.argv[1:]).returncode)\n"
)


def _is_launch(line: str) -> bool:
    """Whether a logged docker call was a launch, by its first two words."""
    words = line.split()
    return len(words) > 1 and words[0] == "docker" and words[1] == "run"


def _rows() -> types.ModuleType:
    """``tools/runs/rows.py`` — the parser gate 8 reads the artifact with."""
    return importlib.import_module("tools.runs.rows")


class Fake:
    """A door-shaped environment around a temp directory, and what the stubs saw."""

    def __init__(self, tmp: Path, host: str, envelope: Path) -> None:
        self.tmp = tmp
        self.host = host
        self.run_id = f"2026-09-05-e2e-{host}-default-step"
        self.out = tmp / "envelope"
        self.out.mkdir()
        self.root = tmp / "root"
        (self.root / "tools" / "runs").mkdir(parents=True)
        (self.root / "tools" / "runs" / "hosts.json").write_text(
            json.dumps(HOSTS), encoding="utf-8"
        )
        for name in ("scan.json", "geometry.json", "placement.json"):
            shutil.copy(envelope / name, self.out / name)
        self.state = tmp / "state"
        self.state.mkdir()
        self.rig = tmp / "rig"
        self.rig.mkdir()
        self.log = tmp / "stub.log"
        self.log.write_text("", encoding="utf-8")
        # The answering stubs sit where the step resolves the door's shims —
        # by path under RUN_ROOT — and PATH offers decoys under the same names.
        shims = self.root / "src" / "mcgyvr" / "serving" / "gate-scripts" / "bin"
        shims.mkdir(parents=True)
        stubs = tmp / "stubs"
        stubs.mkdir()
        for where, name, body in (
            (shims, "ssh", SSH_STUB),
            (shims, "docker", DOCKER_STUB),
            (stubs, "sleep", SLEEP_STUB),
            (stubs, "ssh", DECOY_STUB),
            (stubs, "docker", DECOY_STUB),
        ):
            path = where / name
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
        self.stubs = stubs
        self.shims = shims
        self.door = tmp / "door" / "mcgyvr" / "serving" / "run.py"
        self.door.parent.mkdir(parents=True)
        self.door.write_text(FAKE_DOOR, encoding="utf-8")

    def placement(self, **overrides: object) -> dict[str, object]:
        path = self.out / "placement.json"
        doc: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        doc.update(overrides)
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return doc

    def env(self, **stub: str) -> dict[str, str]:
        model = str(self.placement()["model"])
        env = dict(os.environ)
        # The decoys first, then the interpreter the tests run under, so the
        # step's `python3` proof finds a python that CAN import gatelib.
        path = [str(self.stubs), str(Path(sys.executable).parent)]
        path += (os.environ.get("PATH") or os.defpath).split(os.pathsep)
        env.update(
            PATH=os.pathsep.join(path),
            RUN_ROOT=str(self.root),
            RUN_CAMPAIGN=f"e2e-{self.host}",
            RUN_STEP_FILE=str(SCRIPT),
            RUN_HOST=self.host,
            RUN_SUFFIX="",
            RUN_MODEL=model,
            RUN_PARALLEL="8",
            RUN_CTX_PER_SLOT="2048",
            RUN_UBATCH="256",
            RUN_ROUND=ROUND_ID,
            RUN_PRODUCT_SHA256=PRODUCT_SHA256,
            RUN_ID=self.run_id,
            RUN_OUT_DIR=str(self.out),
            RUN_DATE="2026-09-05",
            RUN_SCAN_JSON=str(self.out / "scan.json"),
            RUN_GEOMETRY_JSON=str(self.out / "geometry.json"),
            RUN_PLACEMENT_JSON=str(self.out / "placement.json"),
            STUB_LOG=str(self.log),
            STUB_STATE=str(self.state),
            STUB_RIG=str(self.rig),
            STUB_RIG_HOME=RIG_HOME,
            STUB_HOST=self.host,
            STUB_DIGEST=DIGEST,
        )
        for key in ("STUB_REFUSE_NCMOE", "STUB_HEALTH_RC", "STUB_RUN_FAILS"):
            env.pop(key, None)
        env.update(stub)
        return env

    def run(self, **stub: str) -> subprocess.CompletedProcess[str]:
        return self.start(self.env(**stub))

    def start(
        self, env: dict[str, str], *, under_door: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """The step, under the stand-in door unless a test wants it bare."""
        argv = [str(SCRIPT)]
        if under_door:
            argv = [sys.executable, str(self.door), *argv]
        return subprocess.run(
            argv,
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def launches(self) -> list[str]:
        """Every launch the docker stub logged, in order."""
        return [line for line in self.calls() if _is_launch(line)]

    def started(self) -> list[str]:
        """Container names handed to ``--name`` by each launch, in order."""
        names: list[str] = []
        for line in self.launches():
            words = line.split()
            names.append(words[words.index("--name") + 1])
        return names

    def removed(self) -> list[str]:
        return [
            line.split()[-1]
            for line in self.calls()
            if line.split()[:3] == ["docker", "rm", "-f"]
        ]

    def sizing(self) -> Path:
        return self.out / "sizing.tsv"


@pytest.fixture
def srv2(tmp_path: Path) -> Fake:
    return Fake(tmp_path, "srv2", SRV2_ENVELOPE)


@pytest.fixture
def srv1(tmp_path: Path) -> Fake:
    return Fake(tmp_path, "srv1", SRV1_ENVELOPE)


# --------------------------------------------------------------------------
# the file itself
# --------------------------------------------------------------------------


def test_the_step_is_executable_and_declares_one_artifact() -> None:
    assert os.access(SCRIPT, os.X_OK), f"{SCRIPT} is not executable; gate 6 refuses it"
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    declared = [line for line in lines if line.startswith("# RUN_ARTIFACTS:")]
    assert declared == ["# RUN_ARTIFACTS: sizing.tsv"], declared
    assert not [
        line for line in lines if line.startswith(("# RUN_REWRITES:", "# RUN_APPENDS:"))
    ]


def test_the_step_parses_under_bash_n_and_shellcheck() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", str(SCRIPT)], check=True)


# --------------------------------------------------------------------------
# the protocol: load at the floor, refuse one below it, remove everything
# --------------------------------------------------------------------------


def test_at_the_floor_loads_and_one_below_refuses(srv2: Fake) -> None:
    floor = int(str(srv2.placement()["floor_n_cpu_moe"]))
    assert floor == 7, "the recorded deepseek placement floors at 7"
    done = srv2.run(STUB_REFUSE_NCMOE=str(floor - 1), STUB_USED="11750")
    assert done.returncode == 0, done.stderr

    sweep = _rows().read(srv2.sizing())
    start = sweep.stamp("START")
    assert start["run_id"] == srv2.run_id
    assert start["host"] == "srv2"
    assert (start["pl1"], start["pl2"]) == ("65000000", "0"), start
    assert start["uptime_since"] == "2026-09-01T05:20:12Z"
    assert sweep.round == {"id": ROUND_ID, "product_sha256": PRODUCT_SHA256}
    end = sweep.stamp("END")
    assert end["run_id"] == srv2.run_id
    assert end["free_mib"] == "11911"
    assert (end["pl1"], end["pl2"]) == ("65000000", "0")

    at_floor = [r for r in sweep.rows if r.fields["arm"] == "at_floor"]
    below = [r for r in sweep.rows if r.fields["arm"] == "below_floor"]
    assert [r.kind for r in at_floor] == ["OK"], "an OK needs no retry"
    assert [r.kind for r in below] == ["REFUSED"] * 3, (
        "a refusal is a 1-in-3 coin flip and is retried three times"
    )
    for r in sweep.rows:
        assert r.host == "srv2"
        assert r.label == "deepseek-coder-v2-16b"
        assert r.fields["img"] == DIGEST, "every row names the image it ran under"
        assert r.fields["free_before_mib"] == "11911"
    ok = at_floor[0]
    assert ok.fields["n_cpu_moe"] == "7"
    assert ok.fields["try"] == "1/3"
    assert ok.num("predicted_mib") == 11794.8
    assert ok.num("measured_mib") == 11750
    assert ok.num("delta_mib") == pytest.approx(11750 - 11794.8)
    refused = below[-1]
    assert refused.fields["n_cpu_moe"] == "6"
    assert refused.fields["try"] == "3/3"
    assert refused.fields["measured_mib"] == "NA"
    assert refused.fields["reason"].startswith("container-exited:")
    assert "out of memory" in refused.fields["reason"]
    # One block back on the card: block 6's expert bytes over the floor.
    assert refused.num("predicted_mib") == pytest.approx(
        11794.8 + 311427072 / 1024**2, abs=0.1
    )

    started = srv2.started()
    assert started == [f"{srv2.run_id}-N7"] + [f"{srv2.run_id}-N6"] * 3
    assert all(name.startswith(f"{srv2.run_id}-") for name in started), (
        "gate 7 finds leftovers by the RUN_ID- prefix"
    )
    for name in started:
        assert name in srv2.removed(), f"{name} was started and never rm -f'd"
    assert not list(srv2.state.iterdir()), "a container is left on the rig"

    launch = srv2.launches()[0]
    assert f"-v {RIG_HOME}/models:/models" in launch, "the bind mount is the RIG's HOME"
    assert "-m /models/moe/deepseek-coder-v2-16b.gguf" in launch
    assert (
        "--parallel 8 -c 16384 -b 256 -ub 256 -ngl 99 -t 10 --n-cpu-moe 7" in launch
    ), "nproc 20 is capped at 10 threads; -c is per-slot times slots"
    assert HOSTS["srv2"]["llamacpp_image"] in launch.split()

    rig_copy = srv2.rig / "mcgyvr-runs" / srv2.run_id / "sizing.tsv"
    assert rig_copy.read_text(encoding="utf-8") == srv2.sizing().read_text(
        encoding="utf-8"
    ), "every line is teed to the rig, because a hard lock takes the pipe with it"


def test_a_load_below_the_floor_is_a_result_and_not_a_refusal(srv2: Fake) -> None:
    done = srv2.run()
    assert done.returncode == 0, done.stderr
    sweep = _rows().read(srv2.sizing())
    below = [r for r in sweep.rows if r.fields["arm"] == "below_floor"]
    assert [r.kind for r in below] == ["OK"], (
        "it loaded: the floor was loose, once is enough"
    )
    assert below[0].fields["n_cpu_moe"] == "6"
    assert not list(srv2.state.iterdir())


def test_a_dense_placement_launches_once_at_zero_and_walks_nowhere(srv2: Fake) -> None:
    srv2.placement(
        dense=True,
        floor_n_cpu_moe=0,
        why="no expert tensors: nothing for --n-cpu-moe to move",
    )
    done = srv2.run()
    assert done.returncode == 0, done.stderr
    sweep = _rows().read(srv2.sizing())
    assert [(r.kind, r.fields["arm"], r.fields["n_cpu_moe"]) for r in sweep.rows] == [
        ("OK", "at_floor", "0")
    ]
    assert "--n-cpu-moe" not in srv2.launches()[0]


# --------------------------------------------------------------------------
# srv1 hard-locks under CPU expert offload: refused before any container
# --------------------------------------------------------------------------


def test_a_host_that_forbids_cpu_expert_offload_is_refused_before_any_launch(
    srv1: Fake,
) -> None:
    srv1.placement(floor_n_cpu_moe=30)
    done = srv1.run()
    assert done.returncode == 2, (done.stdout, done.stderr)
    assert "okf/must-read/touching-rigs.md" in done.stderr
    assert "cpu_expert_offload" in done.stderr

    sweep = _rows().read(srv1.sizing())
    assert sweep.round["id"] == ROUND_ID
    assert [(r.kind, r.fields["arm"], r.fields["n_cpu_moe"]) for r in sweep.rows] == [
        ("REFUSED", "at_floor", "30")
    ]
    assert sweep.rows[0].fields["reason"] == "cpu-expert-offload-disabled-on-host"
    assert sweep.rows[0].fields["img"] == DIGEST
    assert sweep.stamp("END")["run_id"] == srv1.run_id, (
        "the file closes; the rig was read"
    )

    assert srv1.started() == [], "nothing was launched on a host that would lock"
    assert not list(srv1.state.iterdir())


def test_a_host_that_forbids_offload_still_serves_a_placement_that_needs_none(
    srv1: Fake,
) -> None:
    srv1.placement(floor_n_cpu_moe=0)
    done = srv1.run()
    assert done.returncode == 0, done.stderr
    assert srv1.started() == [f"{srv1.run_id}-N0"]


# --------------------------------------------------------------------------
# a server that never answers is a REFUSED row, removed, and the step fails
# --------------------------------------------------------------------------


def test_a_server_that_never_answers_health_is_refused_removed_and_fails(
    srv2: Fake,
) -> None:
    done = srv2.run(STUB_HEALTH_RC="1")
    assert done.returncode == 1, (done.stdout, done.stderr)

    sweep = _rows().read(srv2.sizing())
    assert [(r.kind, r.fields["arm"], r.fields["try"]) for r in sweep.rows] == [
        ("REFUSED", "at_floor", "1/3"),
        ("REFUSED", "at_floor", "2/3"),
        ("REFUSED", "at_floor", "3/3"),
    ], "three tries at the floor, no walk below a floor that did not load"
    for r in sweep.rows:
        assert r.fields["reason"].startswith("health-timeout:"), r.fields["reason"]
        assert r.fields["measured_mib"] == "NA"
    assert sweep.stamp("END")["run_id"] == srv2.run_id

    started = srv2.started()
    assert started == [f"{srv2.run_id}-N7"] * 3
    assert srv2.removed().count(f"{srv2.run_id}-N7") >= 3
    assert not list(srv2.state.iterdir()), (
        "a container that never answered is still ours to kill"
    )


def test_a_docker_run_that_fails_is_a_refused_row_with_the_daemons_words(
    srv2: Fake,
) -> None:
    done = srv2.run(STUB_RUN_FAILS="1")
    assert done.returncode == 1
    sweep = _rows().read(srv2.sizing())
    assert all(r.kind == "REFUSED" for r in sweep.rows)
    assert "port is already allocated" in sweep.rows[0].fields["reason"]


# --------------------------------------------------------------------------
# refusals: exit 2, one line naming the rule, nothing launched
# --------------------------------------------------------------------------


def test_an_underived_placement_is_refused(srv2: Fake) -> None:
    srv2.placement(derived=False, why="the cache cannot be sized")
    done = srv2.run()
    assert done.returncode == 2
    assert "derived=false" in done.stderr
    assert not srv2.sizing().exists()
    assert srv2.started() == []


def test_a_host_without_a_declared_image_is_refused(srv2: Fake) -> None:
    hosts = srv2.root / "tools" / "runs" / "hosts.json"
    hosts.write_text(
        json.dumps({"srv2": {"cpu_expert_offload": True}}), encoding="utf-8"
    )
    done = srv2.run()
    assert done.returncode == 2
    assert "llamacpp_image" in done.stderr
    assert not srv2.sizing().exists()
    assert srv2.started() == []


def test_a_step_started_outside_the_door_is_refused(srv2: Fake) -> None:
    """Every RUN_* the door exports, typed in by hand, and no door ancestor:
    refused naming the door, before the shims by path or the decoys on PATH
    see anything. The environment was once the whole guard."""
    done = srv2.start(srv2.env(), under_door=False)
    assert done.returncode == 2, done.stderr
    assert "not started by the door" in done.stderr, done.stderr
    assert "python -m mcgyvr.serving.run" in done.stderr, done.stderr
    assert srv2.calls() == [], "nothing reached the stubs"


def test_a_step_under_the_door_without_a_run_id_is_refused(srv2: Fake) -> None:
    env = srv2.env()
    del env["RUN_ID"]
    done = srv2.start(env)
    assert done.returncode == 2
    assert "RUN_ID is not set" in done.stderr
    assert srv2.calls() == [], "nothing reached the stubs"


def test_the_step_takes_the_shims_by_path_and_never_from_path(srv2: Fake) -> None:
    """The answering stubs are at the shim path under RUN_ROOT; the ``ssh``
    and ``docker`` on PATH are decoys. A run that reached the rig through
    the shims logged no decoy line."""
    srv2.run()
    assert srv2.launches(), "no launch reached the shims under RUN_ROOT"
    decoys = [line for line in srv2.calls() if line.startswith("decoy ")]
    assert decoys == [], f"the step took ssh or docker from PATH: {decoys}"


def test_a_run_root_without_the_shims_is_refused_before_any_call(srv2: Fake) -> None:
    env = srv2.env()
    env["RUN_ROOT"] = str(srv2.tmp / "elsewhere")
    done = srv2.start(env)
    assert done.returncode == 2, done.stderr
    assert "gate-scripts/bin/ssh" in done.stderr, done.stderr
    assert srv2.calls() == []
