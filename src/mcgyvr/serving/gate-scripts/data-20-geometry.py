#!/usr/bin/env python3
"""The checkpoint's geometry, summed from its own tensor table on the rig.

BITS-PER-WEIGHT IS A GUESS; THE TENSOR TABLE IS NOT. Two defensible estimates
of one GGUF's expert bytes — nominal quant width, and file size over parameter
count — disagreed by 14% and both were wrong. Summing the table gave 278.0 MiB
of expert weight per layer against a measured VRAM delta of 278.0.

THE READER GOES TO THE RIG, THE BLOB NEVER COMES BACK. ggufscan reads headers
only, is piped over as `python3 -`, and nothing lands on the rig's disk. The
model file is where it is; a 13 GB blob is not copied to answer a question
about its header.

WHY IT IS NOT VENDORED HERE. `tools/bench/serving/ggufscan.py` is the one copy,
read by path. A second copy under this directory would be a second parser, and
the first thing a second parser does is disagree with the first about the file
a published measurement was computed from.
"""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from mcgyvr.serving.gatelib import export, need, refuse, root

SCANNER = Path("tools") / "bench" / "serving" / "ggufscan.py"

#: A model has TWO rig-side paths and they are not interchangeable. A step
#: launches a container with `-v $HOME/models:/models` and passes `-m
#: /models/moe/x.gguf`, so the container path is what a serve config names.
#: ggufscan runs on the HOST, outside any container, and needs the host path.
#: --model is given in the container form, because that is the one a caller
#: already has; the translation happens here, once, rather than in every
#: caller. A path that is not under the mount is passed through untouched, so a
#: blob somewhere else can still be read by naming it outright.
CONTAINER_MODELS = "/models"
HOST_MODELS = "$HOME/models"


def host_path(model: str) -> str:
    if model == CONTAINER_MODELS or model.startswith(CONTAINER_MODELS + "/"):
        return HOST_MODELS + model[len(CONTAINER_MODELS) :]
    return model


def main() -> int:
    source = root() / SCANNER
    if not source.is_file():
        refuse(
            f"the geometry reader {SCANNER} is missing. Nothing is sized from "
            "a file nobody read: bits-per-weight is a guess and the tensor "
            "table is not"
        )
    blob = base64.b64encode(source.read_bytes()).decode("ascii")
    model = need("RUN_MODEL")
    host = need("RUN_HOST")
    # `$HOME` is left for the remote shell to expand, so the door never has to
    # know the operator's home directory on the rig.
    remote = host_path(model)

    try:
        done = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                host,
                f"echo {blob} | base64 -d | python3 - {remote}",
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        refuse(f"the geometry read of {remote} on {host} did not finish in 600s")
        raise
    if done.returncode != 0:
        refuse(
            f"the geometry of {remote} could not be read on {host}: "
            f"{done.stderr.strip()[:400]}"
        )
    try:
        rows = json.loads(done.stdout)
    except json.JSONDecodeError as error:
        refuse(f"the geometry reader printed no JSON for {model}: {error}")
        raise
    if not rows:
        refuse(
            f"{remote} matched no file on {host}. --model is the CONTAINER "
            f"path ({CONTAINER_MODELS}/...), which is translated to "
            f"{HOST_MODELS}/... for the header read"
        )
    geometry = rows[0]
    if "error" in geometry:
        refuse(f"the geometry reader refused {model}: {geometry['error']}")

    out = Path(need("RUN_OUT_DIR")) / "geometry.json"
    out.write_text(
        json.dumps(geometry, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    export("RUN_GEOMETRY_JSON", out)
    print(
        f"data-20-geometry: {geometry.get('arch')} "
        f"n_layer={geometry.get('n_layer')} "
        f"placeable={len(geometry.get('placeable_blocks') or [])} "
        f"experts={int(geometry.get('bytes_experts') or 0) / 1024**2:.0f} MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
