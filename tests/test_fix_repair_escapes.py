"""Two ways a repair still wrote where it was not asked to (N3, N4).

Both defects survived the first fix round because each fix answered a
*narrower* question than the promise it was defending.

**The scope promise is about bytes, not about names.** ``_repairable`` was
taught to resolve the path it is handed and re-ask the scope about where the
name lands, which closed every symlink vector. A hard link is not a link: it is
a second directory entry for the same inode, so ``Path.resolve()`` has nothing
to see through and the in-scope name resolves to itself. ``ruff format`` writes
through it in place, and the out-of-scope name — in another directory, or in
another tree entirely — reads back rewritten. The tests here are stated on the
bytes of the file the contract forbids, with the in-scope file asserted as the
control so that a repair which does nothing at all cannot pass.

**A line is where the parser says it is.** ``_insert_imports`` splices by AST
line number into ``str.splitlines(keepends=True)``, and those two disagree on
eight characters the tokenizer does not end a line on — all legal inside a
string literal. One of them in a module docstring shifts the anchor up, and the
import is written *into* the docstring: the file parses, ruff is happy, the
undefined name the import was repairing is still undefined, and the outcome
reports the repair as done. The same cut also has to agree with the parser on
the three terminators that are real, since a file's endings are bytes the
repair was never asked to change.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.repair import RepairOutcome, _insert_imports, repair

# Valid Python the gate rejects on rungs a formatter answers for free, so a
# tool pointed at it leaves a visible mark.
UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)

WORK_CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: {target}
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

DEPS_CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
deps:
  - path: src/pkg/backoff.py
    signature: "def sleep_backoff(attempt: int) -> None"
    note: The backoff the retry loop must wait with.
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

# The characters `str.splitlines` breaks on and the tokenizer does not.
SEPARATORS = ("\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")

# The three the tokenizer does end a line on.
TERMINATORS = ("\n", "\r\n", "\r")

_ENDING = re.compile(r"\r\n|\r|\n")


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout, raising with stderr on failure."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def make_repo(where: Path, files: dict[str, str]) -> Path:
    """A real git repository holding ``files``, committed once."""
    for name, body in files.items():
        path = where / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    git(where.parent, "init", "-q", str(where))
    git(where, "config", "user.email", "fix@example.invalid")
    git(where, "config", "user.name", "fix")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def work_contract(target: str) -> Contract:
    return load_contract(WORK_CONTRACT.format(target=target))


def endings(path: Path) -> set[str]:
    """Every distinct line terminator the file on disk actually holds."""
    return set(_ENDING.findall(path.read_bytes().decode("utf-8")))


def top_level_imports(source: str) -> list[str]:
    """The imports a parser finds at module level in ``source``."""
    return [
        ast.unparse(node)
        for node in ast.parse(source).body
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]


def repaired_repo(tmp_path: Path) -> tuple[Path, str]:
    """A repo whose in-scope file is fixable, and the base to repair against."""
    repo = make_repo(
        tmp_path / "work", {"src/pkg/fetch.py": "def fetch(url):\n    return url\n"}
    )
    base = head(repo)
    (repo / "src" / "pkg" / "fetch.py").write_text(UNFORMATTED, encoding="utf-8")
    return repo, base


def control(outcome: RepairOutcome, repo: Path) -> None:
    """The in-scope file *was* repaired, so an untouched neighbour proves scope."""
    assert "src/pkg/fetch.py" in outcome.repaired, (
        f"control: the in-scope file was not repaired either, so nothing here "
        f"says where the repair may write ({outcome.environment_issues})"
    )
    repaired = (repo / "src" / "pkg" / "fetch.py").read_text(encoding="utf-8")
    assert repaired != UNFORMATTED


# --- N3: the scope promise is about bytes, not about names ----------------


def test_repair_does_not_write_through_a_hard_link_to_a_file_out_of_scope(
    tmp_path: Path,
) -> None:
    """A second name for a forbidden file is still that file.

    ``notes/`` is outside ``src/**/*.py``. The link is an in-scope *name*, and
    what the formatter writes through it lands on the inode the contract
    forbids — reported against the in-scope name, and invisible to a gate that
    only ever looks at the change.
    """
    repo, base = repaired_repo(tmp_path)
    forbidden = repo / "notes" / "secrets.py"
    forbidden.parent.mkdir()
    forbidden.write_text(UNFORMATTED, encoding="utf-8")
    untouched = forbidden.read_bytes()
    os.link(forbidden, repo / "src" / "pkg" / "link.py")

    outcome = repair(repo=repo, contract=work_contract("src/pkg/fetch.py"), base=base)

    assert forbidden.read_bytes() == untouched, (
        "repair rewrote notes/secrets.py through a hard link, and the "
        "contract's scope src/**/*.py forbids it"
    )
    assert "src/pkg/link.py" not in outcome.repaired, (
        "repair reported a repair against the in-scope name of a file it was "
        "not allowed to open"
    )
    control(outcome, repo)


def test_repair_does_not_write_through_a_hard_link_outside_the_repository(
    tmp_path: Path,
) -> None:
    """The same escape, one step further: the other name is in another tree.

    Nothing about the repository bounds the inode, so the only thing standing
    between ``ruff format`` and a stranger's file is the repair refusing to
    open a name whose bytes it cannot account for.
    """
    repo, base = repaired_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "notes.py"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text(UNFORMATTED, encoding="utf-8")
    untouched = elsewhere.read_bytes()
    os.link(elsewhere, repo / "src" / "pkg" / "link.py")

    outcome = repair(repo=repo, contract=work_contract("src/pkg/fetch.py"), base=base)

    assert elsewhere.read_bytes() == untouched, (
        f"repair rewrote {elsewhere}, a file outside the repository entirely"
    )
    assert "src/pkg/link.py" not in outcome.repaired
    control(outcome, repo)


def test_repair_does_not_write_through_a_symlink_out_of_scope(tmp_path: Path) -> None:
    """The vector the first fix closed, kept so it cannot re-open."""
    repo, base = repaired_repo(tmp_path)
    forbidden = repo / "notes" / "secrets.py"
    forbidden.parent.mkdir()
    forbidden.write_text(UNFORMATTED, encoding="utf-8")
    untouched = forbidden.read_bytes()
    (repo / "src" / "pkg" / "link.py").symlink_to(forbidden)

    outcome = repair(repo=repo, contract=work_contract("src/pkg/fetch.py"), base=base)

    assert forbidden.read_bytes() == untouched, "repair wrote through a symlink"
    control(outcome, repo)


def test_repair_does_not_write_through_a_symlink_outside_the_repository(
    tmp_path: Path,
) -> None:
    """The same, pointing out of the tree."""
    repo, base = repaired_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "notes.py"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text(UNFORMATTED, encoding="utf-8")
    untouched = elsewhere.read_bytes()
    (repo / "src" / "pkg" / "link.py").symlink_to(elsewhere)

    outcome = repair(repo=repo, contract=work_contract("src/pkg/fetch.py"), base=base)

    assert elsewhere.read_bytes() == untouched, (
        "repair wrote through a symlink pointing outside the repository"
    )
    control(outcome, repo)


def test_a_hard_link_whose_every_name_is_in_scope_is_still_repaired(
    tmp_path: Path,
) -> None:
    """The refusal is about *where the other names are*, not about link counts.

    Two in-scope names for one inode is a file the contract permits, written
    twice. Refusing it would make the repair skip work it is allowed to do, and
    a guard that refuses every multiply-named file passes the two tests above
    while buying nothing.
    """
    repo, base = repaired_repo(tmp_path)
    target = repo / "src" / "pkg" / "fetch.py"
    os.link(target, repo / "src" / "pkg" / "twin.py")

    outcome = repair(repo=repo, contract=work_contract("src/pkg/fetch.py"), base=base)

    assert outcome.changed, (
        f"a file with a second in-scope name was refused: {outcome.repaired}"
    )
    assert target.read_text(encoding="utf-8") != UNFORMATTED


# --- N4: a line is where the parser says it is ----------------------------


@pytest.mark.parametrize("separator", SEPARATORS, ids=lambda c: f"U+{ord(c):04X}")
def test_an_import_is_never_spliced_into_a_module_docstring(
    tmp_path: Path, separator: str
) -> None:
    """One character ``splitlines`` breaks on and the parser does not.

    The anchor is an AST ``end_lineno``; the list it indexes is one entry longer
    than the parser's count for every such character above it. The import lands
    inside the string literal: the file parses, and the ``F821`` it was
    repairing is still undefined.
    """
    module = tmp_path / "m.py"
    module.write_text(
        f'"""doc one\ndoc{separator}two\ndoc three"""\n\n\ndef use():\n'
        f"    return Retry()\n",
        encoding="utf-8",
    )

    _insert_imports(module, ["from pkg.retry import Retry"], [])

    written = module.read_text(encoding="utf-8")
    assert any("Retry" in line for line in top_level_imports(written)), (
        f"the import was written into the docstring rather than as an import, "
        f"so the name it was repairing is still undefined: {written!r}"
    )
    assert ast.get_docstring(ast.parse(written), clean=False) == (
        f"doc one\ndoc{separator}two\ndoc three"
    ), "the repair edited the module's documentation"


@pytest.mark.parametrize("terminator", TERMINATORS, ids=lambda t: repr(t))
def test_the_cut_agrees_with_the_parser_on_every_real_terminator(
    tmp_path: Path, terminator: str
) -> None:
    """All three of them, and only these three.

    ``ast`` numbers lines over ``\\n``, ``\\r\\n`` and ``\\r`` alike, so a cut
    that knows only ``\\n`` is off by one per CR-terminated line — and a repair
    that rewrites a file's endings has changed bytes nobody asked it to change.
    """
    module = tmp_path / "m.py"
    body = ['"""doc"""', "import os", "", "", "def use():", "    return os, Retry()"]
    module.write_bytes((terminator.join(body) + terminator).encode("utf-8"))

    _insert_imports(module, ["from pkg.retry import Retry"], [])

    written = module.read_bytes().decode("utf-8")
    assert any("Retry" in line for line in top_level_imports(written)), (
        f"the import did not land at module level: {written!r}"
    )
    assert ast.get_docstring(ast.parse(written), clean=False) == "doc", (
        "the repair edited the module's documentation"
    )
    assert endings(module) == {terminator}, (
        f"the repair rewrote the file's line endings: {endings(module)}"
    )


def test_a_repair_that_reports_success_wrote_the_import_it_claims(
    tmp_path: Path,
) -> None:
    """The defect as a caller sees it, through the public entry point.

    ``repaired`` is the only claim a caller acts on. With the import swallowed
    by the docstring the bytes did change, so the outcome says the file was
    repaired — and the undefined name that repair existed to answer for is
    still undefined.
    """
    repo = make_repo(
        tmp_path / "work",
        {
            "src/pkg/fetch.py": "def fetch(url):\n    return url\n",
            "src/pkg/backoff.py": (
                "def sleep_backoff(attempt: int) -> None:\n    return None\n"
            ),
        },
    )
    base = head(repo)
    target = repo / "src" / "pkg" / "fetch.py"
    target.write_text(
        '"""doc one\ndoc\x0ctwo\ndoc three"""\n\n\ndef fetch(url):\n'
        "    sleep_backoff(1)\n"
        "    return url\n",
        encoding="utf-8",
    )

    outcome = repair(repo=repo, contract=load_contract(DEPS_CONTRACT), base=base)

    written = target.read_text(encoding="utf-8")
    assert any("sleep_backoff" in line for line in top_level_imports(written)), (
        f"repair reported {outcome.repaired} and the import it wrote is inside "
        f"the docstring: {written!r}"
    )
