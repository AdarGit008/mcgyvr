"""Two-card serving sweep: one checkpoint, one engine, one card layout per cell.

args: ENGINE CELL...     ENGINE = vllm | lcp
cell = tag:model:layout:p2p:ctx:levels[:extra]

  model    vllm: a HF repo id already in the rig's HF cache (the campaign's
           fetch step puts it there; nothing is downloaded mid-sweep), or a
           checkpoint directory /models/<path>, the container form of
           ~/models/<path>, mounted read-only.
           lcp: /models/<path>.gguf, the container form of ~/models/<path>,
           or /hf/<path>.gguf, the container form of ~/.cache/huggingface/<path>.
  layout   g0 | g1     one card, the other idle (`--gpus device=N`)
           tp2 | pp2   vllm only: --tensor- / --pipeline-parallel-size 2
           layer | row | tensor
                       lcp only: --split-mode over both cards, split by free
                       memory (llama.cpp's default --tensor-split). b10644's
                       CUDA backend refuses row ("does not support split
                       buffers"); tensor is its tensor-parallel successor
           dp2         two single-card replicas, requests alternated between
                       them: the "no model parallelism at all" baseline
  p2p      on | off    vllm: off = NCCL_P2P_DISABLE=1 plus
                       --disable-custom-all-reduce, so every collective
                       bounces through host memory. lcp takes `built` only:
                       llama.cpp has no runtime switch this driver trusts.
  ctx      vllm: --max-model-len. lcp: the per-slot window; -np is the widest
           level and -c is np * ctx, because llama.cpp divides -c across slots.
  levels   concurrency rungs, e.g. 1,4,16
  extra    appended VERBATIM to the engine argv, `+` read as a space and `:`
           kept (the rest of the cell is extra). A word starting `@` is a
           directive to this driver, never passed to the engine:
             @NAME=V      `docker -e NAME=V` (NCCL_*, GGML_CUDA_*, ...)
             @cpuset=0-3  `docker --cpuset-cpus`: the engine sees those cores
             @headroom=N  card MiB kept back per card in the fit prediction
             @prefill=N   PREFILL prompt size in characters (ctx ladders)
             @knob        sustained levels: n=1 is five fixed-length replies
                          (ignore_eos, 256 tokens) with a spread; n>1 is n
                          closed-loop streams for 30 s, steady tokens/s.
                          For A/B-ing one setting; the workload levels are
                          too short (0.7-3 s) for the sidecar to see
           A cell whose extra moves weights off the cards (--n-cpu-moe, -ot,
           --cpu-moe) is not fit-predicted: the engine's refusal decides.

What one cell prints, all tab-separated `host label kind k=v...`:

  SKIP      predicted not to fit (weights against the cards' free memory),
            or a ctx below the workload's need; nothing was launched. Host
            memory is not predicted: both engines map the weights from disk
            onto the cards, and a split exists for checkpoints bigger than
            the host's free RAM
  REFUSED   launched and never answered /health, after up to three tries when
            the engine's words are about memory (a launch near the edge
            fails intermittently)
  CONFIG    what the engine says it built: KV pool, the NCCL transport it
            chose, whether vLLM's custom all-reduce is on, the quant kernel,
            attention backend and graph mode, llama.cpp's per-device model,
            KV and compute buffers (read at -lv 4), ubatch and graph splits,
            card memory after load, and load_s from docker run to /health
  LOG       the raw log lines the CONFIG reader looks for, filed when a
            CONFIG field reads unread, so a changed wording is in the record
  PREFILL   three unique ~1.5k-token prompts, one at a time, max_tokens=4:
            pp = ptok / ttft, the first token in any delta field (a thinking
            model's first token is reasoning); ttft_src=usage when no delta
            streamed and the usage chunk's arrival is the clock. Streaming
            TTFT is the only prefill figure in this file; `agg` is not one
            (generated tokens over the level's whole wall clock, prefill
            included)
  n=K       K concurrent streamed requests from tools/runs/workload.py:
            agg = generated / wall; dec = 1000 / tpot_p50, the per-stream
            decode rate a user sees; ttft_p50; and a rig-side sidecar over
            the level: per card peak power, peak memory, mean utilisation, the
            PCIe link trained to under load (nvidia-smi query), SM busy, PCIe
            rx/tx MB/s mean~peak and clock (nvidia-smi dmon); per core busy,
            the hottest core and %soft (mpstat); swap traffic and lowest free
            memory (vmstat); mean CPU MHz. cards=short when the level lasted
            under 3 s: its 1 Hz samples are too few to read

The workload is `tools/runs/workload.py`, imported and never copied.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.runs import workload
from tools.runs.drivers import mgpu_read as rd

# THE DOOR'S REFUSALS, before argv is read and before docker is touched — the
# same three lcp_sweep.py and vllm_sweep.py carry, for the reasons written
# there: the door proved from /proc, RUN_ID minted by gate 5, and an image that
# is a digest resolved once by gate 3.
try:
    from mcgyvr.serving import gatelib
except ImportError:
    print(
        "mgpu_sweep: mcgyvr.serving.gatelib will not import, so the door cannot be "
        "proved and nothing is started — this driver runs under the door, "
        "python -m mcgyvr.serving.run, on the interpreter that has mcgyvr",
        file=sys.stderr,
    )
    sys.exit(2)
gatelib.door_required("mgpu_sweep")
RUN_ID = os.environ.get("RUN_ID", "")
if not RUN_ID:
    print(
        "mgpu_sweep: RUN_ID is unset — this driver is started by the door, "
        "python -m mcgyvr.serving.run, never bare; a bare run prints unstamped "
        "rows nothing can file",
        file=sys.stderr,
    )
    sys.exit(2)
H = os.environ.get("RUN_HOST", "")
if not H:
    print(
        "mgpu_sweep: RUN_HOST is unset — the door exports the rig a run serves on "
        "(gate 5); without it there is no host to poll and no host column",
        file=sys.stderr,
    )
    sys.exit(2)
ENGINE = sys.argv[1] if len(sys.argv) > 1 else ""
IMG_VAR = {"vllm": "VLLM_IMG", "lcp": "LCP_IMG"}.get(ENGINE, "")
if not IMG_VAR:
    print(f"mgpu_sweep: engine {ENGINE!r} is not vllm or lcp", file=sys.stderr)
    sys.exit(2)
IMG = os.environ.get(IMG_VAR, "")
if not ("@sha256:" in IMG or IMG.startswith("sha256:")):
    print(
        f"mgpu_sweep: {IMG_VAR}={IMG!r} is not an image digest (repo@sha256:<hex> "
        "or sha256:<hex>). A tag is resolved ONCE, by image_digest in "
        "tools/runs/_common.sh (gate 3), and the digest is what this driver runs",
        file=sys.stderr,
    )
    sys.exit(2)

CELLS = sys.argv[2:]
#: Both containers carry the run's name so gate 7 finds what this left behind.
NAMES = (f"{RUN_ID}-mgpu-a", f"{RUN_ID}-mgpu-b")
PORTS = (8096, 8097)
LAYOUTS = {
    "vllm": ("g0", "g1", "tp2", "pp2", "dp2"),
    "lcp": ("g0", "g1", "layer", "row", "tensor", "dp2"),
}
#: Card memory a single-card cell keeps back beyond its weights (CUDA context,
#: activations, a minimum KV pool), and what a two-card cell keeps back in all.
#: A prediction that only decides whether to spend a launch: the engine's own
#: refusal is the measurement, and a cell this lets through may still refuse.
HEADROOM_MIB = 1024
MEMORY_WORDS = re.compile(r"out of memory|OOM|CUDA error|memory", re.IGNORECASE)
#: Target prompt size for the PREFILL probe: inside a 2048 window with room for
#: the chat template. The probe's code lines run ~0.54 Qwen tokens a character,
#: so 2800 is ~1.5k tokens; 5600 was ~3.0k, past a 2048 window, and every
#: PREFILL came back unread.
PREFILL_CHARS = 2800
#: @knob: fixed reply length, n=1 repeats, and the closed-loop window.
KNOB_TOKENS = 256
KNOB_REPS = 5
KNOB_S = 30.0
#: Extra words that move weights off the cards; such a cell is not fit-predicted.
OFFLOAD = re.compile(
    r"(?:^|\s)(?:--n-cpu-moe|-ncmoe|--cpu-moe|-ot|--override-tensor)\b"
)


@dataclass
class Cell:
    """A cell's extra split into the engine's words and this driver's directives."""

    extra: str = ""
    env: dict[str, str] = field(default_factory=dict)
    cpuset: str = ""
    headroom: int = 0
    prefill: int = 0
    knob: bool = False


def parse_extra(raw: str) -> Cell:
    c = Cell()
    words: list[str] = []
    for w in raw.replace("+", " ").split():
        if not w.startswith("@"):
            words.append(w)
        elif w == "@knob":
            c.knob = True
        elif w.startswith("@cpuset="):
            c.cpuset = w.split("=", 1)[1]
        elif w.startswith("@headroom="):
            c.headroom = int(w.split("=", 1)[1])
        elif w.startswith("@prefill="):
            c.prefill = int(w.split("=", 1)[1])
        elif re.fullmatch(r"@[A-Z][A-Z0-9_]*=\S*", w):
            k, v = w[1:].split("=", 1)
            c.env[k] = v
        else:
            raise ValueError(f"unknown directive {w!r}")
    c.extra = " ".join(words)
    return c


#: One request: generated tokens, wall s, prompt tokens, asked-for budget,
#: ttft s (None: nothing streamed), decode s from first to last token.
Req = tuple[int, float, int, int, float | None, float]


def sh(c: str) -> str:
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()


def rig(c: str, timeout: float = 60.0) -> str:
    """A command on the rig, through gatelib.ssh (the door's host or nothing)."""
    try:
        return gatelib.ssh(H, c, timeout=timeout).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def emit(label: str, kind: str, *fields: str) -> None:
    print("\t".join((H, label, kind, *fields)), flush=True)


# --------------------------------------------------------------------------
# the cards
# --------------------------------------------------------------------------

CARD_QUERY = (
    "nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.free,"
    "power.draw,pcie.link.gen.current,pcie.link.width.current "
    "--format=csv,noheader,nounits"
)


def cards() -> list[list[str]]:
    return [
        [f.strip() for f in line.split(",")]
        for line in rig(CARD_QUERY, timeout=20).splitlines()
        if line.strip()
    ]


#: The rig-side sidecar's directory: one per run, removed after every level.
SIDECAR = f"/tmp/{RUN_ID}-sidecar"
#: Its own ceiling, so a driver that dies mid-level does not leave it running.
SIDECAR_MAX_S = 1800
SIDECAR_SH = f"""echo $$ > pid
( sleep {SIDECAR_MAX_S}; kill -- -$$ ) &
LC_ALL=C nvidia-smi dmon -s pucmt -d 1 > dmon 2>&1 &
LC_ALL=C mpstat -P ALL 1 > mpstat 2>&1 &
vmstat -n 1 > vmstat 2>&1 &
while :; do
  {CARD_QUERY} >> cards; echo --- >> cards
  awk '/MHz/ {{ s += $4; n++ }} END {{ if (n) print s / n }}' /proc/cpuinfo >> mhz
  sleep 1
done
"""


class Sidecar:
    """The cards, cores and memory once a second while a level runs, sampled
    on the rig and read back once: two ssh calls a level, not one a second."""

    def start(self) -> None:
        rig(
            f"rm -rf {SIDECAR} && mkdir -p {SIDECAR} && cd {SIDECAR} && "
            f"cat > sidecar.sh <<'SIDECAR'\n{SIDECAR_SH}SIDECAR\n"
            "setsid bash sidecar.sh </dev/null >/dev/null 2>&1 & "
            "for i in 1 2 3 4 5 6 7 8 9 10; do [ -s pid ] && break; sleep 0.2; done"
        )

    def finish(self, wall: float) -> list[str]:
        got = rig(
            f"cd {SIDECAR} 2>/dev/null && kill -- -$(cat pid) 2>/dev/null; "
            "for f in cards dmon mpstat vmstat mhz; do "
            f'echo "=== $f"; cat {SIDECAR}/$f 2>/dev/null; done; rm -rf {SIDECAR}'
        )
        part: dict[str, str] = {}
        for chunk in got.split("=== ")[1:]:
            name, _, body = chunk.partition("\n")
            part[name.strip()] = body
        out = summarise_cards(
            [
                [
                    [f.strip() for f in line.split(",")]
                    for line in snap.splitlines()
                    if line.strip()
                ]
                for snap in part.get("cards", "").split("---")
                if snap.strip()
            ]
        )
        if wall < 3:
            out.append("cards=short")
        out += rd.read_dmon(part.get("dmon", ""))
        out += rd.read_mpstat(part.get("mpstat", ""))
        out += rd.read_vmstat(part.get("vmstat", ""))
        out += rd.read_mhz(part.get("mhz", ""))
        return out


def sidecar_stop() -> None:
    rig(
        f"[ -s {SIDECAR}/pid ] && kill -- -$(cat {SIDECAR}/pid) 2>/dev/null; "
        f"rm -rf {SIDECAR}"
    )


def summarise_cards(rows: list[list[list[str]]]) -> list[str]:
    """Peak summed power; per card mean utilisation, peak memory, and the PCIe
    link it trained to while busy."""
    rows = [snap for snap in rows if snap and all(len(c) >= 7 for c in snap)]
    if not rows:
        return ["cards=unread"]
    out: list[str] = []
    power = [sum(float(c[4]) for c in snap if _num(c[4])) for snap in rows]
    out.append(f"pw_peak={max(power):.0f}")
    for idx in sorted({c[0] for snap in rows for c in snap}):
        mine = [c for snap in rows for c in snap if c[0] == idx]
        util = [float(c[1]) for c in mine if _num(c[1])]
        mem = [int(float(c[2])) for c in mine if _num(c[2])]
        busy = [c for c in mine if _num(c[1]) and float(c[1]) >= 20]
        link = sorted({f"g{c[5]}x{c[6]}" for c in busy}) or ["idle"]
        out.append(f"util{idx}={statistics.mean(util):.0f}" if util else "")
        out.append(f"mem{idx}={max(mem)}" if mem else "")
        out.append(f"link{idx}={'/'.join(link)}")
    return [f for f in out if f]


def _num(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------
# requests
# --------------------------------------------------------------------------


def stream(
    port: int,
    model: str,
    messages: list[dict[str, str]],
    want: int,
    ignore_eos: bool = False,
) -> Req:
    """One streamed chat request; the token clock is read off the stream.

    A token is a delta in any field of rd.TOKEN_FIELDS. When nothing streamed
    but usage says a token was generated (a parser that swallowed a lone
    `<think>`), the usage chunk's arrival is the first-token clock and the
    request's ttft is marked negative so PREFILL can say ttft_src=usage.
    """
    body: dict[str, object] = {
        "messages": messages,
        "max_tokens": want,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if ignore_eos:
        body["ignore_eos"] = True
    if ENGINE == "vllm":
        body["model"] = model
    else:
        body["cache_prompt"] = True
    r = urllib.request.Request(
        f"http://{H}:{port}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    first: float | None = None
    last = t0
    chunks = 0
    usage: dict[str, int] = {}
    usage_at: float | None = None
    try:
        with urllib.request.urlopen(r, timeout=3600) as f:
            for raw in f:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:") or line == "data: [DONE]":
                    continue
                d = json.loads(line[5:])
                if d.get("usage"):
                    usage = d["usage"]
                    usage_at = time.time()
                for choice in d.get("choices") or []:
                    if rd.streamed_token(choice.get("delta") or {}):
                        now = time.time()
                        first = now if first is None else first
                        last = now
                        chunks += 1
    except Exception:
        return (0, time.time() - t0, 0, want, None, 0.0)
    gen = int(usage.get("completion_tokens", chunks))
    ttft = None if first is None else first - t0
    if ttft is None and gen >= 1 and usage_at is not None:
        ttft = -(usage_at - t0)
    return (
        gen,
        time.time() - t0,
        int(usage.get("prompt_tokens", 0)),
        want,
        ttft,
        0.0 if first is None else last - first,
    )


def workload_request(port: int, model: str) -> Req:
    prompt, want = workload.mkprompt()
    return stream(
        port,
        model,
        [
            {"role": "system", "content": workload.SYSTEM},
            {"role": "user", "content": prompt[len(workload.SYSTEM) :]},
        ],
        want,
    )


def prefill_request(port: int, model: str, k: int, chars: int) -> Req:
    """A unique long prompt: the id is at the head so no prefix cache hits."""
    head = f"Review request {RUN_ID}-{k}-{time.time_ns()}. Summarise in one word.\n"
    line = "def f_{0}(x: int) -> int:\n    return (x * {0}) % 9973  # step {0}\n"
    body = head
    i = 0
    while len(body) < chars:
        body += line.format(i)
        i += 1
    return stream(port, model, [{"role": "user", "content": body}], 4)


def fanout(ports: tuple[int, ...], model: str, n: int) -> list[Req | None]:
    """``n`` concurrent workload requests, alternated across ``ports``.

    A slot still ``None`` afterwards is a thread that died, not a request that
    returned nothing, and the level is refused rather than averaged over it.
    """
    out: list[Req | None] = [None] * n

    def one(i: int) -> None:
        out[i] = workload_request(ports[i % len(ports)], model)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def knob_request(port: int, model: str) -> Req:
    """A workload prompt held to exactly KNOB_TOKENS generated tokens."""
    prompt, _ = workload.mkprompt()
    return stream(
        port,
        model,
        [
            {"role": "system", "content": workload.SYSTEM},
            {"role": "user", "content": prompt[len(workload.SYSTEM) :]},
        ],
        KNOB_TOKENS,
        ignore_eos=True,
    )


def closed_loop(ports: tuple[int, ...], model: str, n: int) -> list[Req]:
    """``n`` streams, each issuing its next request as the last returns, until
    KNOB_S has passed; every request that started in the window is kept."""
    out: list[Req] = []
    lock = threading.Lock()
    end = time.time() + KNOB_S

    def one(i: int) -> None:
        while time.time() < end:
            r = knob_request(ports[i % len(ports)], model)
            with lock:
                out.append(r)
            if r[0] == 0:
                return

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def p50(values: list[float]) -> float:
    return statistics.median(values) if values else float("nan")


# --------------------------------------------------------------------------
# launching
# --------------------------------------------------------------------------


def host_path(model: str) -> str:
    """The rig path of a container path under one of the driver's mounts."""
    if model.startswith("/hf/"):
        return "$HOME/.cache/huggingface/" + model.removeprefix("/hf/")
    return "$HOME/models/" + model.removeprefix("/models/")


def weights_mib(model: str) -> int | None:
    if ENGINE == "lcp":
        got = rig(f'stat -Lc %s "{host_path(model)}" 2>/dev/null')
    elif model.startswith("/models/"):
        path = "$HOME/models/" + model.removeprefix("/models/")
        got = rig(
            f'find -L "{path}" -maxdepth 1 -name "*.safetensors" -printf "%s\\n" '
            "2>/dev/null | awk '{ s += $1 } END { if (s) print s }'"
        )
    else:
        repo = "models--" + model.replace("/", "--")
        got = rig(
            f"du -sLb $HOME/.cache/huggingface/hub/{repo}/snapshots 2>/dev/null "
            "| cut -f1"
        )
    return int(got) // 2**20 if got.isdigit() else None


def fit(
    layout: str, weights: int, free: list[int], headroom: int = HEADROOM_MIB
) -> str | None:
    """Why the cell is predicted not to fit, or None.

    One card holds everything; dp2 holds everything on EACH card; vLLM's tp2
    holds half on each and sizes every rank to the smaller card; a layer,
    row or tensor split and pp2 spend the two cards' sum.
    """
    if layout in ("g0", "g1"):
        need, have = weights, free[int(layout[1])] - headroom
        where = f"card {layout[1]} has {free[int(layout[1])]} MiB free"
    elif layout in ("dp2", "tp2"):
        need = weights if layout == "dp2" else weights // 2
        have = min(free) - headroom
        where = f"the smaller card has {min(free)} MiB free"
    else:
        need, have = weights, sum(free) - 2 * headroom
        where = f"the two cards have {sum(free)} MiB free"
    if need > have:
        return (
            f"{need} MiB of weights a card do not fit: {where}, less "
            f"{headroom} MiB a card"
        )
    return None


def argv(
    slot: int, layout: str, p2p: str, model: str, ctx: int, np_: int, cell: Cell
) -> str:
    """The docker line for replica ``slot`` of a cell."""
    name, port = NAMES[slot], PORTS[slot]
    extra = cell.extra
    gpus = {"g0": "device=0", "g1": "device=1"}.get(layout, "all")
    if layout == "dp2":
        gpus = f"device={slot}"
    env = "-e CUDA_DEVICE_ORDER=PCI_BUS_ID "
    env += "".join(f"-e {k}={v} " for k, v in cell.env.items())
    if cell.cpuset:
        env += f"--cpuset-cpus {cell.cpuset} "
    if ENGINE == "vllm":
        par = {"tp2": "--tensor-parallel-size 2", "pp2": "--pipeline-parallel-size 2"}
        flags = par.get(layout, "")
        if layout in ("tp2", "pp2"):
            # vLLM's workers do not reach the container log with NCCL's own
            # lines, so NCCL writes them to a file readback() reads in place.
            env += "-e NCCL_DEBUG=INFO -e NCCL_DEBUG_FILE=/tmp/nccl.%h.%p.log "
            if p2p == "off":
                env += "-e NCCL_P2P_DISABLE=1 "
                flags += " --disable-custom-all-reduce"
        return (
            f"docker run -d --name {name} --runtime=nvidia --gpus {gpus} "
            f"-v $HOME/.cache/huggingface:/root/.cache/huggingface "
            f"-v $HOME/models:/models:ro "
            f"-e HF_HUB_OFFLINE=1 {env}"
            f"-p {port}:8000 --ipc=host {IMG} {model} --port 8000 "
            f"--dtype float16 --gpu-memory-utilization 0.88 "
            f"--max-model-len {ctx} --max-num-seqs {np_} {flags} {extra}"
        )
    split = {"layer": "-sm layer", "row": "-sm row", "tensor": "-sm tensor"}.get(
        layout, ""
    )
    return (
        f"docker run -d --name {name} --gpus {gpus} {env}"
        f"-v $HOME/models:/models:ro -v $HOME/.cache/huggingface:/hf:ro "
        f"-p {port}:8080 {IMG} "
        f"-m {model} -ngl 99 {split} -np {np_} -c {np_ * ctx} -fa on "
        f"-ctk q8_0 -ctv q8_0 --no-warmup -lv 4 --host 0.0.0.0 --port 8080 {extra}"
    )


def healthy(slots: int) -> str | None:
    """None once every replica says ok; else the engine's own last words."""
    for _ in range(450):
        up = [
            sh(f"curl -sf -m 3 http://{H}:{PORTS[s]}/health >/dev/null && echo Y")
            == "Y"
            for s in range(slots)
        ]
        if all(up):
            return None
        names = sh("docker ps --format '{{.Names}}'")
        gone = [NAMES[s] for s in range(slots) if NAMES[s] not in names]
        if gone:
            break
        time.sleep(2)
    why = ""
    for s in range(slots):
        why += sh(
            f"docker logs {NAMES[s]} 2>&1 | "
            "grep -vE '(INFO|DEBUG) [0-9]{2}-[0-9]{2} |^[0-9.]+ I ' | "
            "grep -iE 'error|traceback|not supported|does not support|out of memory|"
            "no such file|capability|assert|divisible|failed|split buffer' | "
            "grep -v 'failed to load model' | tail -3"
        )
        if not why:
            why = sh(f"docker logs {NAMES[s]} 2>&1 | tail -3")
    return " | ".join(why.splitlines())[:400] or "no /health and no log line"


def down() -> None:
    sh(f"docker rm -f {' '.join(NAMES)}")
    sidecar_stop()


def readback(layout: str, slots: int) -> tuple[list[str], list[str]]:
    """What the engine says it built, read from its log and never the flags;
    and the raw lines behind it when any field read unread."""
    log = sh(f"docker logs {NAMES[0]} 2>&1")
    if ENGINE == "vllm" and layout in ("tp2", "pp2"):
        log += "\n" + sh(
            f"docker exec {NAMES[0]} sh -c 'cat /tmp/nccl.*.log' 2>/dev/null"
        )
    out = rd.read_vllm(log, layout) if ENGINE == "vllm" else rd.read_lcp(log)
    if slots == 2 and ENGINE == "lcp":
        other = rd.read_lcp(sh(f"docker logs {NAMES[1]} 2>&1"))
        out += [f"b_{f}" for f in other if f.split("=")[0] in ("buf", "kvbuf")]
    raw = rd.log_excerpt(log) if any(f.endswith("=unread") for f in out) else []
    return out, raw


# --------------------------------------------------------------------------
# a cell
# --------------------------------------------------------------------------


def run_cell(cell: str) -> None:
    tag, model, layout, p2p, ctx_s, lv, *rest = cell.split(":")
    ctx = int(ctx_s)
    levels = [int(x) for x in lv.split(",")]
    extra = ":".join(rest).replace("+", " ")
    c = parse_extra(extra)
    lab = (
        f"{tag} engine={ENGINE} model={model.split('/')[-1]} "
        f"layout={layout} p2p={p2p} ctx={ctx}"
    )
    if extra:
        lab += f" extra={extra.replace(' ', '+')}"
    if layout not in LAYOUTS[ENGINE]:
        emit(
            lab, "SKIP", f"layout {layout} is not one {ENGINE} runs: {LAYOUTS[ENGINE]}"
        )
        return
    if (ENGINE == "lcp" and p2p != "built") or (
        ENGINE == "vllm" and p2p not in ("on", "off")
    ):
        emit(lab, "SKIP", f"p2p={p2p} is not an axis {ENGINE} takes here")
        return
    if ctx < workload.MAXLEN_NEED:
        emit(
            lab,
            "SKIP",
            f"ctx {ctx} < {workload.MAXLEN_NEED}, the worst sampled prompt+reply",
        )
        return

    down()
    time.sleep(2)
    weights = weights_mib(model)
    if weights is None:
        emit(
            lab,
            "REFUSED",
            f"{model} is not on {H} (HF cache or ~/models); run the fetch step",
        )
        return
    now = cards()
    free = [int(float(c[3])) for c in now]
    if len(free) != 2:
        emit(lab, "REFUSED", f"{H} shows {len(free)} cards, and this campaign is two")
        return
    why = (
        None
        if OFFLOAD.search(c.extra)
        else fit(layout, weights, free, c.headroom or HEADROOM_MIB)
    )
    if why:
        emit(lab, "SKIP", why)
        return
    slots = 2 if layout == "dp2" else 1
    np_ = max(levels)
    tries = 0
    failed: str | None = "not launched"
    load_s = 0.0
    while tries < 3 and failed:
        tries += 1
        down()
        t_load = time.time()
        for s in range(slots):
            sh(argv(s, layout, p2p, model, ctx, np_, c))
        failed = healthy(slots)
        load_s = time.time() - t_load
        if failed and not MEMORY_WORDS.search(failed):
            break
    if failed:
        emit(lab, "REFUSED", f"tries={tries}", f"weights_mib={weights}", failed)
        down()
        return

    load = cards()
    vram = ",".join(f"{c[0]}:{c[2]}" for c in load)
    warm = fanout(PORTS[:slots], model, slots)
    if any(w is None or w[0] <= 1 for w in warm):
        emit(
            lab,
            "DEGENERATE",
            f"warmup produced {[w[0] if w else None for w in warm]} tokens",
        )
        down()
        return
    pool, raw = readback(layout, slots)
    maxconc = next((f.split("=")[1] for f in pool if f.startswith("maxconc=")), "")
    if ENGINE == "vllm" and _num(maxconc):
        dropped = [n for n in levels if n > float(maxconc) * slots]
        if dropped:
            emit(
                lab,
                "WIDTH",
                f"dropped n={','.join(map(str, dropped))}: "
                f"pool holds {maxconc}x a replica",
            )
            levels = [n for n in levels if n not in dropped]
    emit(
        lab,
        "CONFIG",
        f"img={IMG}",
        f"weights_mib={weights}",
        f"free_before={','.join(map(str, free))}",
        f"vram={vram}",
        f"tries={tries}",
        f"load_s={load_s:.0f}",
        *pool,
    )
    if raw:
        emit(lab, "LOG", *raw)

    chars = c.prefill or PREFILL_CHARS
    pre = [prefill_request(PORTS[0], model, k, chars) for k in range(3)]
    good = [r for r in pre if r[4]]
    if good:
        ttft = p50([abs(r[4]) for r in good if r[4] is not None])
        ptok = int(p50([float(r[2]) for r in good]))
        by_usage = sum(1 for r in good if r[4] is not None and r[4] < 0)
        emit(
            lab,
            "PREFILL",
            f"ptok={ptok}",
            f"ttft_p50={ttft:.3f}",
            f"pp={ptok / ttft:.1f}",
            f"reps={len(good)}",
            f"ttft_src={'usage' if by_usage else 'delta'}",
        )
    else:
        emit(lab, "PREFILL", "pp=unread", "the long prompt returned no streamed token")

    for n in levels:
        sidecar = Sidecar()
        sidecar.start()
        t0 = time.time()
        if c.knob and n == 1:
            out: list[Req | None] = [
                knob_request(PORTS[0], model) for _ in range(KNOB_REPS)
            ]
        elif c.knob:
            out = list(closed_loop(PORTS[:slots], model, n))
        else:
            out = fanout(PORTS[:slots], model, n)
        wall = time.time() - t0
        gpu = sidecar.finish(wall)
        rows = [o for o in out if o is not None]
        gen = sum(o[0] for o in rows)
        if (not c.knob and len(rows) != n) or gen == 0:
            emit(lab, f"n={n}", "ERR")
            break
        tpot = [o[5] / (o[0] - 1) for o in rows if o[0] > 1 and o[5] > 0]
        ttfts = [abs(o[4]) for o in rows if o[4] is not None]
        spread = []
        if c.knob and n == 1 and len(tpot) > 1:
            decs = [1 / t for t in tpot]
            spread = [
                f"dec_mean={statistics.mean(decs):.2f}",
                f"dec_sd={statistics.stdev(decs):.2f}",
            ]
        if c.knob and n > 1:
            spread = [f"reqs={len(rows)}", f"knob_s={KNOB_S:.0f}"]
        n_ = max(len(rows), 1)
        tp = p50(tpot)
        emit(
            lab,
            f"n={n}",
            f"agg={gen / wall:.1f}",
            f"dec={1 / tp:.1f}" if tpot else "dec=unread",
            f"tpot_ms_p50={tp * 1000:.1f}" if tpot else "tpot_ms_p50=unread",
            f"ttft_p50={p50(ttfts):.3f}",
            f"p50={p50([o[1] for o in rows]):.2f}",
            f"ptok={sum(o[2] for o in rows) // n_}",
            f"otok={gen // n_}",
            f"otok_req={sum(o[3] for o in rows) // n_}",
            f"early_stop={sum(1 for o in rows if 0 < o[0] < o[3])}/{n_}",
            f"failed={sum(1 for o in rows if o[0] == 0)}/{n_}",
            f"wall={wall:.1f}",
            *spread,
            *gpu,
        )
    down()
    time.sleep(2)


for c in CELLS:
    run_cell(c)
