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
- per-``(problem, language)`` cap (``--cap``, default 40), selected round-robin
  across models so no single model's phrasing dominates;
- validation split by problem (``--split-by``, default ``problem``), so both
  language arms of a problem land on the same side.

**Two senses of "arm" meet in this file, and they are not the same thing.** The
``arm`` field in a run's ``results.jsonl`` — and the ``arm`` group of a
candidate path — is the *sampling* arm (``greedy``, ``t07``…): how the reply
was drawn. It is called ``sample`` throughout this module. #197's arm is the
*language* (``jsts``/``python``): two contracts, one problem id, one directory
name in each of ``tools/problems/tasks/ts`` and ``…/py``. It is called
``language`` here, and it is read off the resolved contract rather than guessed
from the tier name.

Why the cap and the split key on those things:

- A problem's two language arms are separate training material — separate
  prompts, separate solutions — so they get separate cap budgets. Keyed on the
  bare problem id (as this tool did before #197 landed paired arms) one arm
  could consume the whole cap and the other contribute nothing. Keyed on the
  *tier* instead, the same contract served by two tiers of one language would
  get two budgets, which is the opposite error.
- A problem's two language arms are near-translations of each other. Bucketing
  the split per reply put one arm in train and its pair in val for roughly 18%
  of problems, so val measured recall of a solution already seen in the other
  language. Holding out the *problem* is what makes val a generalisation
  measure — the property #113's held-out set exists for.
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

_CANDIDATE = re.compile(
    r"^candidates/(?P<task>[^/]+)/(?P<sample>.+)-(?P<draw>\d+)\.txt$"
)

#: One in this many buckets goes to validation.
_VAL_BUCKET = 10

SPLIT_MODES = ("problem", "reply")


def _in_validation(mode: str, task: str, sha: str) -> bool:
    """Whether an example is held out, under the selected split rule.

    ``reply`` is #189's original rule byte for byte — the sha read as an
    integer — so a dataset built before paired arms still reproduces. ``problem``
    hashes the id instead, because a problem id is not hex, and puts both
    language arms of a problem on the same side.
    """
    if mode == "reply":
        return int(sha, 16) % _VAL_BUCKET == 0
    digest = hashlib.sha256(task.encode("utf-8")).hexdigest()
    return int(digest, 16) % _VAL_BUCKET == 0


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


def build(cap: int, out_dir: Path, split_by: str = "problem") -> dict[str, Any]:
    if split_by not in SPLIT_MODES:
        raise SystemExit(
            f"unknown --split-by {split_by!r}: expected one of {SPLIT_MODES}"
        )
    breadth = _load_breadth()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    #: (tier, task) -> (system, user, language). Keyed on the tier because that
    #: is what resolves a contract; the language it yields is what the cap and
    #: the manifest actually key on.
    prompts: dict[tuple[str, str], tuple[str, str, str]] = {}
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
        row = results[run].get((task, match.group("sample"), int(match.group("draw"))))
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
            # The language arm comes off the resolved contract, not off the
            # tier name: load_tier_tasks is what decides it, and a tier is free
            # to change which arm it serves without renaming itself.
            prompts[(tier, task)] = (
                prompt.system,
                prompt.user,
                tasks[task].language.name,
            )
        system, user, language = prompts[(tier, task)]

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
        item = {
            "task": task,
            "tier": tier,
            "language": language,
            "model": entry["model"],
            "run": run,
            "file": entry["file"],
            "sha256": sha,
            "system": system,
            "user": user,
            "assistant": reply.decode("utf-8"),
        }
        seen = candidates.get(sha)
        if seen is not None:
            dropped["duplicate-reply"] += 1
            # Identical bytes, so the example is the same either way — but the
            # attribution differs, and `model` steers the round-robin below.
            # Keep the lexicographically first (run, file) rather than whichever
            # the corpus happened to list first, so the output does not depend
            # on golden.json's entry order.
            if (seen["run"], seen["file"]) <= (run, entry["file"]):
                continue
        candidates[sha] = item

    # The cap's unit is the (problem, language) pair — one problem id names two
    # contracts, and each is its own training material.
    by_arm: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for item in candidates.values():
        by_arm[(item["task"], item["language"])].append(item)

    kept: list[dict[str, Any]] = []
    for key in sorted(by_arm):
        pool = by_arm[key]
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
        dropped["over-arm-cap"] += len(pool) - len(chosen)
        kept.extend(chosen)

    kept.sort(key=lambda i: (str(i["task"]), str(i["language"]), str(i["sha256"])))
    train, val = [], []
    for item in kept:
        held_out = _in_validation(split_by, str(item["task"]), str(item["sha256"]))
        (val if held_out else train).append(item)

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

    by_language = collections.Counter(str(item["language"]) for item in kept)
    manifest = {
        # /2: the cap and the split became arm-aware (#210), so counts carry a
        # language breakdown and `tasks` no longer doubles as an example unit.
        "record": "finetune-dataset/2",
        "source": "records/corpora/worker-replies/golden.json",
        "cap_per_arm": cap,
        "split_by": split_by,
        "counts": {
            "train": len(train),
            "val": len(val),
            "problems": len({str(item["task"]) for item in kept}),
            "arms": len(by_arm),
            "by_language": dict(sorted(by_language.items())),
            "dropped": dict(sorted(dropped.items())),
        },
        "examples": [
            {
                k: item[k]
                for k in ("task", "tier", "language", "model", "run", "file", "sha256")
            }
            for item in kept
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cap",
        type=int,
        default=40,
        help="max examples per (problem, language) arm",
    )
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument(
        "--split-by",
        choices=SPLIT_MODES,
        default="problem",
        help=(
            "hold out whole problems (default, keeps paired arms together) or "
            "individual replies (#189's original rule)"
        ),
    )
    args = parser.parse_args()
    manifest = build(args.cap, args.out, args.split_by)
    counts = manifest["counts"]
    print(
        f"train={counts['train']} val={counts['val']} "
        f"problems={counts['problems']} arms={counts['arms']} "
        f"by_language={counts['by_language']} dropped={counts['dropped']}"
    )


if __name__ == "__main__":
    main()
