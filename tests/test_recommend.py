"""The promise and contract of ``mcgyvr recommend``.

PROMISE
-------
``mcgyvr recommend`` is a read-only planner. It re-reads the rigs it is pointed
at over ssh — measuring free VRAM, available RAM, disk and bandwidth at that
moment rather than trusting any stored spec — and, for the ``coding`` profile,
assembles candidate placements from those measured inputs and lets
:func:`mcgyvr.decision.classify` name one. When no decision backend is
reachable, the pick is deterministic (the largest checkpoint among the
candidates that already fit the measured machine) and the plan says so. Every
number in the emitted plan is a measurement the rig or the checkpoint header
made, or a shipped constant; none is invented. The other three profiles
(``chatting``, ``media_gen``, ``other``) are accepted as scaffolds that make
no placement.

WHAT THIS TEST PINS
-------------------
The command is read-only: it reads a rig over the (read-only) ssh scan path —
``mcgyvr.scan.scan_over``'s transport, seen here as ``mcgyvr.scan._ssh`` — and
its plan carries the numbers that transport just measured, never the numbers of
a stored scan.

Models to place come from exactly one of two places:

* ``--model-store <dir>`` — checkpoint files are discovered (``*.gguf`` in that
  directory, over the same read-only ssh seam) and each header is read ON the
  rig, over the same seam, by shipping ``mcgyvr.serving.ggufscan`` to the rig
  as ``python3 -`` (the blob never comes back). When a discovered checkpoint
  fits, the plan recommends **only** from that store.
* no store, or nothing local fits — the plan recommends from a shipped
  HuggingFace catalog, injected here through ``mcgyvr.recommend.load_catalog``,
  and marks those picks downloadable (``model_id``, ``quant``, ``size_bytes``).
  A catalog pick has no header, so only an entry whose shipped size fits the
  measured free VRAM is assembled.

``--profile coding`` makes a real placement (an engine and a checkpoint are
chosen and the decision seam is consulted); the other three values are accepted
but scaffolded (no engine, no decision).

The seams this test substitutes are existing module attributes, chosen so the
command can be exercised without owning hardware:

* ``mcgyvr.scan._ssh`` — the ssh scan/detection transport (the same seam
  ``tests/test_remote_scan.py`` stubs); the header read and the ``*.gguf``
  discovery both answer through it;
* ``mcgyvr.decision.classify`` — the placement decision (resolved as a module
  attribute, so the command must reach it that way, as ``tests/test_compose.py``
  does for ``mcgyvr.compose.classify``);
* ``mcgyvr.availability.probe_endpoint`` — the reachability probe that decides
  whether the decision backend is there before any model is consulted;
* ``mcgyvr.recommend.load_catalog`` — the shipped HuggingFace catalog loader.

``mcgyvr.serving.ggufscan.scan`` is patched in exactly one test to fail if the
command reads a header in-process: the reader must run on the rig, not here.

The plan is the only thing printed to stdout, as one JSON document, and the
command exits 0.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from mcgyvr import availability, cli, decision
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.runner import TransportError
from mcgyvr.serving import ggufscan as ggufscan_module

# Invented, and shaped so the test can tell a measurement from a stored spec and
# from an invented number: free VRAM is a distinctive figure the fake ssh scan
# reports, and the stale stored scan reports a different one.
FREE_MIB = 9001
STALE_MIB = 1111
AVAILABLE_RAM_GB = 48.0
HOST = "box-7"
STORE_DIR = "/models/store"
CHECKPOINT = f"{STORE_DIR}/invented-moe.gguf"
OTHER = f"{STORE_DIR}/invented-dense.gguf"
SIZE_BYTES = 9_876_543_210

ENGINES = ("llama.cpp", "vllm")
PROFILES = ("coding", "chatting", "media_gen", "other")

#: An invented HuggingFace catalog, the same shape ``load_catalog`` returns
#: from ``data/model-catalog.json``. The test injects it through the seam.
FAKE_CATALOG: dict[str, Any] = {
    "schema_version": 1,
    "models": [
        {
            "model_id": "invented-org/invented-moe",
            "quant": "Q4_K_M",
            "size_bytes": SIZE_BYTES,
            "engines": ["llama.cpp", "vllm"],
        },
        {
            "model_id": "invented-org/invented-dense",
            "quant": "Q4_K",
            "size_bytes": 4_000_000_000,
            "engines": ["llama.cpp"],
        },
    ],
}


def scan_json(host: str, free_mib: int) -> str:
    """An invented rig's scan, as ``mcgyvr scan --json`` would print it.

    The card totals close (``total == reserved + used + free``), so
    ``Scan.from_json`` round-trips it, and every number here is invented.
    """
    total_mib = 16384
    reserved_mib = 256
    used_mib = total_mib - reserved_mib - free_mib
    payload: dict[str, Any] = {
        "machine": {"id": f"machine-{host}", "host": host, "kernel": "0.0.0-example"},
        "gpus": [
            {
                "index": 0,
                "name": "Example Card Z",
                "vram": {
                    "total_mib": total_mib,
                    "used_mib": used_mib,
                    "free_mib": free_mib,
                    "reserved_mib": reserved_mib,
                },
            }
        ],
        "memory": {"total_gb": 64.0, "available_gb": AVAILABLE_RAM_GB},
        "cpu": {"cores": 16, "threads": 32},
        "bandwidth": {"measured_gbps": 60.0, "how": "copy loop"},
        "disk": {"path": "/models", "free_gb": 200.0},
        "notes": [],
        "facts": [{"field": "memory.total_gb", "how": "/proc/meminfo"}],
    }
    return json.dumps(payload, indent=2) + "\n"


def fake_header(path: str, size_bytes: int = SIZE_BYTES) -> dict[str, Any]:
    """An invented checkpoint header, as :func:`ggufscan.scan` would return it."""
    blocks = list(range(24))
    return {
        "file": path,
        "size_bytes": size_bytes,
        "arch": "invented-moe",
        "name": "Invented MoE 8x2",
        "n_layer": 24,
        "n_expert": 8,
        "n_expert_used": 2,
        "n_embd": 2048,
        "n_head_kv": 2,
        "n_ctx_train": 65536,
        "bytes_experts": 7_000_000_000,
        "bytes_nonexpert": size_bytes - 7_000_000_000,
        "bytes_total_tensors": size_bytes,
        "placeable_blocks": blocks,
        "expert_blocks": blocks,
        "expert_bytes_by_block": {
            str(b): (400_000_000 if b == 23 else 300_000_000) for b in blocks
        },
        "nextn_blocks": [23],
        "nextn_predict_layers": 1,
        "caching_layers": 24,
        "caching_layers_from": "every layer caches",
        "kv_layers": [
            {"layer": b, "is_swa": False, "k_elems": 512, "v_elems": 512}
            for b in blocks
        ],
        "recurrent_blocks": [],
        "n_recurrent": 0,
        "n_placeable": 24,
        "key_length": 256,
        "value_length": 256,
        "sliding_window_pattern_declared": False,
        "type_bytes": {"Q4_K": size_bytes},
    }


def _numbers(document: Any) -> frozenset[int | float]:
    """Every number nested in a parsed plan, never a bool."""
    found: set[int | float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(node)
        elif isinstance(node, Mapping):
            for child in node.values():
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(document)
    return frozenset(found)


def _text(document: Any) -> str:
    return json.dumps(document)


_HEADER_READ_MIDDLE = " | base64 -d | python3 - "


def _is_header_read(command: str) -> bool:
    """Whether a recorded ssh command is the shipped-reader header-read line."""
    return command.startswith("echo ") and _HEADER_READ_MIDDLE in command


def _header_path(command: str) -> str:
    """The single-quoted checkpoint path in a header-read line."""
    _blob, _sep, tail = command.partition(_HEADER_READ_MIDDLE)
    assert tail.startswith("'") and tail.endswith("'"), command
    return tail[1:-1]


def _refuses_in_process_header_read(path: str) -> dict[str, Any]:
    """The reader must run on the rig; an in-process read is a contract break."""
    raise AssertionError(
        "recommend read the header in-process; it must ship the reader to the rig"
    )


class RecordedSsh:
    """A stand-in for ``mcgyvr.scan._ssh``: scans, discovery and header reads answer.

    The scan command returns the invented scan; a ``find ... *.gguf`` discovery
    command returns the checkpoint paths this recorder was told are in the
    store; the shipped-reader header-read line returns the checkpoint's header,
    as the reader running on the rig would print it.
    """

    def __init__(self, *reachable: str) -> None:
        self.reachable = set(reachable or (HOST,))
        self.ggufs = [CHECKPOINT]
        self.header_sizes: dict[str, int] = {}
        self.commands: list[tuple[str, str]] = []

    def __call__(self, host: str, command: str) -> str:
        self.commands.append((host, command))
        if host not in self.reachable:
            raise scan_module.Unreachable(host)
        if command == "mcgyvr scan --json":
            return scan_json(host, FREE_MIB)
        if command.startswith("find ") and "*.gguf" in command:
            return "\n".join(self.ggufs) + "\n"
        if _is_header_read(command):
            path = _header_path(command)
            header = fake_header(path, self.header_sizes.get(path, SIZE_BYTES))
            return json.dumps([header]) + "\n"
        raise AssertionError(f"unexpected ssh command: {command!r}")


class RecordedClassify:
    """A stand-in for ``decision.classify``: records what it was asked, answers.

    By default it answers like a reachable backend: it names the first option
    of the placement question. ``reachable=False`` refuses the way a backend
    that is not there refuses.
    """

    def __init__(self, reachable: bool = True) -> None:
        self.reachable = reachable
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        endpoint: Any,
        model: str,
        state: Any,
        questions: Mapping[str, Any],
        *,
        timeout_s: float,
    ) -> decision.Decision:
        self.calls.append(
            {
                "endpoint": endpoint,
                "model": model,
                "state": state,
                "questions": questions,
            }
        )
        if not self.reachable:
            raise TransportError("stubbed unreachable backend")
        placement = questions.get("placement")
        options = placement.options if placement is not None else {}
        first = next(iter(options), None)
        answers: dict[str, Any] = {}
        if first is not None:
            answers["placement"] = decision.ChoiceAnswer(
                choice=first,
                probabilities={first: 1.0},
                confidence=1.0,
            )
        return decision.Decision(answers=answers)


@pytest.fixture
def ssh(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(*reachable: str) -> RecordedSsh:
        recorder = RecordedSsh(*reachable)
        monkeypatch.setattr(scan_module, "_ssh", recorder)
        return recorder

    return install


@pytest.fixture
def classify(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(reachable: bool = True) -> RecordedClassify:
        recorder = RecordedClassify(reachable)
        monkeypatch.setattr(decision, "classify", recorder)
        return recorder

    return install


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(live: bool = True) -> list[Any]:
        calls: list[Any] = []

        def fake(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
            calls.append(endpoint)
            return AvailabilityVerdict(
                source="recommend",
                live=live,
                reason="stub",
                how="stub",
                elapsed_s=0.0,
            )

        monkeypatch.setattr(availability, "probe_endpoint", fake)
        return calls

    return install


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install() -> dict[str, Any]:
        monkeypatch.setattr(recommend_module, "load_catalog", lambda: FAKE_CATALOG)
        return FAKE_CATALOG

    return install


def run_and_parse(
    capsys: pytest.CaptureFixture[str],
    profile: str,
    users: str,
    *model_stores: str,
) -> tuple[int, Any]:
    """Drive the command, then parse the plan it printed to stdout."""
    argv: list[str] = [
        "recommend",
        "--profile",
        profile,
        "--users",
        users,
        "--host",
        HOST,
    ]
    for store in model_stores:
        argv += ["--model-store", store]
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_recommend_accepts_every_profile(
    ssh: Any, classify: Any, probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command exists, and all four profile values are accepted.

    Each profile may be scaffolded or fully placed; the point here is that the
    CLI accepts all four values and echoes the one it was given.
    """
    ssh()
    classify()
    probe()
    for profile in PROFILES:
        code, plan = run_and_parse(capsys, profile, "single", STORE_DIR)
        assert code == 0
        assert plan["profile"] == profile
        assert plan["users"] == 1


def test_recommend_accepts_a_numeric_user_count(
    ssh: Any, classify: Any, probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    ssh()
    classify()
    probe()
    code, plan = run_and_parse(capsys, "coding", "3", STORE_DIR)
    assert code == 0
    assert plan["users"] == 3


def test_recommend_re_reads_the_rig_and_uses_measured_not_stored_numbers(
    ssh: Any,
    classify: Any,
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The plan's numbers are the rig's fresh measurements, never a stored spec's.

    A stored scan of the same rig reports a different free-VRAM figure
    (``STALE_MIB``); the command must re-read the rig over ssh and carry
    ``FREE_MIB`` into the plan, not ``STALE_MIB``.
    """
    recorder = ssh()
    classify()
    probe()
    stale = scan_module.Scan.from_json(scan_json(HOST, STALE_MIB))
    monkeypatch.setattr(scan_module, "load_prior", lambda *a: stale)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert (HOST, "mcgyvr scan --json") in recorder.commands

    numbers = _numbers(plan)
    assert FREE_MIB in numbers
    assert AVAILABLE_RAM_GB in numbers
    assert SIZE_BYTES in numbers
    assert STALE_MIB not in numbers


def test_recommend_prefers_the_local_store_over_the_catalog(
    ssh: Any,
    classify: Any,
    probe: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fitting local checkpoint wins; the catalog is not consulted for it."""
    recorder = ssh()
    classify()
    probe()
    catalog()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    rendered = _text(plan)
    assert plan["source"] == "local-store"
    assert CHECKPOINT in rendered
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    for model in FAKE_CATALOG["models"]:
        assert model["model_id"] not in rendered


def test_recommend_falls_back_to_the_catalog_when_no_store_is_given(
    ssh: Any,
    classify: Any,
    probe: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``--model-store`` the shipped catalog is the only source.

    Only the catalog entry that fits the measured free VRAM is assembled, so
    the plan carries the 4 GB dense entry and never the larger ``SIZE_BYTES``
    entry that does not fit ``FREE_MIB``.
    """
    ssh()
    classify()
    probe(live=False)
    catalog()

    code, plan = run_and_parse(capsys, "coding", "single")
    assert code == 0
    assert plan["source"] == "hf-catalog"
    assert plan["decision"] == "deterministic"
    placement = plan["placement"]
    assert placement["model_id"] == "invented-org/invented-dense"
    assert placement["quant"]
    assert placement["size_bytes"] == 4_000_000_000


def test_recommend_falls_back_to_the_catalog_when_nothing_local_fits(
    ssh: Any,
    classify: Any,
    probe: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A store whose only checkpoint cannot fit is not a source of a placement."""
    recorder = ssh()
    recorder.header_sizes[CHECKPOINT] = 50_000_000_000
    classify()
    probe(live=False)
    catalog()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    assert plan["source"] == "hf-catalog"


def test_coding_places_and_the_other_profiles_are_scaffolded(
    ssh: Any, classify: Any, probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """``coding`` is honoured with a real placement; the rest are stubs.

    A real placement names a checkpoint and an engine and consults the decision
    seam. A scaffold names neither an engine nor a checkpoint and consults
    nothing.
    """
    ssh()
    decisions = classify()
    probe()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    rendered = _text(plan)
    assert CHECKPOINT in rendered
    assert any(engine in rendered for engine in ENGINES)
    assert decisions.calls
    assert plan["decision"] == "model"

    for profile in ("chatting", "media_gen", "other"):
        decisions.calls.clear()
        code, plan = run_and_parse(capsys, profile, "single", STORE_DIR)
        assert code == 0
        rendered = _text(plan)
        assert not any(engine in rendered for engine in ENGINES)
        assert not decisions.calls
        assert plan["placement"] is None
        assert plan["decision"] is None


def test_recommend_reads_each_checkpoint_header_it_is_asked_about(
    ssh: Any, classify: Any, probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every checkpoint discovered in ``--model-store`` is read on the rig."""
    recorder = ssh()
    recorder.ggufs = [CHECKPOINT, OTHER]
    classify()
    probe(live=False)

    code, _ = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    header_paths = [
        _header_path(command)
        for _host, command in recorder.commands
        if _is_header_read(command)
    ]
    assert CHECKPOINT in header_paths
    assert OTHER in header_paths


def test_recommend_reads_the_header_on_the_rig_over_the_read_only_ssh_seam(
    ssh: Any,
    classify: Any,
    probe: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The checkpoint header is read ON the rig, read-only, over the ssh seam.

    ``recommend`` must not read the header in-process from a RIG-local path: it
    ships the reader to the rig and the header facts come back over
    ``mcgyvr.scan._ssh``, the same read-only ssh seam the scan and the
    ``*.gguf`` discovery use.
    """
    recorder = ssh()
    classify()
    probe(live=False)
    monkeypatch.setattr(ggufscan_module, "scan", _refuses_in_process_header_read)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    assert plan["placement"]["checkpoint"] == CHECKPOINT
    assert SIZE_BYTES in _numbers(plan)


def test_recommend_with_no_backend_falls_back_deterministically(
    ssh: Any,
    classify: Any,
    probe: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No backend is reachable: the plan picks deterministically and says so.

    The plan carries only the measured numbers, records ``decision`` as
    ``deterministic``, and never consults the model.
    """
    ssh()
    decisions = classify()
    probe(live=False)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"] == "deterministic"
    assert decisions.calls == []
    numbers = _numbers(plan)
    assert FREE_MIB in numbers
    assert AVAILABLE_RAM_GB in numbers
    assert SIZE_BYTES in numbers


def test_recommend_deterministic_fallback_picks_the_largest_checkpoint_that_fits(
    ssh: Any,
    classify: Any,
    probe: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The deterministic rule is fixed: the largest fitting checkpoint wins."""
    recorder = ssh()
    recorder.ggufs = [CHECKPOINT, OTHER]
    recorder.header_sizes[CHECKPOINT] = SIZE_BYTES
    recorder.header_sizes[OTHER] = 3_000_000_000
    classify()
    probe(live=False)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"] == "deterministic"
    assert plan["placement"]["checkpoint"] == CHECKPOINT
    assert plan["placement"]["size_bytes"] == SIZE_BYTES


def test_recommend_deterministic_catalog_fallback_picks_the_largest_that_fits(
    ssh: Any,
    classify: Any,
    probe: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catalog fallback with no backend picks the largest entry that fits VRAM.

    ``invented-moe`` (``SIZE_BYTES``) does not fit ``FREE_MIB`` of free VRAM;
    ``invented-dense`` (4 GB) does, so the deterministic rule names the dense
    one and never the larger non-fitting entry.
    """
    ssh()
    classify()
    probe(live=False)
    catalog()

    code, plan = run_and_parse(capsys, "coding", "single")
    assert code == 0
    assert plan["decision"] == "deterministic"
    assert plan["placement"]["model_id"] == "invented-org/invented-dense"
    assert plan["placement"]["size_bytes"] == 4_000_000_000


def test_recommend_with_a_reachable_backend_records_model_and_endpoint(
    ssh: Any,
    classify: Any,
    probe: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A reachable backend answers the decision: the plan says ``model`` + endpoint."""
    ssh()
    decisions = classify()
    probe(live=True)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"] == "model"
    assert plan["decision_endpoint"] == "http://127.0.0.1:8080"
    assert decisions.calls
