"""The package as installed: what imports, what is pinned, what the seam allows."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._paths import REPO, SRC

#: Run in a child interpreter: import every module the package's walk finds,
#: print one line per failure, and exit non-zero when there was any. A module
#: that ends the interpreter at import is a failure like any other, so the
#: walk catches that too, and its last line says the walk reached its end.
_WALK_ENDED = "the walk reached its end"


_IMPORT_ALL = f"""
import importlib
import pkgutil
import sys

import mcgyvr

failed = []
tried = 0
for info in pkgutil.walk_packages(
    mcgyvr.__path__, "mcgyvr.", onerror=lambda name: failed.append(name)
):
    tried += 1
    try:
        importlib.import_module(info.name)
    except BaseException as exc:
        failed.append(f"{{info.name}}: {{type(exc).__name__}}: {{exc}}")
print("\\n".join(failed))
print(f"{_WALK_ENDED}: {{tried}} modules tried")
sys.exit(1 if failed else 0)
"""


#: The only inputs a wheel build is given: the package's sources, the data it
#: ships, and the project metadata.
PRODUCT_ALONE = ("pyproject.toml", "LICENSE", "src", "data", "skills/mcgyvr/SETUP.md")


def _uv() -> str:
    found = shutil.which("uv")
    if found is None:
        pytest.fail("uv is not on PATH; the release builds with `uv build`")
    return found


def _git(where: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(where), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
    )


def _product_alone(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    for entry in PRODUCT_ALONE:
        source, target = REPO / entry, tree / entry
        if source.is_dir():
            shutil.copytree(
                source, target, ignore=shutil.ignore_patterns("__pycache__")
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    _git(tree, "init", "-q")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-qm", "the product alone")
    return tree


#: The one module that is allowed to reach into both halves, because reaching
#: into both halves is what it is for. The ``mcgyvr.cli`` package re-exports
#: ``main`` as its command-line entrypoint. A single ``argparse`` parser
#: dispatches ``detect``, ``pool``, ``scan`` and ``emit`` below the seam and
#: ``run`` and ``contract`` above it; it imports ``mcgyvr.serving`` at module
#: level for ``emit`` and defers ``mcgyvr.contract``/``mcgyvr.orchestrator``
#: for ``run`` and ``contract``. Neither import is a half of mcgyvr forgetting
#: where the seam is. Written down here rather than left to a rule's silence,
#: so that what is exempt is a name a reader can find. This is the only
#: exemption in the file that names a whole module, and it names a whole
#: module because an entrypoint reaches into both halves by definition.
THE_COMMAND_LINE_ENTRYPOINT: str = "mcgyvr.cli"


def _module_path(dotted: str) -> Path:
    """The file a dotted ``mcgyvr.*`` module name names, package or plain."""
    rel = dotted.removeprefix("mcgyvr.").replace(".", "/")
    if dotted == "mcgyvr":
        return SRC / "__init__.py"
    direct = SRC / f"{rel}.py"
    if direct.is_file():
        return direct
    return SRC / rel / "__init__.py"


def _is_module(dotted: str) -> bool:
    """Does ``dotted`` name a file in this tree?"""
    return _module_path(dotted).is_file()


def _dotted_name(path: Path) -> str | None:
    """The dotted name ``path`` is importable as, or ``None`` if it is not.

    A ``.py`` file is a module when every path segment is a legal Python
    identifier. The staged gate scripts under ``serving/gate-scripts/`` are
    not — ``01-config.py``, ``data-10-scan.py``, the directory itself — and no
    import statement can reach them.
    """
    rel = path.relative_to(SRC)
    parts = rel.parts[:-1] if rel.name == "__init__.py" else (*rel.parts[:-1], rel.stem)
    if not all(part.isidentifier() for part in parts):
        return None
    return ".".join(("mcgyvr", *parts))


def _imports_in(source: str, package: str = "mcgyvr") -> set[str]:
    """Every ``mcgyvr.*`` module ``source`` imports, wherever the import sits —
    top of the file, inside a function, under ``TYPE_CHECKING``. All of them, on
    purpose: a deferred import is still a real dependency at the moment it runs,
    and both of the crossings this file knows about (in ``detect.detect_docker``
    and ``sandbox.base.open_sandbox``) are exactly that shape, so a check that
    only looked at the top of the file would miss the crossings it was written
    to find.

    Three spellings reach a module and all three are resolved, because a rule
    that only understands one of them can be walked around by writing another:
    ``import mcgyvr.contract``, ``from mcgyvr.contract import Contract``, ``from
    mcgyvr import contract`` (``orchestrator/decompose.py``, ``cli.py``) and the
    relative ``from . import contract`` (``docgen.py``). The last two name a
    module in the *imported names* rather than in the module path, so each name
    is followed only when ``package.name`` is a file in this tree — otherwise
    ``from mcgyvr.contract import Contract`` would report a nonexistent
    ``mcgyvr.contract.Contract``.

    ``package`` is the dotted package a relative import is relative to, so
    ``from . import config`` inside ``mcgyvr/docgen.py`` resolves to
    ``mcgyvr.config``.

    Takes source rather than a path so the same walk that reads the tree can
    be handed a synthetic crossing and shown to catch it.
    """
    tree = ast.parse(source)
    found: set[str] = set()

    def submodules(prefix: str, node: ast.ImportFrom) -> None:
        for alias in node.names:
            candidate = f"{prefix}.{alias.name}"
            if _is_module(candidate):
                found.add(candidate)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                prefix = ".".join([*base, node.module] if node.module else base)
            elif node.module and (
                node.module == "mcgyvr" or node.module.startswith("mcgyvr.")
            ):
                prefix = node.module
            else:
                continue
            found.add(prefix)
            submodules(prefix, node)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "mcgyvr" or alias.name.startswith("mcgyvr."):
                    found.add(alias.name)
    return found


def _mcgyvr_imports(dotted: str) -> set[str]:
    """:func:`_imports_in` over the file ``dotted`` names in the tree."""
    path = _module_path(dotted)
    package = dotted if path.name == "__init__.py" else dotted.rpartition(".")[0]
    return _imports_in(path.read_text(encoding="utf-8"), package=package or "mcgyvr")


TAGS = {"round": "r7", "product_sha256": "ab" * 32, "draws": 3, "warm": True}


_OUTSIDE = """
import json
from pathlib import Path
import mcgyvr
from mcgyvr.local_pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import fold, observe

completion = Completion(
    text="x", stop_reason=StopReason.COMPLETE, raw_stop_reason="stop",
    model="m", source="workstation", protocol=Protocol.OPENAI,
    max_output_tokens=8, latency_s=0.0,
)
sink = Path(SINK)
observe(
    lambda: completion, path=sink, attempt_id="a:1", orchestrator="a", rung="r",
    messages=[{"role": "user", "content": "u"}],
)
(row,) = fold(path=sink)
print(json.dumps({"file": mcgyvr.__file__, "row": row}))
"""


# The modules allowed to hold an `Endpoint`, which is to say the ones that live
# *below* the seam. `local_pool.py` defines it; `runner.py` (#21) is what it was
# defined for — dispatch is the whole reason the type exists, and a runner is
# the last place that can still be said to not know who asked. Anything else
# reaching for it is the failure this guard is here to catch, so the list is
# named rather than pattern-matched: a third entry should be an argument
# someone makes on purpose, not a file that quietly matched.
#
# `availability.py` (#22) is the third, added deliberately. The argument: it
# does the same kind of thing a runner does — it takes an endpoint and sends it
# a request over the network — and it is the only other module that needs a
# base URL and a protocol to do its job. Crucially it does not travel *upward*:
# `source_map` consults it through `SourceProbe`, which passes endpoints down
# and gets back a mapping of source name to reason, so nothing above the seam
# gains a way to learn where a rung runs. If a future module wants on this list
# because it "just needs the URL", that is the case this guard exists to make
# someone argue.
#
# `capacity.py` (#23) is the fourth, and its argument is narrower than
# availability's. It never talks to anything: of an endpoint it reads exactly two
# fields, `source` — the key its semaphores are held under — and `max_parallel`,
# the number it is enforcing. It touches neither `base_url` nor `protocol` nor
# the credential, so it cannot dispatch even by accident. And it is the use
# `Endpoint` itself names: "``source`` is the declared source name, kept for
# capacity accounting and telemetry — both of which live below the seam"
# (`local_pool.py`). Nothing travels upward either — a caller above the seam hands
# `run_batch` a capacity and gets back outcomes, and never an endpoint.
#
# `cooldown.py` (D09) is the fifth, and it is capacity's argument rather than
# availability's. It never talks to anything: probing is delegated whole to
# `Availability`, and of an endpoint it reads exactly one field, `source` — the
# key its failure record is held under, which is the same key capacity holds its
# semaphores under and the use `Endpoint` itself names. It touches neither
# `base_url` nor `protocol` nor the credential, so it cannot dispatch even by
# accident. Nothing travels upward: `source_map` consults it through
# `SourceProbe` exactly as it consults availability, handing endpoints down and
# getting back a mapping of source name to reason.
#
# `decision.py` (the Jev primitive) is the sixth, and its argument is the
# same as availability's: it takes an endpoint and sends it a logprobs request
# over the network, and it reuses the runner's transport so a decision and a
# dispatch reach a unit identically. Nothing travels upward either — it hands
# back a `Decision`, a mapping of answers, and never an endpoint.
#
# It is on this list rather than off it because the alternative was worse. The
# same import spelled `from mcgyvr.availability import Endpoint` — a re-export —
# would satisfy this guard while changing nothing about the dependency, which is
# defeating the guard by spelling instead of making the argument it asks for.
#
# `decision.py` is the sixth, and it is the runner's own argument again: it asks
# a unit a question and reads the answer from next-token probabilities, so it
# takes an `Endpoint` exactly as a runner does and sends exactly one request
# shape through the same transport (`runner._post_json`). Nothing travels
# upward — `delegate.py` calls it through `classify_for`, below the seam, and
# the typed proposer it returns holds no endpoint.
#
# `initialize.py` and `compose.py` reach an endpoint to run the Jev-composed
# setup recommendation: init derives one from a detected backend (compose builds
# it) and hands it to `mcgyvr.compose.recommend`, which is what dispatches the
# decision. init itself never dispatches through it, and both live below the
# seam — init writes the config that defines the ladder, compose ranks its
# candidates.
#
# `pressure.py` reads what a unit says it has in flight, for the capacity. It
# binds the source to an endpoint to ask that one question (the runner's own
# status read) and hands back a number. Nothing travels upward: no endpoint, and
# no credential, leaves it.
#
# `recommend.py` is the same argument for the read-only placement planner:
# it assembles a keyless decision endpoint and hands it to
# `mcgyvr.decision.classify`, which is what dispatches the decision. It never
# dispatches through the endpoint itself, and it lives below the seam — its
# candidates are sized from the rig and the checkpoint header before any model
# is consulted.
BELOW_THE_SEAM = {
    "local_pool.py",
    "runner.py",
    "availability.py",
    "capacity.py",
    "cooldown.py",
    "compose.py",
    "decision.py",
    "initialize.py",
    "pressure.py",
    "recommend.py",
}


#: The names that carry a dispatchable endpoint. ``RoleBinding`` holds one, so
#: reaching either is reaching the same thing.
BELOW_THE_SEAM_NAMES = {"Endpoint", "RoleBinding"}


def seam_offenders(root: Path) -> list[str]:
    """Every way a module under ``root`` reaches an endpoint, with where.

    Three routes, because the guard was defeated by two of them. The original
    checked one shape — ``from mcgyvr.local_pool import Endpoint`` — and the rule
    was crossed anyway by ``import mcgyvr.local_pool`` and by
    a relative import, neither of which that shape matches, and once more by
    ``SourceMap.role()``, which needs no import at all: it *returns* a
    ``RoleBinding``, so a module could hold a live ``credential()`` while
    importing nothing. A guard with three known bypasses is not a weak guard, it
    is a guard that reports on spelling.

    ``role()`` is therefore treated as below-the-seam API and
    ``SourceMap.role_model()`` is what above it may call. The check is by
    method name, which will occasionally catch an unrelated ``.role(...)``: that
    is the intended direction, and the same argument the module list makes — a
    false positive costs someone an argument, a false negative costs the rule.
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name in BELOW_THE_SEAM:
            continue
        where = path.relative_to(root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # `from mcgyvr.local_pool import Endpoint`, and the relative spelling of
            # the same import, which resolves to the same module.
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "mcgyvr.local_pool" or (
                    node.level and module == "local_pool"
                ):
                    imported = {alias.name for alias in node.names}
                    if imported & BELOW_THE_SEAM_NAMES:
                        offenders.append(f"{where}: imports {sorted(imported)}")
            # `import mcgyvr.local_pool`, which reaches every name in it.
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "mcgyvr.local_pool":
                        offenders.append(f"{where}: imports the module whole")
            # `something.role(...)` — an endpoint through an accessor.
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "role":
                    offenders.append(f"{where}:{node.lineno}: calls .role()")
    return offenders
