"""Pattern E — the eight declared boundaries, held by something that fails.

The 2026-08-29 pressure test's pattern E is not "a boundary was crossed". It is
"a boundary was *declared*, and nothing in the suite would notice it being
crossed". Every case below therefore does the crossing for real and asserts on
what came out the other side, rather than asserting that some guard function
returns True.

Each test is written so that reverting its fix makes it fail. That rule is the
one the second round of B1-B9 fixes carried and the first round lacked: a guard
whose test passes with the guard disabled is holding nothing, which is the
pattern this file exists to close.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import RetryNotes
from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.runner import GateResult
from mcgyvr.worker.prompt import build_prompt

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

# The command is a shell no-op (``:``) carrying a distinctive argument, so the
# canary appears in the command *label* and in nothing the command prints. A
# command that echoed its canary would make this test pass or fail on the
# excerpt rather than on the boundary being tested.
CANARY = "canary_acceptance_9f3c"
ACCEPTANCE_COMMAND = f"sh -c ': {CANARY}; exit 1'"

CONTRACT = f"""
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["{ACCEPTANCE_COMMAND}"]
scope:
  allow: ["src/**/*.py"]
"""


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


# --- E1 · #94 on the retry path ---------------------------------------------


def _rejecting_gate(git_repo: Path) -> GateResult:
    """A real acceptance rejection, from running the contract's own command."""
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    contract = load_contract(CONTRACT)
    with TempDirSandbox(git_repo) as sandbox:
        command = tuple(shlex.split(contract.acceptance[0]))
        report = Acceptance(sandbox, (command,)).run()
    assert report.findings, "the canary command must reject, or this proves nothing"
    return GateResult(findings=tuple(report.findings))


def test_the_acceptance_command_never_reaches_the_worker_prompt(
    git_repo: Path,
) -> None:
    """#94: ``acceptance`` is orchestrator-only, on the retry path too.

    ``Contract.worker_view`` excludes ``acceptance`` and documents that the
    exclusion is enforced "by there being no other accessor". The retry note is
    the other accessor: an acceptance finding carries its command in
    ``Finding.path``, and ``RetryNotes.of`` rendered findings with ``str()``,
    which prints the path first.
    """
    contract = load_contract(CONTRACT)
    notes = RetryNotes.of(_rejecting_gate(git_repo))
    assert notes is not None

    prompt = build_prompt(contract, retry=notes)

    assert CANARY not in prompt.user
    assert CANARY not in prompt.system
    assert CANARY not in notes.text


def test_the_retry_note_still_says_the_acceptance_check_failed(
    git_repo: Path,
) -> None:
    """Withholding the command must not withhold the signal.

    The worker cannot be told *which* command to satisfy, and it does not need
    to be: what a retry is for is the failure, which lives in the message. A
    fix that dropped acceptance findings from the note altogether would pass the
    test above and remove the most decisive retry signal there is.
    """
    notes = RetryNotes.of(_rejecting_gate(git_repo))
    assert notes is not None
    assert "acceptance" in notes.checks
    assert "acceptance command failed" in notes.text


def test_the_reviewer_is_not_shown_the_acceptance_command_either(
    git_repo: Path,
) -> None:
    """The same boundary at the second seam that crosses it.

    ``verify._contract_block`` documents that a reviewer "cannot be shown
    ``risk``, ``verification`` or ``acceptance``" because a reviewer that could
    read them "could argue with them instead of judging the code". The gate
    summary rendered beside it handed over the acceptance command anyway, in the
    finding's path. One rendering rule, so both seams move together.
    """
    from mcgyvr.verify import gate_summary

    summary = gate_summary(_rejecting_gate(git_repo))

    assert CANARY not in summary
    assert "acceptance command failed" in summary


def test_a_finding_that_names_a_file_is_unchanged_for_a_model(
    git_repo: Path,
) -> None:
    """The redaction is the exception, not the rule.

    Every check that reads the worker's diff must still tell a model exactly
    where the problem is; a fix that dropped locations generally would pass the
    tests above while making every retry note useless.
    """
    from mcgyvr.gate.findings import Finding

    finding = Finding(
        check="lint",
        path="src/pkg/fetch.py",
        message="unused import",
        line=12,
        code="F401",
    )
    assert finding.for_model() == str(finding)
    assert "src/pkg/fetch.py:12" in finding.for_model()


def test_the_orchestrators_own_rendering_still_carries_the_command(
    git_repo: Path,
) -> None:
    """Withheld from models, not from the operator.

    ``str(finding)`` is what a log, a report and the console are built from, and
    an operator reading "acceptance failed" with no command named cannot act on
    it. The boundary is about who reads the text, so the two renderings have to
    actually differ — asserting only the absence would be satisfied by deleting
    the command everywhere.
    """
    gate = _rejecting_gate(git_repo)
    assert CANARY in str(gate.findings[0])


# --- E3 · D20 applied to the port's own sinks -------------------------------

SECRET_IN_URL = "sk-canary-3d81f"

CONFIG_WITH_CREDENTIALED_URL = f"""
version: 1
sources:
  hosted:
    base_url: https://user:{SECRET_IN_URL}@api.example.invalid/v1
    api: openai
    max_parallel: 2
ladder:
  tiers:
    - name: api_large
      source: hosted
      model: vendor-large
"""


def test_a_credential_in_a_base_url_is_refused_at_load() -> None:
    """D20 at the point the value enters, not at each place it is printed.

    ``Config.secret`` already says a credential belongs in the environment and
    "never write the value into the config file". A ``base_url`` with userinfo
    is that value in that file, and it is the one credential the config format
    accepted silently.
    """
    from mcgyvr.config import ConfigError
    from mcgyvr.config import parse as parse_config

    with pytest.raises(ConfigError) as exc:
        parse_config(CONFIG_WITH_CREDENTIALED_URL)

    message = str(exc.value)
    assert "base_url" in message
    assert "api_key_env" in message  # the message says what to do instead
    assert SECRET_IN_URL not in message  # including in the refusal itself


def test_the_refusal_does_not_fire_on_an_ordinary_url() -> None:
    """The check has to be about userinfo and not about the ``@`` character.

    A port of this rule that matched ``@`` anywhere in the URL would refuse
    every path containing one and would be removed by the first person it
    inconvenienced.
    """
    from mcgyvr.config import parse as parse_config

    config = parse_config(
        CONFIG_WITH_CREDENTIALED_URL.replace(
            f"https://user:{SECRET_IN_URL}@api.example.invalid/v1",
            "https://api.example.invalid/v1/models@latest",
        )
    )
    assert config.sources["hosted"].base_url.endswith("@latest")


def test_no_runner_error_can_quote_a_credentialed_url() -> None:
    """The sink the refusal is protecting, exercised for real.

    ``_post_json`` documents that "no message interpolates a credential — the
    key is in ``headers``, which is never quoted". That was true of the header
    and not of the URL. This drives a real transport failure against a URL that
    would carry one, and asserts on the text that reaches an operator.
    """
    from mcgyvr.runner import RunnerError, _post_json

    url = f"https://user:{SECRET_IN_URL}@127.0.0.1:1/v1/chat/completions"
    with pytest.raises(RunnerError) as exc:
        _post_json(url, {"model": "m"}, {}, 0.25)

    assert SECRET_IN_URL not in str(exc.value)


def test_telemetry_does_not_write_a_credential_into_its_own_sink(
    tmp_path: Path,
) -> None:
    """The second half of D20's application to the port's sinks.

    ``observe`` records ``str(failure)`` for an attempt that raised, and the
    exception is the caller's — this module cannot know what built it. A
    credentialed URL is the one credential shape the project can produce inside
    a message, so it is the one this scrubs. The row is still written and still
    names the failure: a sink that dropped the record would trade one hole for
    another.
    """
    from mcgyvr.telemetry import fold, observe

    sink = tmp_path / "telemetry.jsonl"

    def raises() -> object:
        raise RuntimeError(
            f"could not reach https://user:{SECRET_IN_URL}@api.example.invalid/v1"
        )

    with pytest.raises(RuntimeError):
        observe(
            raises,
            path=sink,
            attempt_id="a1",
            orchestrator="test",
            rung="api_large",
        )

    raw = sink.read_text(encoding="utf-8")
    assert SECRET_IN_URL not in raw

    (record,) = fold(path=sink)
    assert record["ok"] is False
    assert record["error"] == "RuntimeError"
    assert "api.example.invalid" in str(record["error_detail"])  # still diagnostic


# --- E4 · §9's no-global-mutable-state --------------------------------------


def test_no_module_holds_shipped_data_in_an_assignable_global() -> None:
    """§9: "must not bake in single-orchestrator assumptions — no global
    mutable state".

    Read as a source property rather than as a behaviour, because the hazard is
    a name existing at all: a module variable holding the catalog or the
    capability table can be reassigned by anything in the process, and every
    consumer then answers from the substitute with no call site able to tell.
    Contract digest identity is derived from the catalog, so that substitution
    silently re-keys the evidence ``tools/instruments.py`` pins.

    Scoped to ``global`` *statements*, which is what the pressure test counted
    and what distinguishes a rebindable module variable from a memo.
    """
    import ast

    from mcgyvr import catalog as catalog_module

    src_root = Path(catalog_module.__file__).parent
    offenders: list[str] = []
    for module in sorted(src_root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                offenders.append(f"{module.name}:{node.lineno} {', '.join(node.names)}")

    assert offenders == []


def test_the_shipped_table_is_still_loaded_only_once() -> None:
    """Removing the global must not have removed the reason it was there.

    The cost argument is real — both files are read on hot paths — so the memo
    has to still be a memo. Identity, not equality: two equal tables would mean
    it reloaded and revalidated.
    """
    from mcgyvr.capability import shipped_table
    from mcgyvr.catalog import catalog

    assert shipped_table() is shipped_table()
    assert catalog() is catalog()


# --- E2 + E6 · the seam, and the guard that reports on spelling --------------


def test_the_verifier_role_is_answered_without_handing_over_a_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E2: a presence check must not come with something to dispatch with.

    ``reviewer_for`` asked ``source_map.role(VERIFIER_ROLE) is None`` — a yes/no
    question answered with a ``RoleBinding``, which carries an ``Endpoint``,
    which carries ``credential()``. The module imported neither forbidden name,
    which is precisely why the import guard could not see it.
    """
    from mcgyvr.config import parse as parse_config
    from mcgyvr.pool import source_map

    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    pool = source_map(
        parse_config(
            """
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
verifier:
  enabled: true
  source: workstation
  model: qwen2.5-coder:14b
"""
        )
    )

    answer = pool.role_model("verifier")

    assert answer == "qwen2.5-coder:14b"
    assert isinstance(answer, str)  # a name, not a binding with an endpoint on it


def test_the_seam_guard_catches_every_spelling_it_used_to_miss(
    tmp_path: Path,
) -> None:
    """E6: the guard had three bypasses, so it was reporting on spelling.

    Each module below crosses the seam in a way the original guard's single
    shape — ``ast.ImportFrom`` with ``module == "mcgyvr.pool"`` — does not match.
    Written as synthetic source rather than by asserting against ``src/``,
    because a guard is only shown to hold by giving it something that should
    fail.
    """
    from tests.test_pool import seam_offenders

    (tmp_path / "by_module_import.py").write_text(
        "import mcgyvr.pool\n\nE = mcgyvr.pool.Endpoint\n", encoding="utf-8"
    )
    (tmp_path / "by_relative_import.py").write_text(
        "from .pool import Endpoint\n", encoding="utf-8"
    )
    (tmp_path / "by_accessor.py").write_text(
        "def f(source_map):\n    return source_map.role('verifier').endpoint\n",
        encoding="utf-8",
    )

    caught = {line.split(":")[0] for line in seam_offenders(tmp_path)}

    assert caught == {
        "by_module_import.py",
        "by_relative_import.py",
        "by_accessor.py",
    }


def test_the_seam_guard_still_passes_an_innocent_module(tmp_path: Path) -> None:
    """The other half: a guard that fails everything is not holding a boundary.

    ``SourceMap`` and ``Rung`` are the seam's public face and are meant to be
    imported above it; ``role_model`` is the accessor that replaces ``role``.
    """
    from tests.test_pool import seam_offenders

    (tmp_path / "innocent.py").write_text(
        "from mcgyvr.pool import SourceMap\n\n"
        "def f(source_map: SourceMap) -> str | None:\n"
        "    return source_map.role_model('verifier')\n",
        encoding="utf-8",
    )

    assert seam_offenders(tmp_path) == []
