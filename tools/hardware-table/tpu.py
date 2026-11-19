#!/usr/bin/env python3
"""techpowerup's GPU database, read into the table's cell format (wave 4).

  tpu.py index        the listing page and a few text searches -> wave-4/tpu-index.json
  tpu.py map          each GPU row of the slices -> its techpowerup page (tpu-map.json)
  tpu.py fetch [N]    read up to N mapped pages that are not cached; stops when refused
  tpu.py fill         parse the cached pages -> wave-4/tpu-gpu.json (cells with quotes)

Every page is one spec sheet with the same sections, so the cells are parsed, not
typed: a quote is the label and the value as they stand side by side on the page.
Pages are read through ``verify_quotes.fetch`` (``scrape`` for this host), one at
a time, cached. ``fill`` reads only cached pages: a row whose page is not cached
is listed as left. Only the site's text search is used to find a page; its filter
links are left alone, as the site asks of automated readers.
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_db
import verify_quotes

HERE = pathlib.Path(__file__).resolve().parent
WAVE = HERE / "wave-4"
BASE = "https://www.techpowerup.com/gpu-specs/"
SEARCHES = (
    "4060 Ti",
    "RTX 3060",
    "GTX 1650",
    "GTX 1060",
    "RX 6700",
    "RX 6400",
    "RX 560",
    "RX 480",
    "RX 470",
    "RX 460",
    "Arc",
    "UHD Graphics",
    "Iris Xe",
)
LINK = re.compile(
    r'(?is)<a[^>]*href="(?:https://www\.techpowerup\.com)?(/gpu-specs/[^"#?]+\.c\d+)"'
    r"[^>]*>(.*?)</a>"
)


def clean(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", verify_quotes.marks(text))
    text = re.sub(r"(?is)</?(sup|sub|span|b|i|em|strong|a|font|u)\b[^>]*>", "", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def links(raw: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path, text in LINK.findall(raw):
        name = clean(text)
        if name:
            found.setdefault(name, set()).add("https://www.techpowerup.com" + path)
    return found


def index() -> None:
    WAVE.mkdir(exist_ok=True)
    names: dict[str, set[str]] = {}
    log = []
    for url in [BASE] + [BASE + "?q=" + urllib.parse.quote(q) for q in SEARCHES]:
        raw, how = verify_quotes.fetch(url)
        if raw is None:
            log.append(f"NOT READ {how}  {url}")
            if "429" in how:
                break
            continue
        got = links(raw)
        log.append(f"{len(got):4d} names  {url}")
        for name, urls in got.items():
            names.setdefault(name, set()).update(urls)
    out = {name: sorted(urls) for name, urls in sorted(names.items())}
    (WAVE / "tpu-index.json").write_text(json.dumps(out, indent=1))
    print("\n".join(log))
    print(f"{len(out)} names in wave-4/tpu-index.json")


# Rows whose name is not techpowerup's name for the card: row id -> techpowerup's
# name, or its name and the page id where the site has several pages under one
# name (older generations first). The fill step checks each choice against the
# row's launch year.
NAMED: dict[str, str | tuple[str, str]] = {
    "nvidia-rtx-5060-ti-16gb": "GeForce RTX 5060 Ti 16 GB",
    "nvidia-rtx-5060-ti-8gb": "GeForce RTX 5060 Ti 8 GB",
    "nvidia-rtx-4060-ti-8gb": "GeForce RTX 4060 Ti 8 GB",
    "nvidia-rtx-4060-ti-16gb": "GeForce RTX 4060 Ti 16 GB",
    "nvidia-rtx-2060-12gb": "GeForce RTX 2060 12 GB",
    "nvidia-rtx-3080-12gb": "GeForce RTX 3080 12 GB",
    "nvidia-rtx-3060-ti-gddr6x": "GeForce RTX 3060 Ti GDDR6X",
    "nvidia-rtx-4070-gddr6": "GeForce RTX 4070 GDDR6",
    "nvidia-rtx-3060-12gb": "GeForce RTX 3060 12 GB",
    "nvidia-rtx-3060-8gb": "GeForce RTX 3060 8 GB",
    "nvidia-rtx-3050-8gb": "GeForce RTX 3050 8 GB",
    "nvidia-rtx-3050-6gb": "GeForce RTX 3050 6 GB",
    "nvidia-gtx-1650-gddr5": "GeForce GTX 1650",
    "nvidia-gtx-1650-gddr6": "GeForce GTX 1650 GDDR6",
    "nvidia-gtx-1060-3gb": "GeForce GTX 1060 3 GB",
    "amd-rx-9060-xt-16gb": "Radeon RX 9060 XT 16 GB",
    "amd-rx-9060-xt-8gb": "Radeon RX 9060 XT 8 GB",
    "amd-rx-570": "Radeon RX 570",
    "amd-rx-480-8gb": "Radeon RX 480",
    "amd-rx-480-4gb": "Radeon RX 480",
    "intel-arc-a770-16gb": "Arc A770",
    "intel-arc-a770-8gb": "Arc A770",
    "intel-arc-graphics-core-ultra-series1-155h": "Arc Graphics 128EU Mobile",
    "intel-arc-graphics-core-ultra-series1-125h": "Arc Graphics 112EU Mobile",
    "intel-graphics-core-ultra-series1-135u": "Arc Graphics 64EU Mobile",
    "intel-arc-140v-core-ultra-series2-258v": "Arc 140V Mobile",
    "intel-arc-130v-core-ultra-series2-226v": "Arc 130V Mobile",
    "intel-arc-140t-core-ultra-series2-285h": "Arc 140T Mobile",
    "intel-graphics-core-ultra-series2-285k": "Arc Graphics 64EU",
    "intel-uhd-graphics-770": ("UHD Graphics 770", "3844"),
    "intel-uhd-graphics-730": ("UHD Graphics 730", "3877"),
    "intel-uhd-graphics-630": ("UHD Graphics 630", "3105"),
    "intel-iris-xe-graphics-1185g7": "Iris Xe Graphics G7 96EU Mobile",
    "intel-iris-xe-graphics-1135g7": "Iris Xe Graphics G7 80EU Mobile",
    "intel-iris-xe-graphics-12th-mobile-96eu-1260p": (
        "Iris Xe Graphics 96EU Mobile",
        "3881",
    ),
    "intel-iris-xe-graphics-12th-mobile-80eu-1235u": (
        "Iris Xe Graphics 80EU Mobile",
        "3882",
    ),
    "intel-iris-xe-graphics-13th-mobile-96eu-1360p": (
        "Iris Xe Graphics 96EU Mobile",
        "4145",
    ),
    "intel-iris-xe-graphics-13th-mobile-80eu-1335u": (
        "Iris Xe Graphics 80EU Mobile",
        "4059",
    ),
}


def norm(name: str) -> str:
    name = re.sub(r"\b(nvidia|amd|intel|graphics|gpu)\b|[™®]", " ", name.lower())
    name = re.sub(r"(\d)\s*gb\b", r"\1 gb", name).replace("-", " ")
    return re.sub(r"\s+", " ", name).strip()


def value(cell: Any) -> Any:
    return cell.get("v") if isinstance(cell, dict) else cell


def gpu_rows() -> list[dict[str, Any]]:
    """The GPU rows of the slices, before techpowerup's cells are laid over them."""
    return [row for row in build_db.slice_rows() if row["kind"] == "gpu"]


def mapping() -> None:
    names = json.loads((WAVE / "tpu-index.json").read_text())
    by_norm: dict[str, list[str]] = {}
    for name in names:
        by_norm.setdefault(norm(name), []).append(name)
    rows = gpu_rows()
    out, left = {}, []
    for row in rows:
        want = NAMED.get(row["id"])
        page_id = None
        if isinstance(want, tuple):
            want, page_id = want
        if want is None:
            hits = by_norm.get(norm(value(row["name"])), [])
            want = hits[0] if len(hits) == 1 else None
        urls = names.get(want, []) if want else []
        if page_id:
            urls = [u for u in urls if u.endswith(".c" + page_id)]
        if len(urls) == 1:
            out[row["id"]] = {"tpu_name": want, "url": urls[0]}
        else:
            left.append(
                f"{row['id']} | {value(row['name'])} | {want} | {len(urls)} pages"
            )
    (WAVE / "tpu-map.json").write_text(json.dumps(out, indent=1))
    pages = len({m["url"] for m in out.values()})
    print(f"{len(out)} of {len(rows)} GPU rows mapped; {pages} pages")
    print("\n".join("  left: " + line for line in left))


def fetch_pages(limit: int) -> None:
    mapped = json.loads((WAVE / "tpu-map.json").read_text())
    pages = sorted({m["url"] for m in mapped.values()})
    read = have = 0
    for url in pages:
        if verify_quotes.cached(url):
            have += 1
            continue
        if read >= limit:
            break
        raw, how = verify_quotes.fetch(url)
        if raw is None:
            print(f"stopped: {how}  {url}")
            break
        read += 1
    print(f"{len(pages)} pages wanted; {have + read} cached ({read} read now)")


SECTION = re.compile(
    r'(?is)<section[^>]*class="[^"]*details[^"]*"[^>]*>' r"(.*?)</section>"
)
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        (
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        )
    )
}
CHIP = re.compile(r"(\w+) \[([^\]]*)\]")


def sheet(raw: str) -> dict[str, dict[str, str]]:
    """The page's spec sheet: section title -> {label: value}, in its own words."""
    out = {}
    for block in SECTION.findall(raw):
        head = re.search(r"(?is)<h[1-4][^>]*>(.*?)</h[1-4]>", block)
        pairs = re.findall(r"(?is)<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", block)
        if head and pairs:
            out[clean(head.group(1))] = {clean(a): clean(b) for a, b in pairs}
    return out


def number(text: str, unit: str) -> float | None:
    hit = re.search(r"([\d.,]+)\s*" + unit, text)
    return float(hit.group(1).replace(",", "")) if hit else None


def flops(text: str) -> float | None:
    """'10.05 TFLOPS (2:1)' or '157.1 GFLOPS (1:32)' as TFLOPS."""
    for unit, scale in (("TFLOPS", 1.0), ("GFLOPS", 1e-3), ("MFLOPS", 1e-6)):
        got = number(text, unit)
        if got is not None:
            return round(got * scale, 6)
    return None


def formats(text: str) -> list[str] | None:
    """A format line as the list of formats the page marks supported, lower case.

    The line names every format, each followed by its mark: 'INT4 [4-bit Integer:
    Not Supported] INT8 [8-bit Integer: Supported]'. 'Not Supported' alone is an
    empty list. A line without marks says nothing that can be read: None.
    """
    if text.strip().lower() == "not supported":
        return []
    chips = CHIP.findall(text)
    if not chips or any(not mark.rstrip().endswith("Supported") for _, mark in chips):
        return None
    return [
        name.lower()
        for name, mark in chips
        if not mark.rstrip().endswith("Not Supported")
    ]


def rates(pairs: dict[str, str]) -> dict[str, float] | None:
    """A 'Matrix Performance' section as {format: rate}: TOPS for integers, TFLOPS
    for floats."""
    out = {}
    for label, text in pairs.items():
        got = number(text, "TOPS") if "TOPS" in text else flops(text)
        # A line that is not a rate ("Sparse Matrix 2x Throughput") is left in the
        # quote and out of the value.
        if got is not None:
            out[label.lower()] = got
    return out or None


Cells = dict[str, tuple[Any, str, str, str | None]]


def _put(
    out: Cells,
    spec: dict[str, dict[str, str]],
    where: tuple[str, str, str],
    v: Any,
    how: str = "stated",
    note: str | None = None,
) -> None:
    field, section, label = where
    text = (spec.get(section) or {}).get(label)
    if text is not None and v is not None:
        out[field] = (v, f"{label} {text}", how, note)


def _card_cells(spec: dict[str, dict[str, str]], out: Cells) -> None:
    def get(section: str, label: str) -> str | None:
        return (spec.get(section) or {}).get(label)

    for card in ("Graphics Card", "Integrated Graphics", "Mobile Graphics"):
        text = get(card, "Release Date") or ""
        hit = re.search(r"([A-Za-z]{3})[a-z]*\.? (?:\d{1,2}[a-z]{2}, )?(\d{4})", text)
        if hit and hit.group(1).lower() in MONTHS:
            month = MONTHS[hit.group(1).lower()]
            _put(
                out,
                spec,
                ("launch", card, "Release Date"),
                f"{hit.group(2)}-{month:02d}",
            )
    _put(
        out,
        spec,
        ("architecture", "Graphics Processor", "Architecture"),
        get("Graphics Processor", "Architecture"),
    )
    _put(
        out,
        spec,
        ("chip", "Graphics Processor", "GPU Name"),
        get("Graphics Processor", "GPU Name"),
    )
    text = get("Memory", "Memory Size") or ""
    size = number(text, "GB") or (number(text, "MB") or 0) / 1024 or None
    _put(out, spec, ("memory.size_gb", "Memory", "Memory Size"), size)
    kind = get("Memory", "Memory Type")
    if kind:
        shared = "shared" in kind.lower()
        _put(
            out,
            spec,
            ("memory.type", "Memory", "Memory Type"),
            "shared" if shared else kind,
        )
    _put(
        out,
        spec,
        ("memory.bus_bits", "Memory", "Memory Bus"),
        number(get("Memory", "Memory Bus") or "", "bit"),
    )
    _put(
        out,
        spec,
        ("memory.bandwidth_gbps", "Memory", "Bandwidth"),
        number(get("Memory", "Bandwidth") or "", "GB/s"),
    )
    text = get("Clock Speeds", "Memory Clock") or ""
    rate = (
        number(text, "Gbps effective")
        or (number(text, "Mbps effective") or 0) / 1000
        or None
    )
    _put(out, spec, ("memory.speed_gbps", "Clock Speeds", "Memory Clock"), rate)


def _compute_cells(spec: dict[str, dict[str, str]], out: Cells) -> None:
    def get(section: str, label: str) -> str | None:
        return (spec.get(section) or {}).get(label)

    for label in ("Boost Clock", "GPU Clock", "Base Clock"):
        mhz = number(get("Clock Speeds", label) or "", "MHz")
        if mhz is not None:
            _put(
                out,
                spec,
                ("compute.clock_mhz", "Clock Speeds", label),
                mhz,
                note=label.lower(),
            )
            break
    units = number(get("Render Config", "Shading Units") or "", "")
    if units is not None:
        _put(
            out,
            spec,
            ("compute.shading_units", "Render Config", "Shading Units"),
            int(units),
        )
    for label, field in (("FP16", "fp16"), ("FP32", "fp32"), ("FP64", "fp64")):
        for name in (label, f"{label} (half)", f"{label} (float)", f"{label} (double)"):
            found = get("Theoretical Performance", name)
            if found:
                _put(
                    out,
                    spec,
                    (f"compute.{field}_tflops", "Theoretical Performance", name),
                    flops(found),
                )
                break


def _format_cells(spec: dict[str, dict[str, str]], out: Cells) -> None:
    def get(section: str, label: str) -> str | None:
        return (spec.get(section) or {}).get(label)

    section = "Numeric Format Support"
    vector = get(section, "Vector")
    if vector is not None:
        listed = formats(vector)
        _put(out, spec, ("formats.vector", section, "Vector"), listed)
        if listed is not None:
            _put(
                out,
                spec,
                ("formats.fp16", section, "Vector"),
                "fp16" in listed,
                how="derived: the Vector line marks FP16 supported or not",
            )
    matrix = get(section, "Matrix")
    if matrix is not None:
        _put(
            out,
            spec,
            ("formats.matrix.precisions", section, "Matrix"),
            formats(matrix),
        )
    for label in spec.get("Render Config") or {}:
        if re.search(r"(?i)(tensor|xmx|matrix|ai) ", label):
            count = number(get("Render Config", label) or "", "")
            if count is not None:
                _put(
                    out,
                    spec,
                    ("compute.matrix_units", "Render Config", label),
                    {"count": int(count), "called": label},
                )
    pairs = spec.get("Matrix Performance")
    if pairs and rates(pairs):
        out["compute.matrix_rates"] = (
            rates(pairs),
            "Matrix Performance " + " ".join(f"{k} {v}" for k, v in pairs.items()),
            "stated",
            "TOPS for integer formats, TFLOPS for floating point",
        )
    for label, field in (
        ("OpenCL", "api.opencl"),
        ("Vulkan", "api.vulkan"),
        ("CUDA", "api.cuda_compute_capability"),
    ):
        text = get("Graphics Features", label)
        if text and text.strip().upper() != "N/A":
            _put(out, spec, (field, "Graphics Features", label), text.strip())


def cells_of(spec: dict[str, dict[str, str]]) -> Cells:
    """The schema's cells that one spec sheet carries: field -> (value, quote,
    how, note)."""
    out: Cells = {}
    _card_cells(spec, out)
    _compute_cells(spec, out)
    _format_cells(spec, out)
    return out


def nest(flat: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, cell in flat.items():
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = cell
    return out


def _notes(
    row: dict[str, Any], row_id: str, where: dict[str, str], flat: dict[str, Any]
) -> list[dict[str, str]]:
    gaps = []
    named = set((flat.get("formats.matrix.precisions") or {}).get("v") or [])
    rated = set((flat.get("compute.matrix_rates") or {}).get("v") or {})
    rated = {r for r in rated if not any(n.endswith(r) for n in named)}
    if rated:
        gaps.append(
            {
                "what": f"{row_id} compute.matrix_rates",
                "why": f"the page gives a matrix rate for {sorted(rated)}, which its "
                "Matrix line marks not supported; both cells are kept as the page "
                "has them",
            }
        )
    year = str(value(row.get("launch")) or "")[:4]
    seen = str(flat.get("launch", {}).get("v") or "")[:4]
    if year and seen and abs(int(year) - int(seen)) > 1:
        gaps.append(
            {
                "what": f"{row_id} launch",
                "why": f"the row says {year}, techpowerup's page "
                f"{where['tpu_name']!r} says {seen}: check that it is the same card",
            }
        )
    return gaps


def fill() -> None:
    rows = {r["id"]: r for r in gpu_rows()}
    mapped = json.loads((WAVE / "tpu-map.json").read_text())
    sources: dict[str, dict[str, Any]] = {}
    out, gaps, unread = [], [], []
    for row_id, where in mapped.items():
        url = where["url"]
        if verify_quotes.cached(url):
            raw, _ = verify_quotes.fetch(url)
        else:
            raw = None
        if raw is None:
            unread.append(row_id)
            continue
        spec = sheet(raw)
        src = "tpu-c" + url.rsplit(".c", 1)[1]
        title = re.search(r"(?is)<title>(.*?)</title>", raw)
        sources[src] = {
            "id": src,
            "url": url,
            "title": clean(title.group(1)) if title else "",
            "publisher": "techpowerup.com",
            "official": False,
            "fetch": "ok",
        }
        flat = {}
        for field, (v, quote, how, note) in cells_of(spec).items():
            cell = {"v": v, "src": src, "quote": quote, "how": how, "official": False}
            if note:
                cell["note"] = note
            flat[field] = cell
        if not flat:
            gaps.append({"what": row_id, "why": f"no spec sheet parsed from {url}"})
            continue
        row = rows[row_id]
        gaps.extend(_notes(row, row_id, where, flat))
        out.append(
            {
                "id": row_id,
                "vendor": row["vendor"],
                "kind": "gpu",
                "tpu_name": where["tpu_name"],
                **nest(flat),
            }
        )
    doc = {
        "schema": 1,
        "slice": "tpu-gpu",
        "wave": 4,
        "sources": list(sources.values()),
        "rows": out,
        "gaps": gaps,
        "blocked": [],
        "coverage": {
            "target": sorted(mapped),
            "done": [r["id"] for r in out],
            "left": unread,
        },
    }
    (WAVE / "tpu-gpu.json").write_text(json.dumps(doc, indent=1))
    count = sum(len(list(verify_quotes.cells(r))) for r in out)
    print(
        f"{len(out)} rows, {count} cells, {len(unread)} rows whose page is not read "
        f"yet, {len(gaps)} notes"
    )
    for gap in gaps:
        print("  note:", gap["what"], "|", gap["why"])


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "index":
        index()
    elif step == "map":
        mapping()
    elif step == "fetch":
        fetch_pages(int(sys.argv[2]) if len(sys.argv) > 2 else 500)
    elif step == "fill":
        fill()
    else:
        print(__doc__)
