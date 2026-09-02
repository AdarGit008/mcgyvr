"""``launch.py`` keeps its marker check and loses its launch path; run.sh launches.

``tools/bench/serving/launch.py`` was written after 1.5 h of rig time went to
a run whose patch never reached the file (D8): verify the markers, then launch,
as ONE step. The verification is worth keeping. The launch is not: it was the
second of four live entry points to the rigs, with its own ``nohup``, its own
trap, its own ``--release`` — none of it stamping rig state, round or workload
(BRIEF.md, "The problem being solved"). The door does all of that once.

So the fold is two halves. ``launch.py`` exposes ``verify_markers(repo) ->
list[str]`` — the problems, or an empty list — and has no way to launch; run as
a script it points at ``tools/runs/run.sh``. And run.sh runs that check before
any step of a campaign whose ``campaign.json`` (beside ``PLAN.md``) declares
``{"serving": true}``, refusing with exit 2 and nothing written when a marker
is missing — which is exactly the run D8 was written to refuse. A campaign that
does not serve is not held to the serving markers.

The seams are ``tests/onedoor.py``'s: ``RUN_REPO`` points run.sh at a
throw-away copy of the tree (here with ``tools/bench/serving`` copied in and
one marker broken on purpose); ``RUN_PRODUCT_CHECK``, ``RUN_RIG_SNAPSHOT_CMD``,
``RUN_DOCKER`` and ``RUN_SSH`` are stubs. No rig is reachable from here.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

from tests import onedoor

REPO = Path(__file__).resolve().parent.parent
LAUNCH = REPO / "tools" / "bench" / "serving" / "launch.py"

#: The marker the fixture breaks. D3's, first in ``launch.MARKERS``.
BROKEN = ("tools/bench/serving/contract.py", "RAMP_TOKENS = 475")

#: What the refusal must say — ``launch.check``'s own word for a missing marker.
REFUSAL = "MISSING"

CAMPAIGN = "fixture"


def _launch() -> types.ModuleType:
    return importlib.import_module("tools.bench.serving.launch")


def _copy(rel: str, into: Path) -> None:
    source = REPO / rel
    target = into / rel
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns("__pycache__"),
            dirs_exist_ok=True,
        )
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _marker_files(into: Path) -> Path:
    """Every file ``launch.MARKERS`` / ``launch.WITHDRAWN`` name, copied verbatim."""
    launch = _launch()
    for path, _marker, _decision in (*launch.MARKERS, *launch.WITHDRAWN):
        _copy(path, into)
    return into


def _break_a_marker(repo: Path) -> None:
    path, marker = BROKEN
    text = (repo / path).read_text(encoding="utf-8")
    assert marker in text, f"{path} no longer carries {marker!r}; pick another marker"
    (repo / path).write_text(
        text.replace(marker, "RAMP_TOKENS = 476"), encoding="utf-8"
    )


def _campaign(tmp_path: Path, *, serving: bool) -> tuple[Path, Path]:
    """``onedoor.fixture_repo`` plus the serving harness, one marker broken, and
    one campaign whose single step touches a canary file if it ever runs."""
    root = onedoor.fixture_repo(tmp_path)
    _copy("tools/bench/serving", root)
    _marker_files(root)
    _break_a_marker(root)
    campaign = root / "tools" / "runs" / "campaigns" / CAMPAIGN
    campaign.mkdir(parents=True)
    (campaign / "PLAN.md").write_text("# fixture campaign\n", encoding="utf-8")
    (campaign / "campaign.json").write_text(
        json.dumps({"serving": serving}) + "\n", encoding="utf-8"
    )
    canary = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        CAMPAIGN,
        "1-serve.sh",
        "#!/usr/bin/env bash\n"
        "# RUN_ARTIFACTS: serve.tsv\n"
        f"touch '{canary}'\n"
        "echo 'the step ran'\n",
    )
    return root, canary


def _forbidding_rig(stubs: Path) -> Path:
    """A ``RUN_RIG_SNAPSHOT_CMD`` that refuses: the control stops at gate 2."""
    path = stubs / "rig-forbidden"
    path.write_text(
        '#!/usr/bin/env bash\necho "RIG READ FORBIDDEN by the test" >&2\nexit 1\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


# --------------------------------------------------------------------------
# launch.py: a function over a repo, and no launch path
# --------------------------------------------------------------------------


def test_the_marker_check_is_a_function_over_a_repo() -> None:
    launch = _launch()
    verify = getattr(launch, "verify_markers", None)
    assert callable(verify), "launch.py exposes no verify_markers(repo) -> list[str]"
    problems = verify(REPO)
    assert problems == [], f"the tree on disk fails its own markers: {problems}"


def test_the_check_names_the_marker_it_misses(tmp_path: Path) -> None:
    launch = _launch()
    fixture = _marker_files(tmp_path / "repo")
    _break_a_marker(fixture)
    problems = launch.verify_markers(fixture)
    assert any(REFUSAL in p and BROKEN[1] in p for p in problems), (
        f"verify_markers did not name the broken marker {BROKEN[1]!r}: {problems}"
    )


def test_run_as_a_script_it_points_at_the_door() -> None:
    done = subprocess.run(
        [sys.executable, str(LAUNCH)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    out = done.stdout + done.stderr
    assert done.returncode != 0, f"exit {done.returncode}: {out[-400:]}"
    assert "tools/runs/run.sh" in out, f"no pointer at the door in: {out[-400:]}"


def test_the_launch_path_is_gone() -> None:
    launch = _launch()
    code = launch.code_lines(LAUNCH.read_text(encoding="utf-8"))
    left = [
        line
        for line in code
        if "nohup" in line or "--campaign" in line or "--release" in line
    ]
    assert not left, (
        f"launch.py still carries a launch path — {left[:4]}; run.sh is the launcher"
    )


# --------------------------------------------------------------------------
# run.sh: the check runs before a serving step, and only a serving step
# --------------------------------------------------------------------------


def test_run_sh_refuses_a_serving_step_when_a_marker_is_missing(
    tmp_path: Path,
) -> None:
    root, canary = _campaign(tmp_path, serving=True)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs)
    done = onedoor.door(root, [CAMPAIGN, "1", "--host", "srv1"], env)
    out = done.stdout + done.stderr
    assert done.returncode == 2, f"exit {done.returncode}: {out[-600:]}"
    assert REFUSAL in out and BROKEN[1] in out, (
        f"the refusal does not name the missing marker {BROKEN[1]!r}: {out[-600:]}"
    )
    assert not canary.exists(), "the step ran on a harness that failed its markers"
    assert onedoor.written_under_records(root) == [], "a refusal wrote an envelope"
    assert not (stubs / "ssh.reached").exists(), "a rig was reached from a test"


def test_run_sh_does_not_hold_a_non_serving_step_to_the_serving_markers(
    tmp_path: Path,
) -> None:
    root, canary = _campaign(tmp_path, serving=False)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.door_env(root, stubs, rig=_forbidding_rig(stubs))
    done = onedoor.door(root, [CAMPAIGN, "1", "--host", "srv1"], env)
    out = done.stdout + done.stderr
    assert BROKEN[1] not in out and REFUSAL not in out, (
        f"a campaign that does not serve was refused for a serving marker: {out[-600:]}"
    )
    # The rig stub refuses at gate 2, so the run stops there — loudly.
    assert done.returncode == 2, f"exit {done.returncode}: {out[-600:]}"
    assert not canary.exists(), "the step ran past a rig that could not be read"
    assert not (stubs / "ssh.reached").exists(), "a rig was reached from a test"
