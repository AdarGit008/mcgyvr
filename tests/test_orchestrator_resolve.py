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

import pytest

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


@pytest.mark.parametrize(
    ("defining", "source", "other"),
    [
        (
            "internal/a.go",
            "package internal\n\nfunc RenderReport() {}\n",
            "internal/b.go",
        ),
        ("src/a.rs", "pub fn render_report() {}\n", "src/b.rs"),
        (
            "src/A.java",
            "class A {\n  void renderReport() {}\n}\n",
            "src/B.java",
        ),
    ],
)
def test_a_go_rust_or_java_definition_resolves_by_its_symbol(
    tmp_path: Path, defining: str, source: str, other: str
) -> None:
    """The phrase names neither file's path, so only the extracted symbol can
    pick the file that defines it."""
    index = build(tmp_path, {defining: source, other: source.replace("ender", "ead")})
    result = resolve(index, "the render report helper")
    assert result.verdict is Verdict.RESOLVED
    assert result.best is not None
    assert result.best.path == defining


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


def test_a_digit_bearing_symbol_name_resolves_from_prose(tmp_path: Path) -> None:
    # `b64decode` shreds to `b` + `64` + `decode`, and the `b` and `64` parts
    # are dropped as noise, leaving only the generic `decode` — while `strict`
    # matches a `STRICT` export in another file. The digit-bearing prefix must
    # survive so prose naming `b64decode` lands on the file that defines it.
    index = build(
        tmp_path,
        {
            "Lib/base64.py": "def b64decode(s):\n    return s\n",
            "Lib/enum.py": (
                "__all__ = ['STRICT', 'CONFORM']\n"
                "from enum import auto\n"
                "class FlagBoundary:\n"
                "    STRICT = auto()\n"
                "    CONFORM = auto()\n"
            ),
        },
    )
    result = resolve(index, "add a strict mode to b64decode that raises")
    assert result.verdict is Verdict.RESOLVED
    assert result.best is not None
    assert result.best.path == "Lib/base64.py"


def test_a_bare_symbol_name_prefers_the_defining_file_over_a_reexport(
    tmp_path: Path,
) -> None:
    # `createEntityAdapter` is defined in one module and re-exported from the
    # package's index barrel alongside many other names. Naming the symbol
    # outright must land on the definition, not the aggregator.
    index = build(
        tmp_path,
        {
            "src/entities/create_adapter.js": (
                "export function createEntityAdapter() {\n  return {};\n}\n"
            ),
            "src/index.js": (
                "export { createEntityAdapter } from './entities/create_adapter.js';\n"
                "export { createSlice } from './createSlice.js';\n"
                "export { createAsyncThunk } from './createAsyncThunk.js';\n"
            ),
            "src/createSlice.js": "export function createSlice() {\n  return {};\n}\n",
            "src/createAsyncThunk.js": (
                "export function createAsyncThunk() {\n  return {};\n}\n"
            ),
        },
    )
    result = resolve(index, "createEntityAdapter")
    assert result.verdict is Verdict.RESOLVED
    assert result.best is not None
    assert result.best.path == "src/entities/create_adapter.js"


def test_a_symbol_whose_name_starts_with_a_stopword_still_resolves(
    tmp_path: Path,
) -> None:
    # "from" and "is" are stopwords, but they are also the leading token of
    # real symbol names (fromRawHeaders, isRedirect). Naming a symbol outright
    # must match on the full name, so the whole-query pass may not strip a
    # stopword that is part of the symbol's own name.
    index = build(
        tmp_path,
        {
            "src/a.js": (
                "export function fromRawHeaders(headers = []) {\n  return headers;\n}\n"
            ),
            "src/b.js": (
                "export function rawHeaders(headers = []) {\n  return headers;\n}\n"
            ),
            "src/c.js": (
                "export const isRedirect = (code) => code >= 300 && code < 400;\n"
            ),
            "src/d.js": "export const redirectTo = (url) => url;\n",
        },
    )
    for name, path in (("fromRawHeaders", "src/a.js"), ("isRedirect", "src/c.js")):
        result = resolve(index, name)
        assert result.verdict is Verdict.RESOLVED, name
        assert result.best is not None
        assert result.best.path == path, name


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


# --- a query naming a compound that does not exist must not resolve ---------


def test_a_compound_name_that_does_not_exist_does_not_resolve(tmp_path: Path) -> None:
    # "persistInterval" is one camelCase name, not two words; the index has
    # "persist" and "interval" separately, but not the compound, so the query
    # named something that does not exist and must not resolve on the parts.
    index = build(
        tmp_path,
        {
            "index.js": "function persist() {}\nfunction interval() {}\n",
            "cli.js": "module.exports = ora;\n",
        },
    )
    result = resolve(index, "how do I set persistInterval")
    assert result.verdict is Verdict.EMPTY
    assert result.candidates == ()
    assert result.best is None


def test_a_single_generic_directory_word_is_not_a_signal(tmp_path: Path) -> None:
    # The subject (OSC/hyperlink) is absent; only the generic word "support"
    # matches, and it matches many files through a "supports-color" directory.
    # One incidental common word must not stand in for the subject.
    index = build(
        tmp_path,
        {
            f"mod{n}/supports-color/index.js": f"function marker{n}() {{}}\n"
            for n in range(4)
        },
    )
    result = resolve(index, "where is the OSC hyperlink support implemented")
    assert result.verdict is Verdict.EMPTY
    assert result.candidates == ()
    assert result.best is None


def test_a_single_generic_class_word_is_not_a_signal(tmp_path: Path) -> None:
    # The subject (schema) is absent; only the generic word "document" matches,
    # and it matches a Document class and a docs variable rather than the asked
    # subject. One incidental common word must not stand in for the subject.
    index = build(
        tmp_path,
        {
            "db/table.py": "class Document:\n    pass\n",
            "db/storage.py": "class CustomDocument:\n    pass\n",
            "docs/conf.py": "latex_documents = 1\n",
        },
    )
    result = resolve(index, "where do I define a schema to validate document fields")
    assert result.verdict is Verdict.EMPTY
    assert result.candidates == ()
    assert result.best is None


def test_a_central_api_name_is_a_signal_even_when_it_reaches_many_files(
    tmp_path: Path,
) -> None:
    # "curry" is an exact whole-name symbol (a definition) that also appears as
    # the stem of several sibling files, so it reaches many files. That does not
    # make it generic: naming a central API symbol outright is a confident
    # answer, unlike a single incidental common word such as "document".
    files = {"toolz/functoolz.py": "def curry(f):\n    pass\n"}
    for n in range(6):
        files[f"toolz/curry{n}.py"] = "pass\n"
    index = build(tmp_path, files)
    result = resolve(index, "where is the curry decorator class")
    assert result.verdict is not Verdict.EMPTY
    assert result.best is not None
    assert result.best.path == "toolz/functoolz.py"


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


def test_tokenizer_keeps_a_digit_bearing_name_whole() -> None:
    # `b64decode` splits to `b`, `64` and `decode`, and `b` (single letter) and
    # `64` (bare number) are dropped as noise, leaving only the generic
    # `decode`. The whole digit-bearing run must survive as its own token so the
    # distinctive prefix is not lost.
    assert "b64decode" in _tokenize("b64decode")
    assert "a2b" in _tokenize("a2b_base64")
    assert "base64" in _tokenize("a2b_base64")


def test_plural_fold_is_conservative() -> None:
    assert _fold("secrets") == "secret"
    assert _fold("class") == "class"  # an 'ss' ending is left exact
    assert _fold("is") == "is"  # too short to fold


@pytest.mark.xfail(
    reason=(
        "known limitation: resolve does not identify a prose query's semantic subject"
    ),
    strict=True,
)
def test_a_prose_query_naming_an_absent_subject_is_empty(tmp_path: Path) -> None:
    tasks_source = "class Task:\n    pass\nDEFAULT_TASK_QUEUE_NAME = 'default'\n"
    index = build(
        tmp_path,
        {
            "django/tasks.py": tasks_source,
            "django/queue.py": "QUEUE = 'default'\n",
        },
    )
    result = resolve(
        index, "Which module integrates Django with the Celery task queue?"
    )
    assert result.verdict is Verdict.EMPTY
    assert result.best is None
