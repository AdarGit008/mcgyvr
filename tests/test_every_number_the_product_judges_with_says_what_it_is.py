"""Every number the product judges with says what it is, in one place.

The promise: every number mcgyvr sizes, judges, refuses, waits or picks with
says, in ``data/numbers.json``, what it is: a fact, an estimate, or a choice of
the product. A number nobody has classified fails here.

The file has two blocks for this, beside the estimates it already ships:

* ``covered`` names every python file under ``src/mcgyvr/`` once, as
  ``judging`` (its numbers are classified) or with a reason from the closed
  list :data:`mcgyvr.derived.NOT_JUDGING_REASONS`. A new file that is in
  neither fails :func:`test_every_python_file_of_the_package_is_covered`, so
  the check cannot stop covering the tree the day the tree grows.
* ``constants`` classifies each number a judging file holds, keyed by where it
  lives: ``<file>:<NAME>``, ``<file>:<Class>.<attribute>`` or
  ``<file>:<function>(<parameter>)``. A choice names how a user sets it, or a
  reason from the closed list :data:`mcgyvr.derived.CHOICE_REASONS` why nobody
  needs to; an estimate still in code names the number id it will have in the
  ``numbers`` block when its value moves there.

The files are parsed with :mod:`ast` by path, never imported, so a file no
import statement can reach is read like any other. What is collected from a
judging file, at module level and in every class body at any depth (and inside
the ``if``, ``try``, ``with`` and loop blocks at those levels):

* an assignment, annotated assignment or augmented assignment whose value holds
  a numeric literal anywhere (an ``int`` or ``float``, never a ``bool``),
  inside unary and binary operations, tuples, lists, sets, dicts, subscripts,
  lambdas and calls such as ``frozenset({...})`` or ``Fraction(1, 3)``;
  class-level ones cover dataclass field defaults and enum members;
* the default of a parameter of a function or method defined at those levels
  whose default holds a numeric literal anywhere.

What is deliberately not collected, and so what this check cannot see:

* numeric literals inside the body of a function or method: a number written
  where it is used (a compose healthcheck's retry count, an argv value, a
  floor inside ``max(...)``, a concurrency of one when a unit states no
  width). Collecting them would put every loop bound and index in the list;
  the way to bring one of these under the check is to name it at module level;
* the defaults of functions defined inside functions, and decorator arguments
  (a cache size given to ``lru_cache``);
* a module-level call that is not an assignment, and a number held in a
  string (a duration spelled ``"5s"``);
* the files ``covered`` does not mark ``judging``, and numbers in other data
  files;
* whether a classification is true: calling an estimate a fact passes here.
  The closed lists narrow what can be said; review decides whether it is so.

Nothing here restates a number's value: the file and the code are read.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from mcgyvr import config, contract, derived

SRC = Path(__file__).resolve().parent.parent / "src" / "mcgyvr"
CLI = SRC / "cli.py"

#: The fields each kind of entry may carry beside ``kind`` and ``says``.
_OPTIONAL: dict[str, set[str]] = {
    "fact": set(),
    "choice": {"set_by", "reason", "same_as"},
    "estimate": {"moves_to", "set_by"},
}


def _closed(name: str) -> tuple[str, ...]:
    """A closed list :mod:`mcgyvr.derived` states, checked to be words."""
    listed = vars(derived).get(name)
    assert isinstance(listed, tuple) and listed, f"derived states no {name}"
    assert all(isinstance(words, str) for words in listed), name
    return listed


def _word(name: str) -> str:
    """One word :mod:`mcgyvr.derived` states for the check."""
    said = vars(derived).get(name)
    assert isinstance(said, str) and said, f"derived states no {name}"
    return said


def _once_each(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    made: dict[str, Any] = {}
    for key, value in pairs:
        assert key not in made, f"{key!r} is stated twice in one object"
        made[key] = value
    return made


def _document() -> dict[str, Any]:
    loaded = json.loads(
        derived.shipped_path().read_text(encoding="utf-8"),
        object_pairs_hook=_once_each,
    )
    assert isinstance(loaded, dict)
    return loaded


def _block(name: str) -> dict[str, Any]:
    document = _document()
    assert name in document, f"the shipped file has no {name!r} block"
    block = document[name]
    assert isinstance(block, dict) and block, name
    return block


def _constants() -> dict[str, dict[str, Any]]:
    return _block("constants")


def _covered() -> dict[str, str]:
    return _block("covered")


def _judging() -> list[str]:
    return sorted(path for path, says in _covered().items() if says == _word("JUDGING"))


# --- the collector ----------------------------------------------------------


def _holds_a_number(node: ast.AST) -> bool:
    """Whether ``node`` holds an ``int`` or ``float`` literal anywhere, bools aside."""
    return any(
        isinstance(inner, ast.Constant)
        and isinstance(inner.value, (int, float))
        and not isinstance(inner.value, bool)
        for inner in ast.walk(node)
    )


def _names(target: ast.expr) -> list[str]:
    """The names an assignment target binds, a non-name target as it is spelled."""
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _names(element)]
    if isinstance(target, ast.Starred):
        return _names(target.value)
    if isinstance(target, ast.Name):
        return [target.id]
    return [ast.unparse(target)]


def _defaults(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, ast.expr]]:
    """Every parameter of ``function`` that has a default, with that default."""
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    paired = list(
        zip(
            positional[len(positional) - len(arguments.defaults) :],
            arguments.defaults,
            strict=True,
        )
    )
    paired += [
        (argument, default)
        for argument, default in zip(
            arguments.kwonlyargs, arguments.kw_defaults, strict=True
        )
        if default is not None
    ]
    return [(argument.arg, default) for argument, default in paired]


def _collect(statements: list[ast.stmt], prefix: str, found: set[str]) -> None:
    for statement in statements:
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if statement.value is None or not _holds_a_number(statement.value):
                continue
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            found.update(
                f"{prefix}{name}" for target in targets for name in _names(target)
            )
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.update(
                f"{prefix}{statement.name}({parameter})"
                for parameter, default in _defaults(statement)
                if _holds_a_number(default)
            )
        elif isinstance(statement, ast.ClassDef):
            _collect(statement.body, f"{prefix}{statement.name}.", found)
        else:
            for field in ("body", "orelse", "finalbody"):
                inner = getattr(statement, field, None)
                if isinstance(inner, list):
                    _collect(inner, prefix, found)
            for handler in getattr(statement, "handlers", []):
                _collect(handler.body, prefix, found)
            for case in getattr(statement, "cases", []):
                _collect(case.body, prefix, found)


def numbers_in(source: str) -> set[str]:
    """Where ``source`` holds a number, as ``NAME``, ``Class.attr`` or ``f(param)``."""
    found: set[str] = set()
    _collect(ast.parse(source).body, "", found)
    return found


def _numbers_of(path: str) -> set[str]:
    source = (SRC / path).read_text(encoding="utf-8")
    return {f"{path}:{where}" for where in numbers_in(source)}


def _package_files() -> set[str]:
    return {path.relative_to(SRC).as_posix() for path in SRC.rglob("*.py")}


def _uncovered(files: set[str], covered: dict[str, str]) -> set[str]:
    return files - set(covered)


# --- what the file says -----------------------------------------------------


def test_every_python_file_of_the_package_is_covered() -> None:
    covered = _covered()
    assert _uncovered(_package_files(), covered) == set(), (
        "python files under src/mcgyvr/ are not in the covered block: say "
        "whether each holds numbers that judge, or why it is not covered"
    )
    assert set(covered) - _package_files() == set(), (
        "the covered block names files that do not exist under src/mcgyvr/"
    )


def test_a_new_file_nobody_covered_is_named() -> None:
    covered = _covered()
    invented = "an_invented_module_nobody_wrote.py"
    assert invented not in covered
    assert _uncovered(_package_files() | {invented}, covered) == {invented}


def test_every_file_is_judging_or_says_why_not_from_the_closed_list() -> None:
    allowed = {_word("JUDGING"), *_closed("NOT_JUDGING_REASONS")}
    for path, says in _covered().items():
        assert says in allowed, (path, says)


def test_every_number_a_judging_file_holds_is_classified() -> None:
    constants = _constants()
    missing = sorted(
        where
        for path in _judging()
        for where in _numbers_of(path)
        if where not in constants
    )
    assert missing == [], (
        "these numbers are in judging files and nobody has said what they "
        f"are (add each to the constants block): {missing}"
    )


def test_every_classified_number_is_still_in_a_judging_file() -> None:
    judging = set(_judging())
    held = {where for path in judging for where in _numbers_of(path)}
    for where in _constants():
        path = where.partition(":")[0]
        assert path in judging, f"{where} is in a file the check does not judge"
        assert where in held, f"{where} no longer holds a number in {path}"


def test_every_entry_is_of_a_kind_from_the_closed_list_and_says_what_it_is() -> None:
    for where, entry in _constants().items():
        kind = entry.get("kind")
        assert kind in _closed("NUMBER_KINDS"), (where, kind)
        extra = set(entry) - {"kind", "says"} - _OPTIONAL[kind]
        assert extra == set(), (where, sorted(extra))
        says = entry.get("says")
        assert isinstance(says, str), where
        assert says == says.strip() and says[:1].isupper(), where
        assert says.endswith(".") and " " in says, where


def test_every_choice_says_how_it_is_set_or_why_nobody_needs_to() -> None:
    constants = _constants()
    for where, entry in constants.items():
        if entry["kind"] != "choice":
            continue
        has_setting = "set_by" in entry
        has_reason = "reason" in entry
        assert has_setting != has_reason, (
            f"{where}: a choice names how a user sets it or a reason why "
            "nobody needs to, exactly one of the two"
        )
        if has_reason:
            assert entry["reason"] in _closed("CHOICE_REASONS"), (
                where,
                entry["reason"],
            )
        duplicate = has_reason and entry["reason"] == _word("DUPLICATE_REASON")
        assert ("same_as" in entry) == duplicate, where
        if duplicate:
            assert entry["same_as"] in constants, (where, entry["same_as"])
            assert entry["same_as"] != where, where


def test_every_estimate_in_code_names_the_number_it_moves_to() -> None:
    shipped = _block("numbers")
    for where, entry in _constants().items():
        if entry["kind"] != "estimate":
            continue
        moves_to = entry.get("moves_to")
        assert isinstance(moves_to, str) and moves_to.isidentifier(), where
        assert moves_to not in shipped, (
            f"{where} moves to {moves_to}, which the numbers block already "
            "states: the value in code is then a second home"
        )


def _config_keys(fields: tuple[Any, ...], prefix: str = "") -> dict[str, str]:
    keys: dict[str, str] = {}
    for field in fields:
        name = f"{prefix}{field.name}"
        keys[name] = field.kind
        keys.update(_config_keys(field.block, f"{name}."))
    return keys


def _flags() -> set[str]:
    """Every ``--flag`` the command line declares, read off ``add_argument``."""
    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    return {
        argument.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for argument in node.args
        if isinstance(argument, ast.Constant)
        and isinstance(argument.value, str)
        and argument.value.startswith("--")
    }


def _is_a_key(key: str, keys: dict[str, str]) -> bool:
    """A declared key, or a key inside a declared free-form mapping."""
    if key in keys:
        return True
    return any(
        key.startswith(f"{name}.") and kind == "mapping" for name, kind in keys.items()
    )


def test_every_setting_named_is_one_a_user_can_write() -> None:
    config_keys = _config_keys(config.SCHEMA)
    contract_keys = _config_keys(contract.SCHEMA)
    flags = _flags()
    for where, entry in _constants().items():
        if "set_by" not in entry:
            continue
        source, _, key = str(entry["set_by"]).partition(" ")
        assert source in _closed("SETTING_SOURCES"), (where, source)
        if source == "config":
            assert _is_a_key(key, config_keys), (where, key)
        elif source == "contract":
            assert _is_a_key(key, contract_keys), (where, key)
        else:
            assert key in flags, (where, key)


def test_the_closed_lists_are_short_and_say_what_they_mean() -> None:
    assert _closed("NUMBER_KINDS") == ("fact", "choice", "estimate")
    assert set(_OPTIONAL) == set(_closed("NUMBER_KINDS"))
    assert _word("DUPLICATE_REASON") in _closed("CHOICE_REASONS")
    assert _word("JUDGING") not in _closed("NOT_JUDGING_REASONS")
    for words in (*_closed("CHOICE_REASONS"), *_closed("NOT_JUDGING_REASONS")):
        assert isinstance(words, str) and words == words.strip() and " " in words


# --- the collector catches what it is written for -----------------------------

_INVENTED = """
from fractions import Fraction
from dataclasses import dataclass, field

PLAIN = 7
NEGATIVE = -3
SUM = 4 * 1024
SHARE = Fraction(1, 3)
SET = frozenset({11, 13})
TABLE = {"a": (5, "x")}
TEXT = "no number"
FLAG = True
SPAN: float = 2.5
A, B = 1, 2
CHAIN = "word" * 9
if PLAIN:
    GUARDED = 8
SPAN += 1

def outer(first, second=3, *, third=4.5, fourth="x", fifth=None):
    local = 99
    def inner(depth=6):
        return depth
    return local

class Holder:
    COUNT = 12
    flag: bool = False

    @dataclass
    class Inner:
        size: int = 16
        items: list[int] = field(default_factory=lambda: [17])

    def method(self, width=18):
        inside = 19
        return inside
"""


def test_the_collector_finds_every_shape_it_is_written_for() -> None:
    assert numbers_in(_INVENTED) == {
        "PLAIN",
        "NEGATIVE",
        "SUM",
        "SHARE",
        "SET",
        "TABLE",
        "SPAN",
        "A",
        "B",
        "CHAIN",
        "GUARDED",
        "outer(second)",
        "outer(third)",
        "Holder.COUNT",
        "Holder.Inner.size",
        "Holder.Inner.items",
        "Holder.method(width)",
    }


def test_the_collector_is_blind_where_its_docstring_says() -> None:
    found = numbers_in(_INVENTED)
    for unseen in ("TEXT", "FLAG", "Holder.flag", "outer(fourth)", "outer(fifth)"):
        assert unseen not in found, unseen
    assert not any("local" in where or "inside" in where for where in found)
    assert not any("inner" in where for where in found)
