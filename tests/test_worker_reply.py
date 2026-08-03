"""The single-file output protocol, tested mostly on replies that are wrong.

A parser that only ever sees well-formed input is not the thing standing
between a model's prose and a source file. Every refusal below is a real shape
a local worker produces — an apology before the code, two blocks because it
offered an alternative, a fence that never closed because the cap cut it off —
and each one must resolve to a *named* failure rather than to a plausible file.
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


# --- the error surface itself ----------------------------------------------


def test_an_error_reads_as_one_line_naming_its_code() -> None:
    assert str(refused("nothing")).startswith("reply[no-fenced-block]: ")
