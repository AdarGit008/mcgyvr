"""Gate 3 reads ``RepoDigests`` then ``Id`` — fields, not the first digest-like string.

``docker image inspect`` prints ``RepoDigests`` and, further down,
``Config.Labels``. ``1-build-ladder.sh`` labels every rung
``org.mcgyvr.build.toolkit=$RUN_CUDA_DEVEL``, and every rung reaches srv1 by
``docker save | docker load``, so its ``RepoDigests`` is ``[]``. Pin the
toolkit by digest — the natural reproducibility move — and a resolver that
greps the whole document for the first ``@sha256:`` hands the driver
``nvidia/cuda@sha256:…``: it runs the CUDA base image instead of the rung,
the container dies, and a REFUSED row is filed against the arm for what was a
resolution bug.

So ``image_digest`` parses the document and answers ``RepoDigests[0]`` if
there is one, else ``Id``. Seam: ``RUN_DOCKER``, printing the real shape.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor


def test_a_local_build_labelled_with_a_digest_resolves_to_its_own_id(
    tmp_path: Path,
) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.bare_env(stubs, RUN_REPO=str(onedoor.REPO))
    result = onedoor.bash(
        f"set -euo pipefail\n. '{onedoor.COMMON_SH}'\n"
        f"image_digest '{onedoor.LOCAL_TAG}'\n",
        env,
        onedoor.REPO,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"sha256:{onedoor.LOCAL_ID_HEX}", (
        f"resolved to {result.stdout.strip()!r}: a label value, not the image"
    )
    assert onedoor.TOOLKIT_DIGEST not in result.stdout
