"""The cache exists to make exploration cost amortize across tasks, so these
tests hold it to the three things #52 makes acceptance criteria — a second task
on an unchanged repository skips the build, a changed file invalidates its own
entries and no others, and a stale index can never serve a deleted path — plus
the bound and the explicit clear the scope calls for.

The property underneath all of them is equivalence: a cached build must produce
the same index a fresh one would. That is asserted directly rather than
inferred, because every other guarantee here is worthless if the fast path
quietly returns something different.

Every test points the cache at a ``tmp_path`` directory. None of them touch the
real cache under ``$XDG_CACHE_HOME``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.orchestrator.cache import (
    CACHE_VERSION,
    build_index_cached,
    cache_path,
    clear,
    prune,
)
from mcgyvr.orchestrator.index import build_index


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def init_repo(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    return repo


def seeded(repo: Path) -> Path:
    """A small repository with symbols in two languages and a plain-text file."""
    init_repo(repo)
    (repo / "a.py").write_text("def alpha():\n    return 1\n")
    (repo / "b.py").write_text("def beta():\n    alpha()\n")
    (repo / "c.js").write_text("function gamma() { return 2; }\n")
    (repo / "notes.txt").write_text("no grammar here\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    return repo


# --- the equivalence property ----------------------------------------------


def test_cached_build_equals_a_fresh_build(tmp_path: Path) -> None:
    """A cache hit must be indistinguishable from doing the work."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"

    fresh = build_index(repo)
    build_index_cached(repo, directory=cache)  # populate
    cached = build_index_cached(repo, directory=cache).index

    assert [f.path for f in cached.files] == [f.path for f in fresh.files]
    assert [f.lines for f in cached.files] == [f.lines for f in fresh.files]
    assert [f.language for f in cached.files] == [f.language for f in fresh.files]
    assert cached.symbols.all() == fresh.symbols.all()
    assert cached.search("alpha") == fresh.search("alpha")
    assert cached.stats.files_indexed == fresh.stats.files_indexed
    assert cached.stats.bytes_indexed == fresh.stats.bytes_indexed
    assert cached.stats.symbol_count == fresh.stats.symbol_count
    assert cached.stats.languages == fresh.stats.languages
    assert cached.stats.degraded_extensions == fresh.stats.degraded_extensions


def test_cached_symbols_carry_their_path(tmp_path: Path) -> None:
    """The path is the cache key, so it must be restored onto every symbol."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    index = build_index_cached(repo, directory=cache).index
    definitions = index.symbols.definitions("alpha")
    assert [(s.path, s.line, s.detail) for s in definitions] == [
        ("a.py", 1, "function")
    ]
    assert [s.path for s in index.symbols.references("alpha")] == ["b.py"]


# --- acceptance: a second task skips the build ------------------------------


def test_second_build_reuses_every_file(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"

    first = build_index_cached(repo, directory=cache).cache
    assert first.loaded is False
    assert first.note == "no cache yet"
    assert first.rebuilt == 4
    assert first.reused == 0
    assert first.written is True

    second = build_index_cached(repo, directory=cache).cache
    assert second.loaded is True
    assert second.reused == 4
    assert second.rebuilt == 0
    assert second.restamped == 0
    assert second.hit_ratio == 1.0


def test_touch_without_change_does_not_reparse(tmp_path: Path) -> None:
    """A rewritten mtime costs a read, not a parse — content decides."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    same = (repo / "a.py").read_text()
    (repo / "a.py").write_text(same)  # identical bytes, new mtime

    stats = build_index_cached(repo, directory=cache).cache
    assert stats.restamped == 1
    assert stats.rebuilt == 0
    assert stats.reused == 3

    # And the refreshed stamp means the next build takes the fast path again.
    assert build_index_cached(repo, directory=cache).cache.reused == 4


# --- acceptance: a changed file invalidates its own entries and no others ---


def test_change_invalidates_only_the_changed_file(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    (repo / "a.py").write_text("def alpha():\n    return 1\n\ndef delta():\n    pass\n")

    result = build_index_cached(repo, directory=cache)
    assert result.cache.rebuilt == 1
    assert result.cache.reused == 3
    assert result.cache.dropped == 0  # a rebuilt file is not a dropped one

    # The changed file's entries are current...
    assert [s.path for s in result.index.symbols.definitions("delta")] == ["a.py"]
    # ...and every other file's survived intact.
    assert [s.path for s in result.index.symbols.definitions("beta")] == ["b.py"]
    assert [s.path for s in result.index.symbols.definitions("gamma")] == ["c.js"]
    assert result.index.search("no grammar")  # notes.txt still text-searchable


def test_removed_symbol_does_not_linger(tmp_path: Path) -> None:
    """Invalidation must drop what was there, not merely add what is new."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    (repo / "a.py").write_text("def replaced():\n    return 1\n")

    index = build_index_cached(repo, directory=cache).index
    assert index.symbols.definitions("alpha") == ()
    assert [s.path for s in index.symbols.definitions("replaced")] == ["a.py"]
    assert index.search("def alpha") == ()


# --- acceptance: a stale index can never serve a deleted path ---------------


def test_deleted_file_is_gone_from_a_cached_build(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    (repo / "a.py").unlink()
    git(repo, "add", "-A")

    result = build_index_cached(repo, directory=cache)
    indexed = {f.path for f in result.index.files}
    assert "a.py" not in indexed
    assert result.index.symbols.definitions("alpha") == ()
    assert result.index.search("def alpha") == ()
    assert result.cache.dropped == 1

    # The entry is gone from the persisted cache too, not just from this build.
    stored = json.loads(cache_path(repo, directory=cache).read_text())
    assert "a.py" not in stored["entries"]


def test_file_becoming_ignored_leaves_the_index(tmp_path: Path) -> None:
    """Enumeration is always fresh, so ignore rules apply to a cached build."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    git(repo, "rm", "-q", "--cached", "c.js")
    (repo / ".gitignore").write_text("c.js\n")

    index = build_index_cached(repo, directory=cache).index
    assert "c.js" not in {f.path for f in index.files}
    assert index.symbols.definitions("gamma") == ()


def test_file_growing_past_the_cap_drops_out(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache, max_file_bytes=64)

    (repo / "a.py").write_text("x = 1\n" * 100)  # now over the cap

    result = build_index_cached(repo, directory=cache, max_file_bytes=64)
    assert "a.py" not in {f.path for f in result.index.files}
    assert result.index.stats.files_skipped_large == 1
    stored = json.loads(cache_path(repo, directory=cache).read_text())
    assert "a.py" not in stored["entries"]


# --- the cache is an accelerator, never load-bearing ------------------------


def test_corrupt_cache_degrades_to_a_full_build(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)
    cache_path(repo, directory=cache).write_text("{not json")

    result = build_index_cached(repo, directory=cache)
    assert result.cache.loaded is False
    assert "unreadable" in result.cache.note
    assert result.cache.rebuilt == 4
    assert result.index.stats.files_indexed == 4


def test_cache_from_another_version_is_discarded(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    path = cache_path(repo, directory=cache)
    stored = json.loads(path.read_text())
    stored["version"] = CACHE_VERSION + 1
    path.write_text(json.dumps(stored))

    result = build_index_cached(repo, directory=cache)
    assert result.cache.loaded is False
    assert result.cache.rebuilt == 4


def test_cache_from_another_repository_is_discarded(tmp_path: Path) -> None:
    """The stored root is checked, so a copied cache file cannot be believed."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    other = seeded(tmp_path / "other")
    # Hand `other` a cache written for `repo`, under `other`'s own key.
    cache_path(other, directory=cache).write_text(
        cache_path(repo, directory=cache).read_text()
    )

    result = build_index_cached(other, directory=cache)
    assert result.cache.loaded is False
    assert "another repository" in result.cache.note
    assert result.cache.rebuilt == 4


def test_two_repositories_do_not_share_a_cache(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    other = seeded(tmp_path / "other")
    cache = tmp_path / "cache"
    assert cache_path(repo, directory=cache) != cache_path(other, directory=cache)

    build_index_cached(repo, directory=cache)
    assert build_index_cached(other, directory=cache).cache.loaded is False
    assert build_index_cached(repo, directory=cache).cache.reused == 4


def test_a_different_size_cap_is_not_reused(tmp_path: Path) -> None:
    """Entries skipped under one cap are missing for a reason the next may not share."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache, max_file_bytes=1 << 20)

    result = build_index_cached(repo, directory=cache, max_file_bytes=32)
    assert result.cache.loaded is False
    assert "size cap" in result.cache.note


def test_refresh_ignores_the_cache_and_rewrites_it(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)

    refreshed = build_index_cached(repo, directory=cache, refresh=True).cache
    assert refreshed.loaded is False
    assert refreshed.rebuilt == 4
    assert refreshed.written is True
    # The rewritten cache is usable again immediately.
    assert build_index_cached(repo, directory=cache).cache.reused == 4


def test_unwritable_cache_directory_still_builds(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where a directory should be")

    result = build_index_cached(repo, directory=blocked)
    assert result.index.stats.files_indexed == 4  # the build succeeded
    assert result.cache.written is False
    assert "not written" in result.cache.note


# --- bounded size and the explicit clear ------------------------------------


def test_prune_evicts_least_recently_used_until_under_the_bound(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    repos = [seeded(tmp_path / f"r{n}") for n in range(3)]
    for repo in repos:
        build_index_cached(repo, directory=cache)

    paths = [cache_path(repo, directory=cache) for repo in repos]
    sizes = [p.stat().st_size for p in paths]
    # Make use order explicit rather than relying on how fast the loop ran:
    # paths[0] is the most recently used, paths[2] the least.
    for age, path in enumerate(paths):
        os.utime(path, ns=(1_000_000_000, (100 - age) * 1_000_000_000))

    # Room for the two newest only.
    removed = prune(sizes[0] + sizes[1], directory=cache)
    assert removed == (paths[2],)
    assert paths[0].exists() and paths[1].exists()
    assert not paths[2].exists()


def test_prune_rejects_a_negative_bound(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="negative"):
        prune(-1, directory=tmp_path)


def test_a_pruned_repository_simply_rebuilds(tmp_path: Path) -> None:
    """Eviction is a performance choice, never a correctness one."""
    repo = seeded(tmp_path / "repo")
    cache = tmp_path / "cache"
    before = build_index_cached(repo, directory=cache).index

    prune(0, directory=cache)
    result = build_index_cached(repo, directory=cache)

    assert result.cache.loaded is False
    assert result.cache.rebuilt == 4
    assert result.index.symbols.all() == before.symbols.all()


def test_clear_removes_one_repository(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    other = seeded(tmp_path / "other")
    cache = tmp_path / "cache"
    build_index_cached(repo, directory=cache)
    build_index_cached(other, directory=cache)

    removed = clear(repo, directory=cache)
    assert removed == (cache_path(repo, directory=cache),)
    assert not cache_path(repo, directory=cache).exists()
    assert cache_path(other, directory=cache).exists()


def test_clear_removes_everything(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    repos = [seeded(tmp_path / f"r{n}") for n in range(3)]
    for repo in repos:
        build_index_cached(repo, directory=cache)
    (cache / "unrelated.txt").write_text("not ours")

    removed = clear(directory=cache)
    assert len(removed) == 3
    assert (cache / "unrelated.txt").exists()  # scoped to what we wrote


def test_clear_on_a_repository_with_no_cache_is_quiet(tmp_path: Path) -> None:
    repo = seeded(tmp_path / "repo")
    assert clear(repo, directory=tmp_path / "cache") == ()


# --- the build still fails loud where it should -----------------------------


def test_non_git_directory_still_fails_loud(tmp_path: Path) -> None:
    from mcgyvr.orchestrator.index import IndexBuildError

    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(IndexBuildError, match="cannot enumerate"):
        build_index_cached(plain, directory=tmp_path / "cache")
