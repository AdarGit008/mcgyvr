#!/usr/bin/env python3
"""Write every fixed compose this run launches, beside this script.

The as-run composes are the live fleet's own files, copied byte for byte from
`~/.mcgyvr/config/`. Every other compose is one of those, or an earlier campaign's,
with the named flags added or removed and nothing else changed. The M7 pair composes
depend on the solo measurements, so `srv2_pinned.py` writes those.
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import yaml

SCR = Path(__file__).resolve().parent
LIVE = Path.home() / ".mcgyvr" / "config"
REPO = SCR.parents[2]


def load(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def dump(doc: dict[str, Any], name: str) -> None:
    (SCR / name).write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def with_args(doc: dict[str, Any], *extra: str, drop: tuple[str, ...] = ()) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    for block in out["services"].values():
        block["command"] = [a for a in block["command"] if a not in drop] + list(extra)
    return out


def only(doc: dict[str, Any], service: str) -> dict[str, Any]:
    block = copy.deepcopy(doc["services"][service])
    block.pop("depends_on", None)
    return {"services": {service: block}}


def main() -> None:
    shutil.copyfile(LIVE / "compose.srv1.yml", SCR / "compose.srv1-qwen36-as-run.yml")
    shutil.copyfile(LIVE / "compose.srv2.yml", SCR / "compose.srv2-pair-as-run.yml")
    shutil.copyfile(
        REPO / "records/measurements/flexibility-2026-09-09/compose.srv1-vllm-3b.yml",
        SCR / "compose.srv1-3b-vllm.yml",
    )

    qwen = load(SCR / "compose.srv1-qwen36-as-run.yml")
    dump(with_args(qwen, "--load-mode", "none"), "compose.srv1-qwen36-unmapped.yml")
    q32 = with_args(qwen, "--load-mode", "none")
    for block in q32["services"].values():
        cmd = block["command"]
        cmd[cmd.index("--n-cpu-moe") + 1] = "32"
    dump(q32, "compose.srv1-qwen36-unmapped-n32.yml")
    dump(with_args(qwen, "--verbose"), "compose.srv1-qwen36-verbose.yml")

    ling = with_args(
        load(REPO / "records/measurements/measuring-gaps-2026-09-10/compose.srv1-q5-ling.yml"),
        "--n-cpu-moe", "0", drop=("--verbose",),
    )
    dump(ling, "compose.srv1-ling-as-run.yml")
    dump(with_args(ling, "--load-mode", "none"), "compose.srv1-ling-unmapped.yml")
    l4 = with_args(ling, "--load-mode", "none")
    for block in l4["services"].values():
        cmd = block["command"]
        cmd[cmd.index("--n-cpu-moe") + 1] = "4"
    dump(l4, "compose.srv1-ling-unmapped-n4.yml")

    pair = load(SCR / "compose.srv2-pair-as-run.yml")
    s3b = "Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001"
    s7b = "Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002"
    dump(only(pair, s3b), "compose.srv2-3b-alone.yml")
    dump(only(pair, s7b), "compose.srv2-7b-alone.yml")
    dump(with_args(only(pair, s7b), "--kv-cache-dtype", "fp8"), "compose.srv2-7b-fp8.yml")


if __name__ == "__main__":
    main()
