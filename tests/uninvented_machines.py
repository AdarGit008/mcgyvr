"""Find the strings that tie the product to a machine it did not invent.

The check in ``tests/test_the_product_names_no_machine_it_did_not_invent.py``
and the command that writes its list share this module. It holds no name of
any machine, card, user or repository: every kind below is a shape, so the
check can live in the product without carrying the words it keeps out.

What is read
------------
Every file git tracks, and every untracked file git does not ignore, except
the five folders that leave the product (:data:`LEAVING`), the list itself,
and the sections of ``CHANGELOG.md`` that belong to a released version (those
are history). A file is read as UTF-8, with any byte that is not replaced; a
symbolic link is read as the path it points at. A path name is read too, as
line 0 of its file.

The kinds
---------
``home-path``
    A home folder of a named user: ``/home/<name>`` or ``/Users/<name>``. The
    placeholders in :data:`PLACEHOLDER_USERS` pass, and so does a name written
    as a placeholder (``<user>``, ``$USER``, ``...``).
``address``
    An IP address that reaches a machine: any IPv4 or IPv6 literal except
    loopback, the unspecified address and the documentation blocks
    (:data:`PASSING_NETWORKS`).
``host``
    A host name where a machine is named: the host of a URL, and the value of
    a ``host``, ``hostname``, ``ssh_host`` or ``ssh_target`` key. It passes
    when it is ``localhost``, a reserved name (``.invalid``, ``.test``,
    ``.example``, ``.localhost``, ``example.com`` and its siblings), docker's
    name for its own host, the word ``host`` itself, or a placeholder
    (``{host}``, ``<host>``, ``$HOST``, ``RUN_HOST``). An address found there
    is left to the ``address`` kind; a Python annotation (``host: str``) is
    not a value. It is a hit when it is one label with no dot,
    since that names a machine on a private network, or when it ends in a
    private-network suffix (:data:`PRIVATE_SUFFIXES`). A private-network
    suffix other than ``.local`` and ``.internal`` is a hit anywhere in the
    text, not only where a host is expected; those two are also parts of
    ordinary code (``threading.local``) and count only where a host is.
``card-model``
    A graphics card model: a vendor's family name followed by a model number
    (the families are in :data:`CARD_FAMILIES`).
``identity``
    An identity digest the product computes for a real machine or unit
    (``rig-``, ``unt-``, ``cmb-`` or ``mch-`` and eight or more hex digits),
    unless its digits are one digit repeated, which is how a placeholder is
    written.
``dev-pointer``
    A pointer into the development repository: its name (the product's own
    name followed by ``-lab``; the README may name it on one line), or a path
    that starts in one of the five folders that leave the product.

What passes by rule
-------------------
Besides the rules of each kind, a hit whose text is a name the product
invented is passed over: every string the invented machines of
``tests/machine_shapes.py`` carry (labels, machine ids, hosts, card and
process names, models), and the unit, rig and fleet names that
``examples/*.yaml`` declare. When ``examples/`` holds no readable file, its
names are simply not passed over; the generator must import, or the check
fails.

What it cannot see
------------------
A machine's name written in prose where no host is expected; a number read on
one machine (a card size, a count) stated as a rule; a dotted host name under
a public top-level domain; a path joined in code (``REPO / "name"``) rather
than written; a card named without its family; and anything encoded,
compressed or split over lines. The development repository keeps its own
check of the owner's words, which sees what a shape cannot.

The list
--------
The product holds such strings today. :data:`LIST_PATH` names every file that
still does, with a count per kind, sorted by path. The test holds that no file
off the list has a hit, that no listed count is exceeded, and that no entry
(file and kind) is listed without a hit. Run this module to rewrite the list
after cleaning::

    uv run --no-sync python -m tests.uninvented_machines --write

It refuses to add a file or a kind, or to raise a count, unless it is given
``--allow-growth``. ``--compare OLD`` reads only two list files (no scan, no
dependency outside the standard library) and fails when the list grew
against OLD; CI runs it against the list on a pull request's base branch.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
LIST_PATH = Path(__file__).resolve().parent / "uninvented_machines_not_yet_cleaned.txt"
LIST_NAME = LIST_PATH.relative_to(REPO).as_posix()

#: The folders that leave the product; not read, and never a place a pointer
#: may lead.
LEAVING = ("archive", "fleet-setup", "okf", "records", "tools")

KINDS = ("address", "card-model", "dev-pointer", "home-path", "host", "identity")

#: Names that stand for any user in a home folder.
PLACEHOLDER_USERS = frozenset({"example", "me", "name", "someone", "user", "x", "you"})

#: Addresses that reach no machine of anyone's: loopback, unspecified, and the
#: blocks RFC 5737 and RFC 3849 reserve for documentation.
PASSING_NETWORKS = tuple(
    ipaddress.ip_network(block)
    for block in (
        "127.0.0.0/8",
        "0.0.0.0/32",
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "::1/128",
        "::/128",
        "2001:db8::/32",
    )
)

#: Suffixes of names that only resolve on a private network.
PRIVATE_SUFFIXES = (
    ".ts.net",
    ".lan",
    ".home.arpa",
    ".localdomain",
    ".intranet",
    ".corp",
    ".private",
    ".local",
    ".internal",
)
_CODE_WORDS = (".local", ".internal")

#: Top-level names and domains reserved so that they name no machine (RFC 2606,
#: RFC 6761), docker's name for the machine it runs on, and the words that stand
#: for any host.
_RESERVED_SUFFIXES = (".invalid", ".test", ".example", ".localhost")
_RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
_PASSING_HOSTS = frozenset({"localhost", "host.docker.internal", "host", "hostname"})

#: Card families whose models are written as the family and a number.
CARD_FAMILIES = (
    "GeForce",
    "RTX",
    "GTX",
    "GT",
    "RX",
    "Quadro",
    "Tesla",
    "Titan",
    "Radeon",
    "Arc",
    "Instinct",
    "MI",
)

_SEP = r"[ \t_|-]*"
_CARD = re.compile(
    r"(?<![A-Za-z0-9])(?:GeForce"
    + _SEP
    + r")?(?:"
    + "|".join(CARD_FAMILIES)
    + r")"
    + _SEP
    + r"(?:MI)?[A-Z]?[0-9]{2,5}(?![0-9])",
    re.IGNORECASE,
)
_HOME = re.compile(r"(?<![\w.~-])/(?:home|Users)/([^\s/\"'`<>(){}\[\]$\\:;,*|=]+)")
_IPV4 = re.compile(r"(?<![\w.])([0-9]{1,3}(?:\.[0-9]{1,3}){3})(?![\w]|\.[0-9])")
_IPV6 = re.compile(r"(?<![\w:.])([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})(?![\w:])")
_URL_HOST = re.compile(
    r"(?<![\w+.-])[A-Za-z][A-Za-z0-9+.-]*://(?:[^\s/@\"'`<>]*@)?"
    r"([^\s/:\"'`?#<>\[\](){},;|\\]+)"
)
_HOST_KEYS = r"(?:host|hostname|ssh_host|ssh_target)"
# A quoted key and a colon (JSON, a Python dict), or a bare key and `=` (a
# keyword argument); the value quoted.
_KEYED_HOST = re.compile(
    r"(?:[\"']" + _HOST_KEYS + r"[\"']\s*:|(?<![\w-])" + _HOST_KEYS + r"\s*=)"
    r"\s*[\"']([^\"'\s]+)[\"']",
    re.IGNORECASE,
)
# A YAML line of its own, the value bare or quoted; also inside a Python
# string that holds YAML. A Python annotation (``host: str``) is not a value.
_YAML_HOST = re.compile(
    r"^\s*-?\s*" + _HOST_KEYS + r":\s*[\"']?([A-Za-z0-9_.:-]+)[\"']?\s*(?:#.*)?$",
    re.IGNORECASE,
)
_ANNOTATIONS = frozenset({"any", "bytes", "none", "object", "str"})
_SUFFIXED = re.compile(
    r"(?<![\w.-])([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*(?:"
    + "|".join(
        re.escape(suffix) for suffix in PRIVATE_SUFFIXES if suffix not in _CODE_WORDS
    )
    + r"))(?![\w.-])",
    re.IGNORECASE,
)
_IDENTITY = re.compile(
    r"(?<![A-Za-z0-9])(?:rig|unt|cmb|mch)-([0-9a-f]{8,})(?![0-9a-z])"
)
_LEAVING_PATH = re.compile(
    r"(?:(?<=\./)|(?<![\w./-]))(?:"
    + "|".join(re.escape(folder) for folder in LEAVING)
    + r")/(?=[\w.*-])"
)
_RELEASED = re.compile(r"^## \[(?!Unreleased\])", re.MULTILINE)


@dataclass(frozen=True)
class Hit:
    """One string of one kind, where it stands (never what it says)."""

    path: str
    line: int
    kind: str

    def where(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}"


def product_name(repo: Path = REPO) -> str:
    """The product's name, from its own ``pyproject.toml``."""
    import tomllib

    with (repo / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["name"])


def _dev_repo_name(repo: Path) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(product_name(repo)) + r"[ \t_-]+lab(?![a-z])",
        re.IGNORECASE,
    )


def _placeholder(name: str) -> bool:
    return (
        any(mark in name for mark in "{}<>$%*")
        or "..." in name
        or re.fullmatch(r"[A-Z_]+", name) is not None
    )


def _is_address(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _address_hit(text: str) -> bool:
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    return not any(
        address in network
        for network in PASSING_NETWORKS
        if network.version == address.version
    )


def _host_hit(host: str) -> bool:
    """Whether a name found where a host stands names a private machine."""
    name = host.strip().rstrip(".").lower()
    if not name or _placeholder(host) or name.isdigit():
        return False
    if name.startswith("[") or _is_address(name):
        return False  # an address; the address kind reads it
    if name in _PASSING_HOSTS or name in _ANNOTATIONS:
        return False
    if name.endswith(_RESERVED_SUFFIXES):
        return False
    if any(
        name == domain or name.endswith("." + domain) for domain in _RESERVED_DOMAINS
    ):
        return False
    if name.endswith(PRIVATE_SUFFIXES):
        return True
    return "." not in name


def _ipv6_candidate(text: str) -> bool:
    """An IPv6 literal worth reading: one group of three hex digits or more,
    so that a slice (``[1::2]``) or a clock time is not taken for one."""
    return any(len(group) >= 3 for group in text.split(":"))


def scan_text(
    path: str,
    text: str,
    *,
    allowed: frozenset[str] = frozenset(),
    dev_repo: re.Pattern[str] | None = None,
) -> list[Hit]:
    """Every hit in one file's text; its path name is read as line 0."""
    dev_repo = dev_repo or _dev_repo_name(REPO)
    hits: list[Hit] = []
    lines = [(0, path), *enumerate(text.splitlines(), start=1)]
    naming_lines = [n for n, line in lines if n and dev_repo.search(line)]
    readme_line = (
        naming_lines[0] if path == "README.md" and len(naming_lines) == 1 else -1
    )

    def add(number: int, kind: str, name: str) -> None:
        if name not in allowed:
            hits.append(Hit(path, number, kind))

    for number, line in lines:
        for match in _HOME.finditer(line):
            user = match.group(1).rstrip(".")
            if (
                user
                and user.lower() not in PLACEHOLDER_USERS
                and not _placeholder(user)
            ):
                add(number, "home-path", match.group(0))
        for match in _IPV4.finditer(line):
            if _address_hit(match.group(1)):
                add(number, "address", match.group(1))
        for match in _IPV6.finditer(line):
            if _ipv6_candidate(match.group(1)) and _address_hit(match.group(1)):
                add(number, "address", match.group(1))
        hosts = [m.group(1) for m in _URL_HOST.finditer(line)]
        hosts += [m.group(1) for m in _KEYED_HOST.finditer(line)]
        hosts += [m.group(1) for m in _YAML_HOST.finditer(line)]
        seen = set()
        for host in hosts:
            if _host_hit(host):
                seen.add(host.lower())
                add(number, "host", host)
        for match in _SUFFIXED.finditer(line):
            name = match.group(1)
            if name.lower() not in seen and _host_hit(name):
                add(number, "host", name)
        for match in _CARD.finditer(line):
            add(number, "card-model", match.group(0))
        for match in _IDENTITY.finditer(line):
            if len(set(match.group(1))) > 1:
                add(number, "identity", match.group(0))
        for match in _LEAVING_PATH.finditer(line):
            add(number, "dev-pointer", match.group(0))
        for match in dev_repo.finditer(line):
            if number == readme_line and not line[match.end() :].startswith("/"):
                continue
            add(number, "dev-pointer", match.group(0))
    return hits


def files(repo: Path = REPO) -> list[str]:
    """The files read: tracked, or untracked and not ignored; not those that
    leave the product, and not the list."""
    listed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            ".",
            *(f":(exclude,top){folder}" for folder in LEAVING),
        ],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", "surrogateescape")
    chosen: set[str] = set()
    for path in listed.split("\0"):
        if not path or path == LIST_NAME or path.split("/", 1)[0] in LEAVING:
            continue
        if os.path.lexists(repo / path):
            chosen.add(path)
    return sorted(chosen)


def text_of(repo: Path, path: str) -> str:
    """What is read of one file."""
    where = repo / path
    if where.is_symlink():
        return os.readlink(where)
    if where.is_dir():  # a submodule or a folder git lists as one entry
        return ""
    text = where.read_bytes().decode("utf-8", "replace")
    if path == "CHANGELOG.md":
        released = _RELEASED.search(text)
        if released:
            text = text[: released.start()]
    return text


def invented_names(repo: Path = REPO) -> frozenset[str]:
    """Names the product invented: its generator's and its examples'."""
    from tests import machine_shapes

    names: set[str] = set(machine_shapes.VENDORS)
    for machine in machine_shapes.shapes():
        names.update((machine.label, machine.machine_id, machine.host))
        for card in machine.cards:
            names.add(card.name)
            names.update(holder.name for holder in card.holders)
        for server in machine.servers:
            names.update((server.kind, server.host, *server.models))
    names.update(_example_names(repo / "examples"))
    return frozenset(names)


def _example_names(examples: Path) -> set[str]:
    import yaml

    names: set[str] = set()
    for path in sorted(examples.glob("*.yaml")) if examples.is_dir() else ():
        try:
            data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if not isinstance(data, Mapping):
            continue
        for section in ("units", "rigs", "fleets"):
            declared = data.get(section)
            if isinstance(declared, Mapping):
                names.update(str(name) for name in declared)
    return names


def scan(repo: Path = REPO) -> list[Hit]:
    """Every hit in the product."""
    allowed = invented_names(repo)
    dev_repo = _dev_repo_name(repo)
    hits: list[Hit] = []
    for path in files(repo):
        hits.extend(
            scan_text(path, text_of(repo, path), allowed=allowed, dev_repo=dev_repo)
        )
    return hits


Counts = dict[str, dict[str, int]]


def counts(hits: Iterable[Hit]) -> Counts:
    """Hits per file, per kind."""
    table: dict[str, Counter[str]] = {}
    for hit in hits:
        table.setdefault(hit.path, Counter())[hit.kind] += 1
    return {path: dict(sorted(table[path].items())) for path in sorted(table)}


def top_level(path: str) -> str:
    return path.split("/", 1)[0] + "/" if "/" in path else "(root files)"


def summary(hits: Sequence[Hit]) -> str:
    """How many files hold how many hits, per kind and per top-level folder."""
    lines = []
    for kind in KINDS:
        of_kind = [hit for hit in hits if hit.kind == kind]
        where = {hit.path for hit in of_kind}
        lines.append(f"  {kind}: {len(of_kind)} hits in {len(where)} files")
    lines.append(
        f"  all kinds: {len(hits)} hits in {len({h.path for h in hits})} files"
    )
    by_folder = Counter(top_level(hit.path) for hit in hits)
    lines.extend(f"  {folder} {n}" for folder, n in sorted(by_folder.items()))
    return "\n".join(lines)


_HEADER = """\
# Files of the product that still name a machine it did not invent, or point
# into the development repository, with how many hits of each kind they hold.
# Paths and counts only, never the text. Sorted by path; one line per file:
#     path<TAB>kind=count[<TAB>kind=count ...]
# This list may only shrink. A file off it may hold no hit, a count may not
# rise, and a file or kind whose hits are gone leaves it. Rewrite it with
#     uv run --no-sync python -m tests.uninvented_machines --write
# The kinds and what passes are in tests/uninvented_machines.py.
"""


def render(table: Counts) -> str:
    lines = [
        "\t".join([path, *(f"{kind}={n}" for kind, n in sorted(kinds.items()))])
        for path, kinds in sorted(table.items())
    ]
    return _HEADER + "".join(f"{line}\n" for line in lines)


def parse(text: str, *, source: str = LIST_NAME) -> Counts:
    """Read a list; a line that is not an entry in the list's form is refused."""
    table: Counts = {}
    previous = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.startswith("#"):
            continue
        where = f"{source}:{number}"
        path, *fields = raw.split("\t")
        if not fields:
            raise ValueError(f"{where}: an entry with no kind")
        if path in table:
            raise ValueError(f"{where}: {path} is listed twice")
        if path <= previous:
            raise ValueError(f"{where}: {path} is out of order after {previous}")
        if path.split("/", 1)[0] in LEAVING or path == LIST_NAME:
            raise ValueError(f"{where}: {path} is a place the check does not read")
        previous = path
        kinds: dict[str, int] = {}
        for field in fields:
            kind, _, value = field.partition("=")
            if kind not in KINDS:
                raise ValueError(
                    f"{where}: {kind!r} is not a kind ({', '.join(KINDS)})"
                )
            if kind in kinds:
                raise ValueError(f"{where}: {kind} is listed twice")
            if not re.fullmatch(r"[1-9][0-9]*", value):
                raise ValueError(
                    f"{where}: {kind} has count {value!r}, not a positive number"
                )
            kinds[kind] = int(value)
        if list(kinds) != sorted(kinds):
            raise ValueError(f"{where}: the kinds of {path} are out of order")
        table[path] = kinds
    return table


def read_list(path: Path = LIST_PATH) -> Counts:
    return parse(path.read_text(encoding="utf-8"), source=path.name)


def growth(old: Counts, new: Counts) -> list[str]:
    """Where ``new`` holds a file, a kind or a count that ``old`` does not."""
    grown = []
    for path, kinds in sorted(new.items()):
        for kind, n in sorted(kinds.items()):
            before = old.get(path, {}).get(kind, 0)
            if n > before:
                grown.append(f"{path}: {kind} {before} -> {n}")
    return grown


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tests.uninvented_machines",
        description="Scan the product for machines it did not invent; "
        "report, rewrite the list, or compare two lists.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="rewrite the list")
    mode.add_argument(
        "--compare",
        metavar="OLD",
        type=Path,
        help="fail if the list grew against OLD (reads the two lists, no scan)",
    )
    parser.add_argument(
        "--allow-growth",
        action="store_true",
        help="with --write: let the list gain a file or a kind, or a count rise",
    )
    args = parser.parse_args(argv)
    if args.allow_growth and not args.write:
        parser.error("--allow-growth goes with --write")
    listed = read_list()
    if args.compare is not None:
        old = parse(args.compare.read_text(encoding="utf-8"), source=str(args.compare))
        grown = growth(old, listed)
        for line in grown:
            print(f"grew: {line}")
        print(
            f"{LIST_NAME}: {len(listed)} files listed, {len(old)} in {args.compare}; "
            + ("it grew" if grown else "it did not grow")
        )
        return 1 if grown else 0
    hits = scan()
    found = counts(hits)
    print(summary(hits))
    grown = growth(listed, found)
    for line in grown:
        print(f"more than listed: {line}")
    if not args.write:
        return 1 if grown or found != listed else 0
    if grown and not args.allow_growth:
        print(
            "refused: the list may only shrink; pass --allow-growth to list the "
            "files above anyway",
            file=sys.stderr,
        )
        return 1
    LIST_PATH.write_text(render(found), encoding="utf-8")
    print(f"wrote {LIST_NAME}: {len(found)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
