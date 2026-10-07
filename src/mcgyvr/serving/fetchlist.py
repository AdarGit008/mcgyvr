"""What ``serve fetch`` is asked to download, held to a hash before any gate runs.

A fetch list is a JSON object ``{"files": [{repo, revision, file, sha256,
bytes}, ...]}``: each file a weights file of a Hugging Face repository at one
pinned revision (a commit id), its sha256 as the Hub states it, and its size.
These are what the model knowledge records of a downloadable file
(:class:`mcgyvr.knowledge.record.Weights` and ``size_bytes``), and
:func:`from_weights` writes the list from them. The door reads the list
before any gate (:func:`read`), so a file it could not hold to a hash, a
revision that is a branch rather than a commit, or a name that could leave
the weights folder is refused before anything reaches a rig.

On the rig the files land directly in the weights folder under their own
base names (:mod:`mcgyvr.serving.fetcher`), where ``mcgyvr emit`` mounts it
and the scan measured its disk.

The Hub is ``HF_ENDPOINT`` when that is set (the Hub's own variable for a
mirror), else :data:`mcgyvr.knowledge.online.HUB`; a plain ``http`` address
is refused unless it is this machine's loopback, since a token may go to it.
"""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mcgyvr.knowledge import online
from mcgyvr.knowledge.record import ModelRecord, Number, Weights

#: The remote line the fetch step runs; the fetcher and its job come on stdin.
REMOTE_COMMAND = "python3 - mcgyvr-fetch"
#: The fetcher shipped to the rig, read by file: it is never imported there.
FETCHER = Path(__file__).resolve().parent / "fetcher.py"
#: The variable a token is read from when the caller names none.
DEFAULT_TOKEN_ENV = "HF_TOKEN"
#: The Hub's own variable for another address of it (a mirror).
ENDPOINT_ENV = "HF_ENDPOINT"
#: The most bytes of a fetch list the door reads.
MAX_LIST_BYTES = 1024 * 1024

_KEYS = ("repo", "revision", "file", "sha256", "bytes")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE = re.compile(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class FetchListError(ValueError):
    """The fetch list cannot be held to a hash; the message says which entry."""


@dataclass(frozen=True)
class Want:
    """One file a fetch downloads, pinned to its revision and its sha256."""

    repo: str
    revision: str
    file: str
    sha256: str
    bytes: int

    @property
    def name(self) -> str:
        """The name it has in the rig's weights folder: its base name."""
        return PurePosixPath(self.file).name

    def as_json(self) -> dict[str, object]:
        return {key: getattr(self, key) for key in _KEYS}


def _want(raw: object, where: str) -> Want:
    if not isinstance(raw, dict):
        raise FetchListError(f"{where} is not an object of {', '.join(_KEYS)}")
    unknown = sorted(set(raw) - set(_KEYS))
    if unknown:
        raise FetchListError(f"{where} carries {unknown}, which a fetch list has not")
    missing = [key for key in _KEYS if key not in raw]
    if missing:
        raise FetchListError(f"{where} says no {', '.join(missing)}")
    repo, revision, file, sha256, size = (raw[key] for key in _KEYS)
    if not isinstance(repo, str) or _REPO.fullmatch(repo) is None:
        raise FetchListError(f"{where} repo {repo!r} is not an `org/name` repository")
    if not isinstance(revision, str) or _COMMIT.fullmatch(revision) is None:
        raise FetchListError(
            f"{where} revision {revision!r} is not a commit id (40 hex digits); "
            "a branch moves, and a file fetched from it is not the file hashed"
        )
    if (
        not isinstance(file, str)
        or _FILE.fullmatch(file) is None
        or any(part in (".", "..") for part in file.split("/"))
    ):
        raise FetchListError(
            f"{where} file {file!r} is not a plain path inside the repository"
        )
    if not isinstance(sha256, str) or _SHA256.fullmatch(sha256) is None:
        raise FetchListError(
            f"{where} sha256 {sha256!r} is not 64 lower-case hex digits; a file "
            "the door cannot hold to a hash is not fetched"
        )
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise FetchListError(f"{where} bytes {size!r} is not a positive whole number")
    return Want(repo, revision, file, sha256, size)


def parse(text: str) -> tuple[Want, ...]:
    """The fetch list ``text`` holds, or :class:`FetchListError` naming the entry."""
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise FetchListError(f"the fetch list is not JSON: {exc}") from None
    if not isinstance(doc, dict) or set(doc) != {"files"}:
        raise FetchListError("the fetch list is not an object of `files` alone")
    files = doc["files"]
    if not isinstance(files, list):
        raise FetchListError("`files` is not a list")
    wants = tuple(_want(raw, f"files[{index}]") for index, raw in enumerate(files))
    seen: dict[str, Want] = {}
    for want in wants:
        other = seen.setdefault(want.name, want)
        if other is not want and other.sha256 != want.sha256:
            raise FetchListError(
                f"{want.repo}/{want.file} and {other.repo}/{other.file} would both "
                f"land as {want.name} in the weights folder"
            )
    return tuple({want.name: want for want in wants}.values())


def read(path: Path) -> tuple[Want, ...]:
    """The fetch list in the file ``path``."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_LIST_BYTES + 1)
    except OSError as exc:
        raise FetchListError(f"{path} cannot be read: {exc.strerror or exc}") from None
    if len(raw) > MAX_LIST_BYTES:
        raise FetchListError(f"{path} is larger than {MAX_LIST_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise FetchListError(f"{path} is not UTF-8") from None
    return parse(text)


def dump(wants: Iterable[Want]) -> str:
    """``wants`` as a fetch list, the text :func:`parse` reads back."""
    return json.dumps({"files": [want.as_json() for want in wants]}, sort_keys=True)


def from_weights(picked: Iterable[tuple[Weights, Number]]) -> tuple[Want, ...]:
    """The fetch list for each picked file and its recorded size."""
    return tuple(
        _want(
            {
                "repo": weights.repo,
                "revision": weights.revision,
                "file": weights.file,
                "sha256": weights.sha256,
                "bytes": int(size.value),
            },
            f"{weights.repo}/{weights.file}",
        )
        for weights, size in picked
    )


def from_records(records: Iterable[ModelRecord]) -> tuple[Want, ...]:
    """The fetch list for model knowledge records, each naming its file."""
    picked = []
    for record in records:
        if record.weights is None:
            raise FetchListError(
                f"{record.model_id} {record.quant} names no file to download"
            )
        picked.append((record.weights, record.size_bytes))
    return from_weights(picked)


def total_bytes(wants: Iterable[Want]) -> int:
    return sum(want.bytes for want in wants)


def token_variable(named: str | None, env: Mapping[str, str]) -> str:
    """The variable a token is read from: ``named``, or :data:`DEFAULT_TOKEN_ENV`.

    A variable the caller named is refused when it is not a variable name, or
    when it holds nothing: the caller said the download needs a token, and a
    gated download without one fails after the rig is leased. The token itself
    is never read here.
    """
    if named is None:
        return DEFAULT_TOKEN_ENV
    if _VARIABLE.fullmatch(named) is None:
        raise FetchListError(f"--hf-token-env {named!r} is not a variable name")
    if not env.get(named):
        raise FetchListError(
            f"--hf-token-env names {named}, which is empty or not set; put the "
            "Hugging Face token in it, or leave the flag off for a model that "
            "needs none"
        )
    return named


def endpoint(env: Mapping[str, str]) -> str:
    """The Hub's address: ``HF_ENDPOINT``, else the Hub's own."""
    named = env.get(ENDPOINT_ENV, "").strip()
    if not named:
        return online.HUB
    parsed = urllib.parse.urlsplit(named)
    host = parsed.hostname or ""
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if (parsed.scheme == "https" and host) or (parsed.scheme == "http" and loopback):
        return named.rstrip("/")
    raise FetchListError(
        f"{ENDPOINT_ENV}={named!r} is not an https address (plain http is "
        "admitted only for this machine's loopback): a token may be sent to it"
    )


def url(want: Want, hub: str) -> str:
    """Where ``want`` is downloaded from on the Hub at ``hub``."""
    resolved = online.resolve_url(want.repo, want.revision, want.file)
    return hub + resolved[len(online.HUB) :]


def payload(wants: Iterable[Want], hub: str, token_env: str, token: str | None) -> str:
    """The fetcher's source with its job appended: what goes to the rig on stdin."""
    job = {
        "files": [
            {**want.as_json(), "name": want.name, "url": url(want, hub)}
            for want in wants
        ],
        "token_env": token_env,
        "token": token or "",
    }
    source = FETCHER.read_text(encoding="utf-8")
    return f"{source}\n\nraise SystemExit(main({json.dumps(job)!r}))\n"
