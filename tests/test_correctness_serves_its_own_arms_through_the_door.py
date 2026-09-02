"""Step 5 of srv1-kernel-arms starts the servers it measures, through the door.

``5-correctness.sh`` took ``--arm ARM=ENDPOINT=SERVING_BUILD`` and measured
whatever answered at ENDPOINT. Nothing in the campaign started that server:
``run.sh`` is the one executable allowed to start a container on a rig, and
the step it starts is the only thing allowed to do so on its behalf. So on
2026-09-02 (and again on the first run under round r2) the step could not run
at all — its endpoints were nobody's job, and a server started by hand outside
the door is exactly the waiver the door exists to end.

Now ``--arm ARM=IMAGE``: the step resolves IMAGE to a digest once (gate 3),
runs one container per arm named ``<RUN_ID>-<ARM>`` (so gate 7 finds a
leftover), on one host port, mounts ``--gguf`` as the checkpoint, serves it
under ``--model``, waits for ``/health``, measures the arm's two runs against
``http://127.0.0.1:<port>``, and removes the container before the next arm.
``serving_build`` in ``correctness.json`` is ``llama.cpp@<tag>@<digest>`` —
the vocabulary step 6 already writes — never a string the caller typed.

Seams: the ``tests/onedoor.py`` stubs; the real campaign copied into the
fixture; ``--dry-run`` so nothing is launched.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests import onedoor

CAMPAIGN = "srv1-kernel-arms"
RUN_ID = f"{onedoor.RUN_DATE}-{CAMPAIGN}-correctness"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    shutil.copytree(
        onedoor.KERNEL_ARMS, repo / "tools" / "runs" / "campaigns" / CAMPAIGN
    )
    onedoor.envelope(repo, CAMPAIGN).mkdir(parents=True)
    return repo


@pytest.fixture
def env(root: Path, tmp_path: Path) -> dict[str, str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    return onedoor.door_env(root, stubs)


@pytest.fixture
def gguf(tmp_path: Path) -> Path:
    path = tmp_path / "models" / "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf"
    path.parent.mkdir()
    path.write_bytes(b"GGUF")
    return path


def _dry(root: Path, env: dict[str, str], *args: str):
    return onedoor.door(
        root,
        [CAMPAIGN, "correctness", "--host", "srv1", "--", "--dry-run", *args],
        env,
    )


def test_the_step_launches_each_arm_itself_named_for_the_run(
    root: Path, env: dict[str, str], gguf: Path
) -> None:
    result = _dry(
        root,
        env,
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
    # The endpoint is the step's own, derived from its port — nobody typed it.
    assert "--endpoint http://127.0.0.1:8081" in out, out
    assert "-p 127.0.0.1:8081:8081" in out, out
    # What served is checked against what the image declares, before a run.
    assert "load_backend: loaded" in out and "backend_verdict" in out, out
    # And the container is gone before the next arm (and for gate 7).
    assert f"docker rm -f {RUN_ID}-L0" in out, out


def test_two_arms_are_served_one_after_the_other_on_one_port(
    root: Path, env: dict[str, str], gguf: Path
) -> None:
    result = _dry(
        root,
        env,
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
    assert out.count("-p 127.0.0.1:8081:8081") == 2, out


def test_an_endpoint_typed_by_the_caller_is_refused(
    root: Path, env: dict[str, str], gguf: Path
) -> None:
    """The old spelling named a server nobody in the campaign started."""
    result = _dry(
        root,
        env,
        "--arm",
        f"L0=http://127.0.0.1:8081={onedoor.LOCAL_TAG}",
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
    root: Path, env: dict[str, str], gguf: Path, image: str
) -> None:
    """Only a scheme, a third field, or a bare host:port spells an endpoint."""
    result = _dry(
        root,
        env,
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


def test_without_a_checkpoint_nothing_is_served(
    root: Path, env: dict[str, str]
) -> None:
    result = _dry(
        root,
        env,
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
    root: Path, env: dict[str, str], gguf: Path
) -> None:
    result = _dry(
        root,
        env,
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
