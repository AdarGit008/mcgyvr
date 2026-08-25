#!/usr/bin/env python3
"""The knob surface: declared, accepted, effective (#357).

Three columns, and only the first is free.

**DECLARED** is what the engine says it accepts: `vllm serve --help=all` run
inside the pinned image, parsed to data per image digest. Zero rig time, but
it does need the container to start, and vLLM's argument parser constructs a
`VllmConfig` while printing help, which infers the device -- so the capture
runs with `--gpus all` on a host that has one. `capture_declared` is that
command; `parse_help` is the parser; the result is one JSON file named by the
digest, so a moved image is a second file and a diff.

**ACCEPTED** is what THIS rig, with THIS model, actually launched. It cannot be
read off column 1: the 2026-08-24 sweep refused 24 of 106 stage-1 cells and the
split is per rig. It is built from launch attempts, one row per cell, and every
row is in exactly one of these states:

- `accepted` -- the container reached `/health` with the weights on the card.
- `refused` -- the engine exited and its own reason is in the record.
- `refused_reason_lost` -- the engine exited and the record holds only the
  wrapper line (`Engine core initialization failed. See root cause above`)
  because the harness kept 25 log lines and the cause scrolled past. **This is
  a refusal whose reason nobody has**, and the row says so rather than
  inventing one. Re-running the cell with a full log is what fills it.
- `harness_defect` -- the engine refused a value it never received as
  recorded. Detected exactly: the engine's parse error quotes the value it saw
  (`Value {method: cannot be converted`), the record holds the value the
  harness meant to send, and they differ. That is the shell-quoting defect
  that wrote three false refusals per rig into stage 1; the cells are kept and
  are now labelled as what they are. A `harness_defect` row is NOT evidence
  about the rig.
- `untried` -- a declared flag no cell has ever carried. Only enumerable once
  column 1 is captured; until then the count is `{"unknown": true}` with what
  was searched, not zero.

A knob absent because nobody tried it, a knob the hardware refused, and a knob
the harness mangled are three different facts and they never share a label.

**EFFECTIVE** is which knobs moved a number, by how much, and **in which
regime**. It is built from single-flag contrasts: two launched cells on the
same (rig, model) whose flag dicts differ in exactly one key. The parent's
other flags are the context, and the ratio is reported at every concurrency
level both cells ran -- because `--kv-cache-dtype fp8` is inert at n=16 (558
against 530 on srv2's eager baseline) and decisive at n=256 (6,445 against
6,088 with graphs on). One number per knob would hide exactly the thing the
sweep learned.

**Nothing here is reasoned to.** Every row cites the file and the cell it was
read from, and the drift test regenerates the committed surface from the
evidence directory and refuses a difference.

Usage::

    python3 tools/bench/serving/knobs.py build <out-dir> <evidence-dir>...
    python3 tools/bench/serving/knobs.py declared <host|local> <out-dir>
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _sweep() -> types.ModuleType:
    """`sweep.py` by path, as `run.py` loads `contract.py`: the image pin has
    one home and this module reads it rather than restating it."""
    cached = sys.modules.get("serving_sweep")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("serving_sweep", HERE / "sweep.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_sweep"] = module
    spec.loader.exec_module(module)
    return module


IMAGE: str = _sweep().IMAGE

SURFACE_RECORD = "knob-surface/1"
SERVING_ENGINE = "vllm"
#: The declared-column capture. `--gpus all` because the parser constructs a
#: VllmConfig while printing help and that infers the device: run without a
#: GPU on 2026-08-24 the image exits 1 with `Failed to infer device type`.
HELP_COMMAND = f"docker run --rm --gpus all --entrypoint vllm {IMAGE} serve --help=all"
DIGEST_COMMAND = f"docker image inspect --format '{{{{index .RepoDigests 0}}}}' {IMAGE}"


def _short_digest(digest: str) -> str:
    return digest.split("sha256:")[-1][:12]


#: The engine's own wrapper line. It names no cause; a record whose last error
#: is this line has lost the cause.
WRAPPER = "Engine core initialization failed"

#: Lines that carry a reason. Order matters only for readability; the scan
#: takes the LAST such line that is not the wrapper.
_REASON = re.compile(
    r"("
    r"\b[A-Za-z_][\w.]*(?:Error|Exception)\b: "
    r"|Assertion failed, "
    r"|vllm serve: error: "
    r"|CUDA out of memory"
    r"|torch\.OutOfMemoryError"
    r")"
)
_PARSE_ERROR = re.compile(
    r"vllm serve: error: argument (?P<flag>\S+?)(?:/\S+)?: Value (?P<seen>.*?) "
    r"cannot be converted"
)
_PID_PREFIX = re.compile(
    r"^\((?:APIServer|EngineCore(?:_DP\d+)?|Worker\S*) pid=\d+\)\s*"
)


# --------------------------------------------------------------------------
# declared


def parse_help(text: str) -> list[dict[str, Any]]:
    """`vllm serve --help=all` to rows: flag, aliases, shape, choices, default.

    argparse layout: an entry begins at two-space indent with `-`; its option
    strings are comma-separated up to the first metavar or choice set; the
    description follows on deeper-indented lines and may end with
    `(default: X)`. `shape` is `flag` (no value), `choice` (a `{a,b}` set) or
    `value` (a metavar). A `--x, --no-x` pair is one boolean knob.
    """
    rows: list[dict[str, Any]] = []
    entry: dict[str, Any] | None = None
    desc: list[str] = []

    def close() -> None:
        if entry is None:
            return
        text_ = " ".join(part.strip() for part in desc if part.strip())
        found = re.search(r"\(default: (.*?)\)\s*$", text_)
        entry["default"] = found.group(1) if found else None
        entry["help"] = text_
        rows.append(entry)

    for line in text.splitlines():
        head = re.match(r"^  (-\S.*)$", line)
        if head and not line.startswith("    "):
            close()
            desc = []
            # argparse separates the option strings from a same-line help
            # text by two or more spaces; option strings from each other by
            # ", "; a choice set has no space after its commas.
            parts = re.split(r"\s{2,}", head.group(1), maxsplit=1)
            spec, tail = parts[0], parts[1] if len(parts) > 1 else ""
            names: list[str] = []
            choices: list[str] | None = None
            metavar: str | None = None
            for token in spec.split(", "):
                m = re.match(r"^(-\S+)(?:\s+(.+))?$", token.strip())
                if not m:
                    continue
                names.append(m.group(1))
                value = m.group(2)
                if value and value.startswith("{") and value.endswith("}"):
                    choices = value[1:-1].split(",")
                elif value:
                    metavar = value
            if tail.strip():
                desc.append(tail)
            long_names = [n for n in names if n.startswith("--")]
            knob = next(
                (n for n in long_names if not n.startswith("--no-")),
                long_names[0] if long_names else names[0],
            )
            entry = {
                "flag": knob,
                "aliases": [n for n in names if n != knob],
                "shape": "choice" if choices else "value" if metavar else "flag",
                "choices": choices,
                "metavar": metavar,
            }
            continue
        if entry is not None and line.startswith("    "):
            desc.append(line)
            continue
        if entry is not None and not line.strip():
            close()
            entry = None
            desc = []
    close()
    return rows


def capture_declared(host: str, out_dir: Path) -> Path:
    """Run `--help=all` in the pinned image on `host` and write the parsed
    surface beside its digest. `host == "local"` runs docker here."""

    def run(cmd: str) -> str:
        argv = (
            [cmd] if host == "local" else ["ssh", "-o", "ConnectTimeout=10", host, cmd]
        )
        r = subprocess.run(
            argv, shell=host == "local", capture_output=True, text=True, timeout=900
        )
        if r.returncode != 0:
            raise SystemExit(
                f"{cmd!r} on {host} exited {r.returncode}:\n{r.stderr[-2000:]}"
            )
        return r.stdout

    digest = run(DIGEST_COMMAND).strip()
    text = run(HELP_COMMAND)
    rows = parse_help(text)
    short = _short_digest(digest)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"declared-{SERVING_ENGINE}-{short}.json"
    path.write_text(
        json.dumps(
            {
                "record": "knob-declared/1",
                "engine": SERVING_ENGINE,
                "image": IMAGE,
                "digest": digest,
                "captured_on": host,
                "command": HELP_COMMAND,
                "count": len(rows),
                "with_default": sum(1 for r in rows if r["default"] is not None),
                "flags": rows,
            },
            indent=1,
        )
        + "\n"
    )
    (out_dir / f"declared-{SERVING_ENGINE}-{short}.txt").write_text(text)
    return path


def load_declared(out_dir: Path) -> dict[str, Any] | None:
    files = sorted(out_dir.glob(f"declared-{SERVING_ENGINE}-*.json"))
    if not files:
        return None
    loaded: dict[str, Any] = json.loads(files[-1].read_text())
    return loaded


# --------------------------------------------------------------------------
# accepted


def assignments(flags: list[str]) -> dict[str, str | bool]:
    """`["--a", "1", "--b"]` to `{"--a": "1", "--b": True}`. Positional flag
    order does not matter to the engine and must not matter to a contrast."""
    out: dict[str, str | bool] = {}
    i = 0
    while i < len(flags):
        key = flags[i]
        nxt = flags[i + 1] if i + 1 < len(flags) else None
        if nxt is not None and not nxt.startswith("--"):
            out[key] = nxt
            i += 2
        else:
            out[key] = True
            i += 1
    return out


def _strip(line: str) -> str:
    return _PID_PREFIX.sub("", line).strip()


def root_cause(log: str) -> tuple[str | None, bool]:
    """(reason, captured). The last reason-bearing line that is not the
    wrapper; if only the wrapper is there, the cause was lost."""
    lines = [_strip(x) for x in log.splitlines()]
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if not _REASON.search(line) or WRAPPER in line:
            continue
        # A reason that ends in a colon continues on the lines below it
        # (`Failed to find a kernel ... Reasons:` then one line per kernel).
        # Keep those until the next traceback frame or blank line.
        if line.endswith(":"):
            tail = []
            for more in lines[i + 1 : i + 8]:
                if not more or more.startswith(("File ", "Traceback", "During ")):
                    break
                tail.append(more)
            if tail:
                line = line + " " + " ".join(tail)
        return line, True
    for line in reversed(lines):
        if WRAPPER in line:
            return line, False
    return (lines[-1] if lines else None), False


def classify(rec: dict[str, Any]) -> dict[str, Any]:
    """One accepted-column row from one sweep record."""
    launch = rec["launch"]
    row: dict[str, Any] = {
        "cell": rec["cell"],
        "axis": rec.get("axis"),
        "flags": assignments(rec["flags"]),
    }
    if launch.get("ok"):
        row["state"] = "accepted"
        row["reason"] = None
        row["reason_captured"] = True
        return row
    log = launch.get("log") or ""
    reason, captured = root_cause(log)
    parse = _PARSE_ERROR.search(log)
    if parse:
        recorded = row["flags"].get(parse.group("flag"))
        seen = parse.group("seen")
        if recorded is not None and recorded != seen and recorded is not True:
            row["state"] = "harness_defect"
            row["reason"] = reason
            row["reason_captured"] = True
            row["engine_saw"] = seen
            row["record_holds"] = recorded
            row["note"] = (
                "the engine refused a value it never received as recorded; "
                "this row is evidence about the harness, not the rig"
            )
            return row
    row["state"] = "refused" if captured else "refused_reason_lost"
    row["reason"] = reason
    row["reason_captured"] = captured
    if not captured:
        row["note"] = (
            "the harness kept 25 log lines and the engine's cause scrolled "
            "past; a re-run with the full log is owed before this refusal "
            "can be attributed"
        )
    if launch.get("reason") == "timeout":
        row["launch_outcome"] = "timeout"
    return row


# --------------------------------------------------------------------------
# effective


def _levels(rec: dict[str, Any]) -> dict[int, float]:
    return {
        lv["n"]: lv["agg_tok_s"] for lv in rec.get("levels", []) if "agg_tok_s" in lv
    }


def contrasts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Single-flag contrasts among launched cells of one (host, model).

    A pair (parent, child) qualifies when the two flag dicts differ in exactly
    one key -- added, removed or changed. The parent is the cell with the
    shorter flag list, or, for a changed value, the one whose value sorts
    first; direction is reported and a reader can invert it.
    """
    launched = [
        (r, assignments(r["flags"]), _levels(r))
        for r in records
        if r["launch"].get("ok")
    ]
    out: list[dict[str, Any]] = []
    for i, (a, fa, la) in enumerate(launched):
        for b, fb, lb in launched[i + 1 :]:
            keys = {k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
            if len(keys) != 1:
                continue
            (knob,) = keys
            if len(fa) < len(fb) or (
                len(fa) == len(fb) and str(fa.get(knob)) <= str(fb.get(knob))
            ):
                parent, child, fp, fc, lp, lc = a, b, fa, fb, la, lb
            else:
                parent, child, fp, fc, lp, lc = b, a, fb, fa, lb, la
            shared = sorted(set(lp) & set(lc))
            if not shared:
                continue
            per_n = [
                {
                    "n": n,
                    "parent_tok_s": lp[n],
                    "child_tok_s": lc[n],
                    "ratio": round(lc[n] / lp[n], 3),
                }
                for n in shared
            ]
            biggest = max(per_n, key=lambda p: abs(p["ratio"] - 1.0))
            out.append(
                {
                    "knob": knob,
                    "from": fp.get(knob, "absent"),
                    "to": fc.get(knob, "absent"),
                    "context": {k: v for k, v in fp.items() if k != knob},
                    "per_n": per_n,
                    "largest_effect": {"n": biggest["n"], "ratio": biggest["ratio"]},
                    "cites": [
                        {"file": parent["_file"], "cell": parent["cell"]},
                        {"file": child["_file"], "cell": child["cell"]},
                    ],
                }
            )
    out.sort(key=lambda c: (c["knob"], str(c["from"]), str(c["to"]), str(c["context"])))
    return out


# --------------------------------------------------------------------------
# build


def load_records(evidence: list[Path]) -> list[dict[str, Any]]:
    """Every record under every evidence directory, in directory order. A
    record's `_file` is `<directory name>/<file>` so two directories holding
    a file of the same name stay distinguishable in a citation."""
    records = []
    for directory in evidence:
        for path in sorted(directory.glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                rec["_file"] = f"{directory.name}/{path.name}"
                records.append(rec)
    return records


def _link_reruns(rows: list[dict[str, Any]]) -> None:
    """A later record with the same cell id is that cell's re-run. The
    earlier row keeps its state -- it is what was recorded -- and gains
    `rerun`, pointing at the later one; the later gains `rerun_of`. A
    lost reason is *outstanding* only while its row has no re-run."""
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        earlier = seen.get(row["cell"])
        if earlier is not None:
            earlier["rerun"] = dict(row["cite"])
            row["rerun_of"] = dict(earlier["cite"])
        seen[row["cell"]] = row


def build(evidence: list[Path], out_dir: Path) -> dict[str, Any]:
    records = load_records(evidence)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in records:
        groups.setdefault((rec["host"], rec["model"]), []).append(rec)

    declared = load_declared(out_dir)
    tried = {k for r in records for k in assignments(r["flags"])}
    if declared:
        # `--no-x` is argparse's alias for the boolean knob `--x`; a cell that
        # carried the alias tried the knob.
        untried = sorted(
            f["flag"]
            for f in declared["flags"]
            if not tried & ({f["flag"]} | set(f.get("aliases") or []))
        )
        declared_block: dict[str, Any] = {
            "captured": True,
            "digest": declared["digest"],
            "count": declared["count"],
            "with_default": declared["with_default"],
            "file": (
                f"declared-{SERVING_ENGINE}-{_short_digest(declared['digest'])}.json"
            ),
            "tried": sorted(tried),
            "untried": untried,
        }
    else:
        declared_block = {
            "captured": False,
            "command": HELP_COMMAND,
            "why_not_yet": (
                "The parser needs a GPU host to print help at all -- VllmConfig "
                "is constructed while printing and infers the device"
            ),
            "tried": sorted(tried),
            "untried": {
                "unknown": True,
                "searched": [f"declared-{SERVING_ENGINE}-*.json beside this surface"],
            },
        }

    accepted = []
    effective = []
    for (host, model), recs in sorted(groups.items()):
        rows = []
        for rec in recs:
            row = classify(rec)
            row["cite"] = {"file": rec["_file"], "cell": rec["cell"]}
            rows.append(row)
        _link_reruns(rows)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["state"]] = counts.get(row["state"], 0) + 1
        outstanding = [
            row["cell"]
            for row in rows
            if row["state"] == "refused_reason_lost" and "rerun" not in row
        ]
        accepted.append(
            {
                "host": host,
                "model": model,
                "engine": SERVING_ENGINE,
                "counts": counts,
                "lost_reasons_outstanding": outstanding,
                "cells": rows,
            }
        )
        effective.append(
            {
                "host": host,
                "model": model,
                "engine": SERVING_ENGINE,
                "contrasts": contrasts(recs),
            }
        )

    surface = {
        "record": SURFACE_RECORD,
        "issue": 357,
        "engine": SERVING_ENGINE,
        "image": IMAGE,
        "evidence": [str(directory) for directory in evidence],
        "files": sorted({r["_file"] for r in records}),
        "states": {
            "accepted": "launched: /health answered with the weights on the card",
            "refused": "the engine exited and its own reason is in the record",
            "refused_reason_lost": (
                "the engine exited; the record holds only the wrapper line, the "
                "cause scrolled past the 25-line tail. Not attributable."
            ),
            "harness_defect": (
                "the engine refused a value it never received as recorded "
                "(shell-split JSON). Evidence about the harness, not the rig."
            ),
            "untried": "declared by the engine, carried by no cell",
        },
        "declared": declared_block,
        "accepted": accepted,
        "effective": effective,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "surface.json").write_text(json.dumps(surface, indent=1) + "\n")
    (out_dir / "surface.md").write_text(render(surface))
    return surface


def _short_model(model: str) -> str:
    return model.split("/")[-1]


def render(surface: dict[str, Any]) -> str:
    lines = [
        f"# Knob surface — {surface['engine']} `{surface['image']}` (#357)",
        "",
        "Generated by `tools/bench/serving/knobs.py build` from "
        + ", ".join(f"`{e}`" for e in surface["evidence"])
        + "; do not edit. Files: "
        + ", ".join(f"`{f}`" for f in surface["files"])
        + ".",
        "",
        "## 1. Declared",
        "",
    ]
    d = surface["declared"]
    if d["captured"]:
        lines += [
            f"Captured: `{d['file']}` (digest `{d['digest']}`), {d['count']} flags, "
            f"{d['with_default']} with a printed default. Tried by some cell: "
            f"{len(d['tried'])}. **Untried: {len(d['untried'])}.**",
        ]
    else:
        lines += [
            "**Not captured.** Command: `"
            + d["command"]
            + "`. "
            + d["why_not_yet"]
            + ".",
            "",
            f"Flags some cell has carried: {len(d['tried'])} "
            "(" + ", ".join(f"`{t}`" for t in d["tried"]) + "). "
            "Untried count: unknown until the capture lands — not zero.",
        ]
    lines += ["", "## 2. Accepted", ""]
    for block in surface["accepted"]:
        counts = ", ".join(f"{k} {v}" for k, v in sorted(block["counts"].items()))
        outstanding = block["lost_reasons_outstanding"]
        lines += [
            f"### {block['host']} · {_short_model(block['model'])} — {counts}; "
            f"lost reasons outstanding {len(outstanding)}",
            "",
            "| cell | state | reason | cite | re-run |",
            "|---|---|---|---|---|",
        ]
        for row in block["cells"]:
            reason = (row["reason"] or "").replace("|", "\\|")
            if row["state"] == "harness_defect":
                reason = f"engine saw `{row['engine_saw']}`, record holds JSON"
            elif row["state"] == "accepted":
                reason = ""
            link = ""
            if "rerun" in row:
                link = f"→ `{row['rerun']['file']}`"
            elif "rerun_of" in row:
                link = f"re-run of `{row['rerun_of']['file']}`"
            lines.append(
                f"| `{row['cell']}` | {row['state']} | {reason[:140]} | "
                f"`{row['cite']['file']}` | {link} |"
            )
        lines.append("")
    lines += ["## 3. Effective", ""]
    for block in surface["effective"]:
        lines += [
            f"### {block['host']} · {_short_model(block['model'])} — "
            f"{len(block['contrasts'])} single-flag contrasts",
            "",
            "| knob | from → to | context | n: ratio | largest | cites |",
            "|---|---|---|---|---|---|",
        ]
        for c in block["contrasts"]:
            ctx = " ".join(
                f"{k}" if v is True else f"{k}={v}"
                for k, v in sorted(c["context"].items())
            )
            ratios = " ".join(f"{p['n']}:{p['ratio']:.2f}" for p in c["per_n"])
            big = c["largest_effect"]
            cites = ", ".join(f"`{x['cell']}`" for x in c["cites"])
            lines.append(
                f"| `{c['knob']}` | {c['from']} → {c['to']} | `{ctx}` | {ratios} | "
                f"{big['ratio']:.2f}x at n={big['n']} | {cites} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "build":
        surface = build([Path(a) for a in argv[3:]], Path(argv[2]))
        for block in surface["accepted"]:
            print(block["host"], _short_model(block["model"]), block["counts"])
        return 0
    if len(argv) == 4 and argv[1] == "declared":
        path = capture_declared(argv[2], Path(argv[3]))
        print(path)
        return 0
    print(__doc__.split("Usage::")[1])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
