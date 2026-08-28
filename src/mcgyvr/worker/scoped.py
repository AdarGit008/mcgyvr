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
a formatter would put there, so a scoped addition does not fail the gate's
style check on whitespace it never chose.

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

    lines = source.splitlines(keepends=True)
    return "".join(lines[: start - 1]) + fragment + "".join(lines[end:])


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


def _appended(source: str, fragment: str) -> str:
    """``source`` with ``fragment`` added at the end, losing nothing.

    Two blank lines before it: that is where a formatter puts a module-level
    definition, and a scoped addition that fails the gate on blank-line count
    would spend an attempt on whitespace the worker was never shown. An empty
    file gets none of them — a file that starts with two blank lines is a file
    the formatter would immediately change back.
    """
    head = source.rstrip("\n")
    return f"{head}\n\n\n{fragment}" if head else fragment
