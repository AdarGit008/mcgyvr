"""Build a throwaway config for one (host, blob) pair and let `emit` size it.

The wake-rate points this campaign adds must be placed the way the fleet's own
points were placed — by `fit`, from the tensor table — and not by a number
somebody typed into a compose file. So each new blob gets a one-tier config
whose only model is that blob, `emit` writes the compose, and the door runs
what `emit` wrote.

Every new llama.cpp arm is held at **4096 per slot over 2 slots**, so window is
constant across the blobs being compared. The fleet's existing Qwen3.6 point
was taken at 8192 per slot and its deepseek point at 4096; the window moves the
card split and therefore `--n-cpu-moe`, and the blob is read in full under mmap
either way, so this is stated rather than corrected for.

Usage: `uv run --no-sync python make_config.py <host> <blob-stem> [ctx] [slots]`
Writes `<scratch>/emit/<host>-<stem>/` and prints the compose path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

SCR = Path(__file__).resolve().parent
OUT = SCR / "emit"
SCANNER = Path("/home/adaramir/claude/mcgyvr/src/mcgyvr/serving/ggufscan.py")
PORTS = {"srv1": 8080, "srv2": 8080}
IMAGE = "llamacpp:b10644-L3"


def geometry(host: str, stem: str, into: Path) -> Path:
    blob = f"/home/adaramir/models/moe/{stem}.gguf"
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, f"python3 - {blob}"],
        stdin=SCANNER.open("rb"), capture_output=True, text=True, timeout=600,
    )
    rows = json.loads(proc.stdout)
    if not rows or "error" in rows[0]:
        raise SystemExit(f"{host}:{stem}: ggufscan failed: {proc.stdout[:400]}")
    path = into / f"{stem}.geometry.json"
    path.write_text(json.dumps(rows, indent=2))
    return path


def build(host: str, stem: str, ctx: int = 4096, slots: int = 2) -> Path:
    into = OUT / f"{host}-{stem}"
    into.mkdir(parents=True, exist_ok=True)
    geom = geometry(host, stem, into)
    doc = {
        "version": 1,
        "sources": {
            f"{host}_llamacpp": {
                "base_url": f"http://{host}:{PORTS[host]}",
                "api": "openai",
                "image": IMAGE,
                "max_parallel": slots,
                "context_window": ctx,
            }
        },
        "models": {stem: {"geometry_json": f"./{geom.name}"}},
        "ladder": {
            "tiers": [
                {
                    "name": f"probe_{stem.lower()}",
                    "source": f"{host}_llamacpp",
                    "model": stem,
                    "max_parallel": slots,
                }
            ],
            "fanout": "idle",
        },
        "verifier": {"enabled": False},
        "sandbox": {"mode": "docker"},
        "delivery": {"mode": "branch"},
    }
    cfg = into / "mcgyvr.yaml"
    cfg.write_text(yaml.safe_dump(doc, sort_keys=False))
    proc = subprocess.run(
        ["uv", "run", "--no-sync", "python", "-m", "mcgyvr.cli", "emit",
         "--config", str(cfg), "--out", str(into)],
        capture_output=True, text=True, timeout=600,
        cwd="/home/adaramir/claude/mcgyvr",
    )
    (into / "emit.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"{host}:{stem}: emit refused it —\n{proc.stdout}\n{proc.stderr}")
    return into / f"compose.{host}.yml"


if __name__ == "__main__":
    host, stem = sys.argv[1], sys.argv[2]
    ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 4096
    slots = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    path = build(host, stem, ctx, slots)
    print(path)
    print(path.read_text())
