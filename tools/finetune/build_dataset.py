"""Build the #189 pilot's training set from the worker-reply corpus.

The corpus (`records/corpora/worker-replies/golden.json`, ADR-0016) pins every
captured reply with its sha and its parse verdict; each run's `results.jsonl`
records whether the checker passed the reply. This tool joins the two and emits
chat-format training examples for exactly the rows that are **verified passes**:
the reply parsed, the checker accepted it, and the bytes on disk still match the
pinned sha.

The prompt is not stored anywhere — per ADR-0016 the corpus keeps only what the
parser reads — so it is **rebuilt** through the same assembly the rigs used:
:func:`mcgyvr.worker.prompt.build_prompt` over the tier's contracts. Each run
pinned ``sha256(prompt.system)`` as ``bundle_sha256`` at capture time; the
rebuild recomputes it and refuses to emit a run whose prompt no longer matches.
A training pair whose prompt is not the prompt the reply actually answered is
worse than a missing one.

Curation, all deterministic:

- dedup by reply sha across the whole set — the same solution drawn twice is
  one example;
- per-task cap (``--cap``, default 40), selected round-robin across models so
  no single model's phrasing dominates a task;
- validation split by reply-sha bucket (``sha % 10 == 0``), so membership is a
  property of the reply, not of the run order.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MEASUREMENTS = REPO / "records" / "measurements"
GOLDEN = REPO / "records" / "corpora" / "worker-replies" / "golden.json"

sys.path.insert(0, str(REPO / "src"))

_CANDIDATE = re.compile(r"^candidates/(?P<task>[^/]+)/(?P<arm>.+)-(?P<draw>\d+)\.txt$")


def _load_breadth() -> Any:
    spec = importlib.util.spec_from_file_location(
        "breadth_measure", REPO / "tools" / "breadth" / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _results_index(run_dir: Path) -> dict[tuple[str, str, int], dict[str, Any]]:
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    path = run_dir / "results.jsonl"
    if not path.is_file():
        return index
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "arm" in row and "draw" in row:
            index[(row["task"], row["arm"], int(row["draw"]))] = row
    return index


def build(cap: int, out_dir: Path) -> dict[str, Any]:
    breadth = _load_breadth()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    prompts: dict[tuple[str, str], tuple[str, str]] = {}
    verified_bundles: set[str] = set()
    results: dict[str, dict[tuple[str, str, int], dict[str, Any]]] = {}
    dropped = collections.Counter[str]()
    candidates: dict[str, dict[str, Any]] = {}

    for entry in golden["entries"]:
        if "expect" not in entry or "content_sha256" not in entry.get("expect", {}):
            dropped["refusal"] += 1
            continue
        match = _CANDIDATE.match(entry["file"])
        if match is None:
            dropped["unrecognized-path"] += 1
            continue
        run, task = entry["run"], match.group("task")
        run_dir = MEASUREMENTS / run
        if run not in results:
            results[run] = _results_index(run_dir)
        row = results[run].get((task, match.group("arm"), int(match.group("draw"))))
        if row is None:
            dropped["no-results-row"] += 1
            continue
        if not row.get("passed"):
            dropped["not-passed"] += 1
            continue

        reply_path = run_dir / entry["file"]
        reply = reply_path.read_bytes()
        if hashlib.sha256(reply).hexdigest() != entry["sha256"]:
            raise SystemExit(f"corpus rot: {reply_path} disagrees with its pinned sha")

        run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        tier = run_meta.get("tier", "d1")
        if (tier, task) not in prompts:
            tasks = {t.id: t for t in breadth.load_tier_tasks(tier, (task,))}
            prompt = breadth.build_prompt(tasks[task].contract)
            prompts[(tier, task)] = (prompt.system, prompt.user)
        system, user = prompts[(tier, task)]

        pinned = run_meta.get("bundle_sha256")
        rebuilt = hashlib.sha256(system.encode("utf-8")).hexdigest()
        if pinned is not None and pinned != rebuilt and run not in verified_bundles:
            raise SystemExit(
                f"prompt drift: {run} pinned bundle {pinned[:12]} but the current "
                f"assembly produces {rebuilt[:12]} — the rebuilt prompt is not the "
                "prompt these replies answered"
            )
        verified_bundles.add(run)

        sha = entry["sha256"]
        if sha in candidates:
            dropped["duplicate-reply"] += 1
            continue
        candidates[sha] = {
            "task": task,
            "tier": tier,
            "model": entry["model"],
            "run": run,
            "file": entry["file"],
            "sha256": sha,
            "system": system,
            "user": user,
            "assistant": reply.decode("utf-8"),
        }

    by_task: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for item in candidates.values():
        by_task[item["task"]].append(item)

    kept: list[dict[str, Any]] = []
    for task in sorted(by_task):
        pool = by_task[task]
        by_model: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for item in pool:
            by_model[item["model"]].append(item)
        for items in by_model.values():
            items.sort(key=lambda i: str(i["sha256"]))
        order = sorted(by_model)
        chosen: list[dict[str, Any]] = []
        while len(chosen) < cap and any(by_model[m] for m in order):
            for model in order:
                if by_model[model] and len(chosen) < cap:
                    chosen.append(by_model[model].pop(0))
        dropped["over-task-cap"] += len(pool) - len(chosen)
        kept.extend(chosen)

    kept.sort(key=lambda i: (str(i["task"]), str(i["sha256"])))
    train, val = [], []
    for item in kept:
        (val if int(str(item["sha256"]), 16) % 10 == 0 else train).append(item)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, split in (("train", train), ("val", val)):
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for item in split:
                fh.write(
                    json.dumps(
                        {
                            "messages": [
                                {"role": "system", "content": item["system"]},
                                {"role": "user", "content": item["user"]},
                                {"role": "assistant", "content": item["assistant"]},
                            ]
                        }
                    )
                    + "\n"
                )

    manifest = {
        "record": "finetune-dataset/1",
        "issue": 189,
        "source": "records/corpora/worker-replies/golden.json",
        "cap_per_task": cap,
        "counts": {
            "train": len(train),
            "val": len(val),
            "tasks": len(by_task),
            "dropped": dict(dropped),
        },
        "examples": [
            {k: item[k] for k in ("task", "tier", "model", "run", "file", "sha256")}
            for item in kept
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap", type=int, default=40, help="max examples per task")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args()
    manifest = build(args.cap, args.out)
    counts = manifest["counts"]
    print(
        f"train={counts['train']} val={counts['val']} tasks={counts['tasks']} "
        f"dropped={counts['dropped']}"
    )


if __name__ == "__main__":
    main()
