""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mcgyvr.knowledge.record import ModelRecord, Number, Weights

#
HUB = "https://huggingface.co"
#
REMOTE_COMMAND = "python3 - mcgyvr-fetch"
#
FETCHER = Path(__file__).resolve().parent / "fetcher.py"
#
DEFAULT_TOKEN_ENV = "HF_TOKEN"
#
ENDPOINT_ENV = "HF_ENDPOINT"
#
MAX_LIST_BYTES = 1024 * 1024

_KEYS = ("repo", "revision", "file", "sha256", "bytes", "name")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILE = re.compile(r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*")
_NAME = re.compile(r"[A-Za-z0-9._+-]+")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class FetchListError(ValueError):
    ""


def _weights_file_name(model_id: str) -> str:
    ""
    return f"{model_id.replace('/', '_')}.gguf"


@dataclass(frozen=True)
class Want:
    ""

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
    ""
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
    ""
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
    ""
    return json.dumps({"files": [want.as_json() for want in wants]}, sort_keys=True)


def _want_for(weights: Weights, size: Number, name: str) -> Want:
    ""
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


def from_weights(picked: Iterable[tuple[Weights, Number]]) -> tuple[Want, ...]:
    ""
    return tuple(
        _want_for(weights, size, PurePosixPath(weights.file).name)
        for weights, size in picked
    )


def from_records(records: Iterable[ModelRecord]) -> tuple[Want, ...]:
    ""
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
    ""
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
    ""
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
    ""
    return (
        f"{hub}/{urllib.parse.quote(want.repo)}/resolve/"
        f"{urllib.parse.quote(want.revision)}/{urllib.parse.quote(want.file)}"
    )


def payload(wants: Iterable[Want], hub: str, token_env: str, token: str | None) -> str:
    ""
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
