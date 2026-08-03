"""A runner is the first thing below the seam, so what these tests hold it to is
#21's acceptance rather than either backend's JSON: that one contract executes
identically on both protocols, that the cap is genuinely sent by both and
checked afterwards, that truncation is read from what the backend said and never
inferred from what the text looks like, that a local endpoint needs no key, and
that CAV-01 cannot be depended on silently.

The transport is stubbed for most of it — replaced by a lookup that also
*records* what was sent, since half these properties are about the request
rather than the answer — and one test stands up a real loopback HTTP server, so
that the keyless local path is proven against a socket rather than against a
monkeypatch.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import textwrap
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, Protocol, SourceUnavailableError, UnknownRungError
from mcgyvr.pool import source_map as build_source_map
from mcgyvr.runner import (
    BackendError,
    Completion,
    OllamaRunner,
    OpenAIRunner,
    ProtocolError,
    QualityCaveatError,
    Request,
    StopReason,
    TransportError,
    dispatch,
    dispatch_role,
    runner_for,
)

LOCAL_OLLAMA = Endpoint(
    source="local",
    base_url="http://localhost:11434",
    protocol=Protocol.OLLAMA,
    max_parallel=3,
    credential_env=None,
)

LOCAL_OPENAI = Endpoint(
    source="llama-server",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=2,
    credential_env=None,
)

KEYED_OPENAI = Endpoint(
    source="remote",
    base_url="https://api.example.com",
    protocol=Protocol.OPENAI,
    max_parallel=4,
    credential_env="MCGYVR_TEST_KEY",
)


def ollama_answer(
    text: str = "def f():\n    return 1\n",
    done_reason: str = "stop",
    prompt_eval_count: int | None = 120,
    eval_count: int | None = 9,
) -> dict[str, Any]:
    """An /api/generate answer, in the shape Ollama actually returns one."""
    answer: dict[str, Any] = {
        "model": "qwen2.5-coder:7b",
        "response": text,
        "done": True,
        "done_reason": done_reason,
        "total_duration": 1_500_000_000,
    }
    if prompt_eval_count is not None:
        answer["prompt_eval_count"] = prompt_eval_count
    if eval_count is not None:
        answer["eval_count"] = eval_count
    return answer


def openai_answer(
    text: str = "def f():\n    return 1\n",
    finish_reason: str = "stop",
    prompt_tokens: int | None = 120,
    completion_tokens: int | None = 9,
) -> dict[str, Any]:
    """A chat-completions answer, in the shape the compatible servers return."""
    usage: dict[str, Any] = {}
    if prompt_tokens is not None:
        usage["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        usage["completion_tokens"] = completion_tokens
    answer: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ],
    }
    if usage:
        answer["usage"] = usage
    return answer


class Sent:
    """What a stubbed dispatch was asked to send, so requests can be asserted on."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def one(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected one dispatch, got {len(self.calls)}"
        return self.calls[0]

    @property
    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.one["payload"]
        return payload

    @property
    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = self.one["headers"]
        return headers

    @property
    def url(self) -> str:
        url: str = self.one["url"]
        return url


def stub_post(
    monkeypatch: pytest.MonkeyPatch,
    answer: dict[str, Any] | Exception,
) -> Sent:
    """Replace the transport with one recording the request, returning ``answer``."""
    sent = Sent()

    def fake_post(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        sent.calls.append(
            {"url": url, "payload": payload, "headers": headers, "timeout": timeout}
        )
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)
    return sent


def stub_clock(monkeypatch: pytest.MonkeyPatch, elapsed: float) -> None:
    """Make the wall clock advance by exactly ``elapsed`` across one dispatch.

    Settles at the end value afterwards rather than running out, so that a
    clock read by anything else while this is installed cannot fail the test
    with a ``StopIteration`` that has nothing to do with what it asserts.
    """
    ticks = iter([10.0, 10.0 + elapsed])

    def clock() -> float:
        return next(ticks, 10.0 + elapsed)

    monkeypatch.setattr("mcgyvr.runner.time.monotonic", clock)


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


ASK = Request(prompt="write a function", max_output_tokens=256)


# --- the same contract executes identically on either protocol ------------


def test_one_request_produces_the_same_completion_on_both_protocols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#21's first acceptance bullet, asserted as an equality rather than a list.

    Two backends, two wire shapes, two different JSON documents saying the same
    thing. What comes back must differ only in the fields that name where it
    ran and what it cost — everything a caller would branch on is identical, or
    the seam does not hold.
    """
    stub_clock(monkeypatch, 0.5)
    stub_post(monkeypatch, ollama_answer())
    from_ollama = runner_for(LOCAL_OLLAMA).generate("qwen2.5-coder:7b", ASK)

    stub_clock(monkeypatch, 0.5)
    stub_post(monkeypatch, openai_answer())
    from_openai = runner_for(LOCAL_OPENAI).generate("qwen2.5-coder:7b", ASK)

    assert from_ollama.text == from_openai.text
    assert from_ollama.stop_reason is from_openai.stop_reason
    assert from_ollama.complete and from_openai.complete
    assert from_ollama.input_tokens == from_openai.input_tokens
    assert from_ollama.output_tokens == from_openai.output_tokens
    assert from_ollama.max_output_tokens == from_openai.max_output_tokens
    assert from_ollama.latency_s == from_openai.latency_s

    # And the only differences are the ones that say where it ran — plus the
    # caveat flag, which is a property of the path and is tested below.
    differing = {
        field
        for field in vars(from_ollama)
        if getattr(from_ollama, field) != getattr(from_openai, field)
    }
    assert differing == {"source", "protocol", "quality_safe", "notes"}


def test_runner_for_selects_the_implementation_from_the_protocol() -> None:
    """A call site names a rung, never a backend — this is the only lookup."""
    assert isinstance(runner_for(LOCAL_OLLAMA), OllamaRunner)
    assert isinstance(runner_for(LOCAL_OPENAI), OpenAIRunner)
    assert isinstance(runner_for(KEYED_OPENAI), OpenAIRunner)


def test_each_protocol_posts_to_its_own_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate("qwen2.5-coder:7b", ASK)
    assert sent.url == "http://localhost:11434/api/generate"

    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("qwen2.5-coder:7b", ASK)
    assert sent.url == "http://localhost:8080/v1/chat/completions"


def test_a_base_url_written_with_v1_does_not_get_a_second_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Providers document their URL with /v1; pasting it must not 404."""
    endpoint = Endpoint(
        source="remote",
        base_url="https://api.example.com/v1",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )
    sent = stub_post(monkeypatch, openai_answer())
    runner_for(endpoint).generate("big-model", ASK)
    assert sent.url == "https://api.example.com/v1/chat/completions"


def test_the_system_prompt_crosses_both_protocols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ask = Request(prompt="do the thing", max_output_tokens=64, system="be terse")

    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate("m", ask)
    assert sent.payload["system"] == "be terse"
    assert sent.payload["prompt"] == "do the thing"

    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("m", ask)
    assert sent.payload["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "do the thing"},
    ]


def test_no_system_prompt_sends_no_empty_system_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty system prompt is not a system prompt — sending one is a request
    that differs from the one that was asked for."""
    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert "system" not in sent.payload

    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert [m["role"] for m in sent.payload["messages"]] == ["user"]


def test_neither_protocol_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single document is what makes the stop reason and the counts readable."""
    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert sent.payload["stream"] is False

    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert sent.payload["stream"] is False


# --- a hard output cap, enforced by both ---------------------------------


def test_the_cap_is_sent_in_each_protocols_own_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ask = Request(prompt="p", max_output_tokens=128)

    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate("m", ask)
    assert sent.payload["options"]["num_predict"] == 128

    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("m", ask)
    assert sent.payload["max_tokens"] == 128


def test_an_uncapped_request_cannot_be_expressed() -> None:
    """There is no default and no sentinel: the ceiling is thought about or the
    request does not exist. CAV-03 is a record of what an unconsidered output
    budget costs."""
    with pytest.raises(ValueError, match="max_output_tokens"):
        Request(prompt="p", max_output_tokens=0)
    with pytest.raises(ValueError, match="max_output_tokens"):
        Request(prompt="p", max_output_tokens=-1)


def test_a_backend_that_ignores_the_cap_is_caught_by_its_own_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing streams, so the cap cannot be enforced mid-generation. What can
    be done is checking the backend's own report against the ceiling it was
    sent, so an overrun is visible rather than passing for a short answer."""
    stub_post(monkeypatch, ollama_answer(eval_count=999))
    done = runner_for(LOCAL_OLLAMA).generate(
        "m", Request(prompt="p", max_output_tokens=64)
    )
    assert done.overran_cap is True
    assert any("did not honour the ceiling" in note for note in done.notes)


def test_a_respected_cap_is_distinct_from_an_uncheckable_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``None`` means the backend reported no count, which is not the same
    answer as a cap that held."""
    stub_post(monkeypatch, openai_answer(completion_tokens=9))
    held = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert held.overran_cap is False

    stub_post(monkeypatch, openai_answer(completion_tokens=None))
    unknown = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert unknown.overran_cap is None


def test_the_completion_carries_the_cap_it_was_issued_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A telemetry row that cannot say what ceiling it ran against cannot be
    compared with another one."""
    stub_post(monkeypatch, ollama_answer())
    done = runner_for(LOCAL_OLLAMA).generate(
        "m", Request(prompt="p", max_output_tokens=77)
    )
    assert done.max_output_tokens == 77


# --- truncation is surfaced, never inferred ------------------------------


def test_truncation_is_read_from_what_the_backend_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, ollama_answer(done_reason="length"))
    from_ollama = runner_for(LOCAL_OLLAMA).generate("m", ASK)

    stub_post(monkeypatch, openai_answer(finish_reason="length"))
    from_openai = runner_for(LOCAL_OPENAI).generate("m", ASK)

    for done in (from_ollama, from_openai):
        assert done.stop_reason is StopReason.TRUNCATED
        assert done.truncated is True
        assert done.complete is False


def test_output_that_merely_looks_cut_off_is_not_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property that keeps a truncated patch from being applied as a whole
    one is that the *shape* of the text is never evidence. A finished answer
    that ends mid-token, with no newline and no closing brace, is finished."""
    stub_post(monkeypatch, ollama_answer(text="def f(:\n    retur", done_reason="stop"))
    done = runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert done.truncated is False
    assert done.complete is True

    stub_post(monkeypatch, openai_answer(text="", finish_reason="stop"))
    empty = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert empty.text == ""
    assert empty.complete is True
    assert empty.truncated is False


def test_an_unreported_stop_reason_is_not_read_as_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unoptimistic half of "never inferred": a backend that said nothing
    has not said the answer is whole, and neither ``complete`` nor ``truncated``
    may claim otherwise."""
    stub_post(monkeypatch, ollama_answer(done_reason=""))
    done = runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert done.stop_reason is StopReason.UNKNOWN
    assert done.complete is False
    assert done.truncated is False
    assert any("not being read as complete" in note for note in done.notes)


def test_an_unrecognised_stop_reason_keeps_the_backends_own_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new backend inventing a word surfaces as "it did not say", and the word
    survives so that whoever reads the note can see what it actually was."""
    stub_post(monkeypatch, openai_answer(finish_reason="abort"))
    done = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert done.stop_reason is StopReason.UNKNOWN
    assert done.raw_stop_reason == "abort"
    assert any("abort" in note for note in done.notes)


def test_the_stop_words_the_compatible_servers_actually_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`eos_token` is TGI's and `max_tokens` appears where the reference
    implementation says `length`; both are the same two outcomes."""
    stub_post(monkeypatch, openai_answer(finish_reason="eos_token"))
    assert runner_for(LOCAL_OPENAI).generate("m", ASK).complete is True

    stub_post(monkeypatch, openai_answer(finish_reason="max_tokens"))
    assert runner_for(LOCAL_OPENAI).generate("m", ASK).truncated is True

    stub_post(monkeypatch, openai_answer(finish_reason="content_filter"))
    filtered = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert filtered.stop_reason is StopReason.FILTERED
    assert filtered.complete is False


def test_no_stop_sequence_is_sent_on_either_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0009, held as a property of the wire rather than as a comment.

    A stop sequence is consumed by the server and stripped from the answer, so
    it converts a reply that ran long into a shorter one that still parses —
    under ``whole_file`` that is a valid Python file missing most of itself, and
    the gate passes it. The cap fails by name instead. A safe set is derivable
    from ``output_schema`` and belongs to #25's parser; what must never happen
    is one appearing as a constant here.
    """
    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert "stop" not in sent.payload
    assert "stop" not in sent.payload["options"]

    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert "stop" not in sent.payload


def test_a_request_has_no_stop_field_to_fill_in() -> None:
    """The absence is the decision. A caller that reaches for one is re-opening
    ADR-0009, and finds out here rather than in a truncated file."""
    assert "stop" not in {f.name for f in dataclasses.fields(Request)}
    with pytest.raises(TypeError):
        Request(prompt="p", max_output_tokens=8, stop=("```",))  # type: ignore[call-arg]


def test_a_truncated_reply_is_named_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0009's other half: hitting the cap is not a short answer. The note
    travels with the completion so telemetry carries the words too."""
    stub_post(monkeypatch, openai_answer(finish_reason="length"))
    done = runner_for(LOCAL_OPENAI).generate(
        "m", Request(prompt="p", max_output_tokens=64)
    )
    assert done.truncated is True
    assert any("must not be applied to a file" in note for note in done.notes)
    assert any("64-token cap" in note for note in done.notes)


# --- token counts and latency, for telemetry -----------------------------


def test_token_counts_come_from_both_protocols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, ollama_answer(prompt_eval_count=120, eval_count=9))
    from_ollama = runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert (from_ollama.input_tokens, from_ollama.output_tokens) == (120, 9)

    stub_post(monkeypatch, openai_answer(prompt_tokens=120, completion_tokens=9))
    from_openai = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert (from_openai.input_tokens, from_openai.output_tokens) == (120, 9)


def test_an_unreported_count_is_none_and_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend that said nothing about tokens has not said zero, and a zero
    would average into telemetry as a real measurement of nothing."""
    stub_post(monkeypatch, ollama_answer(prompt_eval_count=None, eval_count=None))
    from_ollama = runner_for(LOCAL_OLLAMA).generate("m", ASK)
    assert from_ollama.input_tokens is None
    assert from_ollama.output_tokens is None

    stub_post(monkeypatch, openai_answer(prompt_tokens=None, completion_tokens=None))
    from_openai = runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert from_openai.input_tokens is None
    assert from_openai.output_tokens is None


def test_a_non_numeric_count_is_unreported_rather_than_coerced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = openai_answer()
    answer["usage"]["completion_tokens"] = "9"
    stub_post(monkeypatch, answer)
    assert runner_for(LOCAL_OPENAI).generate("m", ASK).output_tokens is None


def test_latency_is_measured_around_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wall-clock and host-side, so it is the same quantity on both protocols —
    a server-reported duration excludes queueing and is not comparable."""
    stub_clock(monkeypatch, 2.25)
    stub_post(monkeypatch, ollama_answer())
    assert runner_for(LOCAL_OLLAMA).generate("m", ASK).latency_s == pytest.approx(2.25)


def test_the_timeout_reaches_the_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = stub_post(monkeypatch, ollama_answer())
    runner_for(LOCAL_OLLAMA).generate(
        "m", Request(prompt="p", max_output_tokens=8, timeout_s=5.0)
    )
    assert sent.one["timeout"] == 5.0


def test_a_non_positive_timeout_is_refused() -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        Request(prompt="p", max_output_tokens=8, timeout_s=0)


# --- CAV-01: the dependency is allowed, the silence is not ---------------


def test_a_quality_sensitive_request_is_refused_on_ollama_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#21's third acceptance bullet. The refusal happens before anything is
    sent, and it names the remedy — which is a config edit, because Ollama also
    serves the compatible shape."""
    sent = stub_post(monkeypatch, ollama_answer())
    ask = Request(
        prompt="humaneval task", max_output_tokens=512, quality_sensitive=True
    )
    with pytest.raises(QualityCaveatError, match="CAV-01"):
        runner_for(LOCAL_OLLAMA).generate("qwen2.5-coder:7b", ask)
    assert sent.calls == [], "nothing may be dispatched before the caveat is raised"


def test_a_quality_sensitive_request_runs_on_the_compatible_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The remedy has to actually work, or the refusal is just a wall."""
    stub_post(monkeypatch, openai_answer())
    ask = Request(
        prompt="humaneval task", max_output_tokens=512, quality_sensitive=True
    )
    done = runner_for(LOCAL_OPENAI).generate("qwen2.5-coder:7b", ask)
    assert done.quality_safe is True
    assert done.notes == ()


def test_ordinary_work_still_runs_on_ollama_native_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refusing the path outright would refuse the common machine. Every
    completion from it carries the caveat instead, so a number read out of
    telemetry cannot be mistaken for a measurement."""
    stub_post(monkeypatch, ollama_answer())
    done = runner_for(LOCAL_OLLAMA).generate("qwen2.5-coder:7b", ASK)
    assert done.text
    assert done.quality_safe is False
    assert any("CAV-01" in note for note in done.notes)


# --- credentials: named, resolved late, never logged ---------------------


def test_a_local_endpoint_is_sent_no_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#21's second acceptance bullet, at the header level: no key, and not an
    empty header either — some servers reject one of those."""
    sent = stub_post(monkeypatch, openai_answer())
    runner_for(LOCAL_OPENAI).generate("m", ASK)
    assert "Authorization" not in sent.headers


def test_a_keyed_endpoint_carries_the_key_read_at_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-resolved-at-point-of-use")
    sent = stub_post(monkeypatch, openai_answer())
    runner_for(KEYED_OPENAI).generate("big-model", ASK)
    assert sent.headers["Authorization"] == "Bearer sk-resolved-at-point-of-use"


def test_a_key_that_vanished_fails_loudly_rather_than_dispatching_bare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The map checks presence when it is built, so reaching this means the
    environment changed underneath the run. Sending the request anyway would
    read as an auth failure from the provider instead."""
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    sent = stub_post(monkeypatch, openai_answer())
    with pytest.raises(SourceUnavailableError, match="MCGYVR_TEST_KEY"):
        runner_for(KEYED_OPENAI).generate("big-model", ASK)
    assert sent.calls == []


def test_no_credential_reaches_a_completion_or_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key belongs in one header of one request and nowhere else — not in a
    repr, not in a traceback, not in a telemetry row."""
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-secret-value")
    stub_post(monkeypatch, openai_answer())
    done = runner_for(KEYED_OPENAI).generate("big-model", ASK)
    assert "sk-secret-value" not in repr(done)

    stub_post(monkeypatch, BackendError("https://api.example.com answered HTTP 401"))
    with pytest.raises(BackendError) as caught:
        runner_for(KEYED_OPENAI).generate("big-model", ASK)
    assert "sk-secret-value" not in str(caught.value)


# --- failures are named, not folded together -----------------------------


def test_an_unreachable_endpoint_is_a_transport_error() -> None:
    """The port is closed, so this asserts against a real socket failure rather
    than a stub. Whether an endpoint is answering at all is #22's question;
    what this owns is saying which of the failures it was."""
    unreachable = Endpoint(
        source="down",
        # Reserved for documentation (RFC 5737) and not routable, so this fails
        # rather than reaching anything: the timeout is what bounds the test.
        base_url="http://192.0.2.1:9",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )
    ask = Request(prompt="p", max_output_tokens=8, timeout_s=0.25)
    with pytest.raises(TransportError, match="could not reach"):
        runner_for(unreachable).generate("m", ask)


def test_an_http_error_status_is_a_backend_error() -> None:
    with serving(status=401, body='{"error": "invalid api key"}') as base_url:
        endpoint = local_openai(base_url)
        with pytest.raises(BackendError, match="401") as caught:
            runner_for(endpoint).generate("m", ASK)
    assert "invalid api key" in str(caught.value)


def test_an_answer_that_is_not_json_is_a_protocol_error() -> None:
    with (
        serving(body="<html>502 Bad Gateway</html>") as base_url,
        pytest.raises(ProtocolError, match="not JSON"),
    ):
        runner_for(local_openai(base_url)).generate("m", ASK)


def test_json_that_is_not_an_object_is_a_protocol_error() -> None:
    with (
        serving(body="[]") as base_url,
        pytest.raises(ProtocolError, match="list"),
    ):
        runner_for(local_openai(base_url)).generate("m", ASK)


def test_a_missing_response_field_is_a_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_post(monkeypatch, {"done": True, "done_reason": "stop"})
    with pytest.raises(ProtocolError, match="string 'response'"):
        runner_for(LOCAL_OLLAMA).generate("m", ASK)


def test_missing_choices_is_a_protocol_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_post(monkeypatch, {"id": "chatcmpl-1", "choices": []})
    with pytest.raises(ProtocolError, match="no choices"):
        runner_for(LOCAL_OPENAI).generate("m", ASK)


def test_choices_without_string_content_is_a_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A message carrying only tool calls has ``content: null``. Nothing here
    asks for tools, so this is a backend doing something unasked-for, and
    reading it as an empty answer would hand the gate an empty file."""
    stub_post(
        monkeypatch,
        {"choices": [{"message": {"role": "assistant", "content": None}}]},
    )
    with pytest.raises(ProtocolError, match="string content"):
        runner_for(LOCAL_OPENAI).generate("m", ASK)


# --- dispatch: the seam crossing, from a rung name -----------------------


LADDER = """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 3
  fast:
    base_url: http://localhost:8080
    api: openai
    max_parallel: 2
  remote:
    base_url: https://api.example.com
    api: openai
    max_parallel: 4
    api_key_env: MCGYVR_TEST_KEY
ladder:
  tiers:
    - name: cheap
      source: local
      model: qwen2.5-coder:7b
    - name: strong
      source: fast
      model: qwen2.5-coder:14b
    - name: hosted
      source: remote
      model: big-model
verifier:
  source: fast
  model: qwen2.5-coder:14b
"""


def test_dispatch_takes_the_model_from_the_rung_and_the_protocol_from_its_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller names a step of the ladder and nothing about a machine. Both the
    model and the wire shape are resolved on the other side of the seam."""
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    ladder = build_source_map(parse(cfg(LADDER)))

    sent = stub_post(monkeypatch, ollama_answer())
    cheap = dispatch(ladder, "cheap", ASK)
    assert cheap.model == "qwen2.5-coder:7b"
    assert cheap.protocol is Protocol.OLLAMA
    assert cheap.source == "local"
    assert sent.url.endswith("/api/generate")

    sent = stub_post(monkeypatch, openai_answer())
    strong = dispatch(ladder, "strong", ASK)
    assert strong.model == "qwen2.5-coder:14b"
    assert strong.protocol is Protocol.OPENAI
    assert sent.url.endswith("/v1/chat/completions")


def test_repointing_a_rung_at_another_source_changes_the_protocol_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#20's property, now with a runner under it: the config edit moves the
    work between wire protocols and the call site is not touched."""
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    repointed = LADDER.replace(
        "    - name: cheap\n      source: local\n",
        "    - name: cheap\n      source: fast\n",
    )
    ladder = build_source_map(parse(cfg(repointed)))
    sent = stub_post(monkeypatch, openai_answer())
    cheap = dispatch(ladder, "cheap", ASK)
    assert cheap.protocol is Protocol.OPENAI
    assert sent.url.endswith("/v1/chat/completions")


def test_dispatch_keeps_an_unknown_rung_and_an_unusable_one_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    ladder = build_source_map(parse(cfg(LADDER)))

    with pytest.raises(UnknownRungError, match="no rung named 'nope'"):
        dispatch(ladder, "nope", ASK)

    # `hosted` is declared but its key is unset, so the map skipped it.
    with pytest.raises(SourceUnavailableError, match="MCGYVR_TEST_KEY"):
        dispatch(ladder, "hosted", ASK)


def test_dispatch_role_runs_a_role_and_returns_none_when_there_is_not_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A keyless install runs with no verifier at all, and that is an ordinary
    state — the caller gets ``None`` rather than an exception to catch."""
    monkeypatch.delenv("MCGYVR_TEST_KEY", raising=False)
    ladder = build_source_map(parse(cfg(LADDER)))

    stub_post(monkeypatch, openai_answer())
    verified = dispatch_role(ladder, "verifier", ASK)
    assert verified is not None
    assert verified.model == "qwen2.5-coder:14b"
    assert dispatch_role(ladder, "orchestrator", ASK) is None


# --- against a real socket -----------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    """Records what it was sent and answers with what the test configured."""

    status: ClassVar[int] = 200
    body: ClassVar[str] = "{}"
    seen: ClassVar[dict[str, Any]] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        type(self).seen = {
            "path": self.path,
            "headers": dict(self.headers),
            "payload": json.loads(raw) if raw else None,
        }
        encoded = self.body.encode("utf-8")
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr logging."""


@contextlib.contextmanager
def serving(status: int = 200, body: str = "{}") -> Iterator[str]:
    """A real HTTP server on loopback, for the tests that must not be stubbed.

    Yields its base URL. Port 0 so nothing collides with a backend the
    developer actually has running, and the thread is torn down on the way out
    whether or not the body raised.
    """
    _Handler.status = status
    _Handler.body = body
    _Handler.seen = {}
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def local_openai(base_url: str) -> Endpoint:
    return Endpoint(
        source="llama-server",
        base_url=base_url,
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def test_a_keyless_local_endpoint_works_end_to_end_over_a_socket() -> None:
    """The keyless acceptance bullet, proven against a server rather than a
    monkeypatch: a real request is made, it carries no Authorization header at
    all, the cap is on the wire, and a completion comes back."""
    with serving(body=json.dumps(openai_answer(text="hello", completion_tokens=2))) as (
        base_url
    ):
        done = runner_for(local_openai(base_url)).generate(
            "qwen2.5-coder:7b", Request(prompt="hi", max_output_tokens=16)
        )

    assert isinstance(done, Completion)
    assert done.text == "hello"
    assert done.complete is True
    assert done.output_tokens == 2
    assert done.latency_s >= 0.0

    assert _Handler.seen["path"] == "/v1/chat/completions"
    assert "Authorization" not in _Handler.seen["headers"]
    assert _Handler.seen["headers"]["Content-Type"] == "application/json"
    assert _Handler.seen["payload"]["max_tokens"] == 16
    assert _Handler.seen["payload"]["model"] == "qwen2.5-coder:7b"


def test_ollama_native_works_end_to_end_over_a_socket() -> None:
    """The same, for the other protocol: the cap lands in ``options.num_predict``
    and the caveat travels with the answer."""
    with serving(
        body=json.dumps(ollama_answer(text="hello", eval_count=2))
    ) as base_url:
        endpoint = Endpoint(
            source="local",
            base_url=base_url,
            protocol=Protocol.OLLAMA,
            max_parallel=1,
            credential_env=None,
        )
        done = runner_for(endpoint).generate(
            "qwen2.5-coder:7b", Request(prompt="hi", max_output_tokens=16)
        )

    assert done.text == "hello"
    assert done.output_tokens == 2
    assert done.quality_safe is False
    assert _Handler.seen["path"] == "/api/generate"
    assert _Handler.seen["payload"]["options"]["num_predict"] == 16
