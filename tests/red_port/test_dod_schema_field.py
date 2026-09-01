"""F3 — a schema's carrier field is derived from the types a backend honours.

:func:`mcgyvr.worker.reply._schema_field` decides which property of a pinned
response schema holds the file, and it read only a scalar ``"type": "string"``.
JSON Schema lets a field declare its type as an array — ``["string", "null"]``
is the ordinary spelling of a nullable string — and a backend honours that the
same as it honours the scalar. The derivation missed it, so a schema the
backend answered correctly was refused or mis-read as raw text.

The fix reads an array type as its members: a property whose type list contains
``"string"`` is the string field the carrier derivation is looking for.
"""

from __future__ import annotations

import json

from mcgyvr.worker.reply import ReplyError, parse_pinned

TARGET = "src/pkg/fetch.py"
CONTENT = "def fetch(url):\n    return url.strip()\n"


def test_a_nullable_string_field_is_derived_as_the_carrier() -> None:
    schema = {
        "type": "object",
        "properties": {"file": {"type": ["string", "null"]}},
        "required": ["file"],
    }
    reply = json.dumps({"file": CONTENT})

    parsed = parse_pinned(reply, response_schema=schema, target=TARGET)

    assert not isinstance(parsed, ReplyError), (
        f"a schema the backend honoured was refused: {parsed}"
    )
    assert parsed.content == CONTENT
