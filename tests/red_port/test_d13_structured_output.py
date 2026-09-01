"""D13 — a request may pin a response schema, and nothing that cannot honour one breaks.

:class:`mcgyvr.runner.Request` describes a generation without naming who serves it, and
that is why it works on both protocols. What it cannot say is what *shape* the answer
should come back in, so every reply arrives as prose and
:func:`mcgyvr.worker.reply.parse_reply` recovers the file from it by finding exactly one
code fence. That parser is careful — one fence or a named refusal, never a guess — and
being careful is the cost: a reply that explains itself in a second fenced block, or
wraps its answer in a longer fence than it closes, is a spent attempt. Every
OpenAI-compatible server that supports ``response_format`` can be asked to skip the
prose entirely, and the fence-hunting with it.

Three statements, and the middle one is the reason this is a small lever and not a
protocol change.

*A request may pin a schema, and the reply needs no fence-hunting* is asserted on the
field and then on the result of parsing a reply that has no fence in it at all. The
same bytes are also put through today's parser and asserted to be **refused** — that
assertion is what makes the first one mean something. Without it, a structured reply
that happened to contain a fence somewhere would pass, and the test would not
distinguish a schema-aware parser from the one already in the repository.

*A backend that cannot honour a schema still works through the fenced path* is the
statement that keeps this optional. Ollama's ``/api/generate``, older llama-server
builds and anything behind a proxy that drops unknown fields will return prose no
matter what the request asked for. If pinning a schema made those replies unparseable,
the field could never be set on the ladder's cheap rungs — which are exactly the local
backends this project runs on — and the lever would be dead config. So a *pinned*
request is asserted against a *fenced* reply, and the file must come out.

*A structured reply and a fenced reply carrying the same content produce the same
result* is the equivalence, and it is why this cannot be a second output protocol. Two
paths that agree on the easy case and diverge on the hard one give a gate two different
files depending on which server answered, and D26's determinism claim quietly stops
being about the run and starts being about the backend. Same content in, identical
:class:`~mcgyvr.worker.reply.ParsedFile` out — including the trailing newline, which is
where a second implementation of "extract the content" differs first.

Nothing here dispatches. The two replies are literals; ``response_format`` is a field on
a request that is constructed and never sent.
"""

from __future__ import annotations

import json
from typing import Any

from mcgyvr.runner import Request
from mcgyvr.worker.reply import ReplyError, parse_reply
from tests.red_port.conftest import required

BEHAVIOR_PIN = (
    "pin a response schema on a request, so a backend that honours one answers "
    "structured instead of fenced"
)
BEHAVIOR_READ = (
    "read a schema-pinned reply without hunting for a code fence, and still read a "
    "fenced one from a backend that ignored the schema"
)

TARGET = "src/pkg/fetch.py"

# The minimal schema the lever needs: one string field holding the whole file. Named
# loosely on purpose — what matters is that the request can carry *a* schema, not that
# it carries this one.
SCHEMA = {
    "type": "object",
    "properties": {"content": {"type": "string"}},
    "required": ["content"],
    "additionalProperties": False,
}

CONTENT = "def fetch(url):\n    return url.strip()\n"

# The same file, twice: once as a backend that honoured the schema would send it, once
# as a backend that ignored it would.
STRUCTURED = json.dumps({"content": CONTENT})
FENCED = f"Here is the updated file.\n\n```python\n{CONTENT}```\n"


def _pinned_request() -> Any:
    """A request carrying a response schema.

    Resolved through :func:`~tests.red_port.conftest.required` rather than built
    directly, because an unknown keyword on a frozen dataclass raises ``TypeError`` —
    which is an error, not a missing behaviour, and would take the file down as a
    collection failure instead of reporting one absent capability per test.
    """

    def build() -> Any:
        if "response_schema" not in Request.__dataclass_fields__:
            raise AttributeError(
                "mcgyvr.runner.Request carries no response-schema field"
            )
        return Request(
            prompt="Add retry with backoff to the fetch helper.",
            max_output_tokens=512,
            # This carried `# type: ignore[call-arg]` while the field was absent,
            # since the type error *was* the RED condition. The port added the
            # field, so the ignore became unused — and under `strict` an unused
            # ignore is itself an error, which is what makes its removal part of
            # going green rather than a tidy-up someone has to remember.
            response_schema=SCHEMA,
        )

    return required(BEHAVIOR_PIN, build)


def _parse_pinned() -> Any:
    """The reply reader that knows a schema was pinned.

    Placeholder name. What must survive is what it returns for each of the two reply
    shapes, not where the entry point lives.
    """
    return required(
        BEHAVIOR_READ,
        lambda: (
            __import__("mcgyvr.worker.reply", fromlist=["parse_pinned"]).parse_pinned
        ),
    )


def test_a_pinned_schema_makes_the_reply_structured_instead_of_fenced() -> None:
    """The request carries the schema, and the answer arrives without a fence.

    The refusal from today's parser is asserted in the same test, because it is what
    proves the structured path did any work: a reply the fence parser can already read
    would make this test pass against the code as it stands.
    """
    request = _pinned_request()
    assert request.response_schema == SCHEMA

    assert isinstance(parse_reply(STRUCTURED, target=TARGET), ReplyError), (
        "the structured reply is readable by fence-hunting, so this test cannot say "
        "whether a schema-aware path exists"
    )

    parsed = _parse_pinned()(
        STRUCTURED, response_schema=request.response_schema, target=TARGET
    )

    assert not isinstance(parsed, ReplyError), (
        f"a schema-pinned reply was refused: {parsed}"
    )
    assert parsed.content == CONTENT


def test_a_backend_that_ignores_the_schema_still_works() -> None:
    """A pinned request whose reply came back as prose must still yield the file.

    The cheap rungs of this ladder are local backends, and several of them will never
    honour ``response_format``. A schema that made their replies unreadable would be a
    field nobody could set where it would help most.
    """
    request = _pinned_request()

    parsed = _parse_pinned()(
        FENCED, response_schema=request.response_schema, target=TARGET
    )

    assert not isinstance(parsed, ReplyError), (
        f"pinning a schema broke the fenced path a backend that ignores it must use: "
        f"{parsed}"
    )
    assert parsed.content == CONTENT


def test_the_two_reply_shapes_produce_the_same_file() -> None:
    """Same content, two wire shapes, one result — trailing newline included.

    Two paths that disagree about the bytes hand the gate a different file depending on
    which server answered, and the run stops being reproducible for a reason that has
    nothing to do with the contract.
    """
    parse = _parse_pinned()

    via_schema = parse(STRUCTURED, response_schema=SCHEMA, target=TARGET)
    via_fence = parse(FENCED, response_schema=SCHEMA, target=TARGET)

    assert via_schema.content == via_fence.content, (
        f"structured gave {via_schema.content!r}, fenced gave {via_fence.content!r}"
    )
    assert via_schema.content == CONTENT
