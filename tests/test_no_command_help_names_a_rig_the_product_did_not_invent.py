"""No command's help names a rig the product did not invent.

The door's ``--host`` help shipped the owner's own two rig names as if they
were the product's. The scan in
``tests/test_the_product_names_no_machine_it_did_not_invent.py`` did not see
them: it reads shapes only and holds no machine name, and a bare name in a
help sentence (``help="<a> | <b>, as declared in hosts.json"``) has no host
shape (no URL, no ``host:`` key, no ``--host <name>``, no ``<user>@``); it
leaves such a name to the lab guard, which never reads the product's built
help.

So this test builds every command's help as a user sees it: ``mcgyvr`` and
each of its subcommands, the door (``python -m mcgyvr.serving.run`` and its
``serve``, ``read``, ``link`` and ``step``) and ``python -m mcgyvr.docgen``. Each help
must hold none of the owner's rig names, and no hit of a machine kind the
shared scan (:func:`tests.uninvented_machines.scan_text`) counts: an address,
a host, a home folder, a card model or a machine's identity. Its
``dev-pointer`` kind is not held here; a help that names a folder the
product writes under its root is that scan's business. The owner's names
below are assembled from parts, so this file itself holds none.
"""

from __future__ import annotations

import argparse
import re

import pytest

from mcgyvr import docgen
from mcgyvr.cli import build_parser
from mcgyvr.serving import run
from tests import uninvented_machines as um

#: The owner's rigs and the tailnet suffix that reaches them, in parts.
_PRIVATE_NAMES = ("sr" + "v1", "sr" + "v2", "v" + "ps")
_PRIVATE_SUFFIX = ".ts" + ".net"
_NAMED = re.compile(
    r"(?<![\w-])(?:" + "|".join(_PRIVATE_NAMES) + r")(?![\w-])"
    r"|" + re.escape(_PRIVATE_SUFFIX),
    re.IGNORECASE,
)
#: The shared scan's kinds that name a machine.
_MACHINE_KINDS = tuple(kind for kind in um.KINDS if kind != "dev-pointer")


def _mcgyvr_helps(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    """The parser's own help and every subcommand's, depth first."""
    helps = [(parser.prog, parser.format_help())]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                helps += _mcgyvr_helps(sub)
    return helps


def _printed_help(
    capsys: pytest.CaptureFixture[str], main: object, argv: list[str]
) -> str:
    """What ``main(argv + ["--help"])`` prints before it exits 0."""
    assert callable(main)
    with pytest.raises(SystemExit) as exited:
        main([*argv, "--help"])
    assert exited.value.code == 0, (argv, exited.value.code)
    return capsys.readouterr().out


def _every_help(capsys: pytest.CaptureFixture[str]) -> list[tuple[str, str]]:
    helps = _mcgyvr_helps(build_parser())
    for door in ([], ["serve"], ["read"], ["link"], ["step"]):
        prog = " ".join(["mcgyvr.serving.run", *door])
        helps.append((prog, _printed_help(capsys, run.main, door)))
    helps.append(("mcgyvr.docgen", _printed_help(capsys, docgen.main, [])))
    return helps


def test_every_help_is_read(capsys: pytest.CaptureFixture[str]) -> None:
    helps = _every_help(capsys)
    door = [text for prog, text in helps if prog.startswith("mcgyvr.serving.run")]
    assert len(door) == 5 and all("--host" in text for text in door)
    assert len(helps) > 10
    assert len(_MACHINE_KINDS) == len(um.KINDS) - 1


def test_no_help_names_the_owners_rigs(capsys: pytest.CaptureFixture[str]) -> None:
    named = [
        f"{prog}: {match.group(0)!r}"
        for prog, text in _every_help(capsys)
        for match in _NAMED.finditer(text)
    ]
    assert named == []


def test_no_help_names_a_machine_the_shared_scan_sees(
    capsys: pytest.CaptureFixture[str],
) -> None:
    hits = [
        f"{prog}: {hit.kind} on line {hit.line}"
        for prog, text in _every_help(capsys)
        for hit in um.scan_text("help.txt", text)
        if hit.kind in _MACHINE_KINDS
    ]
    assert hits == []


@pytest.mark.parametrize("name", [*_PRIVATE_NAMES, "x" + _PRIVATE_SUFFIX])
def test_the_check_sees_each_name_in_a_help_sentence(name: str) -> None:
    sentence = f"--host HOST  {name.upper()} | other, as declared in hosts.json"
    assert _NAMED.search(sentence)


def test_the_check_passes_a_rig_name_the_product_invented() -> None:
    assert not _NAMED.search("--host HOST  a rig name from hosts.json (rig-a)")
    longer = f"{_PRIVATE_NAMES[0]}0 is not one of them, nor {_PRIVATE_NAMES[2]}s"
    assert not _NAMED.search(f"--host HOST  {longer}")
