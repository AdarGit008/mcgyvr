#!/usr/bin/env python3
"""Build the mcgyvr OKF bundle from the two crews' findings files.

One concept per claim. Multi-arm claims merge into one document; a later entry
marked SUPERSEDES becomes the standing verdict and the earlier one is kept as
history. Re-runnable: regenerate after any crew appends.
"""
from __future__ import annotations
import json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFY = Path(__file__).resolve().parent
OUT = ROOT / "okf"
STAMP = "2026-08-26T00:00:00Z"
PROVISIONAL_UNTIL = "2026-08-27T00:00:00Z"
APPROVALS = VERIFY / "approvals.json"


def load_approvals() -> dict:
    """Human review decisions, keyed by claim id.

    Written by the review loop, not by hand. A concept the human approved is
    signed `human:<who>` and so passes the trust gate in
    okf_rag/api.py::_okf_result; everything else stays machine-signed and
    get_knowledge() abstains on it. Decisions SURVIVE regeneration — that is
    the whole point of keeping them in a separate file.

    Shape: {"M5": {"decision": "yes"|"no"|"note",
                   "by": "human:adar", "at": "<iso>", "note": "<optional>"}}
    """
    if not APPROVALS.is_file():
        return {}
    return json.loads(APPROVALS.read_text(encoding="utf-8"))

# claim id -> (concept path under okf/, title, tags)
MAP = {
 "H1": ("serving/rigs/srv1-identity", "srv1 hardware identity", ["rig:srv1"]),
 "H2": ("serving/rigs/srv2-identity", "srv2 hardware identity", ["rig:srv2"]),
 "H3": ("serving/rigs/image-digests-pinned", "Serving image digests are identical on both rigs", ["rig:srv1","rig:srv2","reproducibility"]),
 "H4": ("serving/rigs/weights-byte-identical", "Model weights are byte-identical across rigs", ["rig:srv1","rig:srv2","reproducibility"]),
 "H5": ("serving/rigs/memory-bandwidth", "Measured memory bandwidth per rig", ["rig:srv1","rig:srv2","bandwidth"]),
 "L1": ("serving/llamacpp/default-slot-count", "llama.cpp b10481 defaults to 4 slots", ["engine:llamacpp","concurrency"]),
 "L2": ("serving/llamacpp/context-divides-across-slots", "-c divides across slots only when -np is passed", ["engine:llamacpp","kv-cache"]),
 "L3": ("serving/llamacpp/n-cpu-moe-semantics", "What --n-cpu-moe actually does", ["engine:llamacpp","moe","placement"]),
 "L4": ("serving/llamacpp/ollama-cannot-express-n-cpu-moe", "ollama cannot express expert offload", ["engine:ollama","moe","placement"]),
 "L5": ("serving/llamacpp/n-cpu-moe-non-monotone-edge", "The --n-cpu-moe curve at the VRAM edge", ["engine:llamacpp","moe","search"]),
 "L6": ("serving/llamacpp/no-mmap-host-asymmetry", "--no-mmap is host-dependent, and by how much", ["engine:llamacpp","memory","rig:srv1","rig:srv2"]),
 "L7": ("serving/llamacpp/kv-q8-cost", "Quantised KV cache at -c 4096", ["engine:llamacpp","kv-cache"]),
 "L8": ("serving/llamacpp/gptoss-architecture-refusal", "gpt-oss-20b will not load in b10481", ["engine:llamacpp","refusal"]),
 "L9": ("serving/llamacpp/srv1-n-cpu-moe-floor", "srv1's expert-offload floor for the 35B", ["engine:llamacpp","moe","rig:srv1","refusal"]),
 "L10": ("serving/llamacpp/ttft-by-rig", "Time to first token, per rig", ["engine:llamacpp","latency","rig:srv1","rig:srv2"]),
 "L11": ("serving/llamacpp/width-sweep-srv2-moe", "Slot width on an expert-offloaded MoE (srv2)", ["engine:llamacpp","moe","concurrency","rig:srv2"]),
 "L12": ("serving/llamacpp/srv1-7b-width-turnover", "srv1's dense 7B turns over at 8 slots", ["engine:llamacpp","concurrency","rig:srv1"]),
 "L13": ("serving/llamacpp/srv1-kv-budget-product", "srv1's KV budget is the product np x ctx_slot", ["engine:llamacpp","kv-cache","rig:srv1","refusal"]),
 "L14": ("serving/llamacpp/context-buys-nothing", "Context length buys throughput nothing and costs VRAM", ["engine:llamacpp","kv-cache"]),
 "L15": ("serving/llamacpp/srv1-throughput-32-slots", "srv1 llama-server throughput at 32 slots", ["engine:llamacpp","throughput","rig:srv1"]),
 "L16": ("serving/llamacpp/srv2-throughput-128-slots", "srv2 llama-server throughput at 128 slots", ["engine:llamacpp","throughput","rig:srv2"]),
 "L17": ("serving/llamacpp/srv2-7b-throughput-32-slots", "srv2 llama-server 7B throughput at 32 slots", ["engine:llamacpp","throughput","rig:srv2"]),
 "L18": ("serving/llamacpp/smaller-quant-bigger-model", "A smaller quant of a bigger model wins", ["engine:llamacpp","quantisation","moe"]),
 "L19": ("serving/llamacpp/thread-count-scaling", "Thread count scales with layers on the CPU", ["engine:llamacpp","threads","moe"]),
 "L20": ("serving/llamacpp/threadpool-spin-wait", "The threadpool spin-waits, so oversubscription collapses throughput", ["engine:llamacpp","threads","contention"]),
 "L21": ("serving/llamacpp/moe-co-residency", "Two expert-offloaded MoE models co-reside on srv1", ["engine:llamacpp","moe","co-residency","rig:srv1"]),
 "L22": ("serving/llamacpp/single-stream-independent-of-slots", "Single-stream rate does not depend on slot count", ["engine:llamacpp","throughput"]),
 "V1": ("serving/vllm/enforce-eager-cost", "What --enforce-eager costs, per rig", ["engine:vllm","cuda-graphs","rig:srv1","rig:srv2"]),
 "V2": ("serving/vllm/cuda-graph-capability-gate", "vLLM 0.26.0 has no compute-capability gate on graph capture", ["engine:vllm","cuda-graphs","source"]),
 "V3": ("serving/vllm/srv1-responsive-axes", "How many configuration axes move srv1", ["engine:vllm","rig:srv1"]),
 "V4": ("serving/vllm/srv1-throughput-ceiling", "srv1's vLLM throughput ceiling", ["engine:vllm","throughput","rig:srv1"]),
 "V5": ("serving/vllm/srv2-best-cell", "srv2's best vLLM configuration", ["engine:vllm","throughput","rig:srv2"]),
 "V6": ("serving/vllm/fp8-kv-mechanism", "What fp8 KV cache actually buys", ["engine:vllm","kv-cache","rig:srv2"]),
 "V7": ("serving/vllm/srv1-capability-refusals", "srv1's compute-capability refusals", ["engine:vllm","refusal","rig:srv1"]),
 "V8": ("serving/vllm/srv1-dense-7b-refusal", "srv1 cannot serve a dense 7B under vLLM", ["engine:vllm","refusal","rig:srv1"]),
 "V9": ("serving/vllm/declared-flag-surface", "The declared vLLM flag surface, and how much was tried", ["engine:vllm","coverage"]),
 "V10": ("serving/vllm/expert-offload-equivalent", "Whether vLLM has an expert-offload knob", ["engine:vllm","moe","placement"]),
 "V11": ("serving/vllm/max-model-len-semantics", "What --max-model-len reserves", ["engine:vllm","kv-cache"]),
 "V12": ("serving/vllm/speculative-decoding-loses", "Speculative decoding at every concurrency", ["engine:vllm","speculative"]),
 "V13": ("serving/vllm/host-ram-invisible-to-resident-model", "Host RAM is invisible to a card-resident model", ["engine:vllm","memory"]),
 "V14": ("serving/vllm/srv2-best-cell-repeatability", "How well srv2's best cell repeats", ["engine:vllm","reproducibility","rig:srv2"]),
 "M1": ("serving/method/tasks-per-hour-void", "The tasks/h figures measured a slot default, not a configuration", ["method","defect"]),
 "M2": ("serving/method/cross-host-contrast-confound", "The cross-host contrasts and their confound", ["method","defect","rig:srv1","rig:srv2"]),
 "M3": ("serving/method/expert-offload-batching", "'Expert offload does not batch' is about -np 4", ["method","moe","concurrency"]),
 "M4": ("serving/method/offload-bandwidth-bound", "Decode under expert offload is memory-bandwidth-bound", ["method","moe","bandwidth"]),
 "M5": ("serving/method/run-to-run-spread", "Run-to-run spread, per rig and per engine", ["method","noise","rig:srv1","rig:srv2"]),
 "M6": ("serving/method/nothing-scores-quality", "Nothing in the serving corpus scores quality", ["method","scope"]),
 "M7": ("serving/method/srv1-engine-choice-gap", "What engine choice is worth on srv1", ["method","rig:srv1"]),
 "M8": ("serving/method/cgroup-cap-not-a-small-machine", "A cgroup memory cap does not simulate a smaller machine", ["method","defect","memory"]),
}

# claims the GPU crew was asked to close; any without a 2026-08-26 entry stays provisional
OWED = {"L5","L6","L12","L13","L15","L19","L20","L21","V7","V8","M5","H5"}

VERDICT_WORD = {"V":"verified","F":"falsified","P":"partial","U":"untestable","-":"untested"}
APPROVED: dict = {}


def _status(cid: str, provisional: bool) -> str:
    d = APPROVED.get(cid, {}).get("decision")
    if d == "no":
        return "deprecated"
    if provisional:
        return "provisional"
    return "stable"

def parse(path: Path, rig: str) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    gpu_at = text.find("## GPU re-runs, 2026-08-26")
    entries, parts = [], re.split(r"^### ", text, flags=re.M)[1:]
    pos = 0
    for p in parts:
        pos = text.find("### " + p[:40], pos)
        head, _, rest = p.partition("\n")
        m = re.match(r"^([HLVM]\d+)\b", head.strip())
        if not m:
            continue
        def field(name):
            mm = re.search(rf"^\*\*{name}:\*\*\s*(.*?)(?=\n\*\*|\Z)", rest, re.S | re.M)
            return mm.group(1).strip() if mm else ""
        vm = re.search(r"\[([VFPU ])\]", head)
        letter = (vm.group(1).strip() or "-") if vm else "-"
        if letter == "-" and re.search(r"FALSIFIED|falsified", head):
            letter = "F"
        am = re.search(r"\(([^)]*arm[^)]*)\)", head)
        entries.append(dict(
            id=m.group(1), rig=rig, arm=am.group(1) if am else None,
            letter=letter, headline=head.strip(), claim=field("Claim"),
            verdict=field("Verdict"), bears=field("Bears on"),
            blocks=re.findall(r"```(?:bash)?\n(.*?)```", rest, re.S),
            supersedes="SUPERSEDES" in head or "SUPERSEDES" in rest[:400],
            from_gpu=gpu_at != -1 and pos >= gpu_at,
        ))
        pos += 1
    return entries

def register_claims() -> dict[str, str]:
    """Canonical claim wording, read from CLAIMS.md rather than an arm restatement."""
    out: dict[str, str] = {}
    for line in (VERIFY / "CLAIMS.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^- \[.\]\s+([HLVM]\d+)\s+(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out

REGISTER = register_claims()


def yaml_list(xs): return "[" + ", ".join(xs) + "]"

def emit(cid: str, group: list[dict]) -> str | None:
    if cid not in MAP:
        return None
    slug, title, tags = MAP[cid]
    settled = [e for e in group if e["letter"] in "VFP"]
    if not settled:
        return None  # untested -> excluded by the chosen scope
    standing = [e for e in settled if e["supersedes"]] or settled
    letters = {e["letter"] for e in standing}
    verdict = "F" if "F" in letters else ("P" if "P" in letters else "V")
    claim = REGISTER.get(cid) or next((e["claim"] for e in group if e["claim"]), "")
    provisional = cid in OWED and not any(e["from_gpu"] for e in group)

    fm = [
        "---",
        "type: Finding",
        f"title: {json.dumps(title)}",
        f"id: claim-{cid}",
        f"description: {json.dumps(f'Claim {cid} of the 2026-08-25 serving report: {VERDICT_WORD[verdict]}.')}",
        f"aliases: {yaml_list([json.dumps(f'claim {cid}'), json.dumps(cid)])}",
        f"tags: {yaml_list([json.dumps(t) for t in ['serving', f'verdict:{VERDICT_WORD[verdict]}', *tags]])}",
        f"status: {_status(cid, provisional)}",
    ]
    decision = APPROVED.get(cid)
    if decision and decision.get("decision") == "yes":
        fm.append("verified: { by: %s, at: %s }" % (decision["by"], decision["at"]))
    else:
        fm.append("verified: { by: machine:claude-opus-5, at: " + STAMP + " }")
    if decision and decision.get("decision") == "no":
        fm.append("status_note: %s" % json.dumps("rejected on human review"))
    if provisional:
        fm.append(f"stale_after: {PROVISIONAL_UNTIL}")
    fm += ["sources:"]
    seen = set()
    for e in group:
        for ref in re.findall(r"`([^`]+)`", e["bears"]):
            ref = ref.strip()
            # keep only real references: a repo path, or a URL. Split backticks
            # in the prose leave fragments like ":69-70" that are not sources.
            is_path = "/" in ref and not ref.startswith(":") and " " not in ref
            is_url = ref.startswith("http")
            if ref in seen or not (is_path or is_url):
                continue
            seen.add(ref)
            fm.append(f"  - resource: {json.dumps(ref)}")
    if not seen:
        fm.append(f'  - resource: ".verify/{group[0]["rig"]}-findings.md"')
    fm.append("---")

    out = ["\n".join(fm), "", f"# {cid} — {title}", "",
           f"**Claim as written.** {claim}", "",
           f"**Standing verdict: {VERDICT_WORD[verdict].upper()}.**", ""]
    for e in group:
        if e["letter"] not in "VFP":
            continue
        label = f"{e['rig']}" + (f", {e['arm']}" if e["arm"] else "")
        stale = " *(superseded below)*" if (e in settled and e not in standing) else ""
        out += [f"## Evidence — {label} [{VERDICT_WORD[e['letter']]}]{stale}", "",
                e["verdict"], ""]
        for i, b in enumerate(e["blocks"]):
            fence = "bash" if i == 0 and len(e["blocks"]) > 1 else ""
            out += [f"```{fence}", b.rstrip(), "```", ""]
        if e["bears"]:
            out += [f"Bears on: {e['bears']}", ""]
    out += ["---", "",
            f"Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · "
            f"Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, "
            f"`records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`"]
    return "\n".join(out) + "\n"

def main():
    global APPROVED
    APPROVED = load_approvals()
    entries = parse(VERIFY / "srv1-findings.md", "srv1") + parse(VERIFY / "srv2-findings.md", "srv2")
    groups = defaultdict(list)
    for e in entries:
        groups[e["id"]].append(e)
    OUT.mkdir(exist_ok=True)
    (OUT / "index.md").write_text('---\nokf_version: "0.2"\n---\n\n# mcgyvr OKF bundle\n\n'
        'Serving findings from the 2026-08-25 report, each verified or falsified against\n'
        'the rigs. One concept per claim. Built by `.verify/build_okf.py` — regenerate,\n'
        'do not hand-edit.\n', encoding="utf-8")
    written, skipped = [], []
    for cid in MAP:
        doc = emit(cid, groups.get(cid, []))
        if doc is None:
            skipped.append(cid); continue
        p = OUT / (MAP[cid][0] + ".md")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(doc, encoding="utf-8")
        written.append(cid)
    print(f"written {len(written)} concepts -> {OUT}")
    print(f"skipped (no verdict-carrying entry): {skipped}")
    prov = [c for c in written if "status: provisional" in (OUT / (MAP[c][0] + ".md")).read_text()]
    print(f"provisional (GPU crew may supersede): {prov}")
    yes = [c for c, d in APPROVED.items() if d.get("decision") == "yes"]
    no = [c for c, d in APPROVED.items() if d.get("decision") == "no"]
    print(f"human-approved (pass the trust gate): {len(yes)} {sorted(yes)}")
    print(f"human-rejected (status deprecated)  : {len(no)} {sorted(no)}")
    print(f"unreviewed (machine-signed, abstain): "
          f"{len([c for c in written if c not in APPROVED])}")

if __name__ == "__main__":
    main()
