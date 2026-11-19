#!/usr/bin/env python3
"""Build the hardware capabilities table from the newest wave file of every slice.

  build_db.py [--built YYYY-MM-DD] [--out PATH] [--quoted PATH]

Writes the shipped table (``data/hardware-capabilities.json`` by default): per cell
the value, the source id, ``how``, ``official`` and ``scope``; per source its URL,
publisher, ``official`` and the date its page was read. ``--quoted PATH`` also
writes the whole table, every cell with its page's words, for the checks
(``verify_quotes.py``, ``verify_values.py``). ``--built`` is the table's build
date (today when not given): the build reads nothing else that changes, so the
same inputs and date give the same bytes.

Rows keep their cells (value, source, quote, how, official). Keys are made
nested, source ids get the slice as a prefix so they stay unique, and every row
is checked against ``schema.json``: the fields of its kind are all present,
every filled cell has a source and a quote, every empty cell a why. Nothing is
repaired silently: a row or cell that does not fit is listed in the report.
Standard library only; reads no page.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
from collections.abc import Iterator
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHIPPED = REPO / "data" / "hardware-capabilities.json"
SCHEMA = json.loads((HERE / "schema.json").read_text(encoding="utf-8"))
SLICES = ("nvidia-gpu", "amd-gpu", "intel-gpu", "intel-cpu", "amd-cpu", "apple-soc")
KIND_OF = {
    "nvidia-gpu": "gpu",
    "amd-gpu": "gpu",
    "intel-gpu": "gpu",
    "intel-cpu": "cpu",
    "amd-cpu": "cpu",
    "apple-soc": "soc",
}
# The day each wave's pages were read: a source is dated by the wave file that
# lists it. A new wave adds its line.
READ = {"wave-3": "2026-11-18", "wave-4": "2026-11-18"}
# What a value is said about, where it is not the product itself. Readers who did
# not fill the table found no wrong value in 300 sampled cells, and 57 "weak"
# ones: nearly all are facts a vendor states for an architecture, a compute
# capability, a product family or a driver, which a row inherits. The build names
# that scope on every cell of these fields, so no reader takes it for a
# per-product statement. A cell without "scope" is said of the product on its
# own page.
SCOPE = {
    ("nvidia", "formats.matrix.precisions"): "compute-capability",
    ("nvidia", "formats.fp16"): "compute-capability",
    ("nvidia", "formats.int8_dot"): "compute-capability",
    ("nvidia", "api.cuda_compute_capability"): "series",
    ("nvidia", "api.vulkan"): "architecture",
    ("nvidia", "api.opencl"): "driver",
    ("nvidia", "segment"): "inferred",
    ("apple", "formats.fp16"): "family",
    ("apple", "api.metal"): "family",
    ("amd", "formats.matrix.precisions"): "architecture",
    ("amd", "api.vulkan"): "driver",
    ("intel", "formats.matrix.precisions"): "architecture",
    ("intel", "formats.fp16"): "architecture",
    ("intel", "formats.int8_dot"): "architecture",
    ("intel", "api.oneapi"): "family",
}
ROW_ID_KEYS = ("id", "vendor", "kind")

# A wave that is not a slice of its own: cells for rows that exist, read from a
# third party's per-product pages (techpowerup's GPU database).
OVERLAYS = ("wave-4/tpu-gpu.json",)
OVERLAY_ROW_KEYS = ("id", "vendor", "kind", "tpu_name")
# Fields where the two sides name or measure by different conventions (a code
# name's spelling, base or boost clock): the third party's cell fills an empty
# cell and is otherwise left out.
FILL_ONLY = ("architecture", "compute.clock_mhz")
# A row whose third-party page is the same chip in another product: every cell
# taken from that page says so.
VARIANT = {
    "intel-iris-xe-graphics-13th-mobile-80eu-1335u": (
        "techpowerup's page names the Core i5-13500H as its only variant; "
        "the row is the 1335U"
    ),
}
# Vendors round their headline rates; the third party computes them.
LOOSE = {"compute.fp32_tflops": 0.03}


def is_cell(node: Any) -> bool:
    return isinstance(node, dict) and "v" in node


def nest(row: dict[str, Any]) -> dict[str, Any]:
    """A row with nested keys, whatever mix of flat ("memory.size_gb") and nested
    it came with, at any depth ("formats": {"matrix.name": cell} too)."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict) and not is_cell(value):
            value = nest(value)
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        last = parts[-1]
        if (
            isinstance(value, dict)
            and not is_cell(value)
            and isinstance(node.get(last), dict)
        ):
            node[last].update(value)
        else:
            node[last] = value
    return out


def at(row: dict[str, Any], path: str) -> Any:
    node: Any = row
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def walk(node: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if is_cell(node):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else key)


def put(row: dict[str, Any], path: str, cell: dict[str, Any]) -> None:
    node = row
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = cell


def _quarter(text: str) -> int | None:
    if "q" in text:
        return int(text.split("q")[1][:1])
    if len(text) >= 7 and text[5:7].isdigit():
        return (int(text[5:7]) + 2) // 3
    return None


def same(field: str, ours: Any, theirs: Any) -> bool:
    """Whether two values of one field say the same thing, allowing for how each
    is written."""
    if (
        isinstance(ours, dict)
        and isinstance(theirs, dict)
        and "count" in ours
        and "count" in theirs
    ):
        return bool(ours["count"] == theirs["count"])
    if isinstance(ours, bool) or isinstance(theirs, bool):
        return bool(ours == theirs)
    if isinstance(ours, int | float) and isinstance(theirs, int | float):
        width = LOOSE.get(field, 0.01) * max(abs(ours), abs(theirs), 1e-9)
        return abs(ours - theirs) <= width
    if isinstance(ours, list) and isinstance(theirs, list):
        return {str(x).lower() for x in ours} == {str(x).lower() for x in theirs}
    a, b = str(ours).strip().lower(), str(theirs).strip().lower()
    if field == "launch":
        # "2019", "2019-Q4" and "2019-10" agree when the coarser one contains the
        # finer one.
        if a[:4] != b[:4]:
            return False
        qa, qb = _quarter(a), _quarter(b)
        return qa is None or qb is None or qa == qb
    if field in ("architecture", "memory.type", "api.vulkan", "api.opencl"):
        a, b = a.replace(".0", ""), b.replace(".0", "")
        return a in b or b in a
    return a == b


def _source(source: dict[str, Any], wave: str) -> dict[str, Any]:
    keys = ("url", "title", "publisher", "official", "fetch")
    return {**{k: source.get(k) for k in keys}, "read": READ[wave]}


def overlay(
    rows: list[dict[str, Any]], sources: dict[str, Any], report: list[str]
) -> None:
    by_id = {row["id"]: row for row in rows}
    tally: dict[str, int] = {}

    def count(what: str) -> None:
        tally[what] = tally.get(what, 0) + 1

    for rel in OVERLAYS:
        path = HERE / rel
        if not path.exists():
            report.append(f"== overlay {rel}: no file")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        name = doc["slice"]
        for source in doc.get("sources", []):
            sources[f"{name}:{source['id']}"] = _source(source, path.parent.name)
        for extra in doc.get("rows", []):
            row = by_id.get(extra["id"])
            if row is None:
                report.append(f"overlay {name}: no row {extra['id']}")
                continue
            # A page that describes the card with another memory size (one page
            # for two sizes) says nothing about this row's memory.
            other_size = None
            for field in ("memory.size_gb", "memory.type"):
                ours, theirs = at(row, field), at(extra, field)
                if (
                    is_cell(ours)
                    and ours.get("v") is not None
                    and is_cell(theirs)
                    and not same(field, ours["v"], theirs["v"])
                ):
                    other_size = (
                        f"{field} {theirs['v']!r} on the page, {ours['v']!r} in the row"
                    )
                    break
            if other_size:
                report.append(
                    f"== {name} {extra['id']}: the page is another memory variant "
                    f"({other_size}); its memory cells were not taken"
                )
            cells = {k: v for k, v in extra.items() if k not in OVERLAY_ROW_KEYS}
            for field, found in walk(cells):
                if other_size and field.startswith("memory."):
                    count("not taken: page is another memory variant")
                    continue
                cell = dict(found, src=f"{name}:{found['src']}")
                if extra["id"] in VARIANT:
                    cell["scope"], cell["note"] = "variant", VARIANT[extra["id"]]
                have = at(row, field)
                if not is_cell(have) or have.get("v") is None:
                    put(row, field, cell)
                    count("filled an empty or new cell")
                elif field in FILL_ONLY:
                    count("left out: named or measured by another convention")
                elif same(field, have["v"], cell["v"]):
                    if have.get("official"):
                        have["confirmed_by"] = cell["src"]
                        count("agrees with the official cell")
                    else:
                        put(row, field, cell)
                        count("replaced an unofficial cell, same value")
                elif not have.get("official"):
                    cell["was"] = {"v": have["v"], "src": have.get("src")}
                    put(row, field, cell)
                    count("replaced an unofficial cell, other value")
                    report.append(
                        f"== {name} {extra['id']} {field}: {cell['v']!r} replaces "
                        f"the unofficial {have['v']!r}"
                    )
                else:
                    have["differs"] = {k: cell[k] for k in ("v", "src", "quote")}
                    count("differs from the official cell (official kept)")
                    report.append(
                        f"== {name} {extra['id']} {field}: official {have['v']!r}, "
                        f"{name} {cell['v']!r}"
                    )
        report.append(
            f"== overlay {name}: {len(doc.get('rows', []))} rows; "
            + "; ".join(f"{n} {what}" for what, n in sorted(tally.items()))
        )


def newest(slice_name: str) -> pathlib.Path | None:
    for wave in range(9, 0, -1):
        path = HERE / f"wave-{wave}" / f"{slice_name}.json"
        if path.exists():
            return path
    return None


def _prefix(cell: dict[str, Any], slice_name: str) -> None:
    for key in ("src", "also"):
        if isinstance(cell.get(key), str):
            cell[key] = f"{slice_name}:{cell[key]}"
        elif isinstance(cell.get(key), list):
            cell[key] = [f"{slice_name}:{one}" for one in cell[key]]


def _check_cell(
    where: tuple[str, str, str],
    cell: dict[str, Any],
    sources: dict[str, Any],
    report: list[str],
) -> bool:
    """Prefix the cell's source ids and check it: False when it is, or is made,
    empty. ``where`` is the slice, the row id and the field."""
    slice_name, ident, field = where
    # Every cell that names a source gets the prefix, an empty one too: a page
    # that states a thing is not there is cited like any other.
    _prefix(cell, slice_name)
    if cell.get("v") is None:
        if not cell.get("why"):
            report.append(f"{ident}: {field} is empty without a why")
        return False
    if not cell.get("src") or not cell.get("quote"):
        # The table's first rule: no value without a quote. Such a cell is
        # emptied here, and the report says so.
        report.append(
            f"== emptied {ident} {field}: it had the value {cell['v']!r} "
            "and no source or quote"
        )
        was = cell["v"]
        cell.clear()
        cell.update(
            {
                "v": None,
                "why": f"a wave gave {was!r} with no page quoted; emptied at the build",
            }
        )
        return False
    for one in [cell.get("src"), *list(cell.get("also") or [])]:
        if one and one not in sources:
            report.append(f"{ident}: {field} names a source that is not listed: {one}")
    if "official" not in cell and cell.get("src") in sources:
        cell["official"] = bool(sources[cell["src"]].get("official"))
    return True


def _scope_and_patch(
    row: dict[str, Any],
    scoped: dict[tuple[str, str, str], int],
    report: list[str],
) -> None:
    ident = row["id"]
    for field, cell in walk({k: v for k, v in row.items() if k not in ROW_ID_KEYS}):
        if cell.get("v") is None:
            continue
        scope = None if row["kind"] == "cpu" else SCOPE.get((row["vendor"], field))
        if field == "api.rocm" and cell["v"] is False:
            scope = "absence"
        if scope:
            cell["scope"] = scope
            key = (row["vendor"], field, scope)
            scoped[key] = scoped.get(key, 0) + 1
        # AMD's current ROCm matrix (10.1.0) lists the card; the operating
        # systems in the cell came from the older page that has moved and prints
        # other versions.
        value = cell["v"]
        if (
            field == "api.rocm"
            and isinstance(value, dict)
            and value.get("rocm") == "10.1.0"
            and "os" in value
        ):
            del value["os"]
            cell["note"] = (
                str(cell.get("note", "")) + " The operating-system list was "
                "dropped at the build: it came from the moved 7.14.0 page, "
                "not from the 10.1.0 matrix."
            ).strip()
            report.append(
                f"== patched {ident}: operating systems dropped from api.rocm"
            )
    # NVIDIA's Tensor Core table read with its column spans: the 12.x row also
    # says Yes under FP6, which the first schema's set lacked.
    formats = at(row, "formats.matrix.precisions")
    if (
        is_cell(formats)
        and isinstance(formats.get("v"), list)
        and "fp4" in formats["v"]
        and "fp6" not in formats["v"]
        and "FP6" in str(formats.get("quote", ""))
    ):
        formats["v"].insert(formats["v"].index("fp4"), "fp6")
        formats["note"] = (
            str(formats.get("note", "")) + " fp6 added at the build: the quoted row "
            "says Yes under FP6 (table read with its column spans, 2026-11-18)."
        ).strip()
        report.append(f"== patched {ident}: fp6 added to formats.matrix.precisions")


def _fields(kind: str, vendor: str) -> list[str]:
    spec = SCHEMA["kinds"][kind]
    return [*spec["fields"], *spec["vendor_fields"].get(vendor, [])]


def slice_rows(
    sources: dict[str, Any] | None = None, report: list[str] | None = None
) -> list[dict[str, Any]]:
    """Every slice's rows, nested and checked, before the overlay."""
    sources = {} if sources is None else sources
    report = [] if report is None else report
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    scoped: dict[tuple[str, str, str], int] = {}
    for slice_name in SLICES:
        path = newest(slice_name)
        if path is None:
            report.append(f"{slice_name}: no wave file")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        kind = KIND_OF[slice_name]
        vendor = slice_name.split("-")[0]
        for source in doc.get("sources", []):
            sources[f"{slice_name}:{source['id']}"] = _source(source, path.parent.name)
        filled = empty = 0
        for raw in doc.get("rows", []):
            row = nest(raw)
            row["kind"], row["vendor"] = kind, row.get("vendor", vendor)
            ident = row.get("id")
            if not ident or ident in seen:
                report.append(f"{slice_name}: row id missing or twice: {ident!r}")
                continue
            seen.add(ident)
            for field in _fields(kind, row["vendor"]):
                if not is_cell(at(row, field)):
                    report.append(f"{ident}: field {field} is missing or not a cell")
            body = {k: v for k, v in row.items() if k not in ROW_ID_KEYS}
            for field, cell in walk(body):
                if _check_cell((slice_name, ident, field), cell, sources, report):
                    filled += 1
                else:
                    empty += 1
            _scope_and_patch(row, scoped, report)
            rows.append(row)
        report.append(
            f"== {slice_name}: {path.parent.name}, {len(doc.get('rows', []))} rows, "
            f"{filled} filled cells, {empty} empty cells"
        )
    for (vendor, field, scope), count in sorted(scoped.items()):
        report.append(f"== scope {scope}: {vendor} {field}, {count} cells")
    return rows


def build(built: str) -> tuple[dict[str, Any], list[str]]:
    """The whole table, every cell with its quote, and the build's report."""
    sources: dict[str, Any] = {}
    report: list[str] = []
    rows = slice_rows(sources, report)
    overlay(rows, sources, report)
    table = {
        "schema": SCHEMA["schema"],
        "built": built,
        "sources": [{"id": key, **value} for key, value in sources.items()],
        "rows": rows,
    }
    return table, report


def _strip(node: Any, keep: tuple[str, ...]) -> Any:
    if is_cell(node):
        return {k: node[k] for k in keep if k in node}
    if isinstance(node, dict):
        return {k: _strip(v, keep) for k, v in node.items()}
    return node


def shipped(table: dict[str, Any]) -> dict[str, Any]:
    """The table the package carries: the shipped keys of each cell, and the
    sources its cells cite."""
    keep = tuple(SCHEMA["shipped"]["cell"])
    rows = [_strip(row, keep) for row in table["rows"]]
    cited = {cell["src"] for row in rows for _, cell in walk(row) if "src" in cell}
    source_keys = SCHEMA["shipped"]["source"]
    sources = [
        {k: source[k] for k in source_keys}
        for source in table["sources"]
        if source["id"] in cited
    ]
    return {
        "schema": table["schema"],
        "built": table["built"],
        "sources": sources,
        "rows": rows,
    }


def text(table: dict[str, Any]) -> str:
    return json.dumps(table, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--built", default=datetime.date.today().isoformat())
    parser.add_argument("--out", type=pathlib.Path, default=SHIPPED)
    parser.add_argument("--quoted", type=pathlib.Path)
    args = parser.parse_args(argv)
    datetime.date.fromisoformat(args.built)
    table, report = build(args.built)
    args.out.write_text(text(shipped(table)), encoding="utf-8")
    if args.quoted:
        args.quoted.write_text(text(table), encoding="utf-8")
    problems = [line for line in report if not line.startswith("==")]
    print(
        f"built {len(table['rows'])} rows, {len(table['sources'])} sources; "
        f"{len(problems)} schema problems"
    )
    print("\n".join(report))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
