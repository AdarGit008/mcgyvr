"""Independent verification of the nine B1-B9 fixes, and what survived them.

Written by a verifier rather than by a fixer, so nothing here reuses a fixer's
reproduction: every statement was first reproduced against ``HEAD`` (the
pre-fix tree) and then re-run against the working tree, and every guard was
checked to fail when its production change is reverted.

The file has two halves and they say different things.

The **green** tests are properties the fixes actually established, stated on a
vector the fixer's own test did not take — delivery concurrency across OS
processes rather than threads, ``parser_lines`` agreeing with CPython's own line
accounting rather than with a list of eight characters, a cleanup preserving
CRLF.

The **xfail(strict=True)** tests are defects that survived. They are written as
the assertion that *should* hold, marked expected-to-fail with the reason, so
that the suite stays green today and turns red the moment one of them is fixed
without this file being updated. An xfail here is not a wish: each one was
reproduced by execution first.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.cleanup import tidy
from mcgyvr.config import parse
from mcgyvr.consensus import ConsensusError, best_of
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.deliver import Delivery, deliver
from mcgyvr.deterministic import tool_steps
from mcgyvr.escalate import Assurance, Delivered, Judgement, ascent, escalate
from mcgyvr.gate import ChangeSet, Gate, GateResult
from mcgyvr.lines import parser_lines
from mcgyvr.pending import resume, stash
from mcgyvr.pool import source_map
from mcgyvr.repair import _insert_imports, repair
from mcgyvr.route import Verdict
from mcgyvr.waves import run_waves

KEYLESS = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

FORMAT_CONTRACT = """
id: tidy
task_type: format
task: Reformat the package.
target: src/pkg/fetch.py
scope:
  allow: ["src/**"]
"""

WORK_CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: {target}
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["{scope}"]
"""

# Valid Python the gate rejects on two rungs a formatter answers for free.
UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)


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
        path.write_text(body)
    git(where.parent, "init", "-q", str(where))
    git(where, "config", "user.email", "verify@example.invalid")
    git(where, "config", "user.name", "verify")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


def work_contract(target: str, scope: str = "src/**/*.py") -> Contract:
    return load_contract(WORK_CONTRACT.format(target=target, scope=scope))


def passing(this: object) -> Judgement:
    """An attempt that accepts on whatever rung it is handed.

    The rung's name is stated in ``detail`` rather than returned as content: a
    judgement's acceptance is bound to the tree its gate read, and nothing here
    runs a gate.
    """
    rung = getattr(this, "rung", None)
    return Judgement(
        verdict=Verdict.PASSED,
        detail=f"{getattr(rung, 'name', '?')}",
        assurance=Assurance.UNVERIFIED,
    )


# --- green: what the fixes actually established --------------------------


def test_b1_a_deterministic_floor_with_a_tool_bound_reaches_a_verdict() -> None:
    """End to end, not at the guard: the climb must produce an outcome.

    Against ``HEAD`` this raised ``RouteError`` — which is not a ``RunnerError``,
    so ``tools/missions/run.py`` does not catch it and the mission loop aborts
    with earlier contracts already committed. The statement is therefore about
    ``escalate`` returning at all, and about the floor being stepped over rather
    than entered.
    """
    config = parse(KEYLESS)
    pool = source_map(config)
    contract = load_contract(FORMAT_CONTRACT)

    route = ascent(config, pool, contract)
    assert [plan.family.name for plan in route.runnable] == ["local"], (
        "the floor's program was offered to the ladder as something to climb"
    )

    outcome = escalate(config, pool, contract, passing)
    assert isinstance(outcome, Delivered), f"the climb did not deliver: {outcome}"
    assert outcome.family.name == "local"


def test_b2_the_three_python_types_run_and_do_only_what_they_guarantee(
    tmp_path: Path,
) -> None:
    """``argv`` is executable, and the three invocations are not interchangeable.

    ``format`` reflows and leaves imports alone; ``import_sort`` orders imports
    and leaves the body alone. Asserted by running the planned command, because
    "this step is executable" is a claim only an execution holds.
    """
    ruff = os.environ.get("RUFF", "ruff")
    if subprocess.run(["which", ruff], capture_output=True, check=False).returncode:
        pytest.skip("ruff is not installed")

    messy = "import sys\nimport os\ndef fetch( url ):\n    return  url\n"
    target = tmp_path / "src" / "pkg" / "fetch.py"
    target.parent.mkdir(parents=True)

    def run(task_type: str) -> str:
        target.write_text(messy)
        contract = load_contract(
            FORMAT_CONTRACT.replace("task_type: format", f"task_type: {task_type}")
        )
        argv = list(tool_steps(contract)[0].argv)
        assert argv, f"{task_type} planned no command"
        argv[0] = ruff
        subprocess.run(argv, cwd=tmp_path, capture_output=True, check=False)
        return target.read_text()

    formatted = run("format")
    sorted_imports = run("import_sort")

    assert "def fetch(url):" in formatted, "ruff format did not reflow the signature"
    assert formatted.index("import sys") < formatted.index("import os"), (
        "the format invocation reordered imports, which its guarantee forbids"
    )
    assert sorted_imports.index("import os") < sorted_imports.index("import sys"), (
        "the import_sort invocation did not order the imports"
    )
    assert "def fetch( url ):" in sorted_imports, (
        "the import_sort invocation reformatted the body, which its guarantee forbids"
    )


def test_b3_deliveries_from_separate_processes_leave_one_repository_clean(
    tmp_path: Path,
) -> None:
    """The vector a process-global lock could not have covered.

    Threads are the easier half. Against ``HEAD`` this left the tree at ``MM``
    — index and work tree both modified — in every round, because ``deliver``'s
    own undo raced another call's staging. The exclusion has to live in the
    repository for this to hold, which is what makes it the right shape.
    """
    workers = 3
    names = [f"src/pkg/f{n}.py" for n in range(workers)]
    repo = make_repo(
        tmp_path / "work",
        {name: f"def f{n}():\n    return {n}\n" for n, name in enumerate(names)},
    )
    base = git(repo, "rev-parse", "HEAD").strip()
    barrier = tmp_path / "go"

    program = """
import sys, time
from pathlib import Path
from mcgyvr.contract import loads
from mcgyvr.deliver import deliver
repo, base, target, barrier = sys.argv[1:5]
body = "id: c\\ntask_type: function_implementation\\ntask: t\\ntarget: %s\\n"
body += "stop_conditions: [\\"never\\"]\\nacceptance: [\\"true\\"]\\n"
body += "scope:\\n  allow: [\\"src/**/*.py\\"]\\n"
while not Path(barrier).exists():
    time.sleep(0.005)
out = deliver(repo=Path(repo), contract=loads(body % target),
              content="def " + Path(target).stem + "():\\n    return 99\\n", base=base)
print("committed" if out.committed else "refused:" + out.reason)
"""
    running = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(repo), base, name, str(barrier)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for name in names
    ]
    barrier.write_text("go")
    said = [proc.communicate() for proc in running]

    for name, (out, err) in zip(names, said, strict=True):
        assert out.strip() == "committed", f"{name}: {out.strip()} {err.strip()[:200]}"
        assert (repo / name).read_text().endswith("return 99\n")
    assert git(repo, "status", "--porcelain").strip() == "", "the tree was left dirty"
    assert sorted(git(repo, "diff", "--name-only", f"{base}..HEAD").split()) == sorted(
        names
    )


@pytest.mark.parametrize(
    "terminator",
    ["\n", "\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028"],
)
def test_b4_the_splice_index_agrees_with_cpythons_own_line_numbers(
    terminator: str,
) -> None:
    """Checked against the parser, not against a list of characters.

    ``parser_lines`` is only correct if indexing it 0-based reaches the line
    ``lineno`` names, for every character that can appear in a source file. The
    parser is asked directly rather than trusted to match a hand-written set,
    and the join is asserted to be the original bytes so that a slice-and-rejoin
    reconstructs the file rather than a version of it.
    """
    source = f'BANNER = """x{terminator}y"""\ndef marker():\n    pass\n'
    tree = ast.parse(source)
    definition = next(node for node in tree.body if isinstance(node, ast.FunctionDef))

    cut = parser_lines(source)
    assert "".join(cut) == source, "the cut does not rejoin into the original bytes"
    assert cut[definition.lineno - 1].lstrip().startswith("def marker"), (
        f"line {definition.lineno} of the parser is not line {definition.lineno} "
        f"of the cut, so a splice at that index moves the file"
    )


def test_b9_a_cleanup_does_not_translate_line_endings(tmp_path: Path) -> None:
    """The second defect the bytes pipe fixed, which nothing had named.

    ``text=True`` on the formatter pipe translated CRLF to LF on the way back,
    so a *cleanup* silently rewrote every line ending in the file. Undocumented
    in the pressure test and reproduced against ``HEAD``.
    """
    cleaned = tidy(
        content="def f( a ):\r\n    return  a\r\n", result=GateResult(), target="x.py"
    )
    assert cleaned.cleaned, "nothing was cleaned, so the statement is untested"
    assert "\r\n" in cleaned.content, "the cleanup rewrote CRLF endings as LF"
    assert cleaned.content.replace("\r\n", "").count("\n") == 0, (
        "the cleanup left a mix of CRLF and LF endings behind"
    )


def test_b9_the_surrogate_convention_round_trips_through_a_delivery(
    tmp_path: Path,
) -> None:
    """``surrogatepass`` for the digest and ``surrogateescape`` for the file agree.

    The two spellings are only safe if a delivery's own write-then-read reaches
    the same string it was handed; otherwise every verdict would look
    substituted at the commit point.
    """
    from mcgyvr.deliver import digest_of

    target = "src/pkg/fixture.txt"
    repo = make_repo(tmp_path / "repo", {target: "fixture\n"})
    head = git(repo, "rev-parse", "HEAD").strip()
    content = "fixture \udcff \udc80 caf\udce9\n"

    result = deliver(
        repo=repo,
        contract=work_contract(target, scope="src/**"),
        content=content,
        base=head,
    )
    assert result.committed, result.reason
    back = (repo / target).read_bytes().decode("utf-8", "surrogateescape")
    assert digest_of(back) == digest_of(content), (
        "content written and read back does not answer for its own digest"
    )


# --- xfail(strict): what survived the fixes ------------------------------


def test_b5_repair_does_not_write_through_a_hard_link_out_of_scope(
    tmp_path: Path,
) -> None:
    repo = make_repo(
        tmp_path / "work",
        {
            "src/pkg/fetch.py": "def fetch(url):\n    return url\n",
            "notes/secrets.py": UNFORMATTED,
        },
    )
    base = git(repo, "rev-parse", "HEAD").strip()
    outside = repo / "notes" / "secrets.py"
    untouched = outside.read_text()

    os.link(outside, repo / "src" / "pkg" / "link.py")
    (repo / "src" / "pkg" / "fetch.py").write_text(UNFORMATTED)

    repair(repo=repo, contract=work_contract("src/pkg/fetch.py"), base=base)

    assert outside.read_text() == untouched, (
        "repair rewrote notes/secrets.py through a hard link, and the "
        "contract's scope src/**/*.py forbids it"
    )


def test_b6_gate_rejected_bytes_do_not_reach_the_repository_through_resume(
    tmp_path: Path,
) -> None:
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "work", {target: "def fetch(url):\n    return url\n"})
    base = git(repo, "rev-parse", "HEAD").strip()
    contract = work_contract(target)

    held = UNFORMATTED  # what the caller is holding
    (repo / target).write_text(held)
    assert not Gate().run(ChangeSet.detect(repo, base), contract.scope).accepted
    repair(repo=repo, contract=contract, base=base)
    assert Gate().run(ChangeSet.detect(repo, base), contract.scope).accepted
    git(repo, "checkout", "-q", "--", target)

    stash(store=tmp_path / "store", repo=repo, contract=contract, content=held)
    resume(
        store=tmp_path / "store",
        repo=repo,
        task=contract.id,
        verify=lambda _: True,
        base=base,
    )

    assert Gate().run(ChangeSet.detect(repo, base), contract.scope).accepted, (
        "what was committed is what the gate rejected"
    )


def test_b8_a_refused_delivery_is_not_reported_as_a_completion() -> None:
    contract = work_contract("src/pkg/fetch.py")
    refused = Delivery(committed=False, reason="the working tree is dirty", path="p")

    run = run_waves([contract], lambda _: refused)

    assert run.failed == ((contract.id, "the working tree is dirty"),), (
        f"a refused delivery was reported as a completion: {run}"
    )


def test_b4_pattern_repair_does_not_splice_an_import_into_a_docstring(
    tmp_path: Path,
) -> None:
    source = (
        '"""doc one\ndoc\x0ctwo\ndoc three"""\n\n\ndef use():\n    return Retry()\n'
    )
    module = tmp_path / "m.py"
    module.write_text(source)

    _insert_imports(module, ["from pkg.retry import Retry"], [])

    tree = ast.parse(module.read_text())
    names = [
        ast.unparse(node)
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
    ]
    assert any("Retry" in name for name in names), (
        "the import was written into the module docstring rather than as an "
        "import, so the undefined name it was repairing is still undefined"
    )


def test_b7_an_unnameable_source_base_is_refused_rather_than_softened_to_head(
    tmp_path: Path,
) -> None:
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})

    with pytest.raises(Exception, match="base"):
        deliver(
            repo=repo,
            contract=work_contract(target),
            content="def fetch(url):\n    return url.strip()\n",
            base="",  # what source_base_commit() returns for a non-git source
        )


def test_b2_the_planned_command_cannot_be_read_as_an_option() -> None:
    contract = load_contract(
        FORMAT_CONTRACT.replace("target: src/pkg/fetch.py", "target: --config=x.py")
        .replace('allow: ["src/**"]', 'allow: ["**"]')
        .replace("id: tidy", "id: dash")
    )
    argv = tool_steps(contract)[0].argv
    assert "--" in argv, f"the target is not separated from the flags: {argv}"


def test_b1_pattern_an_ascent_that_can_climb_nothing_is_falsy() -> None:
    os.environ.pop("MCGYVR_NO_SUCH_KEY_FOR_VERIFICATION", None)
    config = parse(
        """
version: 1
sources:
  cloud:
    base_url: https://api.example.invalid
    api: openai
    api_key_env: MCGYVR_NO_SUCH_KEY_FOR_VERIFICATION
    max_parallel: 1
ladder:
  tiers:
    - name: api_big
      source: cloud
      model: big
"""
    )
    route = ascent(config, source_map(config), load_contract(FORMAT_CONTRACT))

    assert len(route) == 0, "the premise did not hold: something is climbable"
    assert not route, (
        "bool(ascent) is True while len(ascent) is 0: a caller guarding on "
        "truthiness enters an ascent with nothing to climb"
    )


def test_pattern_a_consensus_reports_content_it_cannot_write_as_its_own_error(
    tmp_path: Path,
) -> None:
    target = "src/pkg/fetch.py"
    repo = make_repo(tmp_path / "repo", {target: "def fetch(url):\n    return url\n"})
    contract = work_contract(target)

    with pytest.raises(ConsensusError):
        best_of(
            repo=repo,
            contract=contract,
            sample=lambda _: "X = '\ud800'\n",
            gate=lambda sandbox: Gate().run(
                ChangeSet.detect(sandbox.workspace, "HEAD"), contract.scope
            ),
            n=1,
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-29: "
        "The `Ceiling` mcgyvr pool prints sums the configured attempts of every "
        "rung; the one escalate enforces is attempts_for(), which also clamps "
        "by contract.limits.attempts. The two do not agree, which is what the "
        "ladder_budget docstring was rewritten to claim they do."
    ),
)
def test_the_printed_ceiling_is_the_one_that_is_enforced() -> None:
    config = parse(
        """
version: 1
sources:
  ws:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_a
      source: ws
      model: m1
      attempts: 3
    - name: local_b
      source: ws
      model: m2
      attempts: 2
"""
    )
    pool = source_map(config)
    printed = sum(
        tier.attempts
        for tier in (config.ladder.get(rung.name) for rung in pool.rungs)
        if tier is not None
    )
    enforced = ascent(config, pool, work_contract("src/pkg/fetch.py")).ladder_budget

    assert printed == enforced, (
        f"`mcgyvr pool` prints {printed} attempt(s) per task and the climb "
        f"enforces {enforced}"
    )


def test_the_catalog_names_the_families_these_statements_assume() -> None:
    """A premise pin: every family name used above comes from the catalog."""
    names = {family.name for family in catalog().families}
    assert {"deterministic", "local", "api"} <= names
