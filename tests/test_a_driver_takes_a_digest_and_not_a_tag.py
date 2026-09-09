"""Gate 3: an image reaches a driver as a digest, resolved once, or not at all.

The retired root drivers defaulted to a registry tag and every step script
passed one. A tag is a pointer: the same ``img=`` on two rows can name two
different images a week apart, which is the floating ``:server-cuda`` mistake
the pin was meant to end and only half did. So a tag is resolved ONCE, in
``_common.sh``'s ``image_digest``, through ``docker image inspect`` —
``RepoDigests`` for a registry image, ``Id`` for a local build — and the
digest is handed to the driver; a driver refuses any image value that is not
a digest, before it touches docker.

There is no seam: the drivers call the ``docker`` on PATH, which under the
door is the shim that lands on the rig, and ``_common.sh`` resolves the shim
by path under ``RUN_BIN``. Here that ``docker`` is a stub that logs every
argv it receives, so "before touching docker" is the absence of that log.
Both prove the door before anything else, so the runs that must get past
the image check happen under ``onedoor.fake_door``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import onedoor


def _image_digest(
    tmp_path: Path, tag: str, *, under_door: bool = True
) -> tuple[str, str, int, Path]:
    stubs = tmp_path / "stubs"
    env = onedoor.bare_env(
        stubs,
        RUN_REPO=str(onedoor.REPO),
        RUN_ROOT=str(onedoor.REPO),
        RUN_BIN=str(onedoor.BIN),
    )
    result = onedoor.bash(
        f"set -euo pipefail\n. '{onedoor.COMMON_SH}'\nimage_digest '{tag}'\n",
        env,
        onedoor.REPO,
        door=onedoor.fake_door(tmp_path) if under_door else None,
    )
    return result.stdout, result.stderr, result.returncode, stubs


def test_image_digest_outside_the_door_touches_no_docker(tmp_path: Path) -> None:
    """The same call with every variable set and no door ancestor: refused,
    naming the door, and the stub behind the shim saw nothing."""
    out, err, rc, stubs = _image_digest(tmp_path, onedoor.VLLM_TAG, under_door=False)
    assert rc == 2, (rc, err)
    assert out.strip() == ""
    assert "python -m mcgyvr.serving.run" in err, err
    assert onedoor.docker_log(stubs) == [], "docker was reached outside the door"


def test_a_registry_tag_resolves_to_its_repo_digest_in_one_inspect(
    tmp_path: Path,
) -> None:
    out, err, rc, stubs = _image_digest(tmp_path, onedoor.VLLM_TAG)
    assert rc == 0, err
    assert out.strip() == onedoor.VLLM_DIGEST, out
    inspects = [line for line in onedoor.docker_log(stubs) if "inspect" in line]
    assert len(inspects) == 1, f"resolved {len(inspects)} times, not once: {inspects}"


def test_a_local_build_with_no_repo_digest_resolves_to_its_image_id(
    tmp_path: Path,
) -> None:
    out, err, rc, _ = _image_digest(tmp_path, onedoor.LOCAL_TAG)
    assert rc == 0, err
    assert out.strip() == f"sha256:{onedoor.LOCAL_ID_HEX}", out


def test_an_image_docker_does_not_have_is_refused_with_nothing_on_stdout(
    tmp_path: Path,
) -> None:
    out, err, rc, _ = _image_digest(tmp_path, "nosuch/image:latest")
    assert rc != 0
    assert out.strip() == "", f"a failed resolution still printed {out!r}"
    assert "nosuch/image:latest" in err, err


@pytest.mark.parametrize("name", onedoor.DRIVER_NAMES)
@pytest.mark.parametrize(
    "image",
    [onedoor.LCP_TAG, onedoor.VLLM_TAG, None],
    ids=["registry-tag", "pinned-tag", "unset-so-the-default"],
)
def test_every_driver_refuses_a_non_digest_image_before_touching_docker(
    tmp_path: Path, name: str, image: str | None
) -> None:
    stubs = tmp_path / "stubs"
    extra = {"RUN_ID": f"{onedoor.RUN_DATE}-alpha-probe"}
    if image is not None:
        extra[onedoor.DRIVER_IMG_VAR[name]] = image
    env = onedoor.bare_env(stubs, **extra)
    result = onedoor.driver(name, env, door=onedoor.fake_door(tmp_path))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "digest" in result.stderr, f"the refusal does not say why: {result.stderr}"
    assert onedoor.docker_log(stubs) == [], (
        "the driver reached docker before refusing the image"
    )


@pytest.mark.parametrize("name", ["lcp_sweep.py", "vllm_sweep.py"])
def test_a_digest_is_accepted_and_the_driver_goes_on_to_docker(
    tmp_path: Path, name: str
) -> None:
    """The control for the test above: with a digest the same driver does
    reach the ``docker`` on PATH. Its container never comes up, so it records
    one refusal and returns; ``vllm_cores.py`` waits on nvidia-smi between
    launches and is not driven this far off-rig."""
    stubs = tmp_path / "stubs"
    digest = onedoor.LCP_DIGEST if name == "lcp_sweep.py" else onedoor.VLLM_DIGEST
    env = onedoor.bare_env(
        stubs,
        RUN_ID=f"{onedoor.RUN_DATE}-alpha-probe",
        **{onedoor.DRIVER_IMG_VAR[name]: digest},
    )
    result = onedoor.driver(name, env, door=onedoor.fake_door(tmp_path))
    log = onedoor.docker_log(stubs)
    assert any(line.startswith("run ") for line in log), (
        f"no `docker run` reached the stub: rc={result.returncode} "
        f"log={log} stderr={result.stderr}"
    )
    assert any(f"@sha256:{onedoor.REPO_DIGEST_HEX}" in line for line in log), (
        f"the digest is not what docker was asked to run: {log}"
    )
