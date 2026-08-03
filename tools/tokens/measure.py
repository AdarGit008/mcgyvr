#!/usr/bin/env python3
"""#117 — the token estimator's error against real tokenizers.

``estimate_tokens`` (``orchestrator/read.py``) is four characters per token and
says so. Two places spend against it today: the exploration budget charges a
region before reading it, and the decomposer sizes ``context.max_input_tokens``
off ``worker_view()``. A third will — ``check_prompt_fits`` enforces a hard cap.
A hard cap enforced by an unquantified proxy either over-prunes a prompt that
would have fit or admits one the backend rejects, and there is no way to tell
which is happening. This measures which.

**The corpus is captured, not constructed.** #117 says to measure "through the
injectable ``estimate`` seam — the seam exists for exactly this", and that is
literally what happens here: :class:`Recorder` is passed to the real
:func:`~mcgyvr.orchestrator.read.explore` as its ``estimate``, so every string
measured is a string production actually asked the estimator to count, produced
by the real region planner over real repositories. Nothing here reimplements a
window, and no text is hand-picked.

**What is not measured, and cannot be yet.** #117 asks for "a corpus of actual
worker prompts". There are none: #25 owns prompt assembly and is open, and
``check_prompt_fits`` has no production caller. So the corpus is the two things
the estimator is actually applied to today — read regions and worker-view
documents — and the band is a band over *content*. Whatever fixed wrapper #25
adds is unmeasured here, and since a wrapper is mostly prose its ratio will sit
nearer the prose end than the code end. The claim says this rather than implying
coverage it does not have.

**Queries are derived, not chosen.** A hand-picked query list would be a corpus
decision nobody could recheck. Each frame is queried with its own exported
symbol names, sorted for determinism and capped — with the cap reported, because
a silent cap reads as "everything was measured".

**No tokenizer is a runtime dependency and no model is called.** ``tokenizers``
lives in the ``measure`` dependency group, which is not a default group, so
``make setup`` and CI never install it. A tokenizer is a vocabulary file; it is
downloaded from the model's own repository and cached, and nothing is generated.

Usage::

    uv sync --frozen --group measure
    uv run --group measure python tools/tokens/measure.py \
        --out records/measurements/tokens-YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools" / "reach"))

from frames import load_corpus, prepare_clone  # noqa: E402

from mcgyvr.orchestrator.index import build_index  # noqa: E402
from mcgyvr.orchestrator.read import estimate_tokens, explore  # noqa: E402
from mcgyvr.orchestrator.resolve import resolve  # noqa: E402
from mcgyvr.orchestrator.symbols import SymbolKind  # noqa: E402

# The tokenizers of models the shipped capability table actually measures, one
# per distinct vocabulary rather than one per model: the four Qwen2.5-Coder
# sizes share a tokenizer, so tokenizing with all four would report one result
# four times and make n look larger than it is.
TOKENIZERS = {
    "qwen2.5-coder": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "qwen3-coder": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "deepseek-coder-v2": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    "gpt-oss": "openai/gpt-oss-20b",
}

# How many exported names per frame become queries. A cap, so a large frame does
# not dominate n; reported in the summary rather than applied quietly.
QUERIES_PER_FRAME = 40

# The exploration budget each query runs under. Large enough that the planner
# emits several regions per query rather than stopping at the first — what is
# being sampled is regions, and a budget that truncates every query would sample
# only whatever the top-ranked candidate happened to be.
EXPLORE_BUDGET = 20_000


@dataclass
class Recorder:
    """An ``estimate`` that counts exactly as production does, and keeps the text.

    Passed to :func:`explore` through the seam it already has, so the strings
    collected are the strings the budget was actually spent on — not a
    reconstruction of them.
    """

    texts: list[str] = field(default_factory=list)

    def __call__(self, text: str) -> int:
        self.texts.append(text)
        return estimate_tokens(text)


@dataclass(frozen=True)
class Unit:
    """One string the estimator was asked to count, and where it came from."""

    frame: str
    language: str
    kind: str
    chars: int
    estimated: int
    text: str


def fetch_tokenizer(model: str, cache: Path) -> Path:
    """The model's own ``tokenizer.json``, downloaded once and cached.

    A vocabulary file, not a model: nothing is generated, and the measurement
    re-runs from a checkout with network but without inference.
    """
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (model.replace("/", "_") + ".json")
    if target.exists():
        return target
    url = f"https://huggingface.co/{model}/resolve/main/tokenizer.json"
    print(f"  fetching tokenizer {model} ...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as response:
        target.write_bytes(response.read())
    return target


def frame_language(frame: dict) -> str:
    """The frame's language, as the corpus already declares it."""
    return str(frame.get("language", "unknown")).lower()


def queries_for(index: object) -> list[str]:
    """Each frame's own exported names, sorted and capped.

    Derived from the repository rather than chosen, so the query set is
    reproducible and carries no opinion about what is interesting.
    """
    names = sorted(
        {
            symbol.name
            for symbol in index.symbols.all()  # type: ignore[attr-defined]
            if symbol.kind is SymbolKind.EXPORT and len(symbol.name) > 2
        }
    )
    return names[:QUERIES_PER_FRAME]


def capture(frame: dict, workdir: Path) -> Iterator[Unit]:
    """Every string the real read planner charged the budget for, for one frame."""
    clone = prepare_clone(frame, workdir)
    index = build_index(clone)
    language = frame_language(frame)
    for query in queries_for(index):
        recorder = Recorder()
        explore(
            index,
            resolve(index, query),
            budget=EXPLORE_BUDGET,
            estimate=recorder,
        )
        for text in recorder.texts:
            yield Unit(
                frame=frame["repo"],
                language=language,
                kind="read_region",
                chars=len(text),
                estimated=estimate_tokens(text),
                text=text,
            )


def worker_documents(workdir: Path, frames: list[dict]) -> Iterator[Unit]:
    """Worker-view documents, the other text the estimator sizes today.

    Built from real definitions in each frame — one contract per exported symbol
    the index can state a signature for — so the JSON measured has the shape and
    the content a real ``deps`` block carries, rather than a synthetic one.
    """
    from mcgyvr.orchestrator.decompose import (
        DepRef,
        Proposal,
        RecordedProposer,
        decompose,
    )

    for frame in frames:
        clone = prepare_clone(frame, workdir)
        index = build_index(clone)
        language = frame_language(frame)
        definitions = [
            symbol
            for symbol in index.symbols.all()
            if symbol.kind is SymbolKind.DEFINITION and symbol.signature
        ][:QUERIES_PER_FRAME]
        for symbol in definitions:
            proposal = Proposal(
                task_type="bug_fix",
                task=f"{symbol.name} misbehaves under an empty input; fix it.",
                target=symbol.path,
                interface=f"{symbol.name} keeps its current signature",
                deps=(DepRef(symbol.path, symbol.name, "the symbol under repair"),),
                stop_conditions=("the intended behaviour is ambiguous",),
                acceptance=("the repository's own declared check",),
            )
            proposer = RecordedProposer((proposal,))
            result = decompose(index, symbol.name, propose=proposer)
            for built in result.contracts:
                text = json.dumps(built.worker_view(), sort_keys=True)
                yield Unit(
                    frame=frame["repo"],
                    language=language,
                    kind="worker_view",
                    chars=len(text),
                    estimated=estimate_tokens(text),
                    text=text,
                )


def band(errors: list[float]) -> dict[str, float]:
    """The signed error band. Signed because the two directions are not the same.

    Over-estimation costs context: a prompt is pruned that would have fitted.
    Under-estimation costs a rejected request: the backend refuses what the
    check admitted. They are not interchangeable, so a symmetric summary would
    hide the one that actually breaks a run.
    """
    ordered = sorted(errors)
    return {
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p05": ordered[max(0, int(0.05 * len(ordered)) - 1)],
        "p95": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "min": ordered[0],
        "max": ordered[-1],
        "under_estimated_share": sum(1 for e in ordered if e < 0) / len(ordered),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="measurement directory")
    parser.add_argument(
        "--summarise-only",
        action="store_true",
        help="recompute summary.json from an existing units.jsonl, capturing nothing",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path.home() / ".cache" / "mcgyvr" / "tokenizers",
        help="where downloaded tokenizer.json files are kept",
    )
    args = parser.parse_args()

    if args.summarise_only:
        summary = summarise(args.out / "units.jsonl", load_corpus())
        (args.out / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary["overall"], indent=2))
        return 0

    try:
        from tokenizers import Tokenizer
    except ImportError:
        print(
            "error: the `measure` dependency group is not installed.\n"
            "       uv sync --frozen --group measure",
            file=sys.stderr,
        )
        return 2

    corpus = load_corpus()
    frames = list(corpus["frames"])
    loaded = {
        name: Tokenizer.from_file(str(fetch_tokenizer(model, args.cache)))
        for name, model in TOKENIZERS.items()
    }

    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "units.jsonl"
    units: list[Unit] = []
    with tempfile.TemporaryDirectory(prefix="mcgyvr-tokens-") as tmp:
        workdir = Path(tmp)
        for frame in frames:
            print(f"capturing {frame['repo']} ...", file=sys.stderr)
            units.extend(capture(frame, workdir))
        units.extend(worker_documents(workdir, frames))

        with rows_path.open("w", encoding="utf-8") as handle:
            for unit in units:
                row: dict[str, object] = {
                    "frame": unit.frame,
                    "language": unit.language,
                    "kind": unit.kind,
                    "chars": unit.chars,
                    "estimated": unit.estimated,
                    # Four-characters-per-token is an assumption about ASCII
                    # source. Recorded per unit so "the proxy breaks on
                    # non-ASCII text" is a column that can be checked rather
                    # than a story told about the outliers afterwards.
                    "non_ascii_share": sum(1 for c in unit.text if ord(c) > 127)
                    / max(1, unit.chars),
                }
                for name, tokenizer in loaded.items():
                    encoded = tokenizer.encode(unit.text, add_special_tokens=False)
                    real = len(encoded.ids)
                    row[f"tokens.{name}"] = real
                    row[f"error.{name}"] = (
                        (unit.estimated - real) / real if real else 0.0
                    )
                handle.write(json.dumps(row) + "\n")

    summary = summarise(rows_path, corpus)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["overall"], indent=2))
    return 0


def summarise(rows_path: Path, corpus: dict) -> dict:
    """Bands overall, per tokenizer, per language and per kind."""
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line]
    names = list(TOKENIZERS)

    def errors(subset: list[dict], name: str) -> list[float]:
        return [r[f"error.{name}"] for r in subset]

    def group(subset: list[dict]) -> dict:
        return {name: band(errors(subset, name)) for name in names if subset}

    languages = sorted({r["language"] for r in rows})
    kinds = sorted({r["kind"] for r in rows})
    return {
        "identical_vocabularies": _identical(rows, names),
        "record": "measurement/1",
        "issue": 117,
        "corpus": corpus["id"],
        "queries_per_frame": QUERIES_PER_FRAME,
        "explore_budget": EXPLORE_BUDGET,
        "tokenizers": TOKENIZERS,
        "units": len(rows),
        "overall": group(rows),
        "by_language": {
            language: group([r for r in rows if r["language"] == language])
            for language in languages
        },
        "by_kind": {
            kind: group([r for r in rows if r["kind"] == kind]) for kind in kinds
        },
        "by_frame": {
            frame: group([r for r in rows if r["frame"] == frame])
            for frame in sorted({r["frame"] for r in rows})
        },
    }


def _identical(rows: list[dict], names: list[str]) -> list[list[str]]:
    """Tokenizer names that produced the same counts on every unit, grouped.

    Two models can ship the same vocabulary, and when they do, reporting both
    inflates how many independent tokenizers a band rests on. Computed from the
    counts rather than asserted from the model cards, because the counts are
    what the band is made of.
    """
    groups: list[list[str]] = []
    for name in names:
        counts = [r[f"tokens.{name}"] for r in rows]
        for group in groups:
            if [r[f"tokens.{group[0]}"] for r in rows] == counts:
                group.append(name)
                break
        else:
            groups.append([name])
    return [group for group in groups if len(group) > 1]


if __name__ == "__main__":
    raise SystemExit(main())
