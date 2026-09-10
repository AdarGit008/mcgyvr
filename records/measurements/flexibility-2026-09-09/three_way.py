"""Q16 — a card holding a sleeper *and* an awake unit, with a third unit placed
into what is left.

The state the whole campaign is named for and the one nobody has ever run:
`V_avail(h,S)` with a level-2 sleeper and a live co-resident on the card at
once. `emit` computes every placement against an **idle** card, so this is
exactly the case it cannot express, and the 80B's placement here is chosen from
`vramfit` against the card the sleeper actually left.

It is also where the freeze's third change earns its place: the sleep is issued
through `servelib.sleep`, which is the one function on this fleet through which
a sleep level may be spelled, and which refuses level 1.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

import rig
from mcgyvr.serving import servelib, vramfit

HOST = "srv2"
PAIR = str(Path(__file__).parent / "compose.srv2.sleepmode.yml")
PORTS = {"3b": 8001, "7b": 8002}
MIB = 1024 * 1024
CARD_CONSTANT_MIB = 2430  # measured in Q10, exact to 1 MiB over five placements
OUT = Path(__file__).parent / "results-q16-threeway.json"

GEOM = json.load(open(Path(__file__).parent.parent / "ram-headroom-2026-09-09/qwen80b.geometry.json"))
if isinstance(GEOM, list):
    GEOM = GEOM[0]


def teardown() -> None:
    running = rig.rig(HOST, "docker ps -a --format '{{.Names}}' | grep '^mcgyvr-' || true")
    if not running.strip():
        return
    index = json.loads((rig.SCR / "teardown-index.json").read_text())
    seen: list[str] = []
    for name in [n for n in running.split() if n]:
        compose = index.get(name)
        if compose and compose not in seen:
            seen.append(compose)
    for compose in seen:
        rig.door_or_die("down", HOST, compose, f"q16td-{int(time.time() * 10) % 10**9}")


def eighty_b_compose(ncmoe: int) -> str:
    return str(Path(__file__).parent / f"compose.srv2-80b-mapped-ncmoe{ncmoe}.yml")


def arm(asleep: str, awake: str, index: int) -> dict:
    label = f"q16-80b-with-{awake}-awake-{asleep}-asleep-{index}"
    print(f"\n=== {label}", flush=True)
    teardown()
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)

    rig.door_or_die("up", HOST, PAIR, f"{label}-pair")
    rig.note_up(HOST, PAIR)
    time.sleep(5)
    both_up = rig.gpu(HOST)
    print(f"    pair up: card {both_up['used']} used / {both_up['free']} free MiB", flush=True)

    # The ban fires BEFORE the transport, by design, so it is checkable from
    # here even though the transport is not: `servelib.ssh` refuses any process
    # the door did not start. That guard working is why the level-2 POST below
    # goes through the campaign's own ssh instead.
    banned = None
    try:
        servelib.sleep(HOST, PORTS[asleep], level=1)
    except servelib.SleepLevelError as exc:
        banned = str(exc)
    if banned is None:
        raise SystemExit("a level-1 sleep was NOT refused; the ban is not holding")
    print(f"    level-1 refused as designed: {banned[:70]}...", flush=True)

    code = rig.rig(
        HOST,
        "curl -s -o /dev/null -w '%{http_code}' -X POST "
        f"'http://localhost:{PORTS[asleep]}/sleep?level=2'",
    )
    ok = code.strip() == "200"
    time.sleep(3)
    left = rig.gpu(HOST)
    print(f"    {asleep} asleep (ok={ok}): card {left['used']} used / {left['free']} free MiB", flush=True)

    # Place the 80B into what the sleeper actually left, not into an idle card.
    ncmoe = vramfit.floor(GEOM, left["free"] * MIB, CARD_CONSTANT_MIB * MIB)
    if ncmoe is None:
        print("    no placement fits; recording the refusal", flush=True)
        return {"label": label, "asleep": asleep, "awake": awake,
                "card_free_with_sleeper_mib": left["free"], "ncmoe": None,
                "placed": False}
    predicted = vramfit.predict(GEOM, ncmoe, CARD_CONSTANT_MIB * MIB) / MIB
    print(f"    vramfit floor for {left['free']} MiB free: ncmoe {ncmoe}, predicts {predicted:.0f} MiB", flush=True)

    compose = eighty_b_compose(ncmoe)
    if not Path(compose).exists():
        import copy

        import yaml
        base = yaml.safe_load(Path(eighty_b_compose(41)).read_text())
        d = copy.deepcopy(base)
        c = next(iter(d["services"].values()))["command"]
        c[c.index("--n-cpu-moe") + 1] = str(ncmoe)
        Path(compose).write_text(yaml.safe_dump(d, sort_keys=True, width=200))
        idx = json.loads((rig.SCR / "teardown-index.json").read_text())
        idx["mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003"] = compose
        (rig.SCR / "teardown-index.json").write_text(json.dumps(idx, indent=2))
        print(f"    wrote {Path(compose).name}", flush=True)

    rig.sample_start(HOST)
    t0 = time.time()
    proc = rig.door("up", HOST, compose, f"{label}-80b")
    placed = proc.returncode == 0
    rows = rig.sample_stop(HOST, label)
    result = {
        "label": label, "asleep": asleep, "awake": awake,
        "card_pair_up_used_mib": both_up["used"],
        "card_free_with_sleeper_mib": left["free"],
        "ncmoe": ncmoe, "predicted_mib": predicted, "placed": placed,
        "samples": len(rows),
    }
    if not placed:
        log = rig.rig(HOST, "docker logs --tail 30 mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003 2>&1 || true")
        (rig.LOGS / f"crash-{label}.log").write_text(log)
        result["why"] = log[-600:]
        print("    80B DID NOT COME UP -- log saved", flush=True)
        return result

    wake = rig.wake_from(HOST, "mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003", t0)
    after = rig.gpu(HOST)
    result.update({
        "wake_s": wake,
        "card_all_three_used_mib": after["used"],
        "card_all_three_free_mib": after["free"],
        "measured_vs_predicted_mib": after["used"] - both_up["used"] + left["used"] - left["used"] - predicted,
        "vram_peak_used_mib": max((r["vram_used_mib"] for r in rows), default=None),
        "decode_80b_cold": rig.decode_llamacpp(HOST, 8003),
        "decode_80b_warm": rig.decode_llamacpp_warm(HOST, 8003),
        "awake_still_serving": rig.rig(
            HOST,
            "curl -s -o /dev/null -w '%{http_code}' "
            f"http://localhost:{PORTS[awake]}/v1/models",
        ),
        "sleeper_still_asleep": rig.rig(
            HOST, f"curl -sf http://localhost:{PORTS[asleep]}/is_sleeping || true"
        ),
        "level_one_refused": banned,
    })
    print(f"    80B up in {wake:.1f} s at ncmoe {ncmoe}; card {after['used']} used / {after['free']} free; "
          f"{awake} serving={result['awake_still_serving']}, {asleep} asleep={result['sleeper_still_asleep']}",
          flush=True)
    return result


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for asleep, awake in (("3b", "7b"), ("7b", "3b")):
        for i in (1, 2):
            try:
                results.append(arm(asleep, awake, i))
            except SystemExit as exc:
                print(f"    ARM FAILED: {exc}", flush=True)
                results.append({"label": f"q16-{awake}-awake-{asleep}-asleep-{i}", "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
    teardown()
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
