"""Step 5 of srv1-kernel-arms starts the servers it measures, through the door.

``5-correctness.sh`` took ``--arm ARM=ENDPOINT=SERVING_BUILD`` and measured
whatever answered at ENDPOINT. Nothing in the campaign started that server:
the door is the one executable allowed to start a container on a rig, and
the step it starts is the only thing allowed to do so on its behalf. So the
step could not run at all — its endpoints were nobody's job, and a server
started by hand outside the door is exactly the waiver the door exists to end.

Now ``--arm ARM=IMAGE``: the step resolves IMAGE to a digest once (gate 3),
runs one container per arm named ``<RUN_ID>-<ARM>`` (so gate 7 finds a
leftover), on one port, mounts ``--gguf`` as the checkpoint, serves it under
``--model``, waits for ``/health``, measures the arm's two runs against
``http://<RUN_HOST>:<port>`` — the container runs ON the rig, because the
door's ``docker`` lands there — and removes the container before the next
arm. ``serving_build`` in ``correctness.json`` is ``llama.cpp@<tag>@<digest>``
— the vocabulary step 6 already writes — never a string the caller typed.

The real campaign is copied into the fixture; ``--dry-run`` so nothing is
launched.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

CAMPAIGN = "srv1-kernel-arms"
RUN_ID = f"{onedoor.RUN_DATE}-{CAMPAIGN}-correctness"
ENDPOINT = "http://srv1:8081"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    shutil.copytree(
        onedoor.KERNEL_ARMS, repo / "tools" / "runs" / "campaigns" / CAMPAIGN
    )
    envelope = onedoor.envelope(repo, CAMPAIGN)
    envelope.mkdir(parents=True)
    # What step 4 (serve) leaves behind: the file the verdicts are read from.
    (envelope / "srv1-lcpp-arms.tsv").write_text(
        f"### START run_id={onedoor.RUN_DATE}-{CAMPAIGN}-kernel-arms\n",
        encoding="utf-8",
    )
    return repo


@pytest.fixture
def gguf(tmp_path: Path) -> Path:
    path = tmp_path / "models" / "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf"
    path.parent.mkdir()
    path.write_bytes(b"GGUF")
    return path


def _dry(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return onedoor.door(
        root, Scenario(CAMPAIGN, "5-correctness.sh", step_args=("--dry-run", *args))
    )


def test_the_step_launches_each_arm_itself_named_for_the_run(
    root: Path, gguf: Path
) -> None:
    result = _dry(
        root,
        "--arm",
        f"L0={onedoor.LOCAL_TAG}",
        "--gguf",
        str(gguf),
        "--model",
        "qwen2.5-coder-1.5b",
        "--reference",
        "L0",
    )
    assert result.returncode != 2, (result.stdout, result.stderr)
    out = result.stdout
    assert "docker run" in out, out
    assert f"--name {RUN_ID}-L0" in out, out
    # Gate 3: the container runs the digest the tag resolved to, not the tag.
    assert onedoor.LOCAL_ID_HEX in out, out
    assert f"/models/{gguf.name}" in out, out
    assert "--alias qwen2.5-coder-1.5b" in out, out
    # The endpoint is the step's own, derived from the door's host and its
    # port — nobody typed it, and it is the rig, not this machine.
    assert f"--endpoint {ENDPOINT}" in out, out
    assert "-p 8081:8081" in out, out
    # What served is checked against what the image declares, before a run.
    assert "--list-devices" in out and "backend_verdict" in out, out
    # And the container is gone before the next arm (and for gate 7).
    assert f"docker rm -f {RUN_ID}-L0" in out, out


def test_two_arms_are_served_one_after_the_other_on_one_port(
    root: Path, gguf: Path
) -> None:
    result = _dry(
        root,
        "--arm",
        f"L0={onedoor.LOCAL_TAG}",
        "--arm",
        f"L3={onedoor.LOCAL_TAG}",
        "--gguf",
        str(gguf),
        "--model",
        "q",
        "--reference",
        "L0",
    )
    assert result.returncode != 2, (result.stdout, result.stderr)
    out = result.stdout
    first_up = out.index(f"--name {RUN_ID}-L0")
    first_down = out.index(f"docker rm -f {RUN_ID}-L0")
    second_up = out.index(f"--name {RUN_ID}-L3")
    assert first_up < first_down < second_up, out
    assert out.count("-p 8081:8081") == 2, out


def test_an_endpoint_typed_by_the_caller_is_refused(root: Path, gguf: Path) -> None:
    """The old spelling named a server nobody in the campaign started."""
    result = _dry(
        root,
        "--arm",
        f"L0={ENDPOINT}={onedoor.LOCAL_TAG}",
        "--gguf",
        str(gguf),
        "--model",
        "q",
        "--reference",
        "L0",
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "ARM=IMAGE" in result.stderr, result.stderr
    assert "docker run" not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "image",
    ["localhost:5000/llamacpp:b10644-L3", "llamacpp:2026-09-02-L3"],
)
def test_a_registry_port_or_a_dated_tag_is_still_an_image(
    root: Path, gguf: Path, image: str
) -> None:
    """Only a scheme, a third field, or a bare host:port spells an endpoint."""
    result = _dry(
        root,
        "--arm",
        f"L0={image}",
        "--gguf",
        str(gguf),
        "--model",
        "q",
        "--reference",
        "L0",
    )
    # The stub daemon does not hold these tags, so gate 3 refuses — but as a
    # digest failure, not as an endpoint typed by the caller.
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "ARM=IMAGE" not in result.stderr, result.stderr
    assert "digest" in result.stderr, result.stderr


def test_without_a_checkpoint_nothing_is_served(root: Path) -> None:
    result = _dry(
        root,
        "--arm",
        f"L0={onedoor.LOCAL_TAG}",
        "--model",
        "q",
        "--reference",
        "L0",
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "--gguf" in result.stderr, result.stderr
    assert "docker run" not in result.stdout, result.stdout


def test_an_image_the_daemon_does_not_hold_is_refused_before_any_container(
    root: Path, gguf: Path
) -> None:
    result = _dry(
        root,
        "--arm",
        "L0=llamacpp:b10644-nowhere",
        "--gguf",
        str(gguf),
        "--model",
        "q",
        "--reference",
        "L0",
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "digest" in result.stderr, result.stderr
    assert "docker run" not in result.stdout, result.stdout


def test_the_verdict_source_can_be_named_when_it_lives_in_another_envelope(
    root: Path, gguf: Path
) -> None:
    """The verdicts come from the serve step's ``srv1-lcpp-arms.tsv``. The
    door's envelope is dated, so a step 5 run on a later day than the serve
    step has no such file beside it; ``--arms-tsv PATH`` names the one to read
    (an input, so it may live outside this run's envelope), and the plan says
    which file the verdicts will come from."""
    other = root / "records" / "evidence" / "2026-09-01-srv1-kernel-arms"
    other.mkdir(parents=True, exist_ok=True)
    arms = other / "srv1-lcpp-arms.tsv"
    arms.write_text("### START run_id=x\n", encoding="utf-8")
    result = _dry(
        root,
        "--arm",
        f"L0={onedoor.LOCAL_TAG}",
        "--gguf",
        str(gguf),
        "--model",
        "q",
        "--reference",
        "L0",
        "--arms-tsv",
        str(arms),
    )
    assert result.returncode != 2, (result.stdout, result.stderr)
    assert f"verdicts from {arms}" in result.stdout, result.stdout


def test_a_verdict_source_that_does_not_exist_is_refused_before_any_container(
    root: Path, gguf: Path
) -> None:
    result = _dry(
        root,
        "--arm",
        f"L0={onedoor.LOCAL_TAG}",
        "--gguf",
        str(gguf),
        "--model",
        "q",
        "--reference",
        "L0",
        "--arms-tsv",
        "/nonexistent/srv1-lcpp-arms.tsv",
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "--arms-tsv" in result.stderr, result.stderr
    assert "docker run" not in result.stdout, result.stdout
