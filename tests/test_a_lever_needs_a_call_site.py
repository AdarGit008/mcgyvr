"""Three levers that were built, tested, and reachable from nothing a user runs.

The 2026-08-29 pressure test's status block names them together: *"``worker_attempt``
has no flag on ``mcgyvr run``, and ``consensus.best_of`` and ``cleanup.tidy`` still
have no production caller — which is why phase 3 had to reason about their shape
rather than about a call site."* Reasoning about a shape is what this file replaces.

Nothing here is a coverage exercise. A lever designed against a caller nobody wrote
is a lever whose signature has never been contradicted, and the only way to find out
whether it survives contact is to write the caller and see which arguments it cannot
supply. Each section below drives one lever from the outside — the command line for
the first, a configured install for the other two — and asserts on what a user would
see rather than on the call having happened.

The one thing substituted anywhere is a model, because a test that needed a backend
would not run on a machine without one. The seam that allows it is the seam the whole
project is built on: :func:`mcgyvr.runner.dispatch` takes a rung name and a source
map, so nothing above it knows a socket exists.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import CONFIG_PATH_ENV

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/fetch.py"

#: The file as it is committed: ruff-clean, so every complaint the gate raises
#: below is about a line the worker wrote rather than one it inherited.
BASE = "def fetch(url):\n    return url\n"

#: A ladder with one credential-free rung. `local` is the family every
#: model-executed task type starts on, so this is the smallest install that can
#: climb at all.
LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

#: The same ladder with nothing bound below the api family, and the one source
#: it does declare naming an environment variable that is not set. Structurally
#: unusable, which is knowable without touching the network.
UNBOUND_LADDER = """
version: 1
sources:
  hosted:
    base_url: https://api.example.invalid
    api: openai
    max_parallel: 1
    api_key_env: MCGYVR_TEST_KEY_THAT_IS_NOT_SET
ladder:
  tiers:
    - name: api_big
      source: hosted
      model: big-model
"""

MODEL_CONTRACT = f"""
id: retry
task_type: function_implementation
task: Give the fetch helper a retry budget named RETRY.
target: {TARGET}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
acceptance: ["sh -c 'grep -q RETRY {TARGET}'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real repository with one clean commit for the gate to diff against."""
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text(BASE, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def contract(tmp_path: Path) -> Path:
    path = tmp_path / "retry.yaml"
    path.write_text(MODEL_CONTRACT, encoding="utf-8")
    return path


def _config(tmp_path: Path, text: str = LADDER) -> Path:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _completion(text: str):  # type: ignore[no-untyped-def]
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer each dispatch from a script; return the list of prompts sent.

    Substituted at :data:`mcgyvr.drive.dispatch` rather than at the socket,
    because the point of every test below is what the driver does with an
    answer, not how the answer arrived.
    """
    import mcgyvr.drive as drive

    sent: list[str] = []
    scripted = list(replies)

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(request.prompt)
        if not scripted:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        return _completion(scripted.pop(0))

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


def _fenced(content: str) -> str:
    return f"```python\n{content}```\n"


# --------------------------------------------------------------------------
# 1 · `worker_attempt` is reachable from `mcgyvr run`
# --------------------------------------------------------------------------


def test_the_run_command_climbs_the_ladder_for_a_model_contract(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal at ``cli.py:716`` replaced by the climb it was standing in for.

    The assertion is on the repository rather than on the output, for the reason
    the deterministic half of this command is already asserted that way: a commit
    that exists is the only evidence the task ran. What it proves is that
    ``mcgyvr run`` now reaches :func:`mcgyvr.drive.worker_attempt` and drives it —
    a prompt was assembled, a rung was dispatched to, the reply was parsed and
    gated in a sandbox, and the accepted bytes were delivered.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path)
    _answers(monkeypatch, _fenced("RETRY = 3\n\n\ndef fetch(url):\n    return url\n"))

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    assert code == 0
    assert (repo / TARGET).read_text(encoding="utf-8") == (
        "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"
    )
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s", "-1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip().startswith("retry:")


def test_the_ladder_is_found_the_way_every_other_command_finds_it(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No flag at all still climbs, because the config has its own resolution order.

    ``mcgyvr config`` and ``mcgyvr pool`` already resolve a path from
    ``$MCGYVR_CONFIG``, then the working directory, then the user config dir. A
    ``run`` that could only be pointed at a ladder by flag would be a second
    answer to a question the project has already settled once, and an install
    that has exported the variable would have to repeat itself.

    This is the test that fails on the *refusal* rather than on an unknown flag:
    it passes no new argument at all, so nothing but the driver being reached can
    turn it green.
    """
    from mcgyvr.cli import main

    monkeypatch.setenv(CONFIG_PATH_ENV, str(_config(tmp_path)))
    _answers(monkeypatch, _fenced("RETRY = 3\n\n\ndef fetch(url):\n    return url\n"))

    code = main(["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"])

    assert code == 0
    # No `--commit`, so the accepted file is left in the working tree and the
    # repository is otherwise untouched — the same bargain the deterministic
    # path makes (owner's ruling, 2026-09-03: output files, no commit).
    assert (repo / TARGET).read_text(encoding="utf-8").startswith("RETRY = 3\n")
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "RETRY" not in log.stdout and len(log.stdout.splitlines()) == 1, log.stdout


def test_an_install_with_no_rung_is_told_what_to_bind(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An install with no rung is a configuration message, not a shrug.

    The contract starts on the ``local`` family and this install has bound
    nothing to it; its one declared source names a credential that is not in the
    environment, so the ``api`` family above it is skipped too. Both facts are
    already computed — :func:`mcgyvr.route.plan` writes the sentence and
    :attr:`mcgyvr.escalate.Ascent.reason` collects it — and the only thing that
    was missing is a command that prints them.

    Neither the exit code nor the family name carries this test on its own: the
    command already exited 1 naming ``local`` when it refused every model
    contract outright, so a test resting on those two would have passed against
    the refusal it is meant to replace. The rung and the variable are what only
    a resolved ladder can say.
    """
    from mcgyvr.cli import main

    monkeypatch.delenv("MCGYVR_TEST_KEY_THAT_IS_NOT_SET", raising=False)
    config = _config(tmp_path, UNBOUND_LADDER)

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    stderr = capsys.readouterr().err
    assert code == 1
    assert "local" in stderr, (
        f"the empty family the contract starts on is not named: {stderr!r}"
    )
    assert "api_big" in stderr, (
        f"the skipped rung is not named, so nothing says which source to fix: "
        f"{stderr!r}"
    )
    assert "MCGYVR_TEST_KEY_THAT_IS_NOT_SET" in stderr, (
        f"the unset credential is not named: {stderr!r}"
    )


def test_a_backend_that_does_not_answer_is_reported_against_its_rung(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A dead socket is a named failure of a named rung, never a traceback.

    The structural case above is the one a config edit fixes; this is the one a
    machine fixes, and the two must not print the same thing. What the transport
    layer can say is the URL it could not reach — it knows nothing of ladders —
    so the rung's name has to be supplied by the caller that chose it.
    """
    import mcgyvr.drive as drive
    from mcgyvr.cli import main
    from mcgyvr.runner import TransportError

    def dead(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        raise TransportError("could not reach http://localhost:11434 within 60s")

    monkeypatch.setattr(drive, "dispatch", dead)
    config = _config(tmp_path)

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    stderr = capsys.readouterr().err
    assert code == 1
    assert "local_qwen-7b" in stderr, (
        f"the rung whose backend did not answer is not named: {stderr!r}"
    )
    assert "could not reach" in stderr, (
        f"the transport's own words were lost: {stderr!r}"
    )


# --------------------------------------------------------------------------
# 2 · `consensus.best_of` has a production caller
# --------------------------------------------------------------------------

#: Three draws for one attempt. Only the last carries the name the contract's
#: acceptance command greps for, so the gate can separate them and the ranking
#: has something to rank.
DRAWS = (
    "def fetch(url):\n    return url.upper()\n",
    "def fetch(url):\n    return url.strip()\n",
    "RETRY = 3\n\n\ndef fetch(url):\n    return url\n",
)

BREADTH = (
    LADDER
    + """
breadth:
  draws: 3
"""
)


def _breadth_seen(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record every ``n`` :func:`mcgyvr.consensus.best_of` is asked for.

    A spy over the real function rather than a stand-in for it: what is being
    asserted is that the driver goes through this lever and with which breadth,
    and a fake that returned a :class:`~mcgyvr.consensus.Consensus` of its own
    would assert only that the driver can read one.

    Reaching for ``drive.best_of`` is itself the assertion when there is no
    caller: the name is not there to patch.
    """
    import mcgyvr.drive as drive

    # `type: ignore` for the re-export rule, not for the lookup: `best_of` is
    # imported into `drive`, which mypy will not call an export, and the whole
    # point of reading it here is that the driver's own namespace is where the
    # call site lives.
    real = drive.best_of  # type: ignore[attr-defined]
    seen: list[int] = []

    def spy(**kwargs):  # type: ignore[no-untyped-def]
        seen.append(kwargs.get("n", 1))
        return real(**kwargs)

    monkeypatch.setattr(drive, "best_of", spy)
    return seen


def test_breadth_is_asked_for_in_the_config_and_the_gate_picks_the_winner(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three draws for one attempt, ranked by what the gate found, and one delivered.

    ADR-0008's measurement — "given that a gate-passing candidate exists among N,
    at what index does it first appear?" — needs a run that actually draws N. The
    two draws that miss the contract's acceptance command are gated and beaten;
    the third is what lands in the repository.

    The committed bytes are asserted exactly, because the invariant that makes
    breadth safe is that no rejected draw survives its own workspace reset: a
    delivery carrying any of the first two would be committing a candidate that
    lost.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, BREADTH)
    sent = _answers(monkeypatch, *(_fenced(draw) for draw in DRAWS))

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    assert code == 0
    assert len(sent) == 3, f"the rung was asked {len(sent)} time(s), not three"
    assert (repo / TARGET).read_text(encoding="utf-8") == DRAWS[2]


def test_breadth_is_draws_within_one_attempt_and_not_more_attempts(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Three dispatches, one attempt — the distinction the whole lever rests on.

    Breadth and retry both spend a dispatch and are otherwise nothing alike. A
    retry is a second attempt with the last one's findings in the prompt, counted
    against ``budgets.max_attempts`` and capable of escalating; a draw is the
    same prompt asked again, inside one attempt, with the gate choosing between
    the answers. An implementation that reached breadth by looping the *attempt*
    would satisfy the test above and would have quietly raised the ceiling every
    budget in the config is written against.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, BREADTH)
    _answers(monkeypatch, *(_fenced(draw) for draw in DRAWS))

    main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    stdout = capsys.readouterr().out
    assert "after 1 attempt(s)" in stdout, (
        f"three draws were counted as more than one attempt: {stdout!r}"
    )


def test_an_install_that_asked_for_nothing_draws_once(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default is one draw, and it is reached through the same lever.

    ADR-0008's rule is unchanged for an install that configured nothing: one
    draw, one verdict, and the draw is the answer. What this pins is that the
    default is ``n = 1`` *through* :func:`~mcgyvr.consensus.best_of` rather than
    a second, quieter code path beside it — a lever with a branch that skips it
    on the default setting is a lever the ordinary install never proves.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path)
    seen = _breadth_seen(monkeypatch)
    sent = _answers(monkeypatch, _fenced(DRAWS[2]))

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    assert code == 0
    assert seen == [1], f"an unconfigured install asked for {seen} draw(s)"
    assert len(sent) == 1


# --------------------------------------------------------------------------
# 3 · `cleanup.tidy` has a production caller
# --------------------------------------------------------------------------

#: Right answer, wrong shape: `RETRY` is there, so the contract's acceptance
#: command is satisfied, and every line the worker wrote is one `ruff format`
#: would reflow. The gate files that under `findings` and rejects — the single
#: case `cleanup` exists for, arriving as a rejection rather than as the
#: observation its bucket name suggests.
MESSY = "RETRY = 3\n\n\ndef fetch( url ):\n    return  url\n"

#: What `ruff format` makes of it, and what the repository must end up holding.
TIDIED = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"

#: Misformatted *and* wrong: no RETRY, so the acceptance command fails, and
#: no tool answers that. (An unused import used to stand here; since
#: 2026-09-05 the linter's own autofix removes one, which is the point.)
MESSY_AND_BROKEN = "def fetch( url ):\n    return  url\n"

TIDYING = (
    LADDER
    + """
cleanup:
  enabled: true
"""
)
#: The knob turned off by hand. Since 2026-09-05 a config that says nothing
#: tidies (owner's ruling), so "not tidied" is something an install asks for.
NOT_TIDYING = (
    LADDER
    + """
cleanup:
  enabled: false
"""
)


def _tidies_seen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every target :func:`mcgyvr.cleanup.tidy` is asked to clean.

    As with the breadth spy, reaching for the name in the driver's namespace is
    itself the assertion while there is no caller.
    """
    import mcgyvr.drive as drive

    real = drive.tidy  # type: ignore[attr-defined]
    seen: list[str] = []

    def spy(**kwargs):  # type: ignore[no-untyped-def]
        seen.append(kwargs["target"])
        return real(**kwargs)

    monkeypatch.setattr(drive, "tidy", spy)
    return seen


def test_a_format_only_rejection_is_cleaned_rather_than_sent_back_to_a_model(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole economic argument for the lever, at a call site that pays it.

    Without this the run costs a second dispatch — a full context and an attempt
    off the ceiling — to insert a space. With it the formatter does the work for
    no tokens, and the single dispatch this run makes is asserted so that a
    cleanup which somehow reached a model would fail here rather than look like
    a success.

    The exit code is what proves the caller honoured :attr:`Cleanup.regate`
    rather than :attr:`Cleanup.accepted`. Behind a format rejection the gate
    stopped before its acceptance rung, so ``accepted`` is ``False`` and stays
    ``False``; only a gate re-run over the rewritten bytes can reach 0.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, TIDYING)
    sent = _answers(monkeypatch, _fenced(MESSY))

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    assert code == 0
    assert len(sent) == 1, f"a model was asked {len(sent)} times about whitespace"
    assert (repo / TARGET).read_text(encoding="utf-8") == TIDIED


def test_the_bytes_that_were_delivered_are_the_bytes_that_were_re_gated(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What lands is the rewritten file, never the one the worker actually sent.

    Split from the test above because the two fail differently and the failure
    modes are the interesting part. A caller that re-gated and then delivered the
    binding it was already holding would commit ``MESSY``; a caller that
    delivered the cleaned string without re-gating would commit ``TIDIED`` under
    a verdict about ``MESSY``. Only the first of those is visible in the
    repository, so it is asserted there, and the second is what the exit code
    above rules out.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, TIDYING)
    _answers(monkeypatch, _fenced(MESSY))

    main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    landed = (repo / TARGET).read_text(encoding="utf-8")
    assert landed != MESSY, "the file the worker sent was committed unrewritten"
    assert landed == TIDIED


def test_enabling_the_cleanup_does_not_rescue_a_wrong_answer(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Style is repaired; a wrong answer is rejected, and the knob does not blur that.

    The reply is misformatted *and* wrong — it never names RETRY, so the
    acceptance command fails — and no fixer answers that. The tools may tidy
    the sandbox copy on the way to the second verdict; the repository must
    come back untouched and the run must fail.

    Asserted through the repository because that is where the damage would be:
    the run must fail and write nothing, not tidy its way to a commit. The
    dispatch is counted alongside, because "failed and wrote nothing" is also
    what an install that could not read its own config does, and the two must
    not be the same passing test.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, TIDYING)
    before = (repo / TARGET).read_bytes()
    sent = _answers(monkeypatch, _fenced(MESSY_AND_BROKEN))

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    assert code == 1
    assert len(sent) == 1, "the rung was never asked, so nothing was cleaned or not"
    assert (repo / TARGET).read_bytes() == before


def test_an_install_that_turned_the_cleanup_off_is_not_tidied(
    repo: Path, contract: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The knob is off, and off means the formatter is never reached.

    ``tidy`` rewrites a change after the gate has spoken about it, which is a
    rewrite of somebody's file on a verdict they cannot see. Since 2026-09-05
    that is the default (owner: the formatter after a rung is the point), so
    the install that does not want it says so — and having said so, gets the
    rejection the gate reached and no fourth party touching the bytes.

    Spying rather than inferring: the format-only rejection already failed the
    run before this lever existed, so an assertion on the exit code alone would
    have passed against no caller at all.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, NOT_TIDYING)
    seen = _tidies_seen(monkeypatch)
    _answers(monkeypatch, _fenced(MESSY))

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    assert code == 1
    assert seen == [], f"an unconfigured install reformatted {seen}"
    assert (repo / TARGET).read_text(encoding="utf-8") == BASE


# --------------------------------------------------------------------------
# 4 · `reviewer_for` is reachable from `mcgyvr run`
# --------------------------------------------------------------------------
#
# The fourth lever of the same shape as the three above, found by wiring them:
# `worker_attempt` took a `verifier` and `mcgyvr run` passed `None`, so every
# ladder acceptance was labelled `unverified` even on an install with
# `verifier.enabled: true` and a bound role — and `verify.reviewer_for`, which
# exists to be that argument, had no caller at all.
#
# Wiring it contradicted the signature the same way wiring `best_of` did. A
# `Callable[[], Review]` cannot be built by a caller standing outside the
# attempt: `verify` needs the gate that just ran, the bytes it read and the
# model that wrote them, and none of those exist yet where the old parameter
# had to be supplied. What crosses the seam is the reviewer itself.

VERIFYING = (
    LADDER
    + """
verifier:
  enabled: true
  source: workstation
  model: qwen2.5-coder:14b
"""
)

#: The same install with the rung allowed a second attempt, so a refusal has
#: somewhere to go. The default of 1 is escalate-rather-than-retry, and what is
#: being asserted below is what the *next attempt on this rung* is told.
VERIFYING_TWICE = VERIFYING.replace(
    "      model: qwen2.5-coder:7b\n",
    "      model: qwen2.5-coder:7b\n      attempts: 2\n",
)

#: Verification asked for and bound to a source that cannot authenticate. The
#: ladder is untouched — the rung still runs — so the only thing wrong with this
#: install is the verifier, which is what makes the refusal legible.
VERIFIER_UNUSABLE = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 2
  hosted:
    base_url: https://api.example.invalid
    api: openai
    max_parallel: 1
    api_key_env: MCGYVR_TEST_KEY_THAT_IS_NOT_SET
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
verifier:
  enabled: true
  source: hosted
  model: big-model
"""


def _reviews(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer each *reviewer* dispatch from a script; return the prompts sent.

    Patched at :func:`mcgyvr.verify.dispatch_role`, one seam below
    :func:`~mcgyvr.verify.reviewer_for`, so the role lookup, the independence
    check and the verdict parser all run for real. An empty script is the
    assertion that no reviewer was asked, and it fails loudly rather than
    returning a default: a verifier that was asked when it should not have been
    is spend, and spend is the thing the ordering in ``judge`` exists to prevent.
    """
    import mcgyvr.verify as verify

    asked: list[str] = []
    scripted = list(replies)

    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        asked.append(request.prompt)
        if not scripted:
            raise AssertionError(f"an unscripted dispatch was made to {role!r}")
        return _completion(scripted.pop(0))

    monkeypatch.setattr(verify, "dispatch_role", fake_dispatch_role)
    return asked


def test_a_bound_verifier_is_asked_and_the_acceptance_is_labelled_verified(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The label an operator reads is the difference this lever makes.

    ``unverified`` and ``verified`` are the same delivery with different
    warrants, and before this the second was unreachable from the command line
    however the install was configured. The reviewer's prompt is asserted too,
    because a review of the wrong bytes would print the same word: what it has
    to carry is the change as applied, not the reply the worker sent.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, VERIFYING)
    written = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"
    _answers(monkeypatch, _fenced(written))
    reviewed = _reviews(monkeypatch, "APPROVE — the retry budget is stated and named.")

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "(verified)" in out, (
        f"the acceptance was not labelled verified on an install with a bound "
        f"verifier, so `reviewer_for` was still not reached.\noutput: {out}"
    )
    assert len(reviewed) == 1, f"the reviewer was asked {len(reviewed)} time(s)"
    assert written in reviewed[0], (
        f"the reviewer was not shown the change as applied.\nprompt: {reviewed[0]}"
    )
    assert f"ORIGINAL FILE before the change ({TARGET})" in reviewed[0], (
        f"the reviewer was told the original was not supplied, on an edit to a "
        f"file that is committed in the repository.\nprompt: {reviewed[0]}"
    )
    assert BASE in reviewed[0], (
        f"the original block did not carry the file the change replaced.\n"
        f"prompt: {reviewed[0]}"
    )


def test_a_reviewer_that_refuses_costs_the_attempt_and_tells_the_next_one_why(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A gate that passed and a reviewer that did not is a failed attempt.

    The half that matters beyond the verdict is the note: ``judge`` builds the
    retry note out of the reviewer's own words, and this is the first run in
    which a worker can be told them. Attempt 2's prompt has to carry the
    remediation, and the acceptance that follows has to be verified — a second
    attempt accepted as ``unverified`` would mean the reviewer refused and was
    then never asked again.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, VERIFYING_TWICE)
    first = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"
    second = "RETRY = 3\n\n\ndef fetch(url, retries=RETRY):\n    return url\n"
    sent = _answers(monkeypatch, _fenced(first), _fenced(second))
    reviewed = _reviews(
        monkeypatch,
        "REMEDIATE: RETRY is declared and never used by fetch.",
        "APPROVE_WITH_NOTES: the budget is now applied at the call site.",
    )

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    assert code == 0
    assert len(sent) == 2, f"the rung was asked {len(sent)} time(s), not two"
    assert len(reviewed) == 2, f"the reviewer was asked {len(reviewed)} time(s)"
    assert "RETRY is declared and never used" in sent[1], (
        f"attempt 2 was not told what the reviewer refused over, so the refusal "
        f"cost an attempt and bought nothing.\nprompt: {sent[1]}"
    )
    assert "(verified)" in capsys.readouterr().out


def test_an_install_that_did_not_enable_verification_asks_no_reviewer(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The keyless install is unchanged, and that is the control on the other two.

    ``verifier.enabled`` defaults to false and this ladder never mentions it, so
    the acceptance is labelled ``unverified`` and nothing is dispatched to a
    role. Without this, "the verifier is wired" and "the verifier is always
    asked" would look the same from outside.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path)
    _answers(monkeypatch, _fenced("RETRY = 3\n\n\ndef fetch(url):\n    return url\n"))
    reviewed = _reviews(monkeypatch)

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    assert code == 0
    assert reviewed == [], "a role was dispatched to on an install with no verifier"
    assert "(unverified)" in capsys.readouterr().out


def test_verification_asked_for_and_unusable_is_refused_before_the_sandbox(
    repo: Path,
    contract: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An install told to verify that cannot is stopped, not quietly downgraded.

    ``source_map`` reports a role declared on an unusable source by raising when
    it is asked, which is the distinction that matters here: "no verifier" is an
    ordinary install and "the verifier is misconfigured" is a task that would
    deliver work on a warrant the operator asked for and did not get. It is
    refused before the sandbox is opened, where refusing still costs nothing.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, VERIFIER_UNUSABLE)
    _answers(monkeypatch)
    _reviews(monkeypatch)

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    assert code == 1
    err = capsys.readouterr().err
    assert "verifier.enabled: false" in err, (
        f"the refusal did not name the way out of it.\nstderr: {err}"
    )


#: A target that is not in the repository, so the change creates it. The other
#: half of the original block: `""` and `None` are different absences, and only
#: one of them is "there is nothing to show".
NEW_FILE = "src/pkg/backoff.py"

NEW_FILE_CONTRACT = f"""
id: backoff
task_type: function_implementation
task: Add a backoff helper in its own module.
target: {NEW_FILE}
stop_conditions: ["The backoff curve is not stated."]
acceptance: ["sh -c 'grep -q backoff {NEW_FILE}'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def test_a_change_that_creates_a_file_says_so_rather_than_saying_nothing(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent original is stated as an absence with a reason.

    ``_original_block`` already distinguishes the two: ``""`` is a change that
    creates a file and ``None`` is a caller that supplied nothing. Reading the
    workspace is what makes the first one reachable — before this, every run
    took the second branch, and a reviewer judging a new module was told the
    original "was not supplied" as though something had been withheld.
    """
    from mcgyvr.cli import main

    config = _config(tmp_path, VERIFYING)
    contract = tmp_path / "backoff.yaml"
    contract.write_text(NEW_FILE_CONTRACT, encoding="utf-8")
    _answers(monkeypatch, _fenced("def backoff(attempt):\n    return 2**attempt\n"))
    reviewed = _reviews(monkeypatch, "APPROVE the module is new and self-contained.")

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
        ]
    )

    assert code == 0
    assert "ORIGINAL FILE: none — the change creates a new file." in reviewed[0], (
        f"a created file was reported as an original nobody supplied.\n"
        f"prompt: {reviewed[0]}"
    )
