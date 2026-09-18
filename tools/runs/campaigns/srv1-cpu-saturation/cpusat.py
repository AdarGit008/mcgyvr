"""srv1-cpu-saturation: the sampler the rig runs, the aggregate pass, the artifact.

The footprint-versus-stream test, run with its hard-lock risk
(``okf/must-read/touching-rigs.md``, "A rig that hard-locks under load").
``_arm.sh`` asks this file for five commands, by
path (``_py cpusat.py COMMAND ...``):

* ``sampler`` prints the shell the rig runs to sample every core once a second
  — ``mpstat -P ALL 1 1`` when sysstat is on the rig, ``/proc/stat`` deltas
  otherwise — as ``T <epoch>`` / ``S <cpu> <busy_pct>`` lines teed to a file
  under ``~/mcgyvr-relock/``, until a stop file appears;
* ``remote-file RUN_ID SUFFIX`` prints the rig-side path a run tees to;
* ``rig-agg`` is run ON THE RIG (``python3 - rig-agg SPEC``, this file on
  stdin, as the lock's harness is shipped): W concurrent ``/completion``
  requests of ``n_predict`` tokens each, ``ignore_eos``, read from the server's
  own ``timings``, so the aggregate decode at width W is a number this rig's
  clock took;
* ``write STATE OUT`` files the artifact whole, from whatever the step left
  in its state directory, and judges nothing;
* ``keep-log SRC ENVELOPE NAME`` files a start's ``docker logs`` beside the
  artifact.

Standard library only, on purpose: the rig has no mcgyvr to import, and
``rig-agg`` runs on its python3.
"""

from __future__ import annotations

import http.client
import json
import os
import shlex
import statistics
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "srv1-cpu-saturation/1"
#: Where a step tees its markers and samples on the rig (lock-fleets' folder).
RIG_DIR = "mcgyvr-relock"
#: The marker fields a run's START and END must agree on (lock-fleets').
MARKER_FIELDS = ("uptime_since", "ram_mt_s", "pl1_uw", "pl2_uw")
VMSTAT_FIELDS = ("pswpout", "pgmajfault")
#: The harness's short prompt, as ``mcgyvr/fleet/harness.py`` spells it.
SHORT_PROMPT = "Write a Python function that reverses a singly linked list in place.\n"
#: The sampler stops by itself after this many seconds without a stop file.
SAMPLER_MAX_S = 7200

SAMPLER = r"""set -u
mkdir -p "$HOME"/@RIG_DIR@
f="$HOME"/@RIG_DIR@/@RUN_ID@.cpu
stop="$HOME"/@RIG_DIR@/@RUN_ID@.cpu.stop
rm -f "$stop"
if command -v mpstat >/dev/null 2>&1; then
    printf 'SOURCE mpstat nproc=%s\n' "$(nproc)" | tee -a "$f"
    sample() {
        LC_ALL=C mpstat -P ALL 1 1 | awk '
            /Average/ { next }
            /CPU/ { next }
            {
                cpu = ""
                for (i = 2; i <= 3 && i <= NF; i++)
                    if ($i == "all" || $i ~ /^[0-9]+$/) { cpu = $i; break }
                if (cpu == "" || NF < 5) next
                printf "S %s %.2f\n", cpu, 100 - $NF
            }'
    }
else
    printf 'SOURCE proc_stat nproc=%s\n' "$(nproc)" | tee -a "$f"
    sample() {
        a=$(grep '^cpu' /proc/stat)
        sleep 1
        b=$(grep '^cpu' /proc/stat)
        printf '%s\n===\n%s\n' "$a" "$b" | awk '
            /^===/ { second = 1; next }
            {
                name = ($1 == "cpu") ? "all" : substr($1, 4)
                total = 0
                for (i = 2; i <= NF; i++) total += $i
                idle = $5 + $6
                if (!second) { t0[name] = total; i0[name] = idle; next }
                dt = total - t0[name]; di = idle - i0[name]
                if (dt > 0) printf "S %s %.2f\n", name, 100 * (dt - di) / dt
            }'
    }
fi
end=$(( $(date +%s) + @MAX_S@ ))
while [ ! -e "$stop" ] && [ "$(date +%s)" -lt "$end" ]; do
    { printf 'T %s\n' "$(date +%s.%N)"; sample; } >> "$f"
done
printf 'STOPPED %s\n' "$(date +%s.%N)" >> "$f"
"""


class ProbeError(Exception):
    """A step asked for something this file cannot give."""


def sampler(run_id: str) -> str:
    """The rig's sampler shell for ``run_id``: rendered, nothing else substituted."""
    return (
        SAMPLER.replace("@RIG_DIR@", RIG_DIR)
        .replace("@RUN_ID@", shlex.quote(run_id))
        .replace("@MAX_S@", str(SAMPLER_MAX_S))
    )


def remote_file(run_id: str, suffix: str) -> str:
    """The rig-side file a run tees to, spelled for the rig's shell."""
    return f'"$HOME"/{RIG_DIR}/{shlex.quote(f"{run_id}.{suffix}")}'


# --------------------------------------------------------------------------
# the aggregate pass, on the rig
# --------------------------------------------------------------------------


def _timing(body: Any, key: str) -> float | None:
    timings = body.get("timings") if isinstance(body, Mapping) else None
    value = timings.get(key) if isinstance(timings, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _one(
    port: int,
    payload: Mapping[str, Any],
    out: list[dict[str, Any]],
    index: int,
    lock: threading.Lock,
) -> None:
    record: dict[str, Any] = {"index": index}
    started = time.monotonic()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port)
        connection.request(
            "POST",
            "/completion",
            body=json.dumps(dict(payload)).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
        record["status"] = response.status
        body = json.loads(raw.decode("utf-8")) if raw else None
        for key in (
            "predicted_n",
            "predicted_ms",
            "predicted_per_second",
            "prompt_n",
            "prompt_ms",
        ):
            record[key] = _timing(body, key)
        connection.close()
    except (OSError, ValueError, http.client.HTTPException) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["wall_s"] = time.monotonic() - started
    with lock:
        out.append(record)


def rig_aggregate(spec: Mapping[str, Any]) -> dict[str, Any]:
    """W concurrent ``/completion`` requests of ``n_predict`` tokens, ``rounds`` times.

    ``spec`` is ``{"port": N, "width": W, "n_predict": T, "rounds": R}``. Each
    round's aggregate decode is the sum of every reply's ``predicted_n`` over
    the round's wall seconds (first request sent to last reply read), beside
    the sum of the replies' own ``predicted_per_second``. Filed, never judged.
    """
    port = int(spec["port"])
    width = int(spec.get("width") or 8)
    n_predict = int(spec.get("n_predict") or 256)
    rounds = int(spec.get("rounds") or 2)
    payload = {
        "prompt": SHORT_PROMPT,
        "n_predict": n_predict,
        "temperature": 0,
        "ignore_eos": True,
        "cache_prompt": False,
    }
    out: dict[str, Any] = {
        "width": width,
        "n_predict": n_predict,
        "rounds": [],
        "started_at": _now(),
    }
    for number in range(1, rounds + 1):
        records: list[dict[str, Any]] = []
        lock = threading.Lock()
        threads = [
            threading.Thread(target=_one, args=(port, payload, records, i, lock))
            for i in range(width)
        ]
        began = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        wall = time.monotonic() - began
        records.sort(key=lambda r: int(r["index"]))
        tokens = [r["predicted_n"] for r in records if r.get("predicted_n") is not None]
        rates = [
            r["predicted_per_second"]
            for r in records
            if r.get("predicted_per_second") is not None
        ]
        out["rounds"].append(
            {
                "round": number,
                "wall_s": wall,
                "replies": len(tokens),
                "errors": [r["error"] for r in records if r.get("error")],
                "predicted_tokens": sum(tokens),
                "aggregate_tok_s": (
                    (sum(tokens) / wall) if tokens and wall > 0 else None
                ),
                "sum_predicted_per_second": sum(rates) if rates else None,
                "requests": records,
            }
        )
    values = [
        r["aggregate_tok_s"] for r in out["rounds"] if r["aggregate_tok_s"] is not None
    ]
    out["aggregate_tok_s"] = statistics.median(values) if values else None
    out["finished_at"] = _now()
    return out


# --------------------------------------------------------------------------
# the CPU samples, read back
# --------------------------------------------------------------------------


def parse_samples(text: str) -> dict[str, Any]:
    """The sampler's lines as one record per second: ``all`` and each core's busy %."""
    source: str | None = None
    nproc: int | None = None
    samples: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    stopped: float | None = None
    unparsed: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        try:
            if parts[0] == "SOURCE" and len(parts) >= 2:
                source = parts[1]
                for token in parts[2:]:
                    key, _, value = token.partition("=")
                    if key == "nproc" and value.isdigit():
                        nproc = int(value)
            elif parts[0] == "T" and len(parts) == 2:
                current = {"epoch": float(parts[1]), "all": None, "cores": {}}
                samples.append(current)
            elif parts[0] == "S" and len(parts) == 3 and current is not None:
                busy = float(parts[2])
                if parts[1] == "all":
                    current["all"] = busy
                else:
                    current["cores"][parts[1]] = busy
            elif parts[0] == "STOPPED" and len(parts) == 2:
                stopped = float(parts[1])
            else:
                unparsed.append(line)
        except ValueError:
            unparsed.append(line)
    return {
        "source": source,
        "nproc": nproc,
        "samples": samples,
        "stopped": stopped,
        "unparsed": unparsed,
    }


def phase_stats(
    samples: Sequence[Mapping[str, Any]], start: float | None, end: float | None
) -> dict[str, Any]:
    """Peak and mean all-core busy % over the samples stamped inside a phase."""
    if start is None or end is None:
        return {
            "start": start,
            "end": end,
            "n": 0,
            "peak_all_pct": None,
            "mean_all_pct": None,
        }
    inside = [s for s in samples if start <= float(s["epoch"]) <= end]
    alls = [float(s["all"]) for s in inside if s.get("all") is not None]
    cores: dict[str, list[float]] = {}
    for s in inside:
        for core, busy in (s.get("cores") or {}).items():
            cores.setdefault(str(core), []).append(float(busy))
    return {
        "start": start,
        "end": end,
        "n": len(inside),
        "peak_all_pct": max(alls) if alls else None,
        "mean_all_pct": (sum(alls) / len(alls)) if alls else None,
        "per_core_mean_pct": {c: sum(v) / len(v) for c, v in sorted(cores.items())},
        "per_core_peak_pct": {c: max(v) for c, v in sorted(cores.items())},
    }


# --------------------------------------------------------------------------
# the artifact
# --------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017


def _text(state: Path, name: str) -> str | None:
    path = state / name
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _float(state: Path, name: str) -> float | None:
    text = (_text(state, name) or "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _json_or_raw(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


def key_values(text: str) -> dict[str, str]:
    """``key=value`` lines (a rig snapshot), or the fields of a ``### NAME`` marker."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        for token in line.removeprefix("###").split():
            key, sep, value = token.partition("=")
            if sep:
                out[key] = value
    return out


def vmstat(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in VMSTAT_FIELDS and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


def write(state: Path, out: Path) -> None:
    """``_arm.sh``'s artifact, whole, from what the step left in ``state``."""
    facts = json.loads(_text(state, "arm.json") or "{}")
    snap_start, snap_end = _text(state, "snap-start"), _text(state, "snap-end")
    vm_start, vm_end = _text(state, "vmstat-start"), _text(state, "vmstat-end")
    failure = _text(state, "failure")
    markers_start = key_values(_text(state, "marker-start") or "")
    markers_end = key_values(_text(state, "marker-end") or "")
    cpu = parse_samples(_text(state, "cpu.samples") or "")
    phases = {
        name: phase_stats(
            cpu["samples"], _float(state, f"{name}.t0"), _float(state, f"{name}.t1")
        )
        for name in ("load", "aggregate")
    }
    vms = vmstat(vm_start or ""), vmstat(vm_end or "")
    delta = {
        k: vms[1][k] - vms[0][k] for k in VMSTAT_FIELDS if k in vms[0] and k in vms[1]
    }
    restarts = (_text(state, "restarts") or "").strip()
    record = {
        "schema": SCHEMA,
        "run_id": os.environ.get("RUN_ID"),
        "host": os.environ.get("RUN_HOST"),
        "round": os.environ.get("RUN_ROUND"),
        "product_sha256": os.environ.get("RUN_PRODUCT_SHA256"),
        "arm": facts.get("arm"),
        "n_cpu_moe": facts.get("n_cpu_moe"),
        "image": {"tag": facts.get("image"), "digest": facts.get("digest")},
        "argv": facts.get("argv"),
        "env": facts.get("env"),
        "container_id": (_text(state, "container_id") or "").strip() or None,
        "wake_s": _float(state, "wake_s"),
        "harness": _json_or_raw(_text(state, "harness.json")),
        "load": _json_or_raw(_text(state, "load.json")),
        "aggregate": _json_or_raw(_text(state, "aggregate.json")),
        "cpu": {
            "source": cpu["source"],
            "nproc": cpu["nproc"],
            "sample_count": len(cpu["samples"]),
            "phases": phases,
            "samples": cpu["samples"],
            "stopped": cpu["stopped"],
            "unparsed": cpu["unparsed"],
            "file_on_rig": facts.get("cpu_file"),
        },
        "snapshots": {
            "start": None if snap_start is None else key_values(snap_start),
            "end": None if snap_end is None else key_values(snap_end),
        },
        "markers": {
            "start": (_text(state, "marker-start") or "").strip() or None,
            "end": (_text(state, "marker-end") or "").strip() or None,
            "on_rig": _text(state, "readback"),
            "moved": [
                f"{k} {markers_start.get(k)} -> {markers_end.get(k)}"
                for k in MARKER_FIELDS
                if markers_start.get(k) != markers_end.get(k)
            ]
            if markers_start and markers_end
            else None,
        },
        "vmstat": {
            "start": None if vm_start is None else vms[0],
            "end": None if vm_end is None else vms[1],
            "delta": delta,
        },
        "restarts": int(restarts) if restarts.isdigit() else None,
        "exit": _json_or_raw(_text(state, "exit-state")),
        "docker_log_kept": (_text(state, "docker-log-kept") or "").strip() or None,
        "started_at": (_text(state, "started_at") or "").strip() or None,
        "ended_at": _now(),
        "failure": None if failure is None else failure.strip(),
    }
    out.write_text(
        json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def keep_log(source: Path, envelope: Path, name: str) -> str:
    """A failed start's whole ``docker logs``, written once beside the artifact."""
    target = envelope / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    handle = os.open(target, flags, 0o644)
    with os.fdopen(handle, "wb") as out, source.open("rb") as log:
        out.write(log.read())
    return name


def main(argv: list[str]) -> int:
    command, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    try:
        if command == "sampler" and len(args) == 1:
            sys.stdout.write(sampler(args[0]))
        elif command == "remote-file" and len(args) == 2:
            print(remote_file(args[0], args[1]))
        elif command == "rig-agg" and len(args) == 1:
            print(json.dumps(rig_aggregate(json.loads(args[0]))))
        elif command == "write" and len(args) == 2:
            write(Path(args[0]), Path(args[1]))
        elif command == "keep-log" and len(args) == 3:
            print(keep_log(Path(args[0]), Path(args[1]), args[2]))
        else:
            print(f"cpusat.py: no command {command!r} of {len(args)}", file=sys.stderr)
            return 2
    except (ProbeError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
