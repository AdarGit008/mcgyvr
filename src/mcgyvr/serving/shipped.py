"""The programs the door ships to a rig, assembled from this checkout's modules.

A rig is asked to run a program it does not have installed: the machine
reader, the weights fetcher, the lease, the native launcher. Each is one
Python program, built here at ship time from the modules it imports, so a
module shipped to a rig imports ``mcgyvr.hostos`` or a ``mcgyvr.hubwire`` name
like any other module, and nothing is copied into it to make it stand alone.

:func:`program` writes one: a short bootstrap that refuses a Python older than
:data:`FLOOR` (macOS's own ``python3`` is 3.9), registers each module under its
own name in ``sys.modules`` with empty parent packages (so nothing installed on
the rig is imported in its place), then runs the main module as ``__main__``.
A module given by :func:`constants` is only the named top-level assignments of
its source (and the names they are built from): the wire module's names, not
its classes, which the reader does not need and an old Python cannot run.

:func:`packed` wraps a program as P2's shipped reader is wrapped: its bytes
zlib-compressed and base85-encoded inside one exec line, kept in
``__shipped__`` so a program that must leave a copy of itself on the rig (the
native launcher's supervisors) has its own bytes. The same checkout always
builds the same bytes: sources are read as they stand and embedded by
``repr``, in the order given.

Standard library only; this module runs on the door, never on the rig.
"""

from __future__ import annotations

import ast
import base64
import zlib
from collections.abc import Iterable, Sequence
from pathlib import Path

#: The oldest Python a shipped program runs on: macOS's own ``python3`` (the
#: Command Line Tools'), which a non-login ssh shell finds first there.
FLOOR = (3, 9)

#: The folder the ``mcgyvr`` package is, which every module path is under.
PACKAGE = Path(__file__).resolve().parent.parent

#: The name a shipped program's own bytes are kept under while it runs.
SELF = "__shipped__"

_BOOT = """\
import sys
if sys.version_info < {floor!r}:
    sys.stderr.write(
        "mcgyvr: this program needs Python {need} or newer, and the python here "
        "is %d.%d\\n" % sys.version_info[:2]
    )
    raise SystemExit(127)
import types


def _mcgyvr_module(name, source):
    parts = name.split(".")
    for end in range(1, len(parts)):
        package = ".".join(parts[:end])
        if package not in sys.modules:
            made = types.ModuleType(package)
            made.__path__ = []
            sys.modules[package] = made
            if end > 1:
                setattr(sys.modules[".".join(parts[: end - 1])], parts[end - 1], made)
    module = types.ModuleType(name)
    module.__file__ = "<shipped>/" + "/".join(parts) + ".py"
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)
    return module


"""


class ShipError(ValueError):
    """A program that cannot be assembled from the modules named."""


def module_path(name: str) -> Path:
    """The source file of the ``mcgyvr`` module `name` (``mcgyvr.serving.rigscan``)."""
    parts = name.split(".")
    if parts[0] != "mcgyvr" or len(parts) < 2:
        raise ShipError(f"{name!r} is not a module of the mcgyvr package")
    return PACKAGE.joinpath(*parts[1:-1], parts[-1] + ".py")


def source(name: str) -> str:
    """The source of the ``mcgyvr`` module `name`, as it stands in this checkout."""
    return module_path(name).read_text(encoding="utf-8")


#: The expression nodes a shipped constant may be built from: literals and the
#: names of other constants, so taking it out of its module changes nothing.
_PLAIN = (
    ast.Constant,
    ast.Tuple,
    ast.List,
    ast.Set,
    ast.Dict,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.operator,
    ast.unaryop,
)


def constants(name: str, wanted: Iterable[str]) -> str:
    """The top-level assignments of module `name` that `wanted` names, as a source.

    Each name is taken with the names its value is built from, in the order
    the module assigns them. A value that is not plain (a call, an attribute,
    a comprehension) is a :class:`ShipError`: it could mean something else
    outside its module.
    """
    text = source(name)
    tree = ast.parse(text)
    assigned: dict[str, ast.stmt] = {}
    values: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name):
            assigned[target.id] = node
            values[target.id] = value
    taken: set[str] = set()
    todo = list(wanted)
    while todo:
        one = todo.pop()
        if one in taken:
            continue
        if one not in values:
            raise ShipError(f"{name} assigns no constant {one!r} at its top level")
        for part in ast.walk(values[one]):
            if not isinstance(part, _PLAIN):
                raise ShipError(
                    f"{name}.{one} is not built from literals and constants "
                    f"alone ({type(part).__name__}); it is not shipped"
                )
            if isinstance(part, ast.Name):
                todo.append(part.id)
        taken.add(one)
    lines = [f"# {name}: {', '.join(sorted(taken))}, as this checkout assigns them"]
    for one, node in assigned.items():
        if one in taken:
            segment = ast.get_source_segment(text, node)
            if segment is None:  # pragma: no cover - parsed from this text
                raise ShipError(f"{name}.{one} has no source")
            lines.append(segment)
    return "\n".join(lines) + "\n"


def program(
    main: str,
    *,
    modules: Sequence[str] = (),
    names: Sequence[tuple[str, Sequence[str]]] = (),
    tail: str = "",
) -> bytes:
    """One program: the bootstrap, each module registered, then `main` run.

    `modules` are whole ``mcgyvr`` modules, registered in the order given (a
    module is registered before one that imports it at its top). `names` are
    ``(module, constants)`` pairs registered as that module holding only those
    constants (:func:`constants`). `main` is the module run as ``__main__``,
    followed by `tail` (a call into it, for a program whose job travels inside
    it).
    """
    floor = ".".join(str(part) for part in FLOOR)
    out = [_BOOT.format(floor=FLOOR, need=floor)]
    for module, wanted in names:
        out.append(f"_mcgyvr_module({module!r}, {constants(module, wanted)!r})\n")
    for module in modules:
        out.append(f"_mcgyvr_module({module!r}, {source(module)!r})\n")
    out.append("del _mcgyvr_module\n")
    text = source(main) + ("\n" + tail if tail else "")
    where = "<shipped>/" + "/".join(main.split(".")) + ".py"
    # Its own compile, so its `from __future__` line is its first statement.
    out.append(f"exec(compile({text!r}, {where!r}, 'exec'))\n")
    return "".join(out).encode("utf-8")


def packed(text: bytes) -> bytes:
    """`text` as a program that unpacks itself: zlib-compressed, base85-encoded,
    inside one exec line, its bytes kept in ``__shipped__``.

    The shipped line is one argument to ssh, and Linux refuses an argument past
    MAX_ARG_STRLEN (128 KiB with 4 KiB pages); the packed program is about a
    third of the source. base85 holds no quote or backslash, so the bytes
    literal needs no escaping.
    """
    blob = base64.b85encode(zlib.compress(text, 9))
    return (
        b"import base64,zlib\n%s=zlib.decompress(base64.b85decode(b'%s'))\nexec(%s)\n"
        % (SELF.encode(), blob, SELF.encode())
    )


def b64(data: bytes) -> str:
    """`data` in base64, as a line of a command or of a rig's stdin."""
    return base64.b64encode(data).decode("ascii")


# --- the programs ----------------------------------------------------------------

#: The wire names the reader states its reading in (``mcgyvr.hubwire``).
READER_WIRE = (
    "HOST_OS",
    "HOST_VERSION_MAX",
    "RESOURCE_NAME_MAX",
    "RESOURCE_GPU",
    "RESOURCE_UNIFIED",
    "RESOURCE_RAM",
    "RESOURCE_CPU",
    "FIGURE_ESTIMATE",
    "FIGURE_READING",
)
#: The modules the native launcher imports, each before any that needs it.
NATIVE_MODULES = (
    "mcgyvr.hostos",
    "mcgyvr.userdir",
    "mcgyvr.fleet.roots",
    "mcgyvr.serving.fetcher",
    "mcgyvr.serving.release",
    "mcgyvr.serving.llamacpp",
    "mcgyvr.serving.gatelib",
    "mcgyvr.serving.localrig",
)


def reader() -> bytes:
    """The machine reader (``rigscan``) with ``hostos`` and its wire names."""
    return program(
        "mcgyvr.serving.rigscan",
        modules=("mcgyvr.hostos",),
        names=(
            ("mcgyvr.hubwire", READER_WIRE),
            ("mcgyvr.fleet.roots", ("HOME_ENV", "HOME_DIR")),
        ),
    )


def fetcher(job: str | None) -> bytes:
    """The weights fetcher with ``hostos``, ending in a call to its ``main``.

    `job` (JSON text) travels inside the program, which a POSIX rig reads on
    stdin; None reads it from stdin instead, for a Windows rig, where the
    program is written to a file and a job holding a token must not be.
    """
    call = "__import__('sys').stdin.read()" if job is None else repr(job)
    return program(
        "mcgyvr.serving.fetcher",
        modules=("mcgyvr.hostos",),
        tail=f"raise SystemExit(main({call}))\n",
    )


def lease() -> bytes:
    """The lease (``leasefile``) with ``hostos``: one operation per run."""
    return program("mcgyvr.serving.leasefile", modules=("mcgyvr.hostos",))


def native() -> bytes:
    """The native launcher with the modules it imports, run by its verbs."""
    return program("mcgyvr.serving.native", modules=NATIVE_MODULES)
