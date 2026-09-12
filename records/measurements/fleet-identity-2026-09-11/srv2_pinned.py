#!/usr/bin/env python3
"""M6 and M7 on srv2: pinned KV, contexts, a proposed pair of shares, both start orders.

Stage A — each unit alone, pinned at today's first-start KV, `VLLM_LOGGING_LEVEL=DEBUG`
  so the init snapshot is logged (in GiB, 2 dp). Two cold starts each, then a saturating
  load: 8 streams of ~3,000 prompt and 1,000 output tokens. Reads the context
  (`cuda_memory` at the init snapshot at the upper edge of its rounding, less what was on the card idle) and the peak
  process memory, whose excess over context and KV is the non-KV peak `P`.
Stage B — the proposal, by the plan's sizing rule, written to `proposal.json`.
Stage C — the pair at the proposed shares and KV, 3B-first and 7B-first, two cold starts
  each. The second unit starts while the first serves a load. On the first start of
  each order, the second unit is then killed so docker restarts it.
Stage D — M6's oversized values and the start gate.

Raw rows go to `raw-srv2-pinned.json`.
"""

from __future__ import annotations

import copy
import json
import math
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

import yaml

import arms
import rig

HOST = "srv2"
OUT = rig.SCR / "raw-srv2-pinned.json"
MIB = 1 << 20
GIB = 1 << 30
S3 = "Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001"
S7 = "Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002"
CONTAINER = {S3: f"mcgyvr-srv2-{S3}", S7: f"mcgyvr-srv2-{S7}"}
MODEL = {S3: "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", S7: "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"}
PORT = {S3: 8001, S7: 8002}
#: 2 x layers x kv_heads x head_dim x 2 bytes (fp16): 3B 36 layers, 2 heads; 7B 28, 4.
BYTES_PER_TOKEN = {S3: 36_864, S7: 57_344}
BLOCK = 16
STAGE_A_TOKENS = {S3: 12_352, S7: 8_592}
MAX_TOKENS_PER_UNIT = 8 * 4096
MARGIN = 64 * MIB
PAIR = rig.SCR / "compose.srv2-pair-as-run.yml"


def rows() -> list[dict[str, Any]]:
    return json.loads(OUT.read_text()) if OUT.exists() else []


def done(kind: str, label: str) -> bool:
    return any(r["kind"] == kind and r["label"] == label and not r.get("failed") for r in rows())


# --- composes ---------------------------------------------------------------


def block(service: str, *, tokens_bytes: int, share: float | None = None,
          restart: str | None = None) -> dict[str, Any]:
    doc = yaml.safe_load(PAIR.read_text())
    out = copy.deepcopy(doc["services"][service])
    out.pop("depends_on", None)
    cmd = out["command"]
    if share is not None:
        cmd[cmd.index("--gpu-memory-utilization") + 1] = f"{share:.2f}"
    cmd += ["--kv-cache-memory-bytes", str(tokens_bytes)]
    out["environment"] = {**out["environment"], "VLLM_LOGGING_LEVEL": "DEBUG"}
    port = PORT[service]
    out["healthcheck"] = {
        "interval": "5s", "retries": 3, "start_period": "600s", "timeout": "3s",
        "test": ["CMD-SHELL", f"curl -sf http://localhost:{port}/v1/models >/dev/null 2>&1 || "
                              f"wget -q -O- http://localhost:{port}/v1/models >/dev/null 2>&1"],
    }
    if restart:
        out["restart"] = restart
    return out


def write(name: str, services: dict[str, dict[str, Any]]) -> Path:
    path = rig.SCR / name
    path.write_text(yaml.safe_dump({"services": services}, sort_keys=False))
    return path


# --- load -------------------------------------------------------------------

_PROMPTS: dict[str, str] = {}


def long_prompt(service: str, i: int) -> str:
    """~2,950 prompt tokens, unique from the first token so no prefix is shared."""
    if service not in _PROMPTS:
        line = "value_{n} = transform(value_{m}, weight={n}, bias={m})\n"
        probe = "".join(line.format(n=n, m=n + 1) for n in range(100))
        code, body = rig.http_post(HOST, PORT[service], "/tokenize",
                                   {"model": MODEL[service], "prompt": probe})
        per_line = json.loads(body)["count"] / 100 if code == "200" else 16.0
        n_lines = int(2950 / per_line)
        _PROMPTS[service] = "".join(line.format(n=n, m=n + 1) for n in range(n_lines))
    return f"Request {i}: summarise what this code computes.\n" + _PROMPTS[service]


def one_request(service: str, i: int) -> None:
    body = {"model": MODEL[service], "temperature": 0, "ignore_eos": True, "max_tokens": 1000,
            "messages": [{"role": "user", "content": long_prompt(service, i)}]}
    rig.http_post(HOST, PORT[service], "/v1/chat/completions", body, timeout=900)


def saturate(services: list[str]) -> None:
    threads = [threading.Thread(target=one_request, args=(s, 1000 * k + i))
               for k, s in enumerate(services) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


class LoadLoop:
    """Keeps 8 requests in flight on one unit until stopped."""

    def __init__(self, service: str) -> None:
        self.service = service
        self.stop = threading.Event()
        self.sent = 0
        self.threads = [threading.Thread(target=self._run, args=(k,), daemon=True) for k in range(8)]

    def _run(self, k: int) -> None:
        i = 0
        while not self.stop.is_set():
            self.sent += 1
            one_request(self.service, 50_000 + k * 1000 + i)
            i += 1

    def start(self) -> None:
        for t in self.threads:
            t.start()


def pids(container: str) -> set[str]:
    return set(rig.rig(HOST, f"docker top {container} -eo pid | tail -n +2").split())


def peak_per_container(samples: list[dict[str, Any]], containers: list[str]) -> dict[str, int]:
    owned = {c: pids(c) for c in containers}
    return {c: max((sum(mib for pid, mib in s["apps_mib"].items() if pid in owned[c]) for s in samples), default=0)
            for c in containers}


def snapshot_gib(log: str) -> dict[str, float] | None:
    """The DEBUG init snapshot (`gpu_worker.py:390`), which vLLM prints in GiB to 2 dp."""
    m = re.search(r"worker init memory snapshot: (.*)", log)
    if not m:
        return None
    got = {k: float(v) for k, v in re.findall(r"(\w+_memory)=([\d.]+)GiB", m.group(1))}
    return got or None


def first_reading_mib(label: str, container: str) -> int | None:
    """The container's first per-process card reading in the load sampler: the CUDA
    context before any weight is on the card, at 1 MiB resolution."""
    owned = pids(container)
    for s in json.loads((rig.LOGS / f"sample-{label}-load.json").read_text()):
        got = [mib for pid, mib in s["apps_mib"].items() if pid in owned]
        if got:
            return sum(got)
    return None


# --- stages -----------------------------------------------------------------


def stage_a() -> None:
    for service in (S3, S7):
        for i in (1, 2):
            label = f"pin-solo-{service[:30]}-{i}"
            if done("solo", label):
                continue
            k = STAGE_A_TOKENS[service] * BYTES_PER_TOKEN[service]
            compose = write(f"compose.srv2-pinned-solo-{'3b' if service == S3 else '7b'}.yml",
                            {service: block(service, tokens_bytes=k)})
            print(f"\n=== {label}", flush=True)
            rig.teardown(HOST)
            idle = arms._idle(HOST)
            up = arms.start(HOST, compose, label)
            try:
                readings = arms.unit_readings(HOST, up, idle["clock_offset_s"], label)
                c = CONTAINER[service]
                log = (rig.LOGS / f"{label}-{service}.log").read_text()
                snap = snapshot_gib(log)
                first = first_reading_mib(label, c) if up["door_rc"] == 0 else None
                row: dict[str, Any] = {"kind": "solo", "label": label, "service": service, "unit": MODEL[service],
                                       "kv_cache_memory_bytes": k, "idle": idle, "up": up, "per_unit": readings,
                                       "snapshot_gib": snap, "first_process_reading_mib": first}
                if up["door_rc"] != 0 or snap is None:
                    row["failed"] = f"door rc={up['door_rc']} snapshot={snap is not None} first={first}"
                    arms.append(OUT, row)
                    continue
                rig.sample_start(HOST)
                saturate([service])
                samples = rig.sample_stop(HOST, f"{label}-saturate")
                peak = peak_per_container(samples, [c])[c]
                # The context is what the device held at the init snapshot, less what was on
                # the card idle. vLLM prints it to 2 dp of GiB, so the upper edge of that
                # rounding (+0.005 GiB) is taken: the rule may over-reserve, never under.
                ctx = math.ceil((snap["cuda_memory"] + 0.005) * GIB) - idle["gpu"]["used"] * MIB
                # torch's total is the card less its reserve; the snapshot's 2 dp GiB must agree.
                total = (idle["gpu"]["total"] - idle["gpu"]["reserved"]) * MIB
                row.update(snapshot_agrees=abs(total / GIB - snap["total_memory"]) <= 0.005)
                row.update(context_bytes=ctx, total_bytes=total, peak_process_mib=peak,
                           non_kv_peak_bytes=peak * MIB - ctx - k, restart_count=rig.restarts(HOST, c))
                arms.append(OUT, row)
                print(f"    ctx {ctx / MIB:.0f} MiB  peak {peak} MiB  P {(peak * MIB - ctx - k) / MIB:.0f} MiB  "
                      f"kv {readings[c]['kv_tokens']}", flush=True)
            finally:
                rig.teardown(HOST)


def stage_b() -> dict[str, Any]:
    path = rig.SCR / "proposal.json"
    if path.exists():
        return json.loads(path.read_text())
    solo = [r for r in rows() if r["kind"] == "solo" and not r.get("failed")]
    total = max(r["total_bytes"] for r in solo)
    ctx = {s: max(r["context_bytes"] for r in solo if r["service"] == s) for s in (S3, S7)}
    nonkv = {s: max(r["non_kv_peak_bytes"] for r in solo if r["service"] == s) for s in (S3, S7)}
    tokens = MAX_TOKENS_PER_UNIT // BLOCK * BLOCK
    while tokens > 0:
        kv = {s: tokens * BYTES_PER_TOKEN[s] for s in (S3, S7)}
        need = sum(nonkv[s] + kv[s] + MARGIN for s in (S3, S7)) + sum(ctx.values())
        shares = {s: math.ceil((nonkv[s] + kv[s] + MARGIN) / total * 100) / 100 for s in (S3, S7)}
        rooms = {s: math.ceil(shares[s] * total) for s in (S3, S7)}
        if need <= total and sum(rooms.values()) + sum(ctx.values()) <= total:
            break
        tokens -= BLOCK
    proposal = {"rule": "records/plans/fleet-identity-measurements-2026-09-11.md M7 sizing rule",
                "torch_total_bytes": total, "contexts_bytes": {MODEL[s]: ctx[s] for s in ctx},
                "non_kv_peak_bytes": {MODEL[s]: nonkv[s] for s in nonkv}, "tokens_per_unit": tokens,
                "kv_cache_memory_bytes": {MODEL[s]: kv[s] for s in kv},
                "shares": {MODEL[s]: shares[s] for s in shares},
                "rooms_bytes": {MODEL[s]: rooms[s] for s in rooms},
                "margin_bytes": MARGIN, "today_shares": {MODEL[S3]: 0.26, MODEL[S7]: 0.72}}
    path.write_text(json.dumps(proposal, indent=1))
    print(json.dumps(proposal, indent=1), flush=True)
    return proposal


def order_compose(first: str, proposal: dict[str, Any]) -> Path:
    second = S7 if first == S3 else S3
    services = {}
    for s in (first, second):
        services[s] = block(s, tokens_bytes=proposal["kv_cache_memory_bytes"][MODEL[s]],
                            share=proposal["shares"][MODEL[s]])
    services[second]["depends_on"] = {first: {"condition": "service_healthy"}}
    name = "3b-first" if first == S3 else "7b-first"
    return write(f"compose.srv2-pinned-{name}.yml", services)


def last_kv(log: str) -> tuple[int | None, str | None]:
    toks = arms.KV_TOKENS.findall(log)
    lines = arms.INIT_FREE.findall(log)
    line = re.findall(r"Initial free memory [\d.]+ GiB, reserved [\d.]+ GiB memory for KV Cache", log)
    return (int(toks[-1].replace(",", "")) if toks else None, line[-1] if line else None)


def stage_c(proposal: dict[str, Any]) -> None:
    for first in (S3, S7):
        second = S7 if first == S3 else S3
        order = "3b_first" if first == S3 else "7b_first"
        compose = order_compose(first, proposal)
        for k in (1, 2):
            label = f"pin-{order}-{k}"
            if done("order", label):
                continue
            print(f"\n=== {label}", flush=True)
            rig.teardown(HOST)
            idle = arms._idle(HOST)
            rig.sample_start(HOST)
            result: dict[str, Any] = {}
            loop = LoadLoop(first)
            with rig.ReadyPoller(HOST, {CONTAINER[s]: PORT[s] for s in (S3, S7)}) as poller:
                door = threading.Thread(target=lambda: result.update(
                    zip(("proc", "door_s", "envelope"), rig.door("up", HOST, compose, f"{label}-up"))))
                door.start()
                while CONTAINER[first] not in poller.ready and door.is_alive():
                    time.sleep(0.2)
                if CONTAINER[first] in poller.ready:
                    loop.start()
                while CONTAINER[second] not in poller.ready and door.is_alive():
                    time.sleep(0.2)
                loop.stop.set()
                door.join()
            rig.note_up(HOST, compose)
            rig.sample_stop(HOST, f"{label}-load")
            up = {"door_rc": result["proc"].returncode, "door_process_s": result["door_s"],
                  "envelope": result["envelope"], "ready_local": dict(poller.ready),
                  "units": arms.services(compose)}
            try:
                readings = arms.unit_readings(HOST, up, idle["clock_offset_s"], label)
                row: dict[str, Any] = {"kind": "order", "label": label, "order": order, "start": k,
                                       "idle": idle, "door_rc": up["door_rc"], "per_unit": readings,
                                       "neighbour_requests_sent": loop.sent}
                if up["door_rc"] != 0:
                    row["failed"] = f"door rc={up['door_rc']}"
                    arms.append(OUT, row)
                    continue
                rig.sample_start(HOST)
                saturate([S3, S7])
                samples = rig.sample_stop(HOST, f"{label}-saturate")
                peaks = peak_per_container(samples, [CONTAINER[S3], CONTAINER[S7]])
                row["units"] = {MODEL[s]: {
                    "healthy": readings[CONTAINER[s]]["healthy"],
                    "restart_count": rig.restarts(HOST, CONTAINER[s]),
                    "kv_cache_memory_bytes": proposal["kv_cache_memory_bytes"][MODEL[s]],
                    "kv_tokens": readings[CONTAINER[s]]["kv_tokens"],
                    "kv_line": readings[CONTAINER[s]]["kv_line"],
                    "peak_process_mib": peaks[CONTAINER[s]]} for s in (S3, S7)}
                arms.append(OUT, row)
                print(f"    {json.dumps({m: {k2: v for k2, v in u.items() if k2 != 'kv_line'} for m, u in row['units'].items()})}",
                      flush=True)
                if k == 1:
                    for s, case in ((first, "first_start"), (second, "neighbour_active")):
                        u = row["units"][MODEL[s]]
                        arms.append(OUT, {"kind": "pinned_case", "label": f"{label}-{case}", "case": case,
                                          "unit": MODEL[s], "kv_cache_memory_bytes": u["kv_cache_memory_bytes"],
                                          "kv_tokens": u["kv_tokens"], "kv_line": u["kv_line"],
                                          "restart_count": u["restart_count"],
                                          "neighbour_under_load": case == "neighbour_active" and loop.sent > 0})
                    restart_case(second, proposal, label)
            finally:
                rig.teardown(HOST)


def restart_case(service: str, proposal: dict[str, Any], label: str) -> None:
    c = CONTAINER[service]
    pid = rig.inspect(HOST, c, ".State.Pid").strip()
    rig.rig_or_die(HOST, f"sudo -n kill -9 {pid}")
    deadline = time.time() + 420
    while time.time() < deadline:
        if rig.restarts(HOST, c) >= 1:
            code, _ = rig.http_get(HOST, PORT[service], "/v1/models")
            if code == "200":
                break
        time.sleep(2)
    log = rig.engine_log(HOST, c, f"{label}-restart-{service}")
    tokens, line = last_kv(log)
    arms.append(OUT, {"kind": "pinned_case", "label": f"{label}-restart", "case": "restart",
                      "unit": MODEL[service],
                      "kv_cache_memory_bytes": proposal["kv_cache_memory_bytes"][MODEL[service]],
                      "kv_tokens": tokens, "kv_line": line, "restart_count": rig.restarts(HOST, c),
                      "killed_pid": pid})
    print(f"    restart {service}: kv {tokens} restarts {rig.restarts(HOST, c)}", flush=True)


def outcome_row(label: str, case: str, compose: Path, service: str, extra: dict[str, Any]) -> None:
    if done("pinned_case", label):
        return
    print(f"\n=== {label}", flush=True)
    rig.teardown(HOST)
    idle = arms._idle(HOST)
    up = arms.start(HOST, compose, label)
    try:
        readings = arms.unit_readings(HOST, up, idle["clock_offset_s"], label)
        r = readings[CONTAINER[service]]
        log = (rig.LOGS / f"{label}-{service}.log").read_text()
        snap = snapshot_gib(log)
        served = bool(r["healthy"])
        row = {"kind": "pinned_case", "label": label, "case": case, "unit": MODEL[service],
               "outcome": "served" if served else "failed_at_start", "kv_tokens": r["kv_tokens"],
               "kv_line": r["kv_line"], "restart_count": r["restart_count"],
               "free_at_start_bytes": int(snap["free_memory"] * GIB) if snap else None,
               "error_line": r["start_gate_line"] or r["oom_line"] or _last_error(log), **extra}
        if served:
            rig.sample_start(HOST)
            saturate([service])
            samples = rig.sample_stop(HOST, f"{label}-saturate")
            row["peak_process_mib"] = peak_per_container(samples, [CONTAINER[service]])[CONTAINER[service]]
        arms.append(OUT, row)
        print(f"    {case}: {row['outcome']} kv {row['kv_tokens']} err {str(row['error_line'])[:200]}", flush=True)
    finally:
        rig.teardown(HOST)


def _last_error(log: str) -> str | None:
    errs = [line for line in log.splitlines() if re.search(r"Error|error:|Traceback", line)]
    return errs[-1] if errs else None


def stage_d(proposal: dict[str, Any]) -> None:
    total = proposal["torch_total_bytes"]
    m7 = MODEL[S7]
    share = proposal["shares"][m7]
    room = math.ceil(share * total)
    nonkv = proposal["non_kv_peak_bytes"][m7]
    ctx = proposal["contexts_bytes"][m7]
    # Above the room by 1 GiB, but inside what the card holds with 256 MiB spare.
    over = min(room - nonkv + GIB, total - ctx - nonkv - 256 * MIB)
    over = over // (BYTES_PER_TOKEN[S7] * BLOCK) * BYTES_PER_TOKEN[S7] * BLOCK
    compose = write("compose.srv2-pinned-oversized-share.yml",
                    {S7: block(S7, tokens_bytes=over, share=share, restart="no")})
    outcome_row("pin-oversized-share", "oversized_share", compose, S7,
                {"kv_cache_memory_bytes": over, "room_bytes": room, "share": share})

    beyond = (total // (BYTES_PER_TOKEN[S7] * BLOCK)) * BYTES_PER_TOKEN[S7] * BLOCK
    compose = write("compose.srv2-pinned-oversized-card.yml",
                    {S7: block(S7, tokens_bytes=beyond, share=share, restart="no")})
    outcome_row("pin-oversized-card", "oversized_card", compose, S7,
                {"kv_cache_memory_bytes": beyond, "room_bytes": room, "share": share})

    gate = {S3: block(S3, tokens_bytes=proposal["kv_cache_memory_bytes"][MODEL[S3]],
                      share=proposal["shares"][MODEL[S3]]),
            S7: block(S7, tokens_bytes=proposal["kv_cache_memory_bytes"][m7], share=0.90, restart="no")}
    gate[S7]["depends_on"] = {S3: {"condition": "service_healthy"}}
    compose = write("compose.srv2-pinned-start-gate.yml", gate)
    outcome_row("pin-start-gate", "start_gate", compose, S7,
                {"kv_cache_memory_bytes": proposal["kv_cache_memory_bytes"][m7], "share": 0.90,
                 "neighbour": MODEL[S3]})


def main() -> None:
    stages = sys.argv[1:] or ["a", "b", "c", "d"]
    if "a" in stages:
        stage_a()
    proposal = stage_b() if {"b", "c", "d"} & set(stages) else None
    if "c" in stages and proposal:
        stage_c(proposal)
    if "d" in stages and proposal:
        stage_d(proposal)


if __name__ == "__main__":
    main()
