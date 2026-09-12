#!/usr/bin/env python3
"""Fleet-identity PREFILL measurement — no-NVMe prefill rate per unit x rig.

Protocol mirrors M1 (`README.md`): 3 cold starts per unit, swap OFF and
`--load-mode none` (llama.cpp) / GPU-resident (vLLM), page cache dropped before
each arm, one discarded warm-up then 5 prefill samples. Raw rows go to
`raw-prefill.json`; the runner is resumable (a label already present without a
`failed` key is skipped).

Usage:
    cd records/measurements/fleet-identity-2026-09-11
    ../../.venv/bin/python prefill.py            # everything
    ../../.venv/bin/python prefill.py s1-ling    # only arms whose label starts with s1-ling
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import arms
import rig

OUT = rig.SCR / "raw-prefill.json"
SAMPLES = 5
STARTS = 3

QWEN36 = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
LING = "Ling-3.0-tiny-Q4_K_M"
CODER_3B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
CODER_7B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"

# ~2k tokens of code: the long prompt from measuring-gaps-2026-09-10, so the
# prefill rate is a real prefill and not a short-prompt artifact.
PREFILL_TEXT = (
    "def merge(a, b):\n"
    "    out = []\n"
    "    i = j = 0\n"
    "    while i < len(a) and j < len(b):\n"
    "        if a[i] <= b[j]:\n"
    "            out.append(a[i]); i += 1\n"
    "        else:\n"
    "            out.append(b[j]); j += 1\n"
    "    return out + a[i:] + b[j:]\n\n"
) * 30 + "# Explain the function above.\n"


def _body(model: str | None, stream: bool) -> str:
    body: dict[str, Any] = {"messages": [{"role": "user", "content": PREFILL_TEXT}],
                            "max_tokens": 8, "temperature": 0}
    if model:
        body["model"] = model
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return json.dumps(body)


def prefill_llamacpp(host: str, port: int) -> dict[str, Any] | None:
    proc = rig.sh(["curl", "-s", "-m", "900", f"http://{host}:{port}/v1/chat/completions",
                   "-H", "Content-Type: application/json", "-d", _body(None, False)],
                  timeout=960)
    try:
        t = json.loads(proc.stdout)["timings"]
        return {"prompt_n": int(t["prompt_n"]), "tok_s": float(t["prompt_per_second"])}
    except (ValueError, KeyError, TypeError):
        (rig.LOGS / "prefill-unparsed.txt").open("a").write(proc.stdout[-2000:] + "\n")
        return None


def prefill_vllm(host: str, port: int, model: str) -> dict[str, Any] | None:
    """Time-to-first-token over a streamed reply; prefill rate = prompt_n / ttft."""
    proc = subprocess.Popen(
        ["curl", "-sN", "-m", "600", f"http://{host}:{port}/v1/chat/completions",
         "-H", "Content-Type: application/json", "-d", _body(model, True)],
        stdout=subprocess.PIPE, text=True)
    t0 = time.time()
    first = None
    usage = None
    assert proc.stdout is not None
    for line in proc.stdout:
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except ValueError:
            continue
        if obj.get("usage"):
            usage = obj["usage"]
        for choice in obj.get("choices") or []:
            if (choice.get("delta") or {}).get("content"):
                first = first or time.time()
    proc.wait(timeout=30)
    if not usage or first is None:
        return None
    prompt_n = int(usage["prompt_tokens"])
    ttft = first - t0
    return {"prompt_n": prompt_n, "ttft_s": round(ttft, 3), "tok_s": prompt_n / ttft}


def warm_prefill(fn, *args: Any) -> tuple[list[dict[str, Any]], int]:
    """One discarded warm-up, then SAMPLES prefill samples."""
    fn(*args)
    got: list[dict[str, Any]] = []
    for _ in range(SAMPLES + 3):
        s = fn(*args)
        if s:
            got.append(s)
        if len(got) == SAMPLES:
            break
    if len(got) < SAMPLES:
        raise SystemExit(f"only {len(got)} prefill samples of {SAMPLES}")
    return got, 1


def done() -> set[str]:
    if not OUT.exists():
        return set()
    return {r["label"] for r in json.loads(OUT.read_text()) if not r.get("failed")}


def append(row: dict[str, Any]) -> None:
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    rows.append(row)
    OUT.write_text(json.dumps(rows, indent=1))


def llama_arm(host: str, label: str, compose: Path, unit: str, cls: str) -> dict[str, Any]:
    print(f"\n=== {label}  {unit}  swap=off (no-NVMe)", flush=True)
    base = {"label": label, "rig": host, "unit": unit, "class": cls, "engine": "llamacpp",
            "compose": compose.name, "swap": "off", "t": time.time()}
    rig.teardown(host)
    try:
        rig.swapoff(host)
        idle = arms._idle(host)
        up = arms.start(host, compose, label)
        if up["door_rc"] != 0:
            append({**base, "failed": f"door up rc={up['door_rc']}"})
            raise SystemExit(f"{label}: door up rc={up['door_rc']}")
        readings = arms.unit_readings(host, up, idle["clock_offset_s"], label)
        port = up["units"][0]["port"]
        samples, discarded = warm_prefill(prefill_llamacpp, host, port)
        container = up["units"][0]["container"]
        row = {**base, "idle": idle, "up_gpu": rig.gpu(host), "per_unit": readings,
               "samples": samples, "warmup_discarded": discarded,
               "restart_count_after_prefill": rig.restarts(host, container)}
        append(row)
        rates = [round(s["tok_s"], 1) for s in samples]
        print(f"    prefill {rates} tok/s  prompt_n {samples[0]['prompt_n']}  "
              f"restarts {readings[container]['restart_count']}", flush=True)
        return row
    finally:
        arms.teardown_and_restore(host, "off")


def vllm_arm(host: str, label: str, compose: Path) -> dict[str, Any] | None:
    print(f"\n=== {label}  pair  swap=off (no-NVMe)", flush=True)
    base = {"label": label, "rig": host, "engine": "vllm", "compose": compose.name,
            "swap": "off", "t": time.time()}
    rig.teardown(host)
    try:
        rig.swapoff(host)
        idle = arms._idle(host)
        up = arms.start(host, compose, label)
        readings = arms.unit_readings(host, up, idle["clock_offset_s"], label)
        if up["door_rc"] != 0:
            append({**base, "failed": f"door up rc={up['door_rc']}", "per_unit": readings})
            print(f"    door up rc={up['door_rc']}", flush=True)
            return None
        prefills: dict[str, Any] = {}
        for u in up["units"]:
            samples, discarded = warm_prefill(prefill_vllm, host, u["port"], u["model"])
            prefills[u["container"]] = {"samples": samples, "warmup_discarded": discarded}
        row = {**base, "idle": idle, "up_gpu": rig.gpu(host), "per_unit": readings, "prefill": prefills,
               "restart_count_after_prefill": {
                   u["container"]: rig.restarts(host, u["container"]) for u in up["units"]}}
        append(row)
        for c, p in prefills.items():
            rates = [round(s["tok_s"], 1) for s in p["samples"]]
            print(f"    {c}: prefill {rates} tok/s", flush=True)
        return row
    finally:
        arms.teardown_and_restore(host, "off")


def main() -> None:
    only = set(sys.argv[1:])
    finished = done()

    for i in range(1, STARTS + 1):
        label = f"s1-qwen36-prefill-{i}"
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        try:
            llama_arm("srv1", label, rig.SCR / "compose.srv1-qwen36-unmapped.yml", QWEN36, "cpu_experts")
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)

    for i in range(1, STARTS + 1):
        label = f"s1-ling-prefill-{i}"
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        try:
            llama_arm("srv1", label, rig.SCR / "compose.srv1-ling-unmapped.yml", LING, "llamacpp")
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)

    for i in range(1, STARTS + 1):
        label = f"s2-pair-prefill-{i}"
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        try:
            vllm_arm("srv2", label, rig.SCR / "compose.srv2-pair-as-run.yml")
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)

    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
