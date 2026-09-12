"""The seam holds: nothing below it reads a contract, nothing above it starts a server.

``mcgyvr.pool``:1-8 names the two halves — above the seam a caller sees a
*ladder of rungs*: named steps, cheapest first, each with a model. Below it, a
rung has already resolved to an :class:`~mcgyvr.pool.Endpoint` a runner can
dispatch against. ``mcgyvr.runner``:1-8 calls itself "the first code below the
seam" the pool draws.

This file pins that division as an import rule rather than as prose:

* **Nothing below the seam imports ``contract.py`` or ``orchestrator/``**
  (action 16). Below the seam a rung is already resolved to something a
  machine runs — an endpoint to dispatch against, a sandbox to run a command
  in, the docker probe that decides which sandbox mode is available, a
  serving unit to launch. None of that needs to read a contract or explore a
  repo to decide what to do; deciding is done by the time work gets here.
* **Nothing above the seam imports ``serving/``** (action 17). Above the
  seam a caller only ever sees a ladder of rungs. Turning a chosen rung into
  a running model-server process is ``mcgyvr.serving``'s job alone, and a
  caller that only authors or explores a contract never needs it.
* **A module both halves import reaches into neither half's own world.**
  :data:`SHARED_ACROSS_THE_SEAM` is action 15's list. A module on it is read
  from above *and* from below, so it is subject to both rules at once rather
  than to neither: if ``config.py`` grew an import of ``contract.py`` or of
  ``serving/``, every module that reads config would drag that half along
  with it and the seam would be gone without a single rule above firing.

Membership is exhaustive by construction. Every ``.py`` file under
``src/mcgyvr/`` whose path is a legal module name lands in exactly one of
:data:`BELOW_THE_SEAM`, :data:`ABOVE_THE_SEAM`,
:data:`SHARED_ACROSS_THE_SEAM` or :data:`THE_COMMAND_LINE_ENTRYPOINT`, and
:func:`test_every_module_is_on_one_side_of_the_seam` fails on a module that is
in none of them. A hand-written list that a new module can quietly stay out of
is a rule that stops covering the tree the day the tree grows; a new module
under ``src/mcgyvr/`` breaks that test until somebody says which half it is in.

Action 15's finding is that the boundary is not perfectly clean today: docker
detection is legitimately read from both the probe and the sandbox that acts
on it — ``mcgyvr.detect``:408 defers to
``mcgyvr.sandbox.image.foreign_daemon``, and ``mcgyvr.sandbox.base``:585
defers back to ``mcgyvr.detect.detect_docker``.
:data:`THE_DOCKER_DETECTION_CROSSINGS` writes that cycle down once, as data,
so a rule built on top of it does not rediscover — or misfire on — the same
crossing the day it lands.

It writes it down as the two **edges** it is, ``(importer, imported)``, and
not as two module names. A module name exempted outright is exempt in both
directions and against every rule: it would make ``mcgyvr.detect`` importing
``contract.py`` — a real violation of the first rule — pass in silence, which
is the opposite of what action 15 asked for. What is sanctioned is
``detect`` → ``sandbox.image`` and ``sandbox.base`` → ``detect``, and nothing
else either module does.

``mcgyvr.cli`` is the one exemption that is still whole-module, and for the
opposite reason. It is not read from both halves; it *reaches into* both, and
that is not a crossing to be removed. ``cli.py``:1 says what it is in one
line — "Command-line entrypoint" — and one ``argparse`` parser that dispatches
``mcgyvr detect``, ``mcgyvr pool``, ``mcgyvr scan`` and ``mcgyvr emit`` below
the seam and ``mcgyvr run`` and ``mcgyvr contract`` above it is doing the only
job an entrypoint has. :data:`THE_COMMAND_LINE_ENTRYPOINT` names it once, in
the same written-down way, so the rules below can be exact about what they
exempt instead of quietly passing because nothing happened to be caught.

Which is the other thing this file has to do. Every module in this package
already respects the boundary, so the rules pass today and a rule that passes
today is worth nothing unless it can be shown to catch a violation. So each
rule is followed by a test that hands the same checker a *synthetic*
crossing — source that does not exist in the tree — and asserts it comes back
as an offender. The synthetic sources put their import inside a function on
purpose: a deferred import is still a real dependency at the moment it runs,
and both of the real crossings this file knows about (``detect.py``:408,
``sandbox/base.py``:585) are exactly that shape.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "mcgyvr"
RED_PORT = Path(__file__).resolve().parent / "red_port"

#: ``mcgyvr.runner``'s own words: "the first code below the seam
#: ``mcgyvr.pool`` draws". This is it, and everything else that resolves a
#: rung to something a machine actually runs: an endpoint to dispatch against
#: (pool, runner), what is known about a source before dispatching to it
#: (availability, capacity, cooldown), a sandbox to run a command in
#: (sandbox.*), the docker probe that decides which sandbox mode is available
#: (detect), what the hardware measures and what that is worth running
#: (scan, capability, propose, initialize), a serving unit to write out and
#: launch (emit, serving.*), whether a card that is down is asleep and how it
#: is woken (wake), and how a served model id is read against the name a
#: config declares (weights).
BELOW_THE_SEAM: tuple[str, ...] = (
    "mcgyvr.availability",
    "mcgyvr.capability",
    "mcgyvr.capacity",
    "mcgyvr.cooldown",
    "mcgyvr.derived",
    "mcgyvr.detect",
    "mcgyvr.emit",
    "mcgyvr.fleet",
    "mcgyvr.fleet.admit",
    "mcgyvr.fleet.alerts",
    "mcgyvr.fleet.files",
    "mcgyvr.fleet.ids",
    "mcgyvr.fleet.layout",
    "mcgyvr.fleet.lock",
    "mcgyvr.initialize",
    "mcgyvr.pool",
    "mcgyvr.propose",
    "mcgyvr.runner",
    "mcgyvr.sandbox",
    "mcgyvr.sandbox.base",
    "mcgyvr.sandbox.docker",
    "mcgyvr.sandbox.image",
    "mcgyvr.sandbox.stack",
    "mcgyvr.sandbox.tempdir",
    "mcgyvr.scan",
    "mcgyvr.serving",
    "mcgyvr.serving.gatelib",
    "mcgyvr.serving.ggufscan",
    "mcgyvr.serving.run",
    "mcgyvr.serving.servelib",
    "mcgyvr.serving.vramfit",
    "mcgyvr.wake",
    "mcgyvr.weights",
)

#: ``mcgyvr.pool``'s other half — a caller that sees a ladder of rungs and has
#: not resolved one to anything that runs. The contract and the exploration
#: that produces one (contract, orchestrator.*, docgen), the climb through the
#: ladder (route, escalate, drive, consensus, deterministic, rename, repair,
#: verify, deliver, cleanup), what a worker is sent
#: and what may be read back (worker.*), what judges the change (gate.*,
#: scope), and what the run leaves behind for the caller (result, session,
#: telemetry).
ABOVE_THE_SEAM: tuple[str, ...] = (
    "mcgyvr.cleanup",
    "mcgyvr.consensus",
    "mcgyvr.contract",
    "mcgyvr.delegate",
    "mcgyvr.deliver",
    "mcgyvr.deterministic",
    "mcgyvr.docgen",
    "mcgyvr.drive",
    "mcgyvr.escalate",
    "mcgyvr.gate",
    "mcgyvr.gate.acceptance",
    "mcgyvr.gate.adapter",
    "mcgyvr.gate.adapters",
    "mcgyvr.gate.adapters.javascript",
    "mcgyvr.gate.adapters.python",
    "mcgyvr.gate.changeset",
    "mcgyvr.gate.findings",
    "mcgyvr.gate.preflight",
    "mcgyvr.gate.runner",
    "mcgyvr.gate.secrets",
    "mcgyvr.gate.semantic",
    "mcgyvr.gate.semantic_driver",
    "mcgyvr.gate.structured",
    "mcgyvr.gate.typecheck",
    "mcgyvr.orchestrator",
    "mcgyvr.orchestrator.cache",
    "mcgyvr.orchestrator.context",
    "mcgyvr.orchestrator.decompose",
    "mcgyvr.orchestrator.index",
    "mcgyvr.orchestrator.read",
    "mcgyvr.orchestrator.repo",
    "mcgyvr.orchestrator.resolve",
    "mcgyvr.orchestrator.symbols",
    "mcgyvr.rename",
    "mcgyvr.repair",
    "mcgyvr.result",
    "mcgyvr.route",
    "mcgyvr.scope",
    "mcgyvr.session",
    "mcgyvr.telemetry",
    "mcgyvr.verify",
    "mcgyvr.worker",
    "mcgyvr.worker.bundle",
    "mcgyvr.worker.prompt",
    "mcgyvr.worker.reply",
)

#: Action 15 — the modules both halves import, written down. Each is read from
#: above the seam and from below it, and each answers one question for the
#: whole project rather than for one half of it: the package itself, the one
#: config file (``config.py``:1), the vocabulary of what may be asked for
#: (``catalog.py``:1), the exit codes a caller branches on (``exits.py``:1),
#: where a line ends (``lines.py``:1), what is safe to quote to an
#: operator (``redact.py``:1), and the strict YAML loader both schemas share
#: (``strict_yaml.py``:1). Being on this list is not an exemption: a
#: shared module is held to *both* rules below, because a shared module that
#: reached into either half would pull that half into everything that reads
#: it.
SHARED_ACROSS_THE_SEAM: tuple[str, ...] = (
    "mcgyvr",
    "mcgyvr.catalog",
    "mcgyvr.config",
    "mcgyvr.exits",
    "mcgyvr.lines",
    "mcgyvr.redact",
    "mcgyvr.strict_yaml",
)

#: The one module that is allowed to reach into both halves, because reaching
#: into both halves is what it is for. ``cli.py``:1: "Command-line
#: entrypoint." A single ``argparse`` parser dispatches ``detect``, ``pool``,
#: ``scan`` and ``emit`` below the seam and ``run`` and ``contract`` above it;
#: it imports ``mcgyvr.serving`` at module level for ``emit`` and defers
#: ``mcgyvr.contract``/``mcgyvr.orchestrator`` for ``run`` and ``contract``.
#: Neither import is a half of mcgyvr forgetting where the seam is. Written
#: down here rather than left to a rule's silence, so that what is exempt is a
#: name a reader can find. This is the only whole-module exemption in the
#: file, and it is whole-module because an entrypoint reaches into both halves
#: by definition.
THE_COMMAND_LINE_ENTRYPOINT: str = "mcgyvr.cli"

#: Action 15's finding, as the two edges it actually is. Docker detection is
#: read from the probe and from the sandbox that acts on it, in a cycle:
#: ``mcgyvr.detect``:408 defers to ``mcgyvr.sandbox.image.foreign_daemon`` and
#: ``mcgyvr.sandbox.base``:585 defers back to ``mcgyvr.detect.detect_docker``.
#: An ``(importer, imported)`` pair and not two module names, because a name
#: exempted outright is exempt in both directions against every rule: it would
#: let ``mcgyvr.detect`` import ``contract.py`` in silence, which is a real
#: violation of the first rule below.
THE_DOCKER_DETECTION_CROSSINGS: tuple[tuple[str, str], ...] = (
    ("mcgyvr.detect", "mcgyvr.sandbox.image"),
    ("mcgyvr.sandbox.base", "mcgyvr.detect"),
)


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
    not — ``01-round.py``, ``data-10-scan.py``, the directory itself — and no
    import statement can reach them.
    """
    rel = path.relative_to(SRC)
    parts = rel.parts[:-1] if rel.name == "__init__.py" else (*rel.parts[:-1], rel.stem)
    if not all(part.isidentifier() for part in parts):
        return None
    return ".".join(("mcgyvr", *parts))


def _the_tree() -> set[str]:
    """Every importable module under ``src/mcgyvr/``.

    :func:`_dotted_name` says which files those are. ``gate/semantic_driver.py``
    calls itself "never imported by mcgyvr ... read as text and staged" in its
    own docstring, but it *is* a legal module name, so it is classified like
    everything else rather than skipped.
    """
    return {name for path in SRC.rglob("*.py") if (name := _dotted_name(path))}


def _imports_in(source: str, package: str = "mcgyvr") -> set[str]:
    """Every ``mcgyvr.*`` module ``source`` imports, wherever the import sits —
    top of the file, inside a function, under ``TYPE_CHECKING``. All of them,
    on purpose: a deferred import is still a real dependency at the moment it
    runs, and both of the crossings this file knows about (``detect.py``:408,
    ``sandbox/base.py``:585) are exactly that shape, so a check that only
    looked at the top of the file would miss the crossings it was written to
    find.

    Three spellings reach a module and all three are resolved, because a rule
    that only understands one of them can be walked around by writing another:
    ``import mcgyvr.contract``, ``from mcgyvr.contract import Contract``,
    ``from mcgyvr import contract`` (``orchestrator/decompose.py``:74,
    ``cli.py``:20) and the relative ``from . import contract``
    (``docgen.py``:62). The last two name a module in the *imported names*
    rather than in the module path, so each name is followed only when
    ``package.name`` is a file in this tree — otherwise ``from
    mcgyvr.contract import Contract`` would report a nonexistent
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


def _crossings(
    modules: tuple[str, ...],
    forbidden: tuple[str, ...],
    imports: Callable[[str], set[str]] = _mcgyvr_imports,
) -> list[str]:
    """``module -> imported`` for every ``module`` that reaches a ``forbidden``
    prefix, skipping only what action 15 writes down: the command-line
    entrypoint, whole, and the two docker-detection edges, as edges.

    ``imports`` is the reader that says what a module imports. It defaults to
    the tree and is injectable so the self-tests below can hand the same rule a
    crossing that does not exist on disk.
    """
    offenders: list[str] = []
    for module in modules:
        if module == THE_COMMAND_LINE_ENTRYPOINT:
            continue
        for imported in sorted(imports(module)):
            if (module, imported) in THE_DOCKER_DETECTION_CROSSINGS:
                continue
            if any(imported == p or imported.startswith(f"{p}.") for p in forbidden):
                offenders.append(f"{module} imports {imported}")
    return offenders


#: What a module below the seam has already stopped needing: the contract it
#: was resolved from, and the exploration that produced it.
NOT_BELOW: tuple[str, ...] = ("mcgyvr.contract", "mcgyvr.orchestrator")

#: What a caller above the seam never needs: the running model-server process.
NOT_ABOVE: tuple[str, ...] = ("mcgyvr.serving",)


# A below-the-seam module that reaches back up for a contract, and an
# above-the-seam module that reaches down to start a server. Neither exists in
# the tree; both are written the way the two real crossings are written — the
# import deferred inside the function that needs it — so the self-tests prove
# the rule catches the shape it was built for, not just a header.
_BELOW_REACHING_UP = '''
def dispatch(endpoint, args):
    """A resolved rung deciding what to run by reading a contract."""
    from mcgyvr.contract import Contract

    return Contract
'''

_ABOVE_REACHING_DOWN = '''
def explore(index, query):
    """A caller that has authored a contract starting a model-server."""
    from mcgyvr.serving.run import launch

    return launch
'''

# A shared module dragging one half into everything that reads it, and the
# `from mcgyvr import contract` spelling a rule that only understood
# `import mcgyvr.contract` would walk straight past.
_SHARED_REACHING_UP = '''
def catalog():
    """Config answering a question by reading a contract."""
    from mcgyvr import contract

    return contract
'''


def _synthetic(source: str) -> Callable[[str], set[str]]:
    """An imports reader that answers with ``source``'s imports for any module."""
    imported = _imports_in(source)
    return lambda _module: imported


def test_every_module_is_on_one_side_of_the_seam() -> None:
    """Membership is exhaustive by construction, so a new module cannot opt out
    of the rules by not being listed.

    Two hand-written tuples that between them named a quarter of the tree would
    let ``gate/``, ``worker/``, ``route.py`` and every module written after
    them sit outside both rules — and a rule that does not look at a module
    cannot catch the violation it exists for. Every ``.py`` file under
    ``src/mcgyvr/`` that is a legal module name is here, in exactly one place,
    and a new one fails this until somebody says which half it is in.
    """
    classified = (
        set(BELOW_THE_SEAM)
        | set(ABOVE_THE_SEAM)
        | set(SHARED_ACROSS_THE_SEAM)
        | {THE_COMMAND_LINE_ENTRYPOINT}
    )
    tree = _the_tree()

    assert tree - classified == set(), (
        "modules under src/mcgyvr/ are in neither half and are not written "
        "down as shared or as the entrypoint, so no rule in this file looks "
        "at them: say which half each is in"
    )
    assert classified - tree == set(), (
        "names are classified here that no longer exist under src/mcgyvr/"
    )

    skipped = {
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if _dotted_name(path) is None
    }
    assert all(name.startswith("serving/gate-scripts/") for name in skipped), (
        "a .py file under src/mcgyvr/ has a name no import statement can "
        "reach, outside the staged gate scripts that are read as text: "
        f"{sorted(skipped)}"
    )

    listed = (
        list(BELOW_THE_SEAM)
        + list(ABOVE_THE_SEAM)
        + list(SHARED_ACROSS_THE_SEAM)
        + [THE_COMMAND_LINE_ENTRYPOINT]
    )
    assert len(listed) == len(set(listed)), (
        "a module is written down twice; each is on one side of the seam, "
        "shared across it, or the entrypoint — not two of those"
    )


def test_nothing_below_the_seam_imports_the_contract_or_the_orchestrator() -> None:
    """Below the seam a rung is already resolved; it never needs to read a
    contract or explore a repo to decide what to run.

    ``mcgyvr.cli`` defers ``from mcgyvr.contract import Contract`` and ``from
    mcgyvr.orchestrator import ...`` for its `run` and `contract` subcommands,
    in the same module that also does the resolving. That is the entrypoint
    dispatching, not a half of mcgyvr forgetting where the seam is, and it is
    exempt by name rather than by the rule failing to look.
    """
    assert _crossings(BELOW_THE_SEAM, NOT_BELOW) == []


def test_the_below_the_seam_rule_catches_a_module_that_reaches_up() -> None:
    """The rule above passes today, so it is worth nothing until it is shown to
    fail on a violation. ``mcgyvr.runner`` — "the first code below the seam" —
    is handed a body that defers ``from mcgyvr.contract import Contract``, and
    the rule must name it."""
    offenders = _crossings(
        ("mcgyvr.runner",),
        NOT_BELOW,
        imports=_synthetic(_BELOW_REACHING_UP),
    )
    assert offenders == ["mcgyvr.runner imports mcgyvr.contract"]


def test_nothing_above_the_seam_imports_serving() -> None:
    """Above the seam a caller only ever sees a ladder of rungs; turning one
    into a running process is ``mcgyvr.serving``'s job and no caller above it
    needs that module.

    ``mcgyvr.cli`` carries ``from mcgyvr.serving import (...)`` at module level
    for the `emit` subcommand that lives beside `run` and `contract` in the
    same file. Exempt for the same reason, and written down in the same place.
    """
    assert _crossings(ABOVE_THE_SEAM, NOT_ABOVE) == []


def test_the_above_the_seam_rule_catches_a_module_that_reaches_down() -> None:
    """The same guard for the same reason. ``mcgyvr.orchestrator.read`` is
    handed a body that defers ``from mcgyvr.serving.run import launch``, and
    the rule must name it — including the submodule, which is why the check
    tests the ``mcgyvr.serving.`` prefix and not equality."""
    offenders = _crossings(
        ("mcgyvr.orchestrator.read",),
        NOT_ABOVE,
        imports=_synthetic(_ABOVE_REACHING_DOWN),
    )
    assert offenders == ["mcgyvr.orchestrator.read imports mcgyvr.serving.run"]


def test_a_module_both_halves_import_reaches_into_neither() -> None:
    """Action 15's list is not an exemption list.

    A shared module is read from above the seam and from below it, so an
    import it makes is an import both halves make. ``config.py``,
    ``catalog.py``, ``exits.py``, ``lines.py`` and ``redact.py`` are held to
    both rules at once — the strictest position in the file, and the right one
    for a module that everything reads.
    """
    assert _crossings(SHARED_ACROSS_THE_SEAM, NOT_BELOW + NOT_ABOVE) == []


def test_the_shared_rule_catches_a_module_that_reaches_into_a_half() -> None:
    """``mcgyvr.config`` is handed a body that defers ``from mcgyvr import
    contract``, and the rule must name it.

    That spelling is deliberate. ``orchestrator/decompose.py``:74 and
    ``cli.py``:20 both import a module this way and ``docgen.py``:62 does it
    relatively; a checker that only matched ``import mcgyvr.contract`` would
    report nothing here while the crossing was in the tree.
    """
    offenders = _crossings(
        ("mcgyvr.config",),
        NOT_BELOW + NOT_ABOVE,
        imports=_synthetic(_SHARED_REACHING_UP),
    )
    assert offenders == ["mcgyvr.config imports mcgyvr.contract"]


def test_the_exemption_covers_the_entrypoint_and_the_two_docker_edges() -> None:
    """What is written down is exempt, in the direction it is written down in,
    and nothing else is.

    The entrypoint is exempt whole: the same synthetic crossing is attributed
    to ``mcgyvr.cli``, which :data:`THE_COMMAND_LINE_ENTRYPOINT` names, and to
    ``mcgyvr.pool``, which nothing names; the first is skipped and the second
    is caught.

    Docker detection is exempt as two edges and not as two modules. Handed the
    same synthetic body, ``mcgyvr.detect`` and ``mcgyvr.sandbox.image`` are
    caught reaching for a contract — an exemption by module name would pass
    both, and that is a real violation of the first rule going quiet. The two
    sanctioned edges are still skipped, checked against a ``forbidden`` set
    that would otherwise catch them; and the same importer reaching a
    *different* module below is caught, which is what makes the exemption a
    pair rather than a name.
    """
    reader = _synthetic(_BELOW_REACHING_UP)

    assert _crossings((THE_COMMAND_LINE_ENTRYPOINT,), NOT_BELOW, imports=reader) == []
    assert _crossings(("mcgyvr.pool",), NOT_BELOW, imports=reader) == [
        "mcgyvr.pool imports mcgyvr.contract"
    ]

    assert _crossings(("mcgyvr.detect",), NOT_BELOW, imports=reader) == [
        "mcgyvr.detect imports mcgyvr.contract"
    ]
    assert _crossings(("mcgyvr.sandbox.image",), NOT_BELOW, imports=reader) == [
        "mcgyvr.sandbox.image imports mcgyvr.contract"
    ]

    # The real tree, under a forbidden set chosen so the sanctioned edges would
    # be caught if they were not written down: detect.py:408 reaches
    # sandbox.image, sandbox/base.py:585 reaches back to detect.
    assert _crossings(("mcgyvr.detect",), ("mcgyvr.sandbox",)) == []
    assert _crossings(("mcgyvr.sandbox.base",), ("mcgyvr.detect",)) == []

    # Same importer, different imported module: not the sanctioned edge, so
    # not skipped.
    assert _crossings(
        ("mcgyvr.detect",),
        ("mcgyvr.sandbox",),
        imports=_synthetic("from mcgyvr.sandbox.docker import DockerSandbox"),
    ) == ["mcgyvr.detect imports mcgyvr.sandbox.docker"]


# --- action 18 -----------------------------------------------------------
#
# orchestrator/read.py:54,294 imports capability.py for budget_for_model and
# explore_for, and nothing under src/ calls either — verified by grepping the
# whole tree for both names outside this module. Only tests call them: three
# functions in tests/red_port/test_d12_size_aware_context.py, and
# tests/red_port/test_dod_capability_integrity.py:58,66. A function whose only
# callers are its own tests is not exercising a decision anything downstream
# makes; it is exercising the function, which is not what F8's own bug (a NaN
# params_b sent budget_for_model into StopIteration) needed a fix for — the
# fix belongs on whatever explore is actually sized by, if anything is. The
# end state pinned here is DELETE: the two names go, and the tests that exist
# only to call them go with them, together in one commit, rather than gating a
# path nothing under src/ ever takes.
#
# Both files stay on disk, because the two assertions below can only mean
# something while they do. What is left in each is what stands without the
# deleted names: test_dod_capability_integrity.py keeps F7 and F9 and records
# that F8's StopIteration is closed by the deletion rather than by a fix, and
# test_d12_size_aware_context.py keeps the one statement it called "the most
# important one here" — that overflow is deferred and never cut — asserted
# against explore() and two explicit budgets, which is what a budget is for a
# caller to state.


def test_the_orphaned_context_budget_helpers_are_deleted_with_their_tests() -> None:
    """``budget_for_model`` and ``explore_for`` have no caller under ``src/``;
    the pinned end state removes both from ``orchestrator/read.py`` and
    removes the four tests that exist only to call them."""
    import mcgyvr.orchestrator.read as read_module

    assert not hasattr(read_module, "budget_for_model"), (
        "orchestrator/read.py still defines budget_for_model, which src/ "
        "never calls; the decision was to delete it, not leave it orphaned"
    )
    assert not hasattr(read_module, "explore_for"), (
        "orchestrator/read.py still defines explore_for, which src/ never "
        "calls; the decision was to delete it, not leave it orphaned"
    )


def test_the_size_aware_context_red_port_test_no_longer_calls_explore_for() -> None:
    """``test_d12_size_aware_context.py`` exists only to call ``explore_for``
    three times; deleting the helper without deleting this test would leave a
    file that imports a name that is no longer there."""
    path = RED_PORT / "test_d12_size_aware_context.py"
    assert path.exists(), f"{path} must still exist to make this assertion meaningful"
    text = path.read_text(encoding="utf-8")
    assert "explore_for" not in text, (
        f"{path} still names explore_for; the pinned end state deletes this "
        "test together with the helper it exists only to call"
    )


def test_the_capability_integrity_red_port_test_no_longer_calls_budget_for_model() -> (
    None
):
    """``test_dod_capability_integrity.py``:58,66 calls ``budget_for_model``
    to prove F8's fix; deleting the helper means this assertion moves to
    whatever calls the table instead, not that it is dropped silently."""
    path = RED_PORT / "test_dod_capability_integrity.py"
    assert path.exists(), f"{path} must still exist to make this assertion meaningful"
    text = path.read_text(encoding="utf-8")
    assert "budget_for_model" not in text, (
        f"{path} still names budget_for_model; the pinned end state deletes "
        "the call together with the helper it exists only to exercise"
    )
