"""A `unified_diff` reply is applied onto the content the model was shown.

Under ``output_schema: unified_diff`` a reply is one fenced block holding a
unified diff of the contract's target, and nothing else. It is read strictly —
the target on both sides, at least one hunk, hunk lines only — then applied by
``git apply`` onto the target's content as the prompt showed it, in a scratch
directory of its own, and what comes back is the whole resulting file: the
``ParsedFile`` a ``whole_file`` reply would have produced for the same change.

Every way a diff can be wrong is a named ``ReplyError``, which the attempt turns
into a failed draw and the next try's note, as it does for a malformed
whole-file reply: a diff that names another file, a second file, a deletion, a
rename, a mode change or a binary patch is refused before anything is applied,
and one whose context does not match the base is refused with git's own reason.
Nothing here raises except a caller that gives no base to apply onto.

Every fixture is constructed, as in ``test_worker_reply.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.runner import StopReason
from mcgyvr.worker.reply import (
    ParsedDiff,
    ParsedFile,
    ReplyError,
    parse_diff,
    parse_pinned,
    parse_reply,
)

TARGET = "src/pkg/value.py"

BASE = 'def name() -> str:\n    return "value"\n\n\nVALUE = 0\n'

#: Two blank context lines (one space each), then the change.
HUNK = "@@ -3,3 +3,3 @@\n \n \n-VALUE = 0\n+VALUE = 1\n"

#: The base with the one change every good diff below makes.
CHANGED = 'def name() -> str:\n    return "value"\n\n\nVALUE = 1\n'


def _fence(body: str, info: str = "diff") -> str:
    return f"Here is the change.\n\n```{info}\n{body}```\n"


GOOD = _fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}")


def applied(text: str, base: str = BASE, target: str = TARGET) -> ParsedFile:
    result = parse_reply(text, output_schema="unified_diff", target=target, base=base)
    assert isinstance(result, ParsedFile), result
    return result


def refused(text: str, base: str = BASE, **kwargs: object) -> ReplyError:
    result = parse_reply(
        text,
        output_schema="unified_diff",
        target=TARGET,
        base=base,
        **kwargs,  # type: ignore[arg-type]
    )
    assert isinstance(result, ReplyError), result
    return result


# --- the shapes that apply ---------------------------------------------------


def test_one_fenced_diff_becomes_the_whole_changed_file() -> None:
    file = applied(GOOD)
    assert file.content == CHANGED
    assert file.info_string == "diff"


def test_the_result_is_the_file_a_whole_file_reply_would_have_written() -> None:
    """The two schemas meet at the same `ParsedFile`, so the gate and delivery
    after them cannot tell which one the model answered in."""
    whole = parse_reply(f"```python\n{CHANGED}```\n", target=TARGET)
    assert isinstance(whole, ParsedFile)
    assert applied(GOOD).content == whole.content


def test_paths_without_git_prefixes_and_with_timestamps_apply() -> None:
    """`diff -u` writes bare paths and a tab-separated timestamp."""
    body = (
        f"--- {TARGET}\t2026-01-01 00:00:00\n+++ {TARGET}\t2026-01-01 00:00:01\n{HUNK}"
    )
    assert applied(_fence(body)).content == CHANGED


def test_gits_own_header_lines_are_accepted() -> None:
    body = (
        f"diff --git a/{TARGET} b/{TARGET}\nindex 1111111..2222222 100644\n"
        f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}"
    )
    assert applied(_fence(body)).content == CHANGED


def test_a_miscounted_hunk_header_still_applies_when_the_lines_match() -> None:
    """Models miscount more often than they miscopy: the counts are recounted,
    the context is not loosened."""
    body = f"--- a/{TARGET}\n+++ b/{TARGET}\n" + HUNK.replace("-3,3 +3,3", "-3,7 +3,2")
    assert applied(_fence(body)).content == CHANGED


def test_a_context_line_whose_space_was_stripped_still_matches() -> None:
    """An empty line inside a hunk is an empty context line, as git reads it."""
    hunk = "@@ -3,3 +3,3 @@\n\n\n-VALUE = 0\n+VALUE = 1\n"
    assert applied(_fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n{hunk}")).content == (
        CHANGED
    )


def test_blank_lines_before_the_closing_fence_are_not_context() -> None:
    assert applied(_fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}\n\n")).content == (
        CHANGED
    )


def test_two_hunks_apply_together() -> None:
    hunks = (
        "@@ -1,2 +1,2 @@\n-def name() -> str:\n+def label() -> str:\n"
        '     return "value"\n'
        "@@ -5 +5 @@\n-VALUE = 0\n+VALUE = 1\n"
    )
    file = applied(_fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n{hunks}"))
    assert file.content == CHANGED.replace("def name", "def label")


def test_a_new_file_is_created_from_dev_null() -> None:
    body = f"--- /dev/null\n+++ b/{TARGET}\n@@ -0,0 +1,2 @@\n+X = 1\n+Y = 2\n"
    assert applied(_fence(body), base="").content == "X = 1\nY = 2\n"


def test_a_base_with_no_final_newline_is_diffed_as_the_prompt_shows_it() -> None:
    """The prompt closes the shown content with a newline, so the diff the model
    reads off it applies; the result ends in one, as a whole-file reply does."""
    assert applied(GOOD, base=BASE.rstrip("\n")).content == CHANGED


def test_bytes_that_are_not_utf8_round_trip() -> None:
    base = BASE.replace('"value"', '"caf\udce9"')
    assert applied(GOOD, base=base).content == CHANGED.replace('"value"', '"caf\udce9"')


def test_the_scratch_directory_is_not_mistaken_for_a_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the temporary directory inside someone's repository, git must not
    climb into it: the diff still applies, and the repository is untouched."""
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    scratch = outer / "tmp"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", None)

    assert applied(GOOD).content == CHANGED
    status = subprocess.run(
        ["git", "-C", str(outer), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


# --- malformed ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "code"),
    [
        ("Sure, I would change VALUE to 1.", "no-fenced-block"),
        (GOOD + GOOD, "ambiguous-blocks"),
        (f"```diff\n--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}", "unterminated-fence"),
        ("```diff\n\n```\n", "empty-block"),
        (
            _fence(f"Change VALUE:\n--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}"),
            "malformed-diff",
        ),
        (_fence(f"--- a/{TARGET}\n{HUNK}"), "malformed-diff"),
        (_fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n"), "malformed-diff"),
        (
            _fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n-VALUE = 0\n+VALUE = 1\n"),
            "malformed-diff",
        ),
        (
            _fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}and that is all\n"),
            "malformed-diff",
        ),
    ],
    ids=[
        "prose",
        "two-blocks",
        "unclosed",
        "empty",
        "prose-in-block",
        "no-new-side",
        "no-hunk",
        "no-hunk-header",
        "prose-after-hunk",
    ],
)
def test_a_reply_that_is_not_one_clean_diff_is_named(reply: str, code: str) -> None:
    assert refused(reply).code == code


def test_a_truncated_diff_is_incomplete_before_it_is_read() -> None:
    error = refused(GOOD, stop_reason=StopReason.TRUNCATED)
    assert error.code == "incomplete-reply"


def test_a_malformed_line_is_named_by_number() -> None:
    error = refused(_fence(f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}and that is all\n"))
    assert "line 8" in error.message
    assert "'and that is all'" in error.message


# --- outside the contract ----------------------------------------------------


def test_a_diff_of_another_file_is_outside_the_contract() -> None:
    other = GOOD.replace(TARGET, "src/pkg/other.py")
    error = refused(other)
    assert error.code == "diff-outside-contract"
    assert "src/pkg/other.py" in error.message
    assert TARGET in error.message


def test_a_diff_whose_new_side_names_another_file_is_outside_the_contract() -> None:
    body = f"--- a/{TARGET}\n+++ b/src/pkg/other.py\n{HUNK}"
    assert refused(_fence(body)).code == "diff-outside-contract"


def test_a_path_that_climbs_out_of_the_tree_is_outside_the_contract() -> None:
    body = f"--- a/../{TARGET}\n+++ b/../{TARGET}\n{HUNK}"
    assert refused(_fence(body)).code == "diff-outside-contract"


def test_a_second_file_is_refused_even_when_the_first_is_the_target() -> None:
    second = f"--- a/src/pkg/other.py\n+++ b/src/pkg/other.py\n{HUNK}"
    body = f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}{second}"
    error = refused(_fence(body))
    assert error.code == "diff-many-files"


def test_a_second_git_header_is_a_second_file() -> None:
    body = f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}diff --git a/x b/x\n"
    assert refused(_fence(body)).code == "diff-many-files"


@pytest.mark.parametrize(
    "header",
    [
        "deleted file mode 100644",
        "rename from src/pkg/old.py",
        "copy from src/pkg/old.py",
        "similarity index 90%",
        "old mode 100644",
        "new mode 100755",
        "GIT binary patch",
        f"Binary files a/{TARGET} and b/{TARGET} differ",
    ],
)
def test_a_diff_that_is_not_an_edit_of_lines_is_refused(header: str) -> None:
    git = f"diff --git a/{TARGET} b/{TARGET}\n{header}\n"
    body = f"{git}--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}"
    assert refused(_fence(body)).code == "diff-not-a-text-edit"


def test_a_deletion_is_refused() -> None:
    body = f"--- a/{TARGET}\n+++ /dev/null\n@@ -1,5 +0,0 @@\n" + "".join(
        f"-{line}\n" for line in BASE.splitlines()
    )
    error = refused(_fence(body))
    assert error.code == "diff-not-a-text-edit"
    assert "deletes" in error.message


# --- context that does not match ---------------------------------------------


def test_a_diff_whose_context_does_not_match_is_a_reply_failure() -> None:
    """Not a crash: git's own reason, naming the line, is what the next
    attempt is told."""
    wrong = GOOD.replace("-VALUE = 0", "-VALUE = 2")
    error = refused(wrong)
    assert error.code == "diff-does-not-apply"
    assert f"{TARGET}:3" in error.message
    assert "mcgyvr-diff-" not in error.message  # no scratch path leaks


def test_whitespace_in_context_must_match() -> None:
    """No leniency: an indentation the file does not have is a mismatch."""
    wrong = GOOD.replace("-VALUE = 0", "-    VALUE = 0")
    assert refused(wrong).code == "diff-does-not-apply"


def test_a_new_file_diff_onto_an_existing_target_does_not_apply() -> None:
    body = f"--- /dev/null\n+++ b/{TARGET}\n@@ -0,0 +1 @@\n+X = 1\n"
    assert refused(_fence(body)).code == "diff-does-not-apply"


def test_a_diff_onto_a_target_that_does_not_exist_does_not_apply() -> None:
    assert refused(GOOD, base="").code == "diff-does-not-apply"


# --- refusals, and what the parser needs ---------------------------------------


def test_a_diff_that_leaves_no_code_is_a_refusal() -> None:
    """The result is judged as a whole-file block is: a diff that replaces the
    code with a comment is a refusal dressed as the target."""
    body = (
        f"--- a/{TARGET}\n+++ b/{TARGET}\n@@ -1,5 +1 @@\n"
        + "".join(f"-{line}\n" for line in BASE.splitlines())
        + "+# I cannot do this without the retry policy.\n"
    )
    assert refused(_fence(body)).code == "refusal"


def test_a_diff_reply_needs_its_target_and_base() -> None:
    with pytest.raises(ValueError, match="base content"):
        parse_reply(GOOD, output_schema="unified_diff", target=TARGET)
    with pytest.raises(ValueError, match="base content"):
        parse_reply(GOOD, output_schema="unified_diff", base=BASE)


def test_a_pinned_schema_never_carries_a_diff() -> None:
    result = parse_pinned(
        GOOD,
        response_schema={"type": "object"},
        output_schema="unified_diff",
        target=TARGET,
    )
    assert isinstance(result, ReplyError)
    assert result.code == "unsupported-schema"


def test_the_patch_git_applies_names_the_target_and_nothing_the_model_wrote() -> None:
    """The header is rebuilt, so a prefix or timestamp the model chose never
    reaches git."""
    diff = parse_diff(f"--- {TARGET}\t2026\n+++ {TARGET}\t2026\n{HUNK}", target=TARGET)
    assert isinstance(diff, ParsedDiff)
    assert diff.patch == f"--- a/{TARGET}\n+++ b/{TARGET}\n{HUNK}"
    assert not diff.creates
