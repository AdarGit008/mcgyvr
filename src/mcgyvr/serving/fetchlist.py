"""The fetch list: the JSON document saying exactly which files to download.

A `Want` is a repository at a pinned commit, a path inside it, the sha256 the
bytes must hash to, the byte count and the plain filename the file takes in the
weights folder. This module validates such lists, reads and writes them, builds
them from model knowledge records, and turns them into the program text the
fetcher runs on the far side of `ssh`.
"""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.knowledge.record import ModelRecord, Number, Weights

#: The hub used when HF_ENDPOINT is unset or empty.
HUB = "https://huggingface.co"
#: The command `ssh` runs on the host: the payload arrives on stdin and
#: "mcgyvr-fetch" is argv[0] of the `python3 -` process.
REMOTE_COMMAND = "python3 - mcgyvr-fetch"
#: The variable a Hugging Face token is read from when --hf-token-env is not given.
DEFAULT_TOKEN_ENV = "HF_TOKEN"
#: The variable that replaces HUB, e.g. with a mirror.
ENDPOINT_ENV = "HF_ENDPOINT"
#: The largest fetch list `read` accepts, so a wrong --weights file is refused
#: without holding it whole in memory.
MAX_LIST_BYTES = 1024 * 1024

_KEYS = ("repo", "revision", "file", "sha256", "bytes", "name")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE = re.compile(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*")
_NAME = re.compile(r"[A-Za-z0-9._+-]+")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class FetchListError(ValueError):
    """A fetch list, hub endpoint or token variable that cannot be accepted.

    A ValueError, so a caller validating user input can catch it as one.
    """


def _weights_file_name(model_id: str) -> str:
    """The weights-folder name for a model id: "/" made "_", plus ".gguf"."""
    return f"{model_id.replace('/', '_')}.gguf"


@dataclass(frozen=True)
class Want:
    """One file to fetch, already validated.

    The repo at a pinned commit, the path inside it, the sha256 its bytes must
    hash to, how many bytes that is, and the plain filename it lands under in
    the weights folder.
    """

    repo: str
    revision: str
    file: str
    sha256: str
    bytes: int
    name: str

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
    repo, revision, file, sha256, size, name = (raw[key] for key in _KEYS)
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
    if (
        not isinstance(name, str)
        or _NAME.fullmatch(name) is None
        or name in (".", "..")
    ):
        raise FetchListError(
            f"{where} name {name!r} is not a plain filename inside the weights folder"
        )
    return Want(repo, revision, file, sha256, size, name)


def parse(text: str) -> tuple[Want, ...]:
    """Parse the JSON text of a fetch list into the files it names.

    The document must be an object holding `files` and nothing else, and each
    entry must be an object of exactly the six keys. Two entries that would land
    under the same name are allowed only if they carry the same sha256; where a
    name repeats, the last entry for it is the one returned.
    """
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
    """Read a fetch list file, refusing one that will not be trusted.

    Unreadable, larger than MAX_LIST_BYTES, not UTF-8 or not a valid list is a
    `FetchListError`; valid text is handed to `parse`.
    """
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
    """Write `wants` as fetch list JSON: an object of `files` alone, keys sorted."""
    return json.dumps({"files": [want.as_json() for want in wants]}, sort_keys=True)


def _want_for(weights: Weights, size: Number, name: str) -> Want:
    """A `Want` for one record's weights, its recorded size and landing name.

    The entry goes through `_want`, so a record that would make a fetch list no
    one may act on is refused here, named by `<repo>/<file>`.
    """
    return _want(
        {
            "repo": weights.repo,
            "revision": weights.revision,
            "file": weights.file,
            "sha256": weights.sha256,
            "bytes": int(size.value),
            "name": name,
        },
        f"{weights.repo}/{weights.file}",
    )


def from_records(records: Iterable[ModelRecord]) -> tuple[Want, ...]:
    """A `Want` per model record, sized by its recorded `size_bytes`.

    A record naming no weights is refused, since it names nothing to download.
    Each file lands under the record's model id with "/" made "_" and ".gguf"
    appended, which is not necessarily the hub file's own base name.
    """
    wants: list[Want] = []
    for record in records:
        weights = record.weights
        if weights is None:
            raise FetchListError(
                f"{record.model_id} {record.quant} names no file to download"
            )
        wants.append(
            _want_for(weights, record.size_bytes, _weights_file_name(record.model_id))
        )
    return tuple(wants)


def total_bytes(wants: Iterable[Want]) -> int:
    return sum(want.bytes for want in wants)


def token_variable(named: str | None, env: Mapping[str, str]) -> str:
    """The environment variable a Hugging Face token is to be read from.

    With no name given, DEFAULT_TOKEN_ENV is used. A name given on the command
    line must be a variable name and must be set to a non-empty value in `env`,
    so a token meant to be supplied is not silently missing.
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
    """The hub base URL, HUB unless HF_ENDPOINT in `env` names another.

    A replacement must be https, or plain http only on this machine's loopback,
    because a token may be sent to it. A trailing slash is dropped, since `url`
    builds the rest of the path.
    """
    named = env.get(ENDPOINT_ENV, "").strip()
    if not named:
        return HUB
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
    """The hub URL of one file: `<hub>/<repo>/resolve/<revision>/<file>`.

    Repo, revision and file are each percent-quoted, so the pinned commit in the
    path cannot be read as anything but a revision.
    """
    return (
        f"{hub}/{urllib.parse.quote(want.repo)}/resolve/"
        f"{urllib.parse.quote(want.revision)}/{urllib.parse.quote(want.file)}"
    )


def job(wants: Iterable[Want], hub: str, token_env: str, token: str | None) -> str:
    """The fetcher's job as JSON text: every file with its name, size, hash and
    resolved `url`, plus the token variable's name and the token itself, empty
    when there is none."""
    return json.dumps(
        {
            "files": [
                {**want.as_json(), "name": want.name, "url": url(want, hub)}
                for want in wants
            ],
            "token_env": token_env,
            "token": token or "",
        }
    )


def payload(wants: Iterable[Want], hub: str, token_env: str, token: str | None) -> str:
    """The program text to pipe into `python3 -` on a POSIX host.

    It is the fetcher assembled with the modules it imports
    (:func:`mcgyvr.serving.shipped.fetcher`), ending in a call to its `main`
    with the job (:func:`job`) as a literal.
    """
    from mcgyvr.serving import shipped

    return shipped.fetcher(job(wants, hub, token_env, token)).decode("utf-8")
