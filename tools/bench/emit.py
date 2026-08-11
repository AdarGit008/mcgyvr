#!/usr/bin/env python3
"""#225 — write one paired bench problem's files from an authored spec.

**This emits files. It does not author problems.** Every word of prose, every
reference solution and every assertion is written by hand; what lives here is
only the part that is mechanical and easy to get subtly wrong — the exact
`contract.yaml` shape the strict schema accepts, the folded `task:` scalar, the
`demonstration`-versus-`acceptance` split that distinguishes a `bug_fix` from a
`function_implementation`, and the `meta.json` sidecar that belongs to the ts
arm alone.

Getting those wrong costs a gate rejection per problem, and the f1 band's
remaining tranches are a few hundred problems. The 40 problems of b228-b267
were emitted through this and all 40 were admitted on the first pass.

A spec is a plain dict. The keys are deliberately the same words the brief and
the gate use, so a spec can be read against either:

    {
      "id": "b228-tide-marks",
      "type": "function_implementation",     # or "bug_fix"
      "file_shape": "single_definition",     # or "multi_symbol"
      "shape": "numeric",
      "steering_band": "f1",
      "prose_ts": "...", "prose_py": "...",  # same problem, idiomatic names
      "iface_ts": "...", "iface_py": "...",
      "stop": "one genuine boundary the prose leaves unstated",
      "ref_ts": "...", "ref_py": "...",
      "acc_ts": "...", "acc_py": "...",
      "buggy_ts": "...", "buggy_py": "...",  # bug_fix only -> target_content
      "target_symbol": {"ts": "...", "py": "..."},   # multi_symbol only
      "risk": "low",
    }

Nothing here validates a spec. `tools/bench/admit.py` is the arbiter and this
tool exists to be judged by it, not to anticipate it.

Usage — author a module holding your specs and call :func:`emit` on each::

    from tools.bench.emit import emit
    emit(spec)                       # writes into tools/bench/tasks/
    emit(spec, root=tmp_path)        # or anywhere else
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"

#: Per arm: directory name, reference filename, solution name, checker name and
#: the command the contract declares. The command is what the rig runs, so it
#: is stated here once rather than repeated in every spec.
ARMS = (
    ("ts", "reference.ts", "solution.ts", "accept.mjs", "node accept.mjs"),
    ("py", "reference.py", "solution.py", "accept.py", "python accept.py"),
)


def fold(prose: str) -> str:
    """The `task:` prose as a YAML folded scalar, wrapped and indented two."""
    body = " ".join(prose.split())
    return "\n".join("  " + line for line in textwrap.wrap(body, 68))


def contract(spec: dict[str, Any], arm: str, solution: str, command: str) -> str:
    """One arm's `contract.yaml`.

    A `bug_fix` declares its command under ``demonstration`` rather than
    ``acceptance`` because it must fail on the task's own starting file by
    design (#183); the gate reads that distinction, so it is derived from
    ``type`` here rather than left to the author to remember.
    """
    key = "demonstration" if spec["type"] == "bug_fix" else "acceptance"
    lines = [
        f"id: {spec['id']}",
        f"task_type: {spec['type']}",
        "task: >-",
        fold(spec[f"prose_{arm}"]),
        f"target: {solution}",
    ]
    buggy = spec.get(f"buggy_{arm}")
    if buggy is not None:
        lines.append("target_content: |")
        lines += ["  " + ln if ln.strip() else "" for ln in buggy.splitlines()]
    lines += [
        f'interface: "{spec[f"iface_{arm}"]}"',
        "stop_conditions:",
        f"  - {spec['stop']}",
        f'{key}: ["{command}"]',
        f"risk: {spec.get('risk', 'low')}",
        "scope:",
        f'  allow: ["{solution}"]',
    ]
    return "\n".join(lines) + "\n"


def emit(spec: dict[str, Any], root: Path | None = None) -> list[Path]:
    """Write both arms plus the ts arm's sidecar; return what was written."""
    into = TASKS if root is None else root
    written: list[Path] = []
    for arm, reference, solution, checker, command in ARMS:
        directory = into / arm / spec["id"]
        directory.mkdir(parents=True, exist_ok=True)
        for name, text in (
            (reference, spec[f"ref_{arm}"]),
            (checker, spec[f"acc_{arm}"]),
            ("contract.yaml", contract(spec, arm, solution, command)),
        ):
            (directory / name).write_text(text, encoding="utf-8")
            written.append(directory / name)

    meta: dict[str, Any] = {
        "file_shape": spec["file_shape"],
        "shape": spec["shape"],
        "steering_band": spec["steering_band"],
    }
    if spec["file_shape"] == "multi_symbol":
        meta["target_symbol"] = spec["target_symbol"]
    sidecar = into / "ts" / spec["id"] / "meta.json"
    sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    written.append(sidecar)
    return written
