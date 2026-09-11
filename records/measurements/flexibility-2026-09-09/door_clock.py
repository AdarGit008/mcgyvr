"""Q8 — what `mcgyvr`'s own clock measures, beside the two the corpus uses.

Every wake figure in the corpus is one of two clocks: the container's own
``StartedAt`` to health, or the door's ``up after`` printed from the moment
``docker compose up -d`` returns. ``wake.py`` keeps a **third** — wall clock
around :func:`mcgyvr.wake.spawn_door`, which includes gates 1-8, the rig lease
and ssh — and ``DEVIATION_RATIO = 1.5`` is fitted to none of them.

Each arm here wakes srv1's live ladder through ``mcgyvr serve wake --host srv1``
itself, and reads all three clocks off that one wake:

* **clock 1** — ``StartedAt`` (UTC, ``calendar.timegm``) to the moment the
  command returned;
* **clock 2** — the door's per-unit ``seconds`` in the ``serve-up.json`` it wrote;
* **clock 3** — the seconds ``mcgyvr`` printed, which is ``Wake.seconds``.

Clock 3 minus clock 2 is the door's own overhead, which nothing prices today.

**The first attempt is made the way an operator would make it: without moving
anything aside.** The door's envelope is write-once per campaign-day, so a card
already woken today may refuse a second wake at gate 5. If it does, that is
recorded as a finding about the Waker — which exists to wake a card at dispatch
time, more than once a day — and only then is the envelope moved aside and the
wake retried.

Each arm ends with ``mcgyvr serve sleep``, so srv1 is idle when the block ends.

**The live config cannot do this, and that is the first thing Q8 found.** It
holds no ``serving.compose_dir``, so ``mcgyvr serve wake --host srv1`` on it
refuses before any door opens: "this config holds no launch spec for that
card". The three ``q8-clock-*`` failures on record are that refusal. The
``q8b-*`` arms run on ``q8/mcgyvr.yaml``, a copy that adds that one key and
nothing else, checked by ``mcgyvr emit --check`` to emit exactly the files the
live ladder runs. The door still opens on the live config: ``door_argv`` passes
none, so gate 1 reads the default.

**And ``mcgyvr serve sleep`` cannot take it back down.** On ``q8b-clock-1`` the
wake landed and the sleep died inside ``capacity.drain`` with a ``TypeError``
(the traceback is in ``results-q8-clocks.json``), leaving the card up, so gate 2
refused the next two wakes — correctly. The ``q8c-*`` arms take the card down
through the door between wakes instead, and leave the last wake up: that wake
is srv1's restoration to the live ladder.
"""

from __future__ import annotations

import calendar
import json
import re
import subprocess
import tempfile
import os
import time
from datetime import date
from pathlib import Path

import rig

HOST = "srv1"
CONTAINER = "mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080"
PORT = 8080
ARMS = 2
LIVE_COMPOSE = "/home/adaramir/.mcgyvr/config/compose.srv1.yml"
OUT = rig.SCR / "results-q8-clocks.json"
CONFIG = rig.SCR / "q8" / "mcgyvr.yaml"
LABEL = "q8c-clock"
PRINTED = re.compile(rf"{HOST} (?:wake|sleep): ([\d.]+)s")


def evidence_dir() -> Path:
    return rig.REPO / "records" / "evidence" / f"{date.today():%Y-%m-%d}-live-{HOST}"


def mcgyvr(direction: str) -> dict:
    t0 = time.time()
    proc = subprocess.run(
        ["uv", "run", "--no-sync", "mcgyvr", "serve", direction, "--host", HOST,
         "--config", str(CONFIG)],
        cwd=rig.REPO, capture_output=True, text=True, timeout=1800,
    )
    t1 = time.time()
    got = PRINTED.search(proc.stdout)
    return {
        "rc": proc.returncode,
        "wall_s": round(t1 - t0, 3),
        "t_done": t1,
        "printed_s": float(got.group(1)) if got else None,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-3000:],
    }


def attempt(direction: str, label: str) -> dict:
    artifact = "serve-up.json" if direction == "wake" else "serve-down.json"
    first = mcgyvr(direction)
    said = first["stdout"] + first["stderr"]
    gate5 = first["rc"] != 0 and ("gate 5" in said or "written once" in said)
    if not gate5:
        return {**first, "refused_at_gate5_first": False}
    ev = evidence_dir()
    stale = ev / artifact
    moved = None
    if stale.exists():
        moved = ev / f"{artifact[:-5]}-{label}-aside.json"
        stale.rename(moved)
    second = mcgyvr(direction)
    return {
        **second,
        "refused_at_gate5_first": True,
        "first_attempt": {k: first[k] for k in ("rc", "wall_s", "stderr")},
        "moved_aside": str(moved) if moved else None,
    }


def clock1(t_done: float) -> float:
    sa = rig.started_at(HOST, CONTAINER)
    return t_done - calendar.timegm(time.strptime(sa[:19], "%Y-%m-%dT%H:%M:%S"))


def envelope_seconds() -> tuple[float | None, dict | None]:
    path = evidence_dir() / "serve-up.json"
    if not path.exists():
        return None, None
    env = json.loads(path.read_text())
    units = env.get("units") or []
    secs = [u.get("seconds") for u in units if u.get("container") == CONTAINER]
    return (secs[0] if secs else None), {"run_id": env.get("run_id"), "units": units,
                                          "card_after": env.get("card_after")}


def remembered() -> dict | None:
    p = Path(tempfile.gettempdir()) / f"mcgyvr-wake-{os.getuid()}" / f"{HOST}.wake.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def arm(i: int) -> dict:
    label = f"{LABEL}-{i}"
    print(f"\n=== {label}", flush=True)
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)

    up = attempt("wake", label)
    if up["rc"] != 0:
        raise SystemExit(f"mcgyvr serve wake rc={up['rc']}\n{up['stderr'][-1200:]}")
    rig.note_up(HOST, LIVE_COMPOSE)
    c1 = clock1(up["t_done"])
    c2, env = envelope_seconds()
    c3 = up["printed_s"]
    served = rig.http(HOST, PORT, "/v1/models")[0]
    restarts = rig.restarts(HOST, CONTAINER)
    memo = remembered()
    # The envelope has been read; move it aside so the next arm's gate 5 is
    # not what gets measured again.
    ev = evidence_dir()
    if (ev / "serve-up.json").exists():
        (ev / "serve-up.json").rename(ev / f"serve-up-{label}.json")
    print(f"    clock1 StartedAt {c1:.1f}s   clock2 door {c2}s   clock3 mcgyvr {c3}s   "
          f"wall {up['wall_s']:.1f}s   gate5-first={up['refused_at_gate5_first']}   "
          f"restarts={restarts}   /v1/models {served}", flush=True)

    # `mcgyvr serve sleep` crashes in `capacity.drain` on this config, so the card
    # goes down through the door. The last arm's wake is left up on purpose.
    down_rc = None
    if i < ARMS:
        proc = rig.door("down", HOST, LIVE_COMPOSE, f"{label}-td")
        down_rc = proc.returncode
        print(f"    door down rc={down_rc}", flush=True)
        if down_rc != 0:
            raise SystemExit(f"door down rc={down_rc}\n{proc.stderr[-1200:]}")
    else:
        print("    left up: srv1 is back on the live ladder", flush=True)

    return {
        "label": label,
        "clock1_startedat_s": c1,
        "clock2_door_s": c2,
        "clock3_mcgyvr_s": c3,
        "door_overhead_s": (c3 - c2) if (c3 is not None and c2 is not None) else None,
        "wall_s": up["wall_s"],
        "restart_count": restarts,
        "models_http": served,
        "wake_refused_at_gate5_first": up["refused_at_gate5_first"],
        "teardown_door_rc": down_rc,
        "left_up": i == ARMS,
        "remembered": memo,
        "envelope": env,
        "wake_stderr": up["stderr"],
        "wake_first_attempt": up.get("first_attempt"),
    }


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for i in range(1, ARMS + 1):
        try:
            results.append(arm(i))
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
            results.append({"label": f"{LABEL}-{i}", "failed": str(exc)})
        OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
