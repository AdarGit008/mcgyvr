"""Q16, off the door — a sleeper and an awake unit on one card, and a third unit
placed into what is left.

The state the campaign is named for: ``V_avail(h,S)`` with a level-2 sleeper and
a live co-resident on the card at once, and the 80B's placement chosen by
`vramfit` from the card the sleeper actually left.

**Why off the door.** `three_way.py` ran this through the door and gate 2
refused it, correctly: ``serving/gate-scripts/02-rig.py`` refuses ``serve up``
onto a busy rig, with ``RUN_SERVE == "down"`` the only exemption, and placing a
third unit onto a card that already holds two is the whole experiment. The two
"gate 5 RUN_ID" failures in ``results-q16-threeway.json`` are the retry after
that refusal, not its cause.

**Owner ruling, 2026-09-10: run Q16 off-door.** The pair still comes up and goes
down through the door. Only the 80B's up and down go around it, as
``docker -H ssh://srv2 compose``, which is what the door's own ``docker`` shim
becomes — under its **own compose project**, so nothing the door does to project
``mcgyvr`` touches it, and with ``restart: 'no'`` so a placement that does not
fit is an exited container rather than a crash loop.

What that forfeits is gates 5, 7 and 8 for the 80B's half: no envelope and no
leftover-container check. The leftover check is done here instead — the 80B is
removed and confirmed gone before the door is asked to take the pair down,
because gate 7 requires an empty daemon after.

`three_way.py`'s ``measured_vs_predicted_mib`` also had its arithmetic wrong
(``after - both_up + left - left - predicted``). Here it is the 80B's own
addition to the card, ``after.used - left.used``, against its prediction.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

import yaml  # noqa: E402

import rig  # noqa: E402
import sleep_cycles as sc  # noqa: E402
import three_way as tw  # noqa: E402
from mcgyvr.serving import servelib, vramfit  # noqa: E402

HOST = "srv2"
PROJECT = "mcgyvr-q16-offdoor"
C80 = "mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003"
PORT80 = 8003
MIB = 1024 * 1024
MODELS = {"3b": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", "7b": "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"}
OUT = rig.SCR / "results-q16b-offdoor.json"


def compose_offdoor(ncmoe: int) -> Path:
    base = yaml.safe_load(Path(tw.eighty_b_compose(41)).read_text())
    d = copy.deepcopy(base)
    svc = next(iter(d["services"].values()))
    command = svc["command"]
    command[command.index("--n-cpu-moe") + 1] = str(ncmoe)
    svc["restart"] = "no"
    path = rig.SCR / f"compose.srv2-80b-offdoor-ncmoe{ncmoe}.yml"
    path.write_text(yaml.safe_dump(d, sort_keys=True, width=200))
    return path


def offdoor(compose: Path, *args: str, timeout: int = 900):
    return rig.sh(
        ["docker", "-H", f"ssh://{HOST}", "compose", "-f", str(compose), "-p", PROJECT, *args],
        timeout=timeout,
    )


def names() -> list[str]:
    return rig.rig(HOST, "docker ps -a --format '{{.Names}}'").split()


def remove_80b() -> None:
    if C80 in names():
        rig.rig(HOST, f"docker rm -f {C80} >/dev/null 2>&1; true")
    if C80 in names():
        raise SystemExit(f"{HOST}: {C80} would not go, and the door will not take the pair down past it")


def teardown() -> None:
    remove_80b()
    running = rig.rig(HOST, "docker ps -a --format '{{.Names}}' | grep '^mcgyvr-' || true")
    if not running.strip():
        return
    compose = rig.last_up(HOST)
    if not compose:
        raise SystemExit(f"{HOST}: {running.split()} are up and nothing names their file")
    rig.door_or_die("down", HOST, compose, f"q16btd-{int(time.time() * 10) % 10**9}")


def wait_models(port: int, limit: int = 900) -> float | None:
    t0 = time.time()
    while time.time() - t0 < limit:
        if rig.http(HOST, port, "/v1/models", timeout=10)[0] == "200":
            return time.time()
        state = rig.rig(HOST, f"docker inspect {C80} --format '{{{{.State.Status}}}}' 2>/dev/null || echo gone")
        if state.strip() in ("exited", "dead", "gone"):
            return None
        time.sleep(2)
    return None


def arm(asleep: str, awake: str, index: int) -> dict:
    label = f"q16b-80b-with-{awake}-awake-{asleep}-asleep-{index}"
    print(f"\n=== {label}", flush=True)
    teardown()
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)

    rig.door_or_die("up", HOST, tw.PAIR, f"{label}-pair")
    rig.note_up(HOST, tw.PAIR)
    time.sleep(5)
    both_up = rig.gpu(HOST)
    both_per_unit = sc.per_unit_card()

    banned = None
    try:
        servelib.sleep(HOST, tw.PORTS[asleep], level=1)
    except servelib.SleepLevelError as exc:
        banned = str(exc)[:160]
    if banned is None:
        raise SystemExit("a level-1 sleep was NOT refused; the ban is not holding")

    code = rig.rig(HOST, "curl -s -o /dev/null -w '%{http_code}' -X POST "
                         f"'http://localhost:{tw.PORTS[asleep]}/sleep?level=2'")
    time.sleep(3)
    left = rig.gpu(HOST)
    left_per_unit = sc.per_unit_card()
    print(f"    pair up: card {both_up['used']} used {both_per_unit}; {asleep} asleep "
          f"(http {code.strip()}): {left['used']} used / {left['free']} free {left_per_unit}", flush=True)

    ncmoe = vramfit.floor(tw.GEOM, left["free"] * MIB, tw.CARD_CONSTANT_MIB * MIB)
    result: dict = {
        "label": label, "asleep": asleep, "awake": awake,
        "card_pair_up_used_mib": both_up["used"], "pair_up_per_unit_mib": both_per_unit,
        "card_with_sleeper_used_mib": left["used"], "card_free_with_sleeper_mib": left["free"],
        "with_sleeper_per_unit_mib": left_per_unit, "sleep_http": code.strip(),
        "level_one_refused": banned, "ncmoe": ncmoe,
    }
    if ncmoe is None:
        print("    vramfit: no placement fits what the sleeper left; recording the refusal", flush=True)
        result["placed"] = False
        result["why"] = "vramfit.floor found no --n-cpu-moe that fits"
        return result

    predicted = vramfit.predict(tw.GEOM, ncmoe, tw.CARD_CONSTANT_MIB * MIB) / MIB
    compose = compose_offdoor(ncmoe)
    print(f"    vramfit floor for {left['free']} MiB free: ncmoe {ncmoe}, predicts {predicted:.0f} MiB", flush=True)
    result.update({"predicted_mib": predicted, "compose": str(compose)})

    rig.sample_start(HOST)
    up = offdoor(compose, "up", "-d")
    t_ok = wait_models(PORT80)
    rows = rig.sample_stop(HOST, label)
    if up.returncode != 0 or t_ok is None:
        log = rig.rig(HOST, f"docker logs --tail 40 {C80} 2>&1 || true")
        (rig.LOGS / f"crash-{label}.log").write_text(log + "\n--- compose ---\n" + up.stdout + up.stderr)
        result.update({"placed": False, "compose_up_rc": up.returncode, "why": log[-800:],
                       "vram_peak_used_mib": max((r["vram_used_mib"] for r in rows), default=None)})
        print(f"    80B DID NOT COME UP (compose rc {up.returncode}) -- log saved", flush=True)
        remove_80b()
        return result

    after = rig.gpu(HOST)
    added = after["used"] - left["used"]
    result.update({
        "placed": True,
        "wake_s": rig.wake_from(HOST, C80, t_ok),
        "restart_count": rig.restarts(HOST, C80),
        "card_all_three_used_mib": after["used"],
        "card_all_three_free_mib": after["free"],
        "all_three_per_unit_mib": sc.per_unit_card(),
        "eighty_b_added_mib": added,
        "measured_vs_predicted_mib": added - predicted,
        "vram_peak_used_mib": max((r["vram_used_mib"] for r in rows), default=None),
        "decode_80b_cold": rig.decode_llamacpp(HOST, PORT80),
        "decode_80b_warm": rig.decode_llamacpp_warm(HOST, PORT80),
        "awake_models_http": rig.http(HOST, tw.PORTS[awake], "/v1/models")[0],
        "awake_decode": rig.decode_vllm(HOST, tw.PORTS[awake], MODELS[awake]),
        "sleeper_is_sleeping": rig.rig(HOST, f"curl -s http://localhost:{tw.PORTS[asleep]}/is_sleeping || true"),
    })
    print(f"    80B up in {result['wake_s']:.1f} s at ncmoe {ncmoe}: added {added} MiB against "
          f"{predicted:.0f} predicted ({result['measured_vs_predicted_mib']:+.0f}); card {after['used']} used / "
          f"{after['free']} free; {awake} http {result['awake_models_http']}; "
          f"{asleep} sleeping {result['sleeper_is_sleeping']}", flush=True)
    remove_80b()
    return result


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for asleep, awake in (("7b", "3b"), ("3b", "7b")):
        for i in (1, 2):
            try:
                results.append(arm(asleep, awake, i))
            except SystemExit as exc:
                print(f"    ARM FAILED: {exc}", flush=True)
                results.append({"label": f"q16b-80b-with-{awake}-awake-{asleep}-asleep-{i}", "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
    teardown()
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
