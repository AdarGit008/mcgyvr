"""A change scoped to one definition edits one definition, and nothing else.

The reply protocol next door is whole-file and only whole-file: one fenced
block becomes the whole of a file. That is the right default — it is the only
shape that needs no patch algebra and cannot half-apply — and it is a poor fit
for the common case. A contract that names one function has just asked a small
model to re-emit every other line of the file *correctly*, and every one of
those lines is a chance to drop a decorator, a helper or an import. The worker
is charged output tokens for bytes nobody wanted changed, and the gate can only
tell you afterwards that something else moved.

So a scoped edit asks for the one definition and splices it back. The rules the
splice is built on:

**The bytes outside the named node are the bytes that were there before.**
Not "equivalent", not "reformatted the same way" — the head and the tail are
carried across as the strings they already were, and only the node's own line
span is replaced. That is what makes "nothing else changed" a property of this
function rather than a hope about the worker's output, and it is why the splice
is by line span rather than by unparsing the tree: :func:`ast.unparse` would
rewrite the entire file into its own idea of Python and lose every comment in
it.

**The node is found by AST, not by pattern.** ``def fetch`` appears in a
docstring, in a string literal and in a comment, and a regex that finds the
wrong one writes into the middle of something. The parser knows which
occurrence is a definition and where it ends, including a body that dedents to
column zero inside a triple-quoted string.

**A decorator belongs to what it decorates.** A definition's ``lineno`` is its
``def`` line, so decorators above it are outside the replaced span and survive —
which is what a worker that re-emitted only the function needs. A worker that
*did* re-emit the decorators is the other half: the span then starts at the
existing node's first decorator, because otherwise the file ends up with the
decorator twice and the second one applies to nothing anybody wrote.

**A node the file does not have is appended, never substituted.** Finding no
match and writing the fragment over the file deletes the file; finding no match
and refusing throws away work that was done correctly. Appending is the only
outcome that loses neither. It goes on at module level with the two blank lines
a formatter would put there — and with the file's own line ending, not ``\\n``,
so a scoped addition does not fail the gate's style check on whitespace it never
chose, nor arrive as a whole-file reformat because half the file now ends its
lines differently from the other half.

**Only module-level definitions are spliced.** The worker's fragment comes back
at column zero; writing it over a method's line span would put a dedented body
inside a class. A scope that names something the file has only as a nested
definition is refused by name rather than mis-spliced, and dotted scopes
(``Class.method``) are not part of this port.

**A refusal is returned, not raised.** local-ai's ``merge_back`` raises
``ApplyError``; here the caller is the same one that already distinguishes a
parsed file from a :class:`~mcgyvr.worker.reply.ReplyError`, and a scoped merge
that cannot proceed has exactly the routing consequence a refused reply has —
one attempt spent, a reason to say. Two vocabularies for that would be two
things for a caller to get right.

Ported from local-ai's ``mvp/orchestrator/apply.py`` (``merge_back``,
``docs/port-from-local-ai.md``, D14).
"""

from __future__ import annotations

import ast

from mcgyvr.lines import LINE_END, parser_lines, terminator
from mcgyvr.runner import StopReason
from mcgyvr.worker.reply import ReplyError, parse_reply

# What a scope may name. Async functions are included because a scope naming
# one is asking about the same thing a caller means by "the function"; a file
# whose author wrote `async def` did not choose a different kind of node.
_Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def apply_scoped(
    *,
    source: str,
    reply: str,
    node: str,
    target: str | None = None,
    stop_reason: StopReason = StopReason.COMPLETE,
) -> str | ReplyError:
    """Merge a reply scoped to ``node`` back into ``source``, or refuse by name.

    ``source`` is the file as it stands and ``reply`` is the worker's answer,
    read through :func:`~mcgyvr.worker.reply.parse_reply` so that a scoped edit
    and a whole-file one agree about where a reply stops being text — including
    the JSON carrier a worker in structured mode sends. ``node`` is the
    definition the contract scoped the task to.

    Returns the merged file — ``source`` with that one definition replaced and
    every other byte untouched — or a
    :class:`~mcgyvr.worker.reply.ReplyError` naming why no merge happened, in
    which case nothing was changed. ``target`` and ``stop_reason`` are
    handed to the parser unchanged: a caller holding a real
    :class:`~mcgyvr.runner.Completion` must pass its stop reason, because a
    truncated fragment spliced into a good file is worse than a truncated whole
    file — the file it damages was correct before the attempt.
    """
    parsed = parse_reply(reply, target=target, stop_reason=stop_reason)
    if isinstance(parsed, ReplyError):
        return parsed
    fragment = parsed.content

    try:
        tree = ast.parse(source)
    except SyntaxError as broken:
        return ReplyError(
            "unparsable-target",
            f"the file being edited does not parse ({broken}), so there is no "
            f"node to splice {node!r} over. A scoped edit needs a file the "
            f"parser can locate a definition in; nothing was changed",
        )

    try:
        emitted = ast.parse(fragment)
    except SyntaxError as broken:
        return ReplyError(
            "unparsable-fragment",
            f"the reply is not parseable Python ({broken}), and splicing it "
            f"into a file that currently parses would break the file rather "
            f"than spend an attempt",
        )

    written = _definition(emitted.body, node)
    if written is None:
        # The alternative is to splice whatever came back over the node the
        # contract named, which deletes that definition and records the task as
        # done. What the worker got wrong should cost the attempt, not the file.
        return ReplyError(
            "scope-mismatch",
            f"the reply defines {_named(emitted.body) or 'nothing'} at module "
            f"level and the scope named {node!r}; splicing it would delete "
            f"{node!r} and put something else where it was",
        )

    # A scoped reply is one definition and nothing else. A worker that ignores
    # that and re-emits the whole file still parses, still contains the named
    # definition, and would splice the entire fragment over the node's line
    # span — every other top-level statement comes back twice, once from the
    # carried head/tail and once from the fragment. It still parses, so the
    # only honest outcome is a named refusal naming what else arrived.
    extras = [statement for statement in emitted.body if statement is not written]
    if extras:
        return ReplyError(
            "scope-mismatch",
            f"the reply re-emitted the whole file rather than just {node!r}: "
            f"besides it, the reply also carries {_describe(extras)}; a scoped "
            f"reply is one definition and nothing else, and splicing the whole "
            f"file over one node's lines would write every other statement "
            f"twice",
        )

    existing = _definition(tree.body, node)
    if existing is None:
        if _defined_anywhere(tree, node):
            return ReplyError(
                "scope-not-top-level",
                f"{node!r} exists in the file only as a nested definition, and "
                f"the reply came back at column zero; writing it over those "
                f"lines would move a body out of what encloses it",
            )
        return _appended(source, fragment)

    end = existing.end_lineno
    if end is None:  # only reachable on a tree not built from parsed text
        return _appended(source, fragment)

    # The worker re-emitted the decorators, so the existing ones are being
    # replaced rather than kept — otherwise the file carries both copies.
    start = existing.lineno
    if written.decorator_list and existing.decorator_list:
        start = min(decorator.lineno for decorator in existing.decorator_list)

    lines = parser_lines(source)
    # The head and tail are the bytes they already were. The fragment is not:
    # ``parse_reply`` normalised it to ``\n`` on entry, so a CRLF file would
    # otherwise end up with the node on LF and everything around it on CRLF — a
    # mixed-ending file the next formatter rewrites whole. Re-terminate the
    # fragment the way ``_appended`` does, and only the fragment.
    ending = terminator(source)
    body = LINE_END.sub(ending, fragment)
    return "".join(lines[: start - 1]) + body + "".join(lines[end:])


def _definition(body: list[ast.stmt], name: str) -> _Definition | None:
    """The module-level function or class called ``name``, if the body has one."""
    for statement in body:
        if isinstance(statement, _Definition) and statement.name == name:
            return statement
    return None


def _defined_anywhere(tree: ast.Module, name: str) -> bool:
    """Whether ``name`` is defined at all, at any depth.

    Only ever asked once the module level has been ruled out, and only to tell
    "the file has no such node" (append it) from "the file has one somewhere
    this cannot splice" (say so). Two different situations that a single
    "not found" would report as the same thing.
    """
    return any(
        isinstance(statement, _Definition) and statement.name == name
        for statement in ast.walk(tree)
    )


def _named(body: list[ast.stmt]) -> str:
    """What ``body`` defines at module level, so a refusal can say what arrived.

    A refusal that names only what was asked for leaves the reader to open the
    reply to find out what came instead.
    """
    names = [s.name for s in body if isinstance(s, _Definition)]
    return ", ".join(repr(name) for name in names)


def _describe(body: list[ast.stmt]) -> str:
    """What ``body`` holds at module level, so a refusal can name the extras.

    Definitions are named by their own name; everything else is named by what
    kind of statement it is, because a refusal that says only "something else"
    sends the reader back into the reply to find out what came along.
    """
    parts: list[str] = []
    for statement in body:
        if isinstance(statement, _Definition):
            parts.append(repr(statement.name))
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            parts.append("an import")
        elif isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign):
            parts.append("an assignment")
        elif isinstance(statement, ast.Expr):
            parts.append("an expression statement")
        else:
            parts.append(f"a {type(statement).__name__}")
    return ", ".join(parts)


def _appended(source: str, fragment: str) -> str:
    """``source`` with ``fragment`` added at the end, losing nothing.

    Two blank lines before it: that is where a formatter puts a module-level
    definition, and a scoped addition that fails the gate on blank-line count
    would spend an attempt on whitespace the worker was never shown. An empty
    file gets none of them — a file that starts with two blank lines is a file
    the formatter would immediately change back.

    Those blank lines, and the fragment's own, end the way *this file's* lines
    end rather than with ``\\n``. :func:`~mcgyvr.worker.reply.parse_reply`
    normalises a reply to ``\\n`` on entry as a stated transformation, so a
    fragment appended verbatim to a CRLF file leaves a file with two kinds of
    line ending: nothing fails to parse, but the next ``ruff format`` or
    :func:`mcgyvr.cleanup.tidy` normalises the whole file, and a change that
    added one definition is recorded as having rewritten every line.
    :func:`mcgyvr.lines.terminator` is where that derivation lives, because
    ``repair`` makes the same splice and B4 was the price of answering "where
    does a line end" twice.

    The splice into a file that has the node does the same for its fragment:
    the head and tail are the bytes they already were, and only the fragment's
    own line endings are re-derived, so a CRLF file gets a CRLF node without
    any byte outside the named node being rewritten.
    """
    ending = terminator(source)
    body = LINE_END.sub(ending, fragment)
    # Every trailing terminator, not just `\n`: a CRLF file left its `\r`
    # behind under `rstrip("\n")`, dangling with no `\n` after it.
    head = source.rstrip("\r\n")
    return f"{head}{ending * 3}{body}" if head else body
