"""Citation discipline on the claims register (#118).

ADR-0004 makes a citation a load-bearing part of a claim rather than a
decoration, and the failure that made #109 expensive was citations nobody could
resolve — roughly twenty-five of them pointing into a directory gitignored in
another repository. These pin the two properties that stop that recurring.

A citation is either **vendored** (a path inside this repository, which must
exist) or **pinned** (a URL naming an immutable revision). A GitHub URL on a
branch is neither: ``blob/main/x.md`` resolves to different bytes tomorrow, and
local-ai — where most of this evidence comes from — is an unarchived personal
repository that keeps moving. The branch case is the one worth a test, because
it looks exactly like a working citation right up until it silently isn't.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CLAIMS = sorted((REPO / "records" / "claims").glob("CLM-*.json"))

# A GitHub blob/raw/tree URL: capture the ref between the kind and the path.
_GITHUB_REF = re.compile(
    r"^https://(?:github\.com|raw\.githubusercontent\.com)/"
    r"[^/]+/[^/]+/(?:blob|raw|tree)/(?P<ref>[^/]+)/"
)
# A 40-char SHA, or an abbreviation git itself would accept.
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
# Refs that are emphatically not immutable, spelled out so the failure message
# can say which one was used rather than "not a sha".
_MOVING = frozenset({"main", "master", "HEAD", "develop", "dev", "trunk", "latest"})


def _citations() -> list[tuple[str, str, dict]]:
    """Every (claim id, source path, citation) triple in the register."""
    out = []
    for path in CLAIMS:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for citation in doc.get("citations", []):
            out.append((doc["id"], str(path.relative_to(REPO)), citation))
    return out


def test_the_register_is_not_empty() -> None:
    """A vacuous pass here would hide every property below."""
    assert CLAIMS, "no claim records found — the checks below would all pass empty"
    assert _citations(), "no citations found across the register"


@pytest.mark.parametrize(
    ("claim_id", "url"),
    [(cid, c["url"]) for cid, _, c in _citations()],
    ids=[f"{cid}:{i}" for i, (cid, _, _) in enumerate(_citations())],
)
def test_citation_is_vendored_or_pinned(claim_id: str, url: str) -> None:
    """Every citation resolves to a fixed thing: a file here, or a pinned URL."""
    if not url.startswith(("http://", "https://")):
        target = REPO / url
        assert target.is_file(), (
            f"{claim_id} cites in-repo path {url!r}, which does not exist. "
            "A vendored citation must point at a file that shipped with it."
        )
        return

    match = _GITHUB_REF.match(url)
    if match is None:
        # Not a GitHub content URL — an arXiv id or a release page is immutable
        # by its own convention, and this test is not a link checker.
        return

    ref = match.group("ref")
    assert ref not in _MOVING, (
        f"{claim_id} cites {url!r}, which is pinned to the moving ref {ref!r}. "
        "The bytes behind it change without the claim changing. Use the commit "
        "sha that was actually read."
    )
    assert _SHA.match(ref), (
        f"{claim_id} cites {url!r}, whose ref {ref!r} is not a commit sha. "
        "A tag can be moved and a branch will be; only a sha is evidence."
    )


def test_every_claim_carries_at_least_one_citation() -> None:
    """CLAIM-04's premise: an uncited claim is the thing ADR-0004 forbids."""
    uncited = [
        json.loads(p.read_text(encoding="utf-8"))["id"]
        for p in CLAIMS
        if not json.loads(p.read_text(encoding="utf-8")).get("citations")
    ]
    assert not uncited, f"claims with no citation at all: {uncited}"


def test_vendored_evidence_matches_its_manifest() -> None:
    """The vendored copy is only evidence if it is the bytes that were measured.

    The manifest carries the source commit and a sha256 per file. Without this
    check a vendored tree is just a directory someone said came from somewhere.
    """
    import hashlib

    manifests = sorted((REPO / "records" / "evidence").glob("*/MANIFEST.json"))
    assert manifests, "no vendored evidence manifests found"

    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        root = manifest_path.parent
        assert re.fullmatch(r"[0-9a-f]{40}", manifest.get("source_commit", "")), (
            f"{manifest_path.relative_to(REPO)} has no full source commit — "
            "the vendored bytes cannot be traced back to a revision."
        )
        for entry in manifest.get("files", []):
            if not entry.get("present") or "sha256" not in entry:
                continue
            target = root / entry["path"]
            assert target.is_file(), (
                f"{manifest_path.relative_to(REPO)} lists {entry['path']!r} as "
                "present, but it is not in the vendored tree."
            )
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            assert digest == entry["sha256"], (
                f"{entry['path']!r} does not match the sha256 recorded when it "
                "was vendored — the copy has drifted from what was measured."
            )
