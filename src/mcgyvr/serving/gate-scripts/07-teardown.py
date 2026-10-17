#
""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.serving.gatelib import (
    artifact_escape,
    door_required,
    envelope_escape,
    need,
)
from mcgyvr.serving.rigread import snapshot

#
#
#
COMPARED = (
    "uptime_since",
    "cpu_max_mhz",
    "cpu_model",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "gpu_name",
    "gpu_vram_mib",
    "gpu_cc",
    "driver",
    "gpu_reserve_mib",
    "docker",
)


def _ids(reading: str | None) -> set[str]:
    ""
    return {part for part in (reading or "").split(";") if part and part != "none"}


def _containers_up() -> dict[str, str] | None:
    ""
    try:
        listed = subprocess.run(
            ["docker", "ps", "--format", "{{.ID}}\t{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            "gate 7: 'docker ps' did not answer in 120s; whether the run left a "
            "container is unknown",
            file=sys.stderr,
        )
        return None
    if listed.returncode != 0:
        print(
            "gate 7: 'docker ps' failed; whether the run left a container is "
            f"unknown. {listed.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        return None
    up: dict[str, str] = {}
    for line in listed.stdout.splitlines():
        if not line.strip():
            continue
        ident, _, name = line.partition("\t")
        up[ident.strip()] = name.strip() or ident.strip()
    return up


def main() -> int:
    door_required("gate 7")
    seen: dict[str, object] = {
        "run_id": need("RUN_ID"),
        "step_exit": os.environ.get("RUN_STEP_EXIT") or "unknown",
    }
    status = 1
    try:
        status = judge(seen, user=True)
    finally:
        seen["teardown_exit"] = status
        file_end(seen)
    return status


def file_end(seen: dict[str, object]) -> None:
    ""
    out_dir = Path(need("RUN_OUT_DIR"))
    path = out_dir / f"{need('RUN_ID')}.end.json"
    escape = envelope_escape(out_dir) or artifact_escape(path, out_dir)
    if escape is not None:
        print(f"gate 7: the run's end is not filed: {escape}", file=sys.stderr)
        return
    seen["ended_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(seen, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        print(
            f"gate 7: {path.name} is already filed; not written again", file=sys.stderr
        )


def judge(seen: dict[str, object], *, user: bool) -> int:
    ""
    status = 0
    run_id = need("RUN_ID")
    pre = dict(p.split("=", 1) for p in need("RUN_PRE_RIG").split(" ") if "=" in p)

    #
    #��
    #
    #
    #
    #is
    #
    serve = os.environ.get("RUN_SERVE", "")
    expected = set(os.environ.get("RUN_SERVE_EXPECTED", "").split())
    #
    #
    #
    #
    alone = serve in ("up", "down") and bool(
        os.environ.get("RUN_SERVE_ONLY", "").split()
    )
    judged = set(os.environ.get("RUN_SERVE_ONLY", "").split()) if alone else expected
    #
    #
    #
    if not alone and serve in ("up", "sleep", "wake"):
        judged = expected - set(os.environ.get("RUN_SERVE_ASLEEP", "").split())
    untouched = expected - judged
    seen["only"] = sorted(judged) if alone else []
    #
    #
    #
    opened_busy = serve in ("down", "sleep", "wake")
    keeps = serve in ("up", "sleep", "wake")
    #
    #
    #
    before = (
        set() if opened_busy and not (user or alone) else _ids(pre.get("containers"))
    )
    up = _containers_up()
    if up is None:
        status = 1
    else:
        #
        left = {
            ident: name
            for ident, name in up.items()
            if name not in untouched
            and (ident not in before or ((user or alone) and name in judged))
        }
        seen["containers_up"] = sorted(up.values())
        if keeps:
            serving = {ident: name for ident, name in left.items() if name in judged}
            left = {ident: name for ident, name in left.items() if name not in judged}
            missing = sorted(judged - set(serving.values()))
            seen["serving"] = sorted(serving.values())
            seen["missing"] = missing
            if serving:
                names = " ".join(sorted(serving.values()))
                print(f"gate 7: serving, as declared: {names}")
            if missing:
                print(
                    f"gate 7: serve {serve} ended with declared units not running: "
                    f"{' '.join(missing)} — the ladder is not up, and the run is "
                    "not green",
                    file=sys.stderr,
                )
                status = 1
        seen["left"] = sorted(left.values())
        #
        stuck = sorted(name for name in left.values() if name in judged)
        if stuck:
            print(
                f"gate 7: serve {serve} ended with named units still up: "
                f"{' '.join(stuck)} — they were not stopped, and the run is not "
                "green",
                file=sys.stderr,
            )
            status = 1
        left = {ident: name for ident, name in left.items() if name not in judged}
        if left:
            yours = [n for n in left.values() if n.startswith(f"{run_id}-")]
            others = [n for n in left.values() if not n.startswith(f"{run_id}-")]
            described = []
            if yours:
                described.append(f"named for this run: {' '.join(sorted(yours))}")
            if others:
                described.append(
                    "NOT named for this run (no "
                    f"{run_id}- prefix): {' '.join(sorted(others))}"
                )
            print(
                "gate 7: the step left containers up that gate 2 read none of "
                f"before it — {'; '.join(described)} — a run that leaves a "
                "container is not green, and one it did not name is still one "
                "it left (kill what you started: docker rm -f <name>)",
                file=sys.stderr,
            )
            status = 1

    try:
        post = snapshot(need("RUN_HOST"))
    except SystemExit:
        #
        #s.
        print(
            "gate 7: the rig could not be re-read after the step; its end "
            "state is unknown and the run is not green",
            file=sys.stderr,
        )
        return 1
    seen["rig_after"] = post

    #
    #
    #
    unseen = _ids(post.get("containers")) - before - set(up or {})
    if unseen:
        print(
            "gate 7: the rig's reader lists containers up after the step that "
            f"gate 2 read none of before it: {' '.join(sorted(unseen))} — a run "
            "that leaves a container is not green",
            file=sys.stderr,
        )
        status = 1

    moved = {
        key: {"before": pre.get(key), "after": post.get(key)}
        for key in COMPARED
        if pre.get(key) != post.get(key)
    }
    if moved:
        seen["rig_moved"] = moved
        print(
            "gate 7: rig changed during the run: "
            + ", ".join(
                f"{key} {change['before']} -> {change['after']}"
                for key, change in moved.items()
            ),
            file=sys.stderr,
        )
        status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
