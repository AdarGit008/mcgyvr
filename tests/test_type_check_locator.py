"""The type-check command locator (#114), across both adapters.

ADR-0006 is a decision about **restraint**: mcgyvr never chooses a type checker
and never synthesises its flags — it locates whatever the target repository
already declared and returns that. Every test here is a way of holding that line,
because each way of breaking it looks locally reasonable:

* inventing a checker for a repository that runs none (a fabricated command whose
  failures are nobody's fault),
* adding ``--strict`` (which on an unannotated repository is not a stricter check
  but a different one, failing every change on every rung),
* or answering the question by *running* something (which on the host is
  ADR-0005's line, and which would resolve imports against mcgyvr's environment
  rather than the target's — measuring the wrong project).

It lives in its own file rather than split across the two adapter suites because
the property is one property, and asserting it twice in two places is how the two
adapters would drift into meaning different things by "declared".
"""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr.contract import loads
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter

PY = PythonAdapter()
JS = JavaScriptAdapter()


def write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- a repository that declares nothing gets nothing -----------------------


def test_an_empty_repository_declares_no_checker(tmp_path: Path) -> None:
    assert PY.locate_type_check_command(tmp_path) is None
    assert JS.locate_type_check_command(tmp_path) is None


def test_a_pyproject_without_a_checker_table_declares_nothing(tmp_path: Path) -> None:
    """The common case, and the one a substring match would get wrong."""
    write(tmp_path, "pyproject.toml", '[project]\nname = "x"\nversion = "0.1"\n')

    assert PY.locate_type_check_command(tmp_path) is None


@pytest.mark.parametrize(
    "text",
    [
        '[project]\nname = "x"\ndependencies = ["mypy>=1.0"]\n',  # a pin, not config
        "# we should probably set up [tool.mypy] one day\n",  # a comment
        '[tool.ruff.lint]\nselect = ["ANN"]\n[tool.ruff.lint.flake8-annotations]\n'
        "mypy-init-return = true\n",  # another tool's key that contains the name
    ],
)
def test_mentioning_a_checker_is_not_declaring_one(tmp_path: Path, text: str) -> None:
    """Parsed, not grepped.

    Each of these contains the string ``mypy`` and configures no type checker.
    A substring test would fabricate a command for all three, and a fabricated
    acceptance command fails in the sandbox as though the worker's change were
    at fault.
    """
    write(tmp_path, "pyproject.toml", text)

    assert PY.locate_type_check_command(tmp_path) is None


def test_an_unparseable_manifest_is_not_a_declaration(tmp_path: Path) -> None:
    """A malformed file is the target's business; the honest answer is "no"."""
    write(tmp_path, "pyproject.toml", "[tool.mypy\nstrict = true\n")

    assert PY.locate_type_check_command(tmp_path) is None


# --- what each checker's own config files mean -----------------------------


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("pyproject.toml", "[tool.mypy]\nstrict = true\n"),
        ("mypy.ini", "[mypy]\nstrict = True\n"),
        (".mypy.ini", "[mypy]\nstrict = True\n"),
        ("setup.cfg", "[mypy]\nstrict = True\n"),
    ],
)
def test_mypy_is_found_wherever_mypy_itself_looks(
    tmp_path: Path, name: str, text: str
) -> None:
    """A project with ``mypy.ini`` has declared mypy as much as one with a table.

    ADR-0006 turns on what the repository declared, not on where it chose to
    write it down.
    """
    write(tmp_path, name, text)

    assert PY.locate_type_check_command(tmp_path) == ["mypy"]


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("pyproject.toml", "[tool.pyright]\ntypeCheckingMode = 'strict'\n"),
        ("pyrightconfig.json", json.dumps({"typeCheckingMode": "strict"})),
    ],
)
def test_pyright_is_found_wherever_pyright_looks(
    tmp_path: Path, name: str, text: str
) -> None:
    write(tmp_path, name, text)

    assert PY.locate_type_check_command(tmp_path) == ["pyright"]


def test_a_per_module_override_alone_does_not_declare_mypy(tmp_path: Path) -> None:
    """``[mypy-somepkg.*]`` in a setup.cfg that never configures mypy itself."""
    write(tmp_path, "setup.cfg", "[mypy-vendored.*]\nignore_errors = True\n")

    assert PY.locate_type_check_command(tmp_path) is None


def test_a_tsconfig_is_the_declaration_for_js(tmp_path: Path) -> None:
    write(tmp_path, "tsconfig.json", json.dumps({"compilerOptions": {"strict": True}}))

    assert JS.locate_type_check_command(tmp_path) == ["tsc", "--noEmit"]


def test_a_typecheck_script_is_not_read_from_package_json(tmp_path: Path) -> None:
    """Script detection alone finds nothing on a real TypeScript repository.

    Measured while sizing #133: ``immerjs/immer`` carries a ``tsconfig.json``
    and pins ``typescript`` at all 27 commits of the pinned corpus while
    declaring no type-check script at any of them. A repository that *does*
    declare one has declared an acceptance command, and that belongs in the
    contract, which outranks a sniff.
    """
    write(tmp_path, "package.json", json.dumps({"scripts": {"typecheck": "tsc -p ."}}))

    assert JS.locate_type_check_command(tmp_path) is None


# --- no flag the repository did not declare --------------------------------


def test_no_strictness_flag_is_ever_synthesised(tmp_path: Path) -> None:
    """The acceptance criterion, asserted as an absence over every arm.

    ``--strict`` on a repository that carries no annotations is not a stricter
    setting of this check. It is a different check that always fails, and no
    rung can clear it: clearing it means annotating the surrounding file, which
    scope validation rejects. The gate would reject, the task would escalate,
    the ladder would exhaust, and spend would convert to a guaranteed zero.
    """
    forbidden = {
        "--strict",
        "--ignore-missing-imports",
        "--disallow-untyped-defs",
        "--no-strict-optional",
        "--strictNullChecks",
        "-p",
        "--project",
    }
    declarations = [
        ("pyproject.toml", "[tool.mypy]\nstrict = true\n", PY),
        ("mypy.ini", "[mypy]\n", PY),
        ("pyrightconfig.json", "{}", PY),
        ("tsconfig.json", "{}", JS),
    ]
    for name, text, adapter in declarations:
        repo = tmp_path / name.replace(".", "_")
        repo.mkdir()
        write(repo, name, text)
        command = adapter.locate_type_check_command(repo)
        assert command is not None
        assert not forbidden & set(command), f"{name} synthesised a flag: {command}"


def test_the_python_command_is_bare_so_the_repository_sets_the_scope() -> None:
    """``mypy`` with no path reads the repository's own ``files`` and ``exclude``.

    Adding a path here would substitute mcgyvr's idea of what to check for the
    one the project wrote down — the same error as adding a flag, in a different
    costume.
    """
    repo = Path(__file__).resolve().parent.parent

    assert PY.locate_type_check_command(repo) == ["mypy"]


# --- the locator never runs anything ---------------------------------------


_FORBIDDEN_CALLS = frozenset(
    {
        "run",
        "check_output",
        "check_call",
        "Popen",
        "system",
        "popen",
        "import_module",
        "__import__",
        "eval",
        "exec",
        "compile",
        "load_module",
        "spawn",
    }
)


def _called_names(function: Callable[..., object]) -> set[str]:
    """Every name called anywhere in a function's source."""
    tree = ast.parse(inspect.getsource(function).lstrip())
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def test_the_locator_evaluates_nothing_in_the_target(tmp_path: Path) -> None:
    """The acceptance criterion, asserted structurally rather than by inspection.

    Answering "which checker does this repository use" by *running* something is
    the ADR-0005 line — and it is wrong before it is unsafe, because on the host
    a checker resolves imports against mcgyvr's environment rather than the
    target's, so a check whose whole premise is *the project's* checker on *the
    project's* code would measure the wrong project.

    Checked over the locator and every helper it reaches, by parsing rather than
    grepping, so the guard is about what the code *does* and not about which
    words appear in it.
    """
    from mcgyvr.gate.adapters import python as python_adapter

    reached: list[tuple[str, Callable[..., object]]] = [
        ("PythonAdapter.locate_type_check_command", PY.locate_type_check_command),
        ("JavaScriptAdapter.locate_type_check_command", JS.locate_type_check_command),
        ("_declares_mypy", python_adapter._declares_mypy),
        ("_declares_pyright", python_adapter._declares_pyright),
        ("_has_toml_table", python_adapter._has_toml_table),
        ("_has_ini_section", python_adapter._has_ini_section),
    ]
    offenders = {
        f"{name}: {sorted(found)}"
        for name, function in reached
        if (found := _called_names(function) & _FORBIDDEN_CALLS)
    }

    assert offenders == set()


def test_a_hostile_module_in_the_target_is_never_executed(tmp_path: Path) -> None:
    """The behavioural half: a repository whose Python would blow up on import."""
    write(tmp_path, "pyproject.toml", "[tool.mypy]\nstrict = true\n")
    write(tmp_path, "conftest.py", "raise SystemExit('the locator imported me')\n")
    write(tmp_path, "setup.py", "import os\nos._exit(1)\n")

    assert PY.locate_type_check_command(tmp_path) == ["mypy"]


# --- the contract always wins ----------------------------------------------


def test_a_contract_keeps_the_acceptance_commands_it_declared() -> None:
    """A sniff is a fallback and may never overrule a caller who said what to run.

    There is no consumer of the locator yet — emitting it into a contract's
    ``acceptance`` is the decomposer's job and is not wired (see the session
    record for lane/114). This pins the property the consumer must not break:
    what a contract declares survives loading untouched, so a future injection
    that appended or replaced would fail here rather than silently changing what
    a direct-mode caller asked for.
    """
    declared = """
id: annotate-fetch
task_type: function_implementation
task: Annotate the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The intended type is not inferable from the call sites.
acceptance:
  - mypy --config-file ops/mypy-ci.ini src/pkg/fetch.py
scope:
  allow: ["src/**/*.py"]
"""

    contract = loads(declared)

    assert contract.acceptance == (
        "mypy --config-file ops/mypy-ci.ini src/pkg/fetch.py",
    )
