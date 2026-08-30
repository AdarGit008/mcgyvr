"""A pinned schema does not make the target stop deciding what an envelope is.

:mod:`mcgyvr.worker.reply` opens a ``{"content": "..."}`` carrier in exactly one
situation, and its docstring is explicit about why:

    Whether such an object *is* the file or merely carries it is not answerable
    from the bytes, so the answer comes from where every other content judgement
    here comes from: the target. With one, both readings are already handled
    correctly — ``{"status": "blocked"}`` destined for a ``.py`` file is #174's
    refusal, and the same object destined for a ``.json`` file is a real file —
    so nothing is unwrapped and nothing is guessed. With no target neither rule
    can run, and the object would be written verbatim into a file this module
    cannot name; that is the one outcome that is wrong under either reading, and
    it is exactly where the envelope is opened.

:func:`~mcgyvr.worker.reply.parse_pinned`'s not-honoured fallback called
``parse_reply(text, …)`` **without** ``target``, and the comment above it says
why it did: #174 would refuse a carrier as a data blob before anything looked
inside it, so the judgement is deferred and made afterwards on what the carrier
holds. That reason is good. Dropping the target is how it was bought, and the
target carries a second rule as well as the one being deferred — so the fallback
also lost "with a target, nothing is unwrapped", and did it silently.

What that costs is a file. A contract whose target is a ``.json`` file whose
legitimate content *is* an object with a non-empty string ``content`` key — a
manifest, a fixture, a bundle entry, anything at all — comes back through the
fallback truncated to that one field's value. It is the exact case the module
docstring names as already handled correctly, failing in the one reader that
does not pass the target along.

**The fix has to keep the comment's protection.** Passing the target back and
doing nothing else would restore the early #174 refusal and break every carrier
a backend sent inside a fence, which is the case the fallback exists for. So the
two rules are separated: the structural read is what the fallback asks for, and
both target rules are applied here, in the order that lets each one answer what
it is about. Whether the object is an envelope at all is decided by the target
the same way #174 is — an object bound for a file whose language the gate owns
is not a file in that language, so it is opened and judged on what came out; an
object bound for a ``.json`` file is the file.

**The controls.** A real carrier for a ``.py`` target must still be unwrapped —
that is what the fallback is for, and a fix that simply stopped unwrapping would
pass the statement above and make pinning a schema cost an attempt on every
backend that ignores one. A declining carrier must still reach #174's named
refusal, on its contents rather than on its envelope, which is the thing the
comment protects. A schema-honouring reply must still be read from the object,
and the two shapes must still produce the same bytes — that equivalence is D13's
whole claim, and it is what stops a run's reproducibility being a property of
which server answered.
"""

from __future__ import annotations

import json

from mcgyvr.worker.reply import ParsedFile, ReplyError, parse_pinned

#: The schema a caller pins for whole-file output.
SCHEMA = {
    "type": "object",
    "properties": {"content": {"type": "string"}},
    "required": ["content"],
    "additionalProperties": False,
}

#: The same lever with the field spelled the caller's way. ``_schema_field``
#: reads the name off the schema rather than assuming, so a reader that unwraps
#: ``content`` here is not opening the envelope that was asked for at all.
NAMED_SCHEMA = {
    "type": "object",
    "properties": {"file": {"type": "string"}},
    "required": ["file"],
    "additionalProperties": False,
}

JSON_TARGET = "src/pkg/manifest.json"
PY_TARGET = "src/pkg/fetch.py"

#: A `.json` file that is a real file and happens to be shaped like a carrier.
#: Nothing in the bytes distinguishes it from one; the target does.
MANIFEST = json.dumps({"content": "the manifest's own text", "version": 2}) + "\n"

#: The same shape with no second key, so that not even "it has other fields"
#: is available as a tell.
BARE = json.dumps({"content": "the whole file"}) + "\n"

PY_FILE = "def fetch(url):\n    return url.strip()\n"


def _fenced(body: str, info: str = "json") -> str:
    """``body`` as a backend that ignored the schema would send it.

    The closing fence has to start a line of its own or the reply is an
    unterminated one, which is a different refusal and would make every
    statement below a test of this helper.
    """
    ended = body if body.endswith("\n") else body + "\n"
    return f"Here is the file.\n\n```{info}\n{ended}```\n"


def test_a_json_file_shaped_like_a_carrier_survives_the_fallback() -> None:
    """The finding, on the file the module docstring says is already handled.

    Byte equality against the file the worker sent, because every weaker
    assertion passes on the truncation: the result is still a string, it is
    still non-empty, and it is still exactly what one of the file's own fields
    said.
    """
    parsed = parse_pinned(_fenced(MANIFEST), response_schema=SCHEMA, target=JSON_TARGET)

    assert isinstance(parsed, ParsedFile), f"a real `.json` file was refused: {parsed}"
    assert parsed.content == MANIFEST, (
        f"the `.json` file was unwrapped to one of its own fields: {parsed.content!r}"
    )


def test_a_json_file_with_no_other_field_survives_too() -> None:
    """The narrower case, so the fix cannot rest on "it had a second key".

    A one-field object is the shape a carrier has, and it is also a perfectly
    ordinary ``.json`` file. What separates them is where the bytes are going,
    which is the rule this file is about.
    """
    parsed = parse_pinned(_fenced(BARE), response_schema=SCHEMA, target=JSON_TARGET)

    assert isinstance(parsed, ParsedFile), f"a real `.json` file was refused: {parsed}"
    assert parsed.content == BARE, (
        f"a one-field `.json` file was read as an envelope: {parsed.content!r}"
    )


def test_the_field_that_gets_opened_is_the_one_the_schema_pinned() -> None:
    """The same defect from the other side: the wrong field was being read.

    The caller pinned ``file``. The fallback read ``content``, because that is
    what a reader with no target falls back to — so a reply that was never an
    envelope for the pinned field was opened anyway, against a name nobody
    asked for. ``_schema_field`` exists precisely so this cannot happen: *"the
    schema is the caller's"*.
    """
    parsed = parse_pinned(
        _fenced(BARE), response_schema=NAMED_SCHEMA, target=JSON_TARGET
    )

    assert isinstance(parsed, ParsedFile), f"a real `.json` file was refused: {parsed}"
    assert parsed.content == BARE, (
        f"the reply was unwrapped through `content` when the pinned field was "
        f"`file`: {parsed.content!r}"
    )


# --- the controls: what the fallback is for, and what it protects ----------


def test_a_fenced_carrier_for_a_python_target_is_still_unwrapped() -> None:
    """The case the fallback exists for, and the one a lazy fix would break.

    A backend that ignored ``response_format`` but answered in JSON anyway sends
    the object inside a fence. Refusing to open it would write a JSON blob into
    a ``.py`` file, and stopping there would make pinning a schema cost an
    attempt on exactly the cheap local rungs it was added to help.
    """
    parsed = parse_pinned(
        _fenced(json.dumps({"content": PY_FILE})),
        response_schema=SCHEMA,
        target=PY_TARGET,
    )

    assert isinstance(parsed, ParsedFile), f"a fenced carrier was refused: {parsed}"
    assert parsed.content == PY_FILE, (
        f"the carrier was written into the `.py` file verbatim: {parsed.content!r}"
    )


def test_a_declining_carrier_is_judged_on_what_it_holds() -> None:
    """What the fallback's comment protects, stated as its own test.

    #174's refusal must be reached *through* the envelope: a worker that
    declined inside a schema-shaped answer has declined, and the judgement is
    made on the file, not on the carrier. A fix that restored the target by
    handing it to the early check would refuse this at the wrong layer — with a
    message about a data blob — and would refuse the control above with it.
    """
    parsed = parse_pinned(
        _fenced(json.dumps({"content": "# I cannot complete this task.\n"})),
        response_schema=SCHEMA,
        target=PY_TARGET,
    )

    assert isinstance(parsed, ReplyError), f"a refusal became a file: {parsed}"
    assert parsed.code == "refusal", (
        f"the decline was refused as {parsed.code!r} rather than as #174's "
        f"named outcome, so escalation cannot tell it from a failed check"
    )


def test_a_bare_status_object_for_a_python_target_is_still_a_refusal() -> None:
    """#174 unchanged where no envelope is involved at all.

    ``{"status": "blocked"}`` holds no ``content`` field, so nothing opens it;
    it is a data blob bound for a ``.py`` file, and that is the whole of #174.
    """
    parsed = parse_pinned(
        _fenced(json.dumps({"status": "blocked"})),
        response_schema=SCHEMA,
        target=PY_TARGET,
    )

    assert isinstance(parsed, ReplyError), f"a refusal became a file: {parsed}"
    assert parsed.code == "refusal"


def test_the_two_wire_shapes_still_produce_the_same_file() -> None:
    """D13's equivalence, which the fix must not spend.

    A backend that honours the schema and one that ignores it have to hand the
    gate the same bytes, trailing newline included, or a run's reproducibility
    becomes a fact about which server answered.
    """
    structured = parse_pinned(
        json.dumps({"content": PY_FILE}), response_schema=SCHEMA, target=PY_TARGET
    )
    fenced = parse_pinned(
        _fenced(PY_FILE, info="python"), response_schema=SCHEMA, target=PY_TARGET
    )

    assert isinstance(structured, ParsedFile), f"the structured reply: {structured}"
    assert isinstance(fenced, ParsedFile), f"the fenced reply: {fenced}"
    assert structured.content == fenced.content == PY_FILE


def test_no_target_still_opens_the_envelope() -> None:
    """The reader with nothing to judge against is unchanged.

    With no target neither rule can run, and an object written verbatim into a
    file this module cannot name is wrong under either reading. That is the one
    place the envelope is opened on the bytes alone, and it stays that way.
    """
    parsed = parse_pinned(_fenced(BARE), response_schema=SCHEMA)

    assert isinstance(parsed, ParsedFile), f"a carrier was refused: {parsed}"
    assert parsed.content == "the whole file\n", (
        f"a carrier with no target to judge it was not opened: {parsed.content!r}"
    )
