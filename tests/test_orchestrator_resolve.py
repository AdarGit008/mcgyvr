"""The resolver is the deterministic bridge between a phrase and a shortlist, so
these tests hold it to the three things #48 makes acceptance criteria — common
phrasings land on the right files, the shortlist is bounded, and genuine
ambiguity is *reported* rather than guessed — plus the ranking properties that
make those hold on a real repository: a named symbol beats a fragment of a long
name, a rare word outweighs a common one, and a test file does not crowd out the
implementation it exercises.

Resolutions are exercised through :func:`resolve` against small built repos, so
the assertions are about outcomes a caller sees, not the scoring internals.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.resolve import Verdict, _fold, _tokenize, resolve


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def build(tmp_path: Path, files: dict[str, str]) -> Index:
    """Init a git repo with ``files`` and return its built index."""
    repo = tmp_path
    git(repo, "init", "-q", "-b", "main")
    for rel, body in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return build_index(repo)


# --- the phrase names the thing: whole-query resolution --------------------


def test_a_phrasing_resolves_to_the_symbol_it_names(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {
            "src/net.py": "def fetch_helper(url):\n    return url\n",
            "src/math.py": "def add(a, b):\n    return a + b\n",
        },
    )
    result = resolve(index, "the fetch helper")
    assert result.verdict is Verdict.RESOLVED
    assert result.best is not None
    assert result.best.path == "src/net.py"
    # The evidence says *why* — it named the definition, not merely brushed it.
    assert any("fetch_helper" in reason for reason in result.best.evidence)


def test_an_exact_symbol_name_resolves(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {
            "src/repo.py": "class AttachedRepo:\n    pass\n",
            "src/other.py": "x = 1\n",
        },
    )
    result = resolve(index, "AttachedRepo")
    assert result.verdict is Verdict.RESOLVED
    assert result.best is not None
    assert result.best.path == "src/repo.py"


def test_an_explicit_path_is_taken_literally(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {
            "src/mcgyvr/scope.py": "def in_scope():\n    return True\n",
            "a.py": "y = 2\n",
        },
    )
    result = resolve(index, "src/mcgyvr/scope.py")
    assert result.verdict is Verdict.RESOLVED
    assert result.best is not None
    assert result.best.path == "src/mcgyvr/scope.py"


def test_a_filename_resolves_without_a_symbol(tmp_path: Path) -> None:
    index = build(tmp_path, {"config.py": "SETTING = 1\n", "main.py": "z = 3\n"})
    result = resolve(index, "config")
    assert result.best is not None
    assert result.best.path == "config.py"


# --- the shortlist is bounded ----------------------------------------------


def test_the_shortlist_is_bounded(tmp_path: Path) -> None:
    files = {f"mod{n}/handler.py": "def handle():\n    pass\n" for n in range(20)}
    index = build(tmp_path, files)
    result = resolve(index, "handler", limit=5)
    assert len(result.candidates) <= 5


def test_limit_zero_yields_no_candidates(tmp_path: Path) -> None:
    index = build(tmp_path, {"a.py": "def handle():\n    pass\n"})
    result = resolve(index, "handle", limit=0)
    assert result.candidates == ()
    assert result.verdict is Verdict.EMPTY


# --- ambiguity is reported, not guessed ------------------------------------


def test_a_genuine_tie_is_reported_ambiguous(tmp_path: Path) -> None:
    # Two files define the very same name: nothing distinguishes them, so the
    # resolver must decline to promote one to "the answer".
    index = build(
        tmp_path,
        {
            "pkg_a/client.py": "def send():\n    pass\n",
            "pkg_b/client.py": "def send():\n    pass\n",
        },
    )
    result = resolve(index, "send")
    assert result.verdict is Verdict.AMBIGUOUS
    # ...but the contenders are still returned for the reader to choose between.
    assert len(result.candidates) >= 2
    assert {c.path for c in result.candidates} == {"pkg_a/client.py", "pkg_b/client.py"}


def test_no_match_is_an_empty_resolution(tmp_path: Path) -> None:
    index = build(tmp_path, {"a.py": "def alpha():\n    pass\n"})
    result = resolve(index, "nonexistent zzz target")
    assert result.verdict is Verdict.EMPTY
    assert result.candidates == ()
    assert result.best is None


# --- ranking properties on a realistic mix ---------------------------------


def test_a_named_symbol_outranks_a_fragment_of_a_long_name(tmp_path: Path) -> None:
    # 'attach' is the whole of one name and a sliver of the other; specificity,
    # not mere presence, must decide the order.
    index = build(
        tmp_path,
        {
            "src/repo.py": "def attach():\n    pass\n",
            "src/util.py": "def attach_and_reconcile_everything_now():\n    pass\n",
        },
    )
    result = resolve(index, "attach")
    assert result.best is not None
    assert result.best.path == "src/repo.py"


def test_a_rare_word_outweighs_a_common_one(tmp_path: Path) -> None:
    # 'client' is everywhere and 'telemetry' is rare; the file carrying the rare
    # word is the one meant, even though both files match 'client'.
    files = {f"pkg{n}/client.py": "class Client:\n    pass\n" for n in range(6)}
    files["obs/client.py"] = "class Client:\n    pass\n\nclass Telemetry:\n    pass\n"
    index = build(tmp_path, files)
    result = resolve(index, "telemetry client")
    assert result.best is not None
    assert result.best.path == "obs/client.py"


def test_a_test_file_does_not_outrank_the_source_it_shadows(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {
            "src/adapter.py": "class Adapter:\n    pass\n",
            "tests/test_adapter.py": "ADAPTER = 1\n\ndef test_adapter():\n    pass\n",
        },
    )
    result = resolve(index, "the adapter")
    assert result.best is not None
    assert result.best.path == "src/adapter.py"
    # The test is demoted, not excluded — it still appears for the reader.
    assert "tests/test_adapter.py" in {c.path for c in result.candidates}


def test_a_test_is_reachable_when_the_query_asks_for_it(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {
            "src/adapter.py": "class Adapter:\n    pass\n",
            "tests/test_adapter.py": "def test_adapter_owns_files():\n    pass\n",
        },
    )
    result = resolve(index, "the adapter test")
    assert "tests/test_adapter.py" in {c.path for c in result.candidates}


# --- degradations and edges ------------------------------------------------


def test_a_plural_query_reaches_a_singular_name_and_the_reverse(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {"src/secrets.py": "def scan_secret():\n    pass\n", "src/misc.py": "q = 1\n"},
    )
    singular = resolve(index, "secret").best
    plural = resolve(index, "secrets").best
    assert singular is not None and singular.path == "src/secrets.py"
    assert plural is not None and plural.path == "src/secrets.py"


def test_an_all_stopword_query_matches_nothing(tmp_path: Path) -> None:
    index = build(tmp_path, {"a.py": "def real():\n    pass\n"})
    result = resolve(index, "the function that is a helper")
    assert result.verdict is Verdict.EMPTY


def test_candidates_are_ordered_and_scored(tmp_path: Path) -> None:
    index = build(
        tmp_path,
        {"src/fetcher.py": "def fetch():\n    pass\n", "notes/fetch.md": "fetch\n"},
    )
    result = resolve(index, "fetch")
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(c.evidence for c in result.candidates)


# --- the pieces that make the ranking legible ------------------------------


def test_tokenizer_splits_camel_and_snake_and_folds_plurals() -> None:
    assert _tokenize("fetchHelper") == ["fetch", "helper"]
    assert _tokenize("scan_secrets") == ["scan", "secret"]
    assert _tokenize("HTTPClient") == ["http", "client"]


def test_plural_fold_is_conservative() -> None:
    assert _fold("secrets") == "secret"
    assert _fold("class") == "class"  # an 'ss' ending is left exact
    assert _fold("is") == "is"  # too short to fold
