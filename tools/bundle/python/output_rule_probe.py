#!/usr/bin/env python3
"""#167 — is mcgyvr's high c0 its output rule, or the contracts it was ported to?

The Python arm run through mcgyvr's rig is flat, and it is flat at a baseline
that already sits where CLM-0004's *bundle* got to: c0 scores 13/20 at 111.8
completion tokens where the original harness's c0 scores 7/20 at 427.4. The
reading is that mcgyvr's user-message assembly ends with an output rule —
"Reply with the complete new content of solution.py, as one fenced code block
and nothing else" — and that is the device CLM-0004 measured the bundle working
through, so the bundle arrives with nothing left to do.

There is an obvious competing explanation and it is not flattering: the mcgyvr
contracts were written by hand for this port, and a rewrite can make tasks
easier without anyone meaning it to. Arm A's per-task pattern already argues
against a wholesale effect — six tasks never pass in every arm, and arm A's set
differs from the other two by one swap in each direction — but "roughly cancels"
is not the same as "is not there".

This probe removes the rewrite from the question. It runs the **recovered**
tasks through the **recovered** harness at c0, changing exactly one thing: the
mcgyvr output rule is appended to the contract text, in the user message, where
mcgyvr puts it. Nothing else moves — same twenty contracts local-ai wrote, same
extractor, same acceptance, same endpoint.

If completion tokens collapse and the rate rises, the output rule is doing the
work and the port is not. If they do not move, arm A's baseline is an artefact
of how these contracts were written and the finding does not stand.

The vendored files are imported, never edited: the task dicts are copied and the
copies are what get the extra sentence.

Usage::

    tools/bundle/python/output_rule_probe.py --base-url http://srv1:11434/v1 \\
        --instrument <dir with the vendored mvp/instrumentation> \\
        --out records/measurements/python-bundle-YYYY-MM-DD/output-rule-probe.jsonl
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

# The tail of ``render_user_message``, verbatim. Quoted rather than imported
# because the point is to add it to a prompt this project does not build: the
# probe is about the sentence, not about mcgyvr's assembly, and importing the
# renderer would bring the rest of the assembly with it.
OUTPUT_RULE = (
    "OUTPUT: Reply with the complete new content of solution.py, as one fenced "
    "code block and nothing else. Not a diff, not an excerpt, not the changed "
    "lines — the whole file as it should exist after your change."
)


def load_instrument(instrument: Path) -> tuple[Any, list[dict[str, str]]]:
    """The vendored harness and its task set, imported by path and unmodified."""
    sys.path.insert(0, str(instrument))
    spec = importlib.util.spec_from_file_location(
        "context_exp_probe", instrument / "context_exp.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import context_exp.py from {instrument}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, list(module.TASKS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:3b")
    parser.add_argument("--instrument", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--tasks", default="", help="comma-separated task ids; default all"
    )
    args = parser.parse_args()

    harness, tasks = load_instrument(args.instrument)
    only = {t.strip() for t in args.tasks.split(",") if t.strip()}
    if only:
        tasks = [t for t in tasks if t["id"] in only]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    passed = 0
    with args.out.open("w", encoding="utf-8") as handle:
        for n, task in enumerate(tasks, start=1):
            amended = copy.deepcopy(task)
            amended["contract"] = f"{task['contract']}\n\n{OUTPUT_RULE}"
            # bundle=None is c0: no system prompt at all, which is the condition
            # the original harness scored 7/20 on.
            record = harness.run_one(
                args.base_url,
                args.model,
                "c0+output_rule",
                None,
                amended,
                remediate=False,
            )
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            passed += bool(record["pass1"])
            print(
                f"[{n}/{len(tasks)}] {task['id']} pass1={record['pass1']} "
                f"completion_tokens={record.get('completion_tokens')}",
                flush=True,
            )
    print(f"\n{passed}/{len(tasks)} first-pass with the output rule appended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
