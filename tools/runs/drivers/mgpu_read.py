"""What mgpu_sweep reads off an engine: stream deltas, launch logs, sidecar files.

Pure functions of text, so a test can hold each engine's real wording. Every
field a reader cannot find comes back ``unread``, never a guess, and
:func:`log_excerpt` files the raw lines the reader looked for so a wording the
next build changes is in the record, not lost with the container.
"""

from __future__ import annotations

import re
import statistics

#: The delta fields a generated token can arrive in. llama.cpp streams a
#: reasoning model's thinking as `reasoning_content`; vLLM 0.26 renamed it
#: `reasoning`. Counting only `content` timed nothing for a thinking model.
TOKEN_FIELDS = ("content", "reasoning_content", "reasoning", "tool_calls")


def streamed_token(delta: dict[str, object]) -> bool:
    return any(delta.get(k) for k in TOKEN_FIELDS)


# --------------------------------------------------------------------------
# launch logs
# --------------------------------------------------------------------------

#: NCCL 2.28 prints `Channel 00 : 0[0] -> 1[1] via SHM/direct/direct` for the
#: host-memory path (no `/connIndex`) and `Channel 00/0 : ... via P2P/...` for
#: peer paths; the reader takes both. custom_ar is `on` when vLLM names CUSTOM
#: among the all-reduce backends it enabled, which is what it prints once the
#: driver grants peer access (step 19-p2p).
NCCL_VIA = re.compile(r"NCCL INFO Channel \d+(?:/\d+)? : .*? via (\S+)")
CAR_OFF = re.compile(r"Custom allreduce is disabled because ([^.\n]*)")
CAR_FLAG = re.compile(r"disable_custom_all_reduce=(True|False)")
#: vLLM's own peer test (all_reduce_utils.gpu_p2p_access_check). It runs only
#: under VLLM_SKIP_P2P_CHECK=0; by default vLLM trusts can_device_access_peer.
#: The rank that runs it logs `generating`, a rank that finds its file `reading`.
P2P_CHECK = (
    ("tested", "generating GPU P2P access cache"),
    ("cache", "reading GPU P2P access cache"),
)


def _first(pattern: str, log: str) -> str:
    m = re.search(pattern, log)
    return m.group(1) if m else "unread"


def read_vllm(log: str, layout: str) -> list[str]:
    out = [
        f"kv_tok={_first(r'GPU KV cache size: ([\d,]+) tokens', log).replace(',', '')}",
        "maxconc="
        + _first(r"Maximum concurrency for [\d,]+ tokens per request: ([\d.]+)x", log),
    ]
    kernel = re.search(r"Using (\w+) ?(?:Linear)?Kernel", log) or re.search(
        r"quantization=(\w+)", log
    )
    out.append(f"kernel={kernel.group(1) if kernel else 'unread'}")
    out.append("attn=" + _first(r"Using (\w+) (?:attention )?backend", log))
    out.append("kv_dtype=" + _first(r"kv_cache_dtype=['\"]?(\w+)", log))
    out.append("chunked=" + _first(r"chunked_prefill=(True|False)", log))
    out.append(
        "graphs="
        + _first(r"cudagraph_mode'?\s*[:=]\s*<?(?:CUDAGraphMode\.)?(\w+)", log)
    )
    out.append("graph_s=" + _first(r"Graph capturing finished in ([\d.]+) secs", log))
    backends = re.search(r"Using \[([^\]]*)\] all-reduce backends", log)
    if layout in ("tp2", "pp2"):
        ar = backends.group(1).replace("'", "").replace(" ", "") if backends else ""
        out.append(f"ar_backend={ar or 'unread'}")
        via = sorted(set(NCCL_VIA.findall(log)))
        out.append(f"transport={','.join(via) or 'unread'}")
        proto = sorted(
            set(re.findall(r"NCCL INFO .*?[Pp]roto(?:col)?s? ?[=:] ?(\w+)", log))
        )
        out.append(f"nccl_proto={','.join(proto) or 'unread'}")
        car = CAR_OFF.search(log)
        flag = CAR_FLAG.search(log)
        if layout == "pp2":
            state = "tp1"
        elif car:
            state = "engine_disabled"
        elif "CUSTOM" in ar.split(","):
            state = "on"
        elif flag and flag.group(1) == "True":
            state = "flag_disabled"
        elif flag:
            state = "on"
        else:
            state = "unread"
        out.append(f"custom_ar={state}")
        # `none` is read: the log carries no peer-test line at all.
        check = next((k for k, words in P2P_CHECK if words in log), "none")
        out.append(f"p2p_check={check}")
    return out


def read_lcp(log: str) -> list[str]:
    """llama.cpp's own words; the buffer lines need `-lv 4` to be printed at all
    (library INFO is verbosity 4 and llama-server's default threshold is 3)."""
    bufs = re.findall(r"load_tensors:\s+(\S+) model buffer size =\s*([\d.]+) MiB", log)
    kvb = re.findall(r"(\S+) KV buffer size =\s*([\d.]+) MiB", log)
    comp = re.findall(r"(\S+) compute buffer size =\s*([\d.]+) MiB", log)

    def join(pairs: list[tuple[str, str]]) -> str:
        return ",".join(f"{d}:{float(m):.0f}" for d, m in pairs) or "unread"

    return [
        "buf=" + join(bufs),
        "kvbuf=" + join(kvb),
        "compbuf=" + join(comp),
        "real_ctx_slot=" + _first(r"n_ctx_(?:slot|seq)\s*=\s*(\d+)", log),
        "n_ubatch=" + _first(r"n_ubatch\s*=\s*(\d+)", log),
        "graph_splits=" + _first(r"graph splits = (\d+)", log),
    ]


#: The lines each reader looks for, filed raw when any field reads unread.
EXCERPT = re.compile(
    r"NCCL INFO (?:Channel|Connected all|comm .* nRanks)|Custom allreduce|"
    r"model buffer|KV buffer|compute buffer|n_ctx|n_ubatch|graph splits|"
    r"KV cache size|Maximum concurrency|backend|cudagraph|P2P access cache"
)


def log_excerpt(log: str, per: int = 3, width: int = 300) -> list[str]:
    """The first ``per`` lines of each pattern family, tabs gone, cut to ``width``."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for line in log.splitlines():
        m = EXCERPT.search(line)
        if not m:
            continue
        key = m.group(0).split()[0]
        if seen.get(key, 0) >= per:
            continue
        seen[key] = seen.get(key, 0) + 1
        out.append(line.replace("\t", " ").strip()[:width])
    return out


# --------------------------------------------------------------------------
# sidecar files: nvidia-smi dmon, mpstat, vmstat, cpu MHz, taken rig-side
# --------------------------------------------------------------------------


def rd_num(v: str) -> bool:
    return re.fullmatch(r"-?[\d.]+", v) is not None


def _mean(xs: list[float]) -> float:
    return statistics.mean(xs) if xs else float("nan")


def read_dmon(text: str) -> list[str]:
    """Per card: SM busy and PCIe rx/tx MB/s (mean, and peak) over the level."""
    cols: list[str] = []
    per: dict[str, dict[str, list[float]]] = {}
    for line in text.splitlines():
        if line.startswith("# gpu") or line.startswith("#gpu"):
            cols = line.lstrip("#").split()
            continue
        if not cols or line.startswith("#") or not line.strip():
            continue
        vals = line.split()
        if len(vals) != len(cols):
            continue
        row = dict(zip(cols, vals, strict=True))
        g = per.setdefault(row["gpu"], {})
        for k in ("sm", "mem", "rxpci", "txpci", "pclk", "pwr"):
            v = row.get(k, "-")
            if rd_num(v):
                g.setdefault(k, []).append(float(v))
    out: list[str] = []
    for gpu, g in sorted(per.items()):
        if g.get("sm"):
            out.append(f"sm{gpu}={_mean(g['sm']):.0f}")
        if g.get("rxpci") and g.get("txpci"):
            out.append(
                f"pcie{gpu}={_mean(g['rxpci']):.0f}/{_mean(g['txpci']):.0f}"
                f"~{max(g['rxpci']):.0f}/{max(g['txpci']):.0f}"
            )
        if g.get("pclk"):
            out.append(f"pclk{gpu}={_mean(g['pclk']):.0f}")
    return out or ["dmon=unread"]


def read_mpstat(text: str) -> list[str]:
    """Mean busy over all cores, the hottest core's mean busy, and mean %soft."""
    head: list[str] = []
    cores: dict[str, list[float]] = {}
    soft: list[float] = []
    for line in text.splitlines():
        parts = line.split()
        if "%idle" in parts:
            head = parts
            continue
        if not head or len(parts) != len(head):
            continue
        row = dict(zip(head, parts, strict=True))
        cpu = row.get("CPU", "")
        try:
            idle = float(row["%idle"])
        except (KeyError, ValueError):
            continue
        if cpu == "all":
            soft.append(float(row.get("%soft", "0")))
        elif cpu.isdigit():
            cores.setdefault(cpu, []).append(100.0 - idle)
    if not cores:
        return ["cpu=unread"]
    means = {c: _mean(v) for c, v in cores.items()}
    hot = max(means, key=lambda c: means[c])
    return [
        f"cpu_mean={_mean(list(means.values())):.0f}",
        f"cpu_hot={means[hot]:.0f}@{hot}",
        f"cpu_soft={_mean(soft):.1f}",
    ]


def read_vmstat(text: str) -> list[str]:
    """Swap traffic (si+so, KiB/s summed over the level) and the lowest free.

    vmstat's first row is the average since boot, so it is dropped."""
    head: list[str] = []
    rows = 0
    swap = 0.0
    free: list[float] = []
    for line in text.splitlines():
        parts = line.split()
        if "si" in parts and "so" in parts:
            head = parts
            continue
        if not head or len(parts) != len(head) or not parts[0].isdigit():
            continue
        rows += 1
        if rows == 1:
            continue
        row = dict(zip(head, parts, strict=True))
        swap += float(row["si"]) + float(row["so"])
        free.append(float(row["free"]))
    if not free:
        return ["vm=unread"]
    return [f"swap_kib={swap:.0f}", f"free_min_mib={min(free) / 1024:.0f}"]


def read_mhz(text: str) -> list[str]:
    xs = [float(x) for x in text.split() if re.fullmatch(r"[\d.]+", x)]
    return [f"cpu_mhz={_mean(xs):.0f}"] if xs else ["cpu_mhz=unread"]
