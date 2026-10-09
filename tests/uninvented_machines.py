"""Find the strings that tie the product to a machine it did not invent.

The check in ``tests/test_the_product_names_no_machine_it_did_not_invent.py``
and the command that writes its list share this module. It holds no machine
name, no real card model, no real user's name and no name of a repository:
every kind below is a shape. It does hold the names of card families and of
the vendors that write them (:data:`CARD_FAMILIES`, :data:`CARD_VENDORS`),
the user names that stand for any user or for the CI runner
(:data:`PLACEHOLDER_USERS`), and the names of the four folders that leave the
product (:data:`LAB_FOLDERS`).

What is read
------------
Every file git tracks, and every untracked file git does not ignore (it
ignores the writer's temporary file), except the folders in :data:`UNREAD`,
the list itself, and ``CHANGELOG.md`` from its first heading that names a
released version, as the release script reads a heading (released sections
are history; a release moves the open section's hits out of what is read).
A file is read as UTF-8, a byte that is not UTF-8 replaced; a symbolic link
is read as the path it points at. A path name is read too, as line 0 of its
file.

:data:`UNREAD` holds the folders that leave the product, while they are in
it: a test fails once one of them holds no tracked file, and that folder is
then dropped from :data:`UNREAD` and read again. :data:`LAB_FOLDERS` stays
as it is: a pointer into one of its folders is a hit whether that folder is
read or not.

The kinds
---------
A name passes by the rules of its kind or not at all; no list of allowed
names exists.

``home-path``
    A home folder of a named user: ``/home/<name>``, ``/Users/<name>`` or
    ``~<name>/``. The names in :data:`PLACEHOLDER_USERS` pass, and so does a
    name written as a placeholder (``<user>``, ``$USER``, ``...``) or in
    capitals only (``/home/USER``).
``address``
    An IP address outside loopback, the unspecified address and the
    documentation blocks (:data:`PASSING_NETWORKS`): an IPv4 literal of four
    decimal parts, leading zeros read as the number they write; and an IPv6
    literal that has a group of three hex digits or more, unless it is
    decimal digits only right after a name, a call or a subscript and ``[``
    (a slice, ``x[100::2]``). Not read in lock files (:data:`LOCK_FILES`),
    nor after a version comparison (``==``) or a version key (``version``,
    alone or after ``_``: ``__version__``, ``node_version``), where four
    numbers are a version.
``host``
    A host name where a machine is named: the host of a URL; the value of a
    ``host``, ``hostname``, ``ssh_host`` or ``ssh_target`` key, quoted, or on
    a YAML line of its own (a user before ``@`` allowed), or unquoted after
    ``=`` (spaces around it allowed) outside Python sources; the value of
    ``--host``; and the machine of a ``<user>@<name>``, the user by name or as
    a variable (``$USER``, ``${USER}``, ``{user}``), after ``ssh`` and its
    options (``-p 22``, ``-p22``, ``-oName=value``, ``--``), after any
    one-dash option and its value or after ``--`` (``-o Name=value
    <user>@<name>``), quoted on its own (``"<user>@<name>"``), or before
    ``:`` and a path that does not start with ``//`` (a copy's source or
    target); and a name with no user before ``:`` and an absolute path or
    one under ``~/`` (a copy's ``<name>:/srv/x``). A digest after ``@``
    (``sha256:``, ``SHA256:``, ``blake3:``) is no machine in the rules with
    a user. It passes when it is ``localhost`` or
    the generic local name under ``.localdomain``, a reserved name
    (``.invalid``, ``.test``, ``.example``, ``.localhost``, ``example.com``
    and its siblings), docker's name for its own host, the words ``host``
    and ``hostname``, a Python annotation (``host: str``), a placeholder
    (``{host}``, ``<host>``, ``$HOST``, ``RUN_HOST``), or digits with dots,
    dashes or underscores (a date, a version). An address is left to the
    ``address`` kind; a scheme that names no host (``file://``) gives none.
    A name two of these rules find at one place is one hit. It is a hit
    when it is one label with no dot, or ends in a private-network suffix
    (:data:`PRIVATE_SUFFIXES`). The suffixes in :data:`ANYWHERE_SUFFIXES`
    are hits anywhere in the text, before a full stop too, except on a line
    where a rule above found the same name.
``card-model``
    A graphics card model: a family written as vendors write it (capitals,
    or a capitalised name, :data:`CARD_FAMILIES`), a vendor's name before it
    allowed, followed by a model number of two to five digits; or a
    lower-case ``rtx`` or ``gtx`` before the number, joined to it or after a
    space, ``_`` or ``-``. So a shell ``-gt 10`` or a unit ``rx 1500`` is
    not one.
``identity``
    An identity digest the product computes for a machine or unit:
    ``rig-``, ``unt-``, ``cmb-`` or ``mch-`` and eight or more hex digits,
    or eight or more hex digits as the value of an id key
    (:data:`ID_KEYS`), a prefix to the key allowed (``os_machine_id``);
    unless the digits are one digit repeated, which is how a placeholder is
    written.
``dev-pointer``
    A pointer into the development repository: its name (the product's own
    name followed by ``-lab``; the README may name it on one line); a path
    that starts in one of :data:`LAB_FOLDERS`, with no path before it,
    including the bare folder (``<folder>/`` then a space, a quote or a
    backtick); an import from one of them (``from <folder>.x import``,
    ``import <folder>.x``, ``python -m <folder>.x``); and a path joined to
    one of them in code with ``/`` (``REPO / "<folder>"``). The names in
    :data:`NOT_POINTERS` are not pointers, each for the reason given there.

Hits by design, not false alarms: a netmask; a public resolver's address;
the link-local address clouds serve metadata on; a container's name as a
URL host (``http://<container>:port``); an invented single-label host a test
uses as input; a quoted ``<name>@<word>`` where the word is no machine (a
name and a date written in words), and a package's ``<name>@<tag>`` quoted
or after a one-dash option (``npx -y <pkg>@latest``, ``git commit -m
"<a>@<b>"``); an unquoted ``host = <word>`` outside Python sources that is
no setting (a variable in JavaScript or TypeScript, a notebook, a Python
script with no extension, prose); a key that ends in an id key
(``config_unit_id``); a card series named in lower case by ``rtx`` or
``gtx`` and two digits; a slice of decimal digits and ``::`` written after a
comma or a space or on a string literal, and a scoped name of three or four
hex letters on each side of ``::``; a docker volume's name before ``:`` and
an absolute path (``-v <volume>:/data``); the home folder of a cloud image's
default user; a made-up digest that is not one digit repeated; and a leaving
folder's name joined to any base in code, a temporary folder included, since
the join does not know its base.

What it cannot see
------------------
It is a net for careless mistakes, not for evasion: a name written in
capitals where the kind reads lower case, split over lines or strings,
encoded or compressed passes. It also does not see:

- ``ssh <name>`` without a user: in the product's shell scripts every
  ``ssh`` followed by a word is prose, a comment or a loop list; nor a bare
  ``<user>@<name>`` with no ``ssh``, option, quote or path beside it; nor a
  copy's ``<user>@<name>:`` with nothing after the colon and no option
  before it; nor ``ssh-copy-id``, ``sftp`` or ``mosh`` with no option before
  the destination; nor a jump host given without a user (``-J <name>``);
  nor a copy's ``<name>:dir/`` with no user and a relative path;
- a machine's name in prose where no host is expected, or under keys other
  than those above (``server:``, ``rig:``, ``hosts: [...]``), or as a
  constant (``DEFAULT_HOST = "name"``), or as ``name:8080``; nor a host key
  with a space before its colon (``host : name``), with an annotation before
  its value (``host: str = "name"``), or on a YAML line inside a one-line
  string (``"host: name\\n"``); nor a prefixed key (``<PREFIX>_HOST=<name>``),
  make's ``host ?= <name>`` and ``host := <name>``, a shell test
  (``[ "$host" = <name> ]``) or an object literal (``{host: <name>}``);
- a home folder under ``/root/`` (a container's path in the product), on
  Windows (``C:\\Users\\<name>``), after a path (``/mnt/home/<name>``), or of
  a placeholder user name used for a real one;
- an IPv4 address written as an integer, in hex, or with a letter or ``_``
  beside it; an IPv6 address whose groups are all shorter than three digits,
  or of decimal digits only written as a subscript;
- a dotted host name under a public top-level domain, and a name ending in
  ``.local``, ``.internal``, ``.corp``, ``.intranet`` or ``.private`` outside
  a host position;
- a card named by its number alone, by vendor and number, by a letter and a
  number (``A100``), or in lower case with a space, ``rtx`` and ``gtx``
  aside, which are read with one space but not with two, a tab, or a capital
  first letter only;
- a bare 64-digit digest under no id key, and an id prefix in capitals or
  joined with ``_`` (``rig_<hex>``); a machine id under ``machine-id:`` or
  ``machineId``, as a bytes value (``b'<hex>'``), or as 32 hex digits under
  no key;
- a leaving folder cited after a path (``$REPO/<folder>/x``) or in capitals;
  joined by ``Path("<folder>")``, ``joinpath`` or ``os.path.join``; named as
  one item of a list of paths (a type checker's ``files``); or imported or
  run bare (``import <folder>``, ``-m <folder>``);
- the development repository's name with no separator, with a dot, as a
  plural, or with a hyphen that is not ASCII;
- a number read on one machine (a card size, a count) stated as a rule.

The list
--------
:data:`LIST_PATH` names every file that holds hits today, with a count per
kind, in two sections: "not yet cleaned" and "kept on purpose" (a file that
needs such strings as inputs). The test demands that the scan finds exactly
the files, kinds and counts listed. A hit replaced by another of the same
kind in a listed file keeps the count and passes; that is what it does not
hold. A path is listed as it is, also when the path itself is a hit.
Rewrite the list after cleaning::

    uv run --no-sync python -m tests.uninvented_machines --write

It refuses to add a file or a kind, or to raise a count, unless it is given
``--allow-growth``; a new file goes to the first section, and no entry moves
between sections: a person moves it. A renamed file is a new file to it, so
a person renames the entry by hand. It builds the whole list first and
replaces the file in one step. A file name the list cannot hold (a byte that
is not UTF-8, a tab, a line break, a leading ``#``) is refused by name.
``--compare OLD`` reads only two list files (no scan, no dependency outside
the standard library) and fails when the list grew against OLD; CI runs it
against the list on a pull request's base branch. It reads OLD by its
entries alone, whatever its comment lines say, so a change of the headers is
not growth. The list itself is refused, by the test and by every mode, when
it is not in the form ``--write`` writes (line endings aside), a comment line
included. The command runs as ``python -m tests.uninvented_machines`` or by
its file path.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIST_PATH = Path(__file__).resolve().parent / "uninvented_machines_not_yet_cleaned.txt"
LIST_NAME = LIST_PATH.relative_to(REPO).as_posix()

#: The folders that leave the product: never a place a pointer may lead,
#: whether they are read or not.
LAB_FOLDERS = ("archive", "fleet-setup", "records", "tools")

#: The folders not read, while they are in the product. The four folders have
#: left the product, so nothing is excluded: a file is read again.
UNREAD: tuple[str, ...] = ()

KINDS = ("address", "card-model", "dev-pointer", "home-path", "host", "identity")

#: Names that stand for any user in a home folder, and the name of the CI
#: runner's user, whose home folder every checkout on CI has.
PLACEHOLDER_USERS = frozenset(
    {"example", "me", "name", "runner", "someone", "user", "x", "you"}
)

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

#: Files of pinned package versions: four numbers there are a version.
LOCK_FILES = frozenset({"uv.lock", "package-lock.json"})

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
#: The suffixes read anywhere in the text; the others are also parts of
#: ordinary code (``threading.local``, ``self.private``) and count only
#: where a host stands.
ANYWHERE_SUFFIXES = (".ts.net", ".lan", ".home.arpa", ".localdomain")

#: Top-level names and domains reserved so that they name no machine (RFC 2606,
#: RFC 6761).
_RESERVED_SUFFIXES = (".invalid", ".test", ".example", ".localhost")
_RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
#: This machine's names, docker's name for the machine it runs on, and the
#: words that stand for any host.
_PASSING_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "host.docker.internal",
        "host",
        "hostname",
    }
)
#: Values where a host stands that are Python annotations (``host: str``),
#: not host names.
_ANNOTATIONS = frozenset(
    {"any", "bool", "bytes", "float", "int", "none", "object", "path", "str"}
)
#: URL schemes whose authority is not a machine.
_NO_HOST_SCHEMES = frozenset({"file", "unix", "s3", "gs", "npipe", "data"})

#: Card families, as vendors write them.
CARD_FAMILIES = (
    "RTX",
    "GTX",
    "GT",
    "RX",
    "MI",
    "ARC",
    "GeForce",
    "Quadro",
    "Tesla",
    "Titan",
    "Radeon",
    "Arc",
    "Instinct",
)
#: Vendors' names, as they write them before a family.
CARD_VENDORS = ("NVIDIA", "AMD", "Intel", "GeForce")

#: Keys whose value is an identity digest; a prefix to the key is allowed.
ID_KEYS = (
    "rig_id",
    "unit_id",
    "unt_id",
    "cmb_id",
    "combination_id",
    "mch_id",
    "machine_id",
)

#: Strings shaped like a pointer into a leaving folder that are not one.
NOT_POINTERS = {
    "tools/call": "a method name of the Model Context Protocol",
    "tools/list": "a method name of the Model Context Protocol",
}

_SEP = r"[ \t_|-]*"
_CARD = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:"
    + "|".join(CARD_VENDORS)
    + r")"
    + _SEP
    + r")*(?:(?:"
    + "|".join(CARD_FAMILIES)
    + r")"
    + _SEP
    + r"(?:MI)?[A-Z]?|(?:rtx|gtx)[ _-]?)[0-9]{2,5}(?![0-9])"
)
_HOME = re.compile(r"(?<![\w.~-])/(?:home|Users)/([^\s/\"'`<>(){}\[\]$\\:;,*|=]+)")
_TILDE_HOME = re.compile(r"(?<![\w~/.-])~([A-Za-z_][A-Za-z0-9_.-]*)/")
_IPV4 = re.compile(r"(?<![\w.])([0-9]{1,3}(?:\.[0-9]{1,3}){3})(?![\w]|\.[0-9])")
_IPV6 = re.compile(r"(?<![\w:.])([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})(?![\w:])")
_VERSION_BEFORE = re.compile(
    r"(?:[=<>!~]=\s*v?|(?<![A-Za-z0-9])_*version_*[\"']?\s*[:=]\s*[\"']?v?)$",
    re.IGNORECASE,
)
_URL_HOST = re.compile(
    r"(?<![\w+.-])([A-Za-z][A-Za-z0-9+.-]*)://(?:[^\s/@\"'`<>]*@)?"
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
# A key and `=`, spaces around it allowed, with the value unquoted (a shell
# line, a config file). Not read in Python sources, where the value is a
# variable.
_BARE_KEYED_HOST = re.compile(
    r"(?<![\w-])" + _HOST_KEYS + r"\s*=\s*([A-Za-z0-9_.@-]+)", re.IGNORECASE
)
# A YAML line of its own, the value bare or quoted, a user before `@`
# allowed; also a line of a string that holds YAML over several lines.
_YAML_HOST = re.compile(
    r"^\s*-?\s*" + _HOST_KEYS + r":\s*[\"']?([A-Za-z0-9_.:@-]+)[\"']?\s*(?:#.*)?$",
    re.IGNORECASE,
)
_FLAG_HOST = re.compile(r"(?<![\w-])--host(?:=|\s+)[\"']?([A-Za-z0-9_.-]+)")
# A user by name or as a variable ($USER, ${USER}, {user}).
_USER_AT = r"(?:[A-Za-z0-9_.-]+|\$\{?[A-Za-z_]\w*\}?|\{\w*\})@"
# A machine; a digest after @ (sha256:, SHA256:, blake3:) is not one.
_MACHINE = r"(?!(?i:sha|blake|md)[0-9]+[a-z]?:)([A-Za-z0-9_.-]+)"
# An option, its value joined to it (-p22, -oName=value) or after a space.
_OPTION = r"(?:-[A-Za-z]\S*(?:\s+[^\s@-]\S*)?|--)\s+"
_SSH_USER_HOST = re.compile(
    r"(?<![\w-])ssh\s+(?:" + _OPTION + r")*" + _USER_AT + _MACHINE
)
# A destination after an option and its value, in a command held in one
# string or line (``"-o Name=value <user>@<name> cmd"``).
_OPTION_USER_HOST = re.compile(r"(?<![\w-])" + _OPTION + _USER_AT + _MACHINE)
# A destination quoted on its own, as in an argument list.
_QUOTED_USER_HOST = re.compile(r"[\"'`]" + _USER_AT + _MACHINE + r"[\"'`]")
# A copy's source or target, a path after the colon (not `//`: a URL).
_COPY_USER_HOST = re.compile(
    r"(?<![\w@/.-])" + _USER_AT + _MACHINE + r":(?!//)(?=[\w~/.$-])"
)
# A copy's source or target with no user: a name, then `:` and an absolute
# path or one under `~/`.
_COPY_HOST = re.compile(
    r"(?:^|(?<=[\s\"'`]))([A-Za-z][A-Za-z0-9_.-]+):(?!//)(?=/[\w~.]|~/)"
)
_SUFFIXED = re.compile(
    r"(?<![\w.-])([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*(?:"
    + "|".join(re.escape(suffix) for suffix in ANYWHERE_SUFFIXES)
    + r"))(?![\w-]|\.[\w-])",
    re.IGNORECASE,
)
_IDENTITY = re.compile(
    r"(?<![A-Za-z0-9])(?:rig|unt|cmb|mch)-([0-9a-f]{8,})(?![0-9a-z])"
)
_KEYED_IDENTITY = re.compile(
    r"(?<![\w-])[\"']?(?:\w*_)?(?:"
    + "|".join(ID_KEYS)
    + r")[\"']?\s*[:=]\s*[\"']?([0-9a-f]{8,})(?![0-9a-z])"
)
_LEAVE = "|".join(re.escape(folder) for folder in LAB_FOLDERS)
_LEAVE_MODULES = "|".join(
    re.escape(folder) for folder in LAB_FOLDERS if folder.isidentifier()
)
_LEAVING_PATH = re.compile(
    r"(?:(?<=\./)|(?<![\w./-]))(?:" + _LEAVE + r")/(?=[\w.*\s\"'`-]|$)"
)
_LEAVING_IMPORT = re.compile(
    r"(?<![\w.])(?:from\s+(?:" + _LEAVE_MODULES + r")(?:\.\w|\s+import\b)"
    r"|import\s+(?:" + _LEAVE_MODULES + r")\.\w"
    r"|-m\s+(?:" + _LEAVE_MODULES + r")\.\w)"
)
_LEAVING_JOIN = re.compile(r"/\s*[\"'](?:" + _LEAVE + r")[\"']")
#: Where section 2 starts, in any wording of its header.
_SECTION_2 = "# Section 2"


@dataclass(frozen=True)
class Hit:
    """One string of one kind, where it stands (never what it says)."""

    path: str
    line: int
    kind: str

    def where(self) -> str:
        return f"{shown(self.path)}:{self.line}: {self.kind}"


def shown(path: str) -> str:
    """A path as it can be printed: as it is when the list could hold it."""
    return path if listable(path) else ascii(path)


def listable(path: str) -> bool:
    """Whether a line of the list can hold this path."""
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return not path.startswith("#") and not any(c in path for c in "\t\n\r\v\f")


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


def _ipv4(text: str) -> ipaddress.IPv4Address | None:
    """Four decimal parts as an address, leading zeros read as written."""
    parts = [int(part) for part in text.split(".")]
    if any(part > 255 for part in parts):
        return None
    return ipaddress.IPv4Address(".".join(map(str, parts)))


def _passes(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        address in network
        for network in PASSING_NETWORKS
        if network.version == address.version
    )


def _is_address(text: str) -> bool:
    if re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}", text):
        return True
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _host_hit(host: str) -> bool:
    """Whether a name found where a host stands names a private machine."""
    name = host.strip().rsplit("@", 1)[-1].rstrip(".").lower()
    if not name or _placeholder(host) or re.fullmatch(r"[0-9._-]+", name):
        return False  # empty, a placeholder, or digits: a date, a version
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
    so that a clock time or a short slice (``x[1::2]``) is not taken for
    one. A longer slice is left to :func:`_subscript`."""
    return any(len(group) >= 3 for group in text.split(":"))


def _subscript(line: str, match: re.Match[str]) -> bool:
    """Decimal digits and colons right after a name, a call or a subscript
    and ``[``: a slice (``x[100::2]``), not an address."""
    start = match.start(1)
    return (
        re.fullmatch(r"[0-9:]+", match.group(1)) is not None
        and re.search(r"[\w)\]]\[$", line[:start]) is not None
    )


def scan_text(
    path: str, text: str, *, dev_repo: re.Pattern[str] | None = None
) -> list[Hit]:
    """Every hit in one file's text; its path name is read as line 0."""
    dev_repo = dev_repo or _dev_repo_name(REPO)
    hits: list[Hit] = []
    lines = [(0, path), *enumerate(text.splitlines(), start=1)]
    naming_lines = [n for n, line in lines if n and dev_repo.search(line)]
    readme_line = (
        naming_lines[0] if path == "README.md" and len(naming_lines) == 1 else -1
    )
    name = path.rsplit("/", 1)[-1]
    read_addresses = name not in LOCK_FILES
    python = name.endswith(".py")

    def add(number: int, kind: str) -> None:
        hits.append(Hit(path, number, kind))

    for number, line in lines:
        for match in _HOME.finditer(line):
            user = match.group(1).rstrip(".")
            if (
                user
                and user.lower() not in PLACEHOLDER_USERS
                and not _placeholder(user)
            ):
                add(number, "home-path")
        for match in _TILDE_HOME.finditer(line):
            user = match.group(1)
            if user.lower() not in PLACEHOLDER_USERS and not _placeholder(user):
                add(number, "home-path")
        if read_addresses:
            for match in _IPV4.finditer(line):
                if _VERSION_BEFORE.search(line[: match.start()]):
                    continue
                address = _ipv4(match.group(1))
                if address is not None and not _passes(address):
                    add(number, "address")
            for match in _IPV6.finditer(line):
                if not _ipv6_candidate(match.group(1)) or _subscript(line, match):
                    continue
                try:
                    six = ipaddress.IPv6Address(match.group(1))
                except ValueError:
                    continue
                if not _passes(six):
                    add(number, "address")
        # Each host by where its name starts, so that a name two rules find
        # is one hit: `ssh` with an option before `<user>@<name>`, or a copy
        # with an option before `<user>@<name>:<path>`.
        hosts: dict[int, str] = {}
        for rule, group in (
            (_KEYED_HOST, 1),
            (_YAML_HOST, 1),
            (_FLAG_HOST, 1),
            (_SSH_USER_HOST, 1),
            (_OPTION_USER_HOST, 1),
            (_QUOTED_USER_HOST, 1),
            (_COPY_USER_HOST, 1),
            (_COPY_HOST, 1),
            *(() if python else ((_BARE_KEYED_HOST, 1),)),
        ):
            for m in rule.finditer(line):
                at = m.start(group) + m.group(group).rfind("@") + 1
                hosts.setdefault(at, m.group(group))
        for m in _URL_HOST.finditer(line):
            if m.group(1).lower() not in _NO_HOST_SCHEMES:
                hosts.setdefault(m.start(2), m.group(2))
        seen = set()
        for host in hosts.values():
            if _host_hit(host):
                seen.add(host.rsplit("@", 1)[-1].rstrip(".").lower())
                add(number, "host")
        for match in _SUFFIXED.finditer(line):
            if match.group(1).lower() not in seen and _host_hit(match.group(1)):
                add(number, "host")
        for _ in _CARD.finditer(line):
            add(number, "card-model")
        for match in _IDENTITY.finditer(line):
            if len(set(match.group(1))) > 1:
                add(number, "identity")
        for match in _KEYED_IDENTITY.finditer(line):
            if len(set(match.group(1))) > 1:
                add(number, "identity")
        for match in _LEAVING_PATH.finditer(line):
            rest = line[match.start() :]
            if any(
                re.match(re.escape(word) + r"(?![\w/.-])", rest)
                for word in NOT_POINTERS
            ):
                continue
            add(number, "dev-pointer")
        for _ in _LEAVING_IMPORT.finditer(line):
            add(number, "dev-pointer")
        for _ in _LEAVING_JOIN.finditer(line):
            add(number, "dev-pointer")
        for match in dev_repo.finditer(line):
            if number == readme_line and not line[match.end() :].startswith("/"):
                continue
            add(number, "dev-pointer")
    return hits


def files(repo: Path = REPO) -> list[str]:
    """The files read: tracked, or untracked and not ignored; not those in
    :data:`UNREAD`, not the list and not the writer's temporary file."""
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
            *(f":(exclude,top){folder}" for folder in UNREAD),
        ],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", "surrogateescape")
    chosen: set[str] = set()
    for path in listed.split("\0"):
        if not path or path == LIST_NAME or path.split("/", 1)[0] in UNREAD:
            continue
        if os.path.lexists(repo / path):
            chosen.add(path)
    return sorted(chosen)


def tracked_in(folder: str, repo: Path = REPO) -> int:
    """How many files git tracks under one top-level folder."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z", "--", f":(top){folder}/"],
        check=True,
        capture_output=True,
    ).stdout
    return len([p for p in out.split(b"\0") if p])


def text_of(repo: Path, path: str) -> str:
    """What is read of one file."""
    where = repo / path
    if where.is_symlink():
        return os.readlink(where)
    if where.is_dir():  # a submodule or a folder git lists as one entry
        return ""
    text = where.read_bytes().decode("utf-8", "replace")
    if path == "CHANGELOG.md":
        from scripts.release.changelog_notes import released

        lines = text.splitlines(keepends=True)
        for number, line in enumerate(lines):
            if line.startswith("## ") and released(line[3:].strip()) is not None:
                return "".join(lines[:number])
    return text


def scan(repo: Path = REPO) -> list[Hit]:
    """Every hit in the product."""
    dev_repo = _dev_repo_name(repo)
    hits: list[Hit] = []
    for path in files(repo):
        hits.extend(scan_text(path, text_of(repo, path), dev_repo=dev_repo))
    return hits


Counts = dict[str, dict[str, int]]


@dataclass
class Listed:
    """The list: the files not yet cleaned, and those kept on purpose."""

    cleaning: Counts = field(default_factory=dict)
    kept: Counts = field(default_factory=dict)

    def all(self) -> Counts:
        return {**self.cleaning, **self.kept}


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


HEADER = """\
# Files of the product that name a machine it did not invent, or point into
# the development repository, in the places and shapes that
# tests/uninvented_machines.py reads, with how many hits of each kind they
# hold.
# Paths and counts only, never the text of a line; a path that is itself a
# hit is listed as it is. One line per file, sorted by path within its
# section:
#     path<TAB>kind=count[<TAB>kind=count ...]
# The test demands that the scan finds exactly these files, kinds and counts.
# What that does not hold: a hit replaced by another of the same kind in a
# listed file keeps the count and passes. On a pull request CI compares this
# list with the base branch's and fails when a file or a kind was added or a
# count rose.
# After cleaning, rewrite the counts with
#     uv run --no-sync python -m tests.uninvented_machines --write
# It refuses to add a file or a kind, or to raise a count, unless given
# --allow-growth; it puts a new file in the first section and never moves an
# entry between sections, which a person does. A renamed file is a new file
# to it: rename the entry by hand, in its section and in order.
# On a merge conflict in this file: take the base branch's list, then run the
# command above without a flag.
# Any other comment line, and any line not in this form, is refused.
#
# Section 1: not yet cleaned.
"""

KEPT_HEADER = """\
# Section 2: kept on purpose. A file here needs such strings as its inputs;
# a person moves an entry here and says why in the change that moves it.
"""


def _entries(table: Counts) -> str:
    lines = []
    for path, kinds in sorted(table.items()):
        if not listable(path):
            raise ValueError(f"the list cannot hold the file name {path!a}")
        lines.append(
            "\t".join([path, *(f"{kind}={n}" for kind, n in sorted(kinds.items()))])
        )
    return "".join(f"{line}\n" for line in lines)


def render(listed: Listed) -> str:
    """The list's text; a file name it cannot hold is refused by name."""
    return HEADER + _entries(listed.cleaning) + KEPT_HEADER + _entries(listed.kept)


def _parse_entries(lines: list[tuple[int, str]], source: str) -> Counts:
    table: Counts = {}
    for number, raw in lines:
        where = f"{source}:{number}"
        path, *fields = raw.split("\t")
        if not fields:
            raise ValueError(f"{where}: an entry with no kind")
        if path.split("/", 1)[0] in UNREAD or path == LIST_NAME:
            raise ValueError(f"{where}: {path} is a place the check does not read")
        kinds: dict[str, int] = {}
        for item in fields:
            kind, _, value = item.partition("=")
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
        if path in table:
            raise ValueError(f"{where}: {path} is listed twice")
        table[path] = kinds
    return table


def parse(text: str, *, source: str = LIST_NAME) -> Listed:
    """Read a list. Only the text ``--write`` would write is accepted: a
    comment that is not the header, a blank line, a file listed in both
    sections, an order or a spacing of its own are refused."""
    header = HEADER.splitlines()
    kept_header = KEPT_HEADER.splitlines()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    numbered = list(enumerate(lines, start=1))
    if lines[: len(header)] != header:
        wrong = next(
            (
                n
                for n, (a, b) in enumerate(zip(lines, header, strict=False), 1)
                if a != b
            ),
            min(len(lines), len(header)) + 1,
        )
        raise ValueError(f"{source}:{wrong}: not the list's header")
    rest = numbered[len(header) :]
    starts = [
        i
        for i in range(len(rest))
        if [line for _, line in rest[i : i + len(kept_header)]] == kept_header
    ]
    if len(starts) != 1:
        raise ValueError(f"{source}: the header of section 2 is not there once")
    first, second = rest[: starts[0]], rest[starts[0] + len(kept_header) :]
    for number, line in first + second:
        if line.startswith("#") or not line.strip():
            raise ValueError(f"{source}:{number}: a line the list does not write")
    listed = Listed(_parse_entries(first, source), _parse_entries(second, source))
    both = sorted(set(listed.cleaning) & set(listed.kept))
    if both:
        raise ValueError(f"{source}: {both[0]} is in both sections")
    if render(listed) != text:
        for number, (got, want) in enumerate(
            zip(text.split("\n"), render(listed).split("\n"), strict=False), 1
        ):
            if got != want:
                raise ValueError(f"{source}:{number}: not as --write writes it")
        raise ValueError(f"{source}: not as --write writes it")
    return listed


def entries(text: str, *, source: str) -> Listed:
    """A list read by its entries alone, whatever its comment lines say: how
    ``--compare`` reads the base branch's list, so that a change of the
    headers is not growth. Each entry is still refused as the list's own
    would be: an unknown kind, a count that is not positive, or a path the
    check does not read (so a change that stops reading a folder the base
    lists is refused, not taken for a shrink)."""
    parts: tuple[list[tuple[int, str]], list[tuple[int, str]]] = ([], [])
    part = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith(_SECTION_2):
            part = 1
        if line.strip() and not line.startswith("#"):
            parts[part].append((number, line))
    return Listed(_parse_entries(parts[0], source), _parse_entries(parts[1], source))


def read_list(path: Path | None = None) -> Listed:
    path = path or LIST_PATH
    return parse(path.read_text(encoding="utf-8"), source=path.name)


def write_list(listed: Listed, path: Path | None = None) -> None:
    """Replace the list in one step, the whole text built first."""
    path = path or LIST_PATH
    text = render(listed)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.chmod(temporary, 0o644)  # as git checks a file out; mkstemp gives 600
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def rewritten(old: Listed, found: Counts) -> Listed:
    """The list with the counts found: each file stays in its section, a new
    file goes to the first."""
    return Listed(
        cleaning={p: k for p, k in found.items() if p not in old.kept},
        kept={p: k for p, k in found.items() if p in old.kept},
    )


def growth(old: Counts, new: Counts) -> list[str]:
    """Where ``new`` holds a file, a kind or a count that ``old`` does not."""
    grown = []
    for path, kinds in sorted(new.items()):
        for kind, n in sorted(kinds.items()):
            before = old.get(path, {}).get(kind, 0)
            if n > before:
                grown.append(f"{shown(path)}: {kind} {before} -> {n}")
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
    try:
        listed = read_list()
        if args.compare is not None:
            old = entries(
                args.compare.read_text(encoding="utf-8"), source=str(args.compare)
            )
    except ValueError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    if args.compare is not None:
        grown = growth(old.all(), listed.all())
        for line in grown:
            print(f"grew: {line}")
        moved = sorted(set(old.cleaning) & set(listed.kept))
        for path in moved:
            print(f"moved to kept on purpose: {path}")
        print(
            f"{LIST_NAME}: {len(listed.all())} files listed, {len(old.all())} in "
            f"{args.compare}; " + ("it grew" if grown else "it did not grow")
        )
        return 1 if grown else 0
    hits = scan()
    found = counts(hits)
    print(summary(hits))
    grown = growth(listed.all(), found)
    for line in grown:
        print(f"more than listed: {line}")
    if not args.write:
        return 1 if found != listed.all() else 0
    if grown and not args.allow_growth:
        print(
            "refused: the list may only shrink; pass --allow-growth to list the "
            "files above anyway",
            file=sys.stderr,
        )
        return 1
    try:
        write_list(rewritten(listed, found))
    except ValueError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    print(f"wrote {LIST_NAME}: {len(found)} files")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO))  # run by its path: the release script's import
    sys.exit(main())
