#!/usr/bin/env python3
"""Fit the CUDA speed shares the product ships, from public pages only.

Reads the rows of llama.cpp's CUDA scoreboard (``scoreboard-15013.json`` beside
this script: Llama 2 7B at Q4_0, pp512 and tg128 per card, as the page states
them) and the shipped hardware table (``data/hardware-capabilities.json``), and
matches each card to its row by name and memory size. For each matched card:

  decode share  = tg128 x the file's bytes / the card's memory bandwidth
  prefill share = 2 x the parameters x pp512 / the card's rate

where the rate is the matrix units' FP16 rate on a card whose matrix units take
FP16 (the ``matrix`` path) and the FP32 rate on any other (the ``vector`` path).
Each share shipped is the median of its path's cards, with the lowest, the
highest, the count and the card furthest from the median. ``--json`` prints
what the product ships (``hubwire.DECODE_SHARES``, ``estimate.PREFILL_SHARES``);
a test holds the two equal. Standard library only; reads no page.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROWS = HERE / "scoreboard-15013.json"
TABLE = HERE.parent.parent / "data" / "hardware-capabilities.json"

#: The build the scoreboard ran, and the width class its file is of.
BUILD = "cuda"
WIDTH = "4bit"
#: Places a share is rounded to; its lowest card is rounded down and its highest
#: up, so the spread stated holds every card.
PLACES = 3
GIB = 1 << 30
#: "llama 7B Q4_0 3.56 GiB 6.74 B": the size in GiB and the parameters in billions.
MODEL = re.compile(r"([\d.]+) GiB ([\d.]+) B$")
#: One scoreboard row: the card, its memory, pp512 and tg128 (each with its
#: spread), and the commit, which one row leaves out.
ROW = re.compile(
    r"((?:RTX|GTX|Titan|Tesla|Quadro)[\w .]*?) (\d+) GB / \w+ / \d+ bit "
    r"([\d.]+) [±+] [\d.]+ ([\d.]+) [±+] [\d.]+(?: \w{7})?$"
)


def _cell(row: dict, field: str):
    node = row
    for part in field.split("."):
        node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            return None
    return node.get("v") if isinstance(node, dict) and "v" in node else None


def _key(name: str, memory_gb: object) -> str:
    plain = name.lower().replace("geforce", "").replace("nvidia", "")
    return re.sub(r"[^a-z0-9]", "", plain) + str(memory_gb)


def cards(rows_doc: dict, table: dict) -> list[dict]:
    """Every scoreboard row matched to a table row, with its two shares."""
    size_gib, params_b = MODEL.search(rows_doc["model"]).groups()
    file_bytes = float(size_gib) * GIB
    params = float(params_b) * 1e9
    by_key: dict[str, dict] = {}
    for row in table["rows"]:
        if row["vendor"] == "nvidia" and row["kind"] == "gpu":
            size = _cell(row, "memory.size_gb")
            by_key.setdefault(_key(_cell(row, "name") or "", int(size or 0)), row)
    found = []
    for quoted in rows_doc["rows"]:
        parsed = ROW.match(quoted)
        if parsed is None:
            continue
        name, memory, pp, tg = parsed.groups()
        row = by_key.get(_key(name, int(memory)))
        if row is None:
            continue
        bandwidth = _cell(row, "memory.bandwidth_gbps")
        matrix = "fp16" in (_cell(row, "formats.matrix.precisions") or [])
        rate = (
            (_cell(row, "compute.matrix_rates") or {}).get("fp16")
            if matrix
            else _cell(row, "compute.fp32_tflops")
        )
        if not bandwidth or not rate:
            continue
        found.append(
            {
                "card": f"{name} {memory} GB",
                "row": row["id"],
                "path": "matrix" if matrix else "vector",
                "decode": float(tg) * file_bytes / (bandwidth * 1e9),
                "prefill": 2 * params * float(pp) / (rate * 1e12),
            }
        )
    return found


def share(group: list[dict], what: str) -> dict:
    """The median of ``what`` over ``group``, its spread and its worst card."""
    values = [one[what] for one in group]
    middle = statistics.median(values)
    worst = max(group, key=lambda one: abs(one[what] / middle - 1))
    return {
        "value": round(middle, PLACES),
        "cards": len(group),
        "low": math.floor(min(values) * 10**PLACES) / 10**PLACES,
        "high": math.ceil(max(values) * 10**PLACES) / 10**PLACES,
        "worst": worst["card"],
    }


def shares(found: list[dict]) -> dict:
    """What the product ships: decode by build, path and width class; prefill by
    build and path."""
    paths = sorted({one["path"] for one in found})
    group = {path: [one for one in found if one["path"] == path] for path in paths}
    return {
        "source": None,
        "decode": {BUILD: {p: {WIDTH: share(group[p], "decode")} for p in paths}},
        "prefill": {BUILD: {p: share(group[p], "prefill") for p in paths}},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="print the shipped shares")
    args = parser.parse_args(argv)
    rows_doc = json.loads(ROWS.read_text(encoding="utf-8"))
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    found = cards(rows_doc, table)
    fitted = shares(found)
    fitted["source"] = rows_doc["url"]
    if args.json:
        json.dump(fitted, sys.stdout, indent=1, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    print(f"{len(rows_doc['rows'])} rows, {len(found)} matched to the table")
    print(f"{'card':24} {'path':6} {'decode':>7} {'prefill':>8}")
    for one in sorted(found, key=lambda one: (one["path"], one["decode"])):
        print(
            f"{one['card']:24} {one['path']:6} {one['decode']:7.3f} "
            f"{one['prefill']:8.3f}"
        )
    for what in ("decode", "prefill"):
        for path in sorted({one["path"] for one in found}):
            group = [one for one in found if one["path"] == path]
            got = share(group, what)
            error = statistics.median(
                abs(one[what] / statistics.median(o[what] for o in group) - 1)
                for one in group
            )
            print(
                f"{what} {path}: {got['value']} over {got['cards']} cards "
                f"({got['low']} to {got['high']}, worst {got['worst']}), "
                f"median error {error:.3f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
