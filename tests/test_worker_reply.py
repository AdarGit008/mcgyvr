"""The single-file output protocol, tested mostly on replies that are wrong.

A parser that only ever sees well-formed input is not the thing standing
between a model's prose and a source file. **Every fixture in this file is
constructed**: an author imagining an apology before the code, two blocks
because the model offered an alternative, a fence the cap cut off — and each
must resolve to a *named* failure rather than to a plausible file. An earlier
docstring called these "real shapes a local worker produces"; nothing linked
any fixture to a run, so under this repository's own filter the claim was
unverifiable, and it is withdrawn (#184).

The population the parser actually faces is the captured one: the measurement
rigs keep every raw reply, and ``test_reply_corpus.py`` asserts the whole set
against pinned verdicts. #174 — a refusal shape no author here had imagined —
is why the constructed set alone is not enough. Per ADR-0016 the split is
deliberate: a shape found in a capture is pinned there as gold; a shape an
adversarial imagination proposes lives here, marked as what it is.
"""

from __future__ import annotations

import pytest

from mcgyvr.runner import StopReason
from mcgyvr.worker.reply import ParsedFile, ReplyError, parse_reply

GOOD = """Here is the implementation.

```python
def fetch(url: str) -> bytes:
    return b""
```
"""


def parsed(text: str, **kwargs: object) -> ParsedFile:
    result = parse_reply(text, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, ParsedFile), result
    return result


def refused(text: str, **kwargs: object) -> ReplyError:
    result = parse_reply(text, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, ReplyError), result
    return result


# --- the one shape that parses ---------------------------------------------


def test_one_fenced_block_becomes_the_file() -> None:
    file = parsed(GOOD)
    assert file.content == 'def fetch(url: str) -> bytes:\n    return b""\n'
    assert file.info_string == "python"


def test_prose_around_the_block_is_discarded() -> None:
    """Explanations are fine to receive and must never reach the file."""
    assert "Here is the implementation" not in parsed(GOOD).content


def test_a_block_with_no_info_string_parses() -> None:
    file = parsed("```\nvalue = 1\n```\n")
    assert file.content == "value = 1\n"
    assert file.info_string == ""


def test_content_always_ends_with_exactly_one_newline() -> None:
    assert parsed("```\nvalue = 1\n```\n").content.endswith("value = 1\n")


def test_crlf_replies_parse_identically_to_lf_ones() -> None:
    """A stray carriage return on a fence line must not read as no fence."""
    assert parsed(GOOD.replace("\n", "\r\n")).content == parsed(GOOD).content


def test_blank_lines_and_indentation_inside_the_block_survive() -> None:
    reply = "```python\nclass A:\n\n    def b(self) -> None:\n        pass\n```\n"
    file = parsed(reply)
    assert file.content == "class A:\n\n    def b(self) -> None:\n        pass\n"


def test_a_fence_indented_up_to_three_spaces_is_still_a_fence() -> None:
    assert parsed("   ```python\n   value = 1\n   ```\n").content == "   value = 1\n"


def test_more_than_three_backticks_is_a_fence() -> None:
    assert parsed("````python\nvalue = 1\n````\n").content == "value = 1\n"


# --- every ambiguity refuses, by name --------------------------------------


def test_no_fence_at_all_refuses() -> None:
    """The whole reply is never treated as file content."""
    assert refused("def fetch(): pass").code == "no-fenced-block"


def test_two_blocks_refuse_rather_than_taking_the_first() -> None:
    """A model offering an alternative is the common case, and 'the first one'
    is a guess that writes the wrong file."""
    reply = (
        "```python\nfirst = 1\n```\n\nOr alternatively:\n\n```python\nsecond = 2\n```\n"
    )
    error = refused(reply)
    assert error.code == "ambiguous-blocks"
    assert "2" in error.message


def test_an_unterminated_fence_refuses() -> None:
    error = refused("```python\ndef fetch() -> bytes:\n    return b''\n")
    assert error.code == "unterminated-fence"


def test_an_empty_block_refuses() -> None:
    assert refused("```python\n```\n").code == "empty-block"


def test_a_whitespace_only_block_refuses() -> None:
    assert refused("```python\n\n   \n```\n").code == "empty-block"


def test_a_longer_outer_fence_carries_an_inner_fence_through() -> None:
    """A fence is closed only by one at least as long, so a worker that wrapped
    a fence-containing file in a longer fence produced exactly one block. This
    is not a guess being resolved — the widths say which fence is which."""
    reply = "````md\n# doc\n```python\nvalue = 1\n```\n````\n"
    assert parsed(reply).content == "# doc\n```python\nvalue = 1\n```\n"


def test_same_width_nesting_refuses() -> None:
    """With no width difference there is nothing to distinguish an inner fence
    from a closing one: the inner fence reads as the close, and the file's real
    closing fence then opens a block that never closes. Refused either way —
    what matters is that a file containing fences is never half-written."""
    reply = "```md\n# doc\n```python\nvalue = 1\n```\n```\n"
    assert refused(reply).code == "unterminated-fence"


# --- truncation is refused before parsing ----------------------------------


@pytest.mark.parametrize(
    "reason", [StopReason.TRUNCATED, StopReason.UNKNOWN, StopReason.FILTERED]
)
def test_a_reply_that_did_not_complete_refuses(reason: StopReason) -> None:
    """The text can be a perfect fenced block and still be missing its tail;
    only the backend's stop reason knows."""
    error = refused(GOOD, stop_reason=reason)
    assert error.code == "incomplete-reply"
    assert reason.value in error.message


def test_a_complete_reply_parses() -> None:
    assert parsed(GOOD, stop_reason=StopReason.COMPLETE).content


def test_truncation_is_checked_before_the_text_is_parsed() -> None:
    """Otherwise a truncated *and* malformed reply reports the wrong cause."""
    assert refused("no fence here", stop_reason=StopReason.TRUNCATED).code == (
        "incomplete-reply"
    )


# --- only whole_file parses ------------------------------------------------


def test_unified_diff_is_refused_rather_than_parsed_as_a_file() -> None:
    """Parsing a patch as whole-file content applies its +-prefixed body lines
    as source. ADR-0009 scopes v1 to whole_file."""
    error = refused(GOOD, output_schema="unified_diff")
    assert error.code == "unsupported-schema"
    assert "unified_diff" in error.message


def test_an_unknown_schema_is_refused() -> None:
    assert refused(GOOD, output_schema="jsonl").code == "unsupported-schema"


# --- refusals dressed as file content (#174) -------------------------------
#
# The four shapes the issue tabulates, plus the cases that show why the check
# cannot run without knowing the target. Every one of these is structurally a
# perfect reply: exactly one fence, closed, complete. Only the content betrays
# them, and only against a target.


def fenced(body: str, info: str = "python") -> str:
    return f"```{info}\n{body}\n```\n"


def test_a_comment_only_block_is_a_refusal_not_a_file() -> None:
    """Shape 1: valid Python, passes syntax and lint, and is a decline."""
    assert refused(fenced("# I cannot complete this task."), target="a.py").code == (
        "refusal"
    )


def test_a_status_object_block_is_a_refusal_not_a_file() -> None:
    """Shape 2: a bare expression statement — source in name only."""
    body = '{"status": "blocked", "reason": "unsafe"}'
    assert refused(fenced(body), target="a.py").code == "refusal"


def test_a_stub_body_parses_because_acceptance_owns_it_not_this_parser() -> None:
    """Shape 3: ruled out deliberately — a stub is legitimate for some types."""
    file = parsed(fenced("def f(x):\n    raise NotImplementedError"), target="a.py")
    assert "NotImplementedError" in file.content


def test_an_unfenced_refusal_still_refuses_for_the_original_reason() -> None:
    """Shape 4: already caught, and by the ambiguity rule rather than this one."""
    error = refused("I am sorry, I cannot help with that.", target="a.py")
    assert error.code == "no-fenced-block"


def test_a_refusal_says_to_escalate_rather_than_retry_the_rung() -> None:
    error = refused(fenced("# I cannot do this."), target="a.py")
    assert "escalate" in error.message


# --- the same bytes, judged only against a target --------------------------


def test_without_a_target_a_refusal_shaped_block_parses() -> None:
    """The parser never guesses: no target, no opinion about content."""
    assert parsed(fenced("# I cannot complete this task.")).content.startswith("#")


def test_a_heading_is_not_a_comment_when_the_target_is_markdown() -> None:
    """The exact bytes of shape 1 are a legitimate Markdown file."""
    file = parsed(fenced("# I cannot complete this task.", "md"), target="NOTES.md")
    assert file.content.startswith("# I cannot")


def test_a_status_object_is_a_real_file_when_the_target_is_json() -> None:
    body = '{"status": "blocked", "reason": "unsafe"}'
    assert parsed(fenced(body, "json"), target="state.json").content.startswith("{")


def test_a_javascript_line_comment_refusal_is_caught() -> None:
    assert refused(fenced("// I cannot do this.", "ts"), target="a.ts").code == (
        "refusal"
    )


def test_a_javascript_block_comment_refusal_is_caught() -> None:
    body = "/*\n I cannot complete this task.\n*/"
    assert refused(fenced(body, "js"), target="a.js").code == "refusal"


# --- what must keep parsing ------------------------------------------------


def test_a_comment_above_real_code_parses() -> None:
    body = "# Fetch the thing.\ndef fetch() -> bytes:\n    return b''"
    assert "def fetch" in parsed(fenced(body), target="a.py").content


def test_a_docstring_only_module_parses() -> None:
    """A bare string is not a data blob — ``__init__.py`` is a real file."""
    assert parsed(fenced('"""The package."""'), target="pkg/__init__.py").content


def test_a_hash_inside_a_string_is_not_a_comment() -> None:
    assert parsed(fenced('TAG = "# not a comment"'), target="a.py").content


def test_a_list_literal_file_is_still_refused_but_a_number_is_not_judged() -> None:
    """Scalars are excluded from the data-blob rule; containers are not."""
    assert refused(fenced('["a", "b"]'), target="a.py").code == "refusal"
    assert parsed(fenced("42"), target="a.py").content == "42\n"


def test_an_unknown_language_is_left_alone_rather_than_judged_badly() -> None:
    """The gate owns Python and JS/TS; nothing else gets an opinion here."""
    assert parsed(fenced("# I cannot do this.", "rb"), target="a.rb").content


# --- the error surface itself ----------------------------------------------


def test_an_error_reads_as_one_line_naming_its_code() -> None:
    assert str(refused("nothing")).startswith("reply[no-fenced-block]: ")
