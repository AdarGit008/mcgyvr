#!/usr/bin/env python3
"""Context-size-vs-quality experiment harness (issue #27).

Runs the fixed task set (context_tasks.py) against a llama-server
OpenAI-compatible endpoint under each context condition (bundle as system
prompt), executes each task's acceptance script, and appends one JSON line
per task x condition to the results file. Resume-safe: existing
(condition, task) keys in the results file are skipped.

Usage:
  python context_exp.py --selftest
  python context_exp.py --model q3b  --base-url http://127.0.0.1:8080/v1
  python context_exp.py --model qwen3 --base-url http://127.0.0.1:8080/v1 \
      --conditions c0,c2
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

from context_tasks import TASKS

REPO = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO / "data" / "context_exp" / "bundles"
RESULTS_DIR = REPO / "data" / "context_exp"
CONDITIONS = ("c0", "c1", "c2", "c3")

MODELS = {
    "q3b": "qwen2.5-coder:3b",
    "qwen3": "qwen3-coder-30b-a3b",
}

MAX_TOKENS = 768
REQUEST_TIMEOUT_S = 600
ACCEPT_TIMEOUT_S = 30
REMEDIATION_FEEDBACK_CHARS = 1000


def load_bundle(condition: str) -> str | None:
    """Return the system-prompt text for a condition; None for c0."""
    if condition == "c0":
        return None
    return (BUNDLE_DIR / f"{condition}.md").read_text()


def extract_code(reply: str) -> str:
    """Pull the code out of a model reply (fenced block preferred)."""
    text = reply.strip()
    if "```" not in text:
        return text
    blocks = []
    parts = text.split("```")
    # parts[1], parts[3], ... are inside fences
    for i in range(1, len(parts), 2):
        block = parts[i]
        first_newline = block.find("\n")
        if first_newline != -1 and block[:first_newline].strip().lower() in (
                "python", "py", ""):
            block = block[first_newline + 1:]
        blocks.append(block)
    if not blocks:
        return text
    return max(blocks, key=len).strip()


def run_acceptance(code: str, accept_src: str) -> tuple[bool, str]:
    """Run the acceptance script against the generated code in a temp dir."""
    with tempfile.TemporaryDirectory(prefix="ctxexp_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "solution.py").write_text(code + "\n")
        (tmp_path / "accept.py").write_text(accept_src)
        try:
            proc = subprocess.run(
                [sys.executable, "accept.py"],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=ACCEPT_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return False, f"acceptance timed out after {ACCEPT_TIMEOUT_S}s"
        output = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, output


def vram_mb() -> int:
    """Current GPU memory usage in MiB (0 if nvidia-smi unavailable)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(out.splitlines()[0])
    except Exception:
        return 0


def chat(base_url: str, model: str, messages: list[dict]) -> tuple[str, dict, float]:
    """One chat completion; returns (content, usage, wall_seconds)."""
    t0 = time.monotonic()
    resp = requests.post(
        f"{base_url}/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": MAX_TOKENS,
        },
        timeout=REQUEST_TIMEOUT_S,
    )
    elapsed = time.monotonic() - t0
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"] or ""
    return content, data.get("usage", {}), elapsed


def run_one(base_url: str, model: str, condition: str, bundle: str | None,
            task: dict, remediate: bool) -> dict:
    """Run one task under one condition, with at most one remediation round."""
    messages = []
    if bundle is not None:
        messages.append({"role": "system", "content": bundle})
    messages.append({"role": "user", "content": task["contract"]})

    reply, usage, latency = chat(base_url, model, messages)
    code = extract_code(reply)
    passed, output = run_acceptance(code, task["accept"])

    record = {
        "task": task["id"],
        "type": task["type"],
        "model": model,
        "condition": condition,
        "pass1": passed,
        "pass_final": passed,
        "remediation_used": False,
        "latency_s": round(latency, 2),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "vram_mb": vram_mb(),
        "fail_output": None if passed else output[:REMEDIATION_FEEDBACK_CHARS],
    }

    if not passed and remediate:
        messages.append({"role": "assistant", "content": reply})
        messages.append({
            "role": "user",
            "content": (
                "The solution failed acceptance with this output:\n\n"
                f"{output[:REMEDIATION_FEEDBACK_CHARS]}\n\n"
                "Return the corrected code only, in a single ```python block."
            ),
        })
        reply2, usage2, latency2 = chat(base_url, model, messages)
        code2 = extract_code(reply2)
        passed2, output2 = run_acceptance(code2, task["accept"])
        record.update({
            "pass_final": passed2,
            "remediation_used": True,
            "remediation_latency_s": round(latency2, 2),
            "remediation_prompt_tokens": usage2.get("prompt_tokens"),
            "remediation_completion_tokens": usage2.get("completion_tokens"),
        })
        if not passed2:
            record["fail_output"] = output2[:REMEDIATION_FEEDBACK_CHARS]

    return record


def selftest() -> int:
    """Validate the rig: every reference solution must pass its acceptance."""
    failures = 0
    for task in TASKS:
        passed, output = run_acceptance(task["reference"], task["accept"])
        status = "ok" if passed else "FAIL"
        print(f"  {task['id']} [{task['type']}] {status}")
        if not passed:
            failures += 1
            print(f"    {output}")
    total = len(TASKS)
    print(f"selftest: {total - failures}/{total} references pass")
    return 0 if failures == 0 else 1


def existing_keys(out_path: Path) -> set:
    """(condition, task) pairs already recorded — for resume."""
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done.add((rec["condition"], rec["task"]))
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--model", choices=sorted(MODELS))
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--conditions", default=",".join(CONDITIONS))
    parser.add_argument("--tasks", default="",
                        help="comma-separated task ids; default all")
    parser.add_argument("--no-remediate", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if not args.model:
        parser.error("--model is required unless --selftest")

    model = MODELS[args.model]
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    for c in conditions:
        if c not in CONDITIONS:
            parser.error(f"unknown condition {c!r}")
    task_filter = {t.strip() for t in args.tasks.split(",") if t.strip()}
    tasks = [t for t in TASKS if not task_filter or t["id"] in task_filter]

    out_path = Path(args.out) if args.out else (
        RESULTS_DIR / f"results_{args.model}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = existing_keys(out_path)
    if done:
        print(f"resume: {len(done)} results already in {out_path}")

    total = len(conditions) * len(tasks)
    n = 0
    with out_path.open("a") as out:
        for condition in conditions:
            bundle = load_bundle(condition)
            for task in tasks:
                n += 1
                if (condition, task["id"]) in done:
                    continue
                record = run_one(args.base_url, model, condition, bundle,
                                 task, remediate=not args.no_remediate)
                out.write(json.dumps(record) + "\n")
                out.flush()
                print(f"[{n}/{total}] {condition} {task['id']} "
                      f"pass1={record['pass1']} final={record['pass_final']} "
                      f"{record['latency_s']}s", flush=True)
    print(f"done -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
