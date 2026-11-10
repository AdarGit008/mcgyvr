"""The promise and contract of ``mcgyvr recommend``.

PROMISE
-------
``mcgyvr recommend`` is a read-only planner. It re-reads the rigs it is pointed
at over ssh — measuring free VRAM, available RAM, disk and bandwidth at that
moment rather than trusting any stored spec — and, for the ``coding`` profile,
assembles candidate placements from those measured inputs and picks one
deterministically: the largest checkpoint among the candidates that already fit
the measured machine. No model is asked, and the plan says so. Every
number in the emitted plan is a measurement the rig or the checkpoint header
made, or a shipped constant; none is invented. ``chat`` and ``agent`` place
one unit from their own candidates; the profile that is not a use case
(``other``) is accepted as a scaffold that makes no placement.

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
chosen, and no model is consulted); ``other`` is accepted but scaffolded (no
engine, no decision).

The seams this test substitutes are existing module attributes, chosen so the
command can be exercised without owning hardware:

* ``mcgyvr.scan._ssh`` — the ssh scan/detection transport (the same seam
  ``tests/test_remote_scan.py`` stubs); the header read and the ``*.gguf``
  discovery both answer through it;
* ``mcgyvr.decision.classify`` and ``mcgyvr.availability.probe_endpoint`` —
  replaced, where a test pins that no model is asked, by recorders that must
  stay empty;
* ``mcgyvr.recommend.load_catalog`` — the shipped HuggingFace catalog loader.

``mcgyvr.serving.ggufscan.scan`` is patched in exactly one test to fail if the
command reads a header in-process: the reader must run on the rig, not here.

The plan is the only thing printed to stdout, as one JSON document, and the
command exits 0.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import availability, cli, decision
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.serving import gatelib
from mcgyvr.serving import ggufscan as ggufscan_module
from tests import records

# Invented, and shaped so the test can tell a measurement from a stored spec and
# from an invented number: free VRAM is a distinctive figure the fake ssh scan
# reports, and the stale stored scan reports a different one.
FREE_MIB = 9001
STALE_MIB = 1111
AVAILABLE_RAM_GB = 48.0
HOST = "box-7.invalid"
STORE_DIR = "/models/store"
CHECKPOINT = f"{STORE_DIR}/invented-moe.gguf"
OTHER = f"{STORE_DIR}/invented-dense.gguf"
MISSING_STORE_DIR = "/models/missing"
SIZE_BYTES = 9_876_543_210

ENGINES = ("llama.cpp", "vllm")
PROFILES = ("code", "chat", "agent", "other")

#: An invented HuggingFace catalog, the same shape ``load_catalog`` returns
#: from ``data/model-catalog.json``. The test injects it through the seam.
FAKE_CATALOG: dict[str, Any] = {
    "schema_version": 1,
    "models": [
        {
            "model_id": "invented-org/invented-moe",
            "quant": "Q4_K_M",
            "size_bytes": SIZE_BYTES,
            "context_length": 32768,
            "kv_bytes_per_token": 1000,
            "recurrent_bytes_per_slot": 0,
            "engines": ["llama.cpp", "vllm"],
        },
        {
            "model_id": "invented-org/invented-dense",
            "quant": "Q4_K",
            "size_bytes": 4_000_000_000,
            "context_length": 4096,
            "kv_bytes_per_token": 1000,
            "recurrent_bytes_per_slot": 0,
            "engines": ["llama.cpp"],
        },
    ],
}

#: A catalog whose large entry fits on size alone but not once the KV cache it
#: prices is added: ``context_length * kv_bytes_per_token`` pushes it past the
#: invented card's free VRAM.
KV_HEAVY_CATALOG: dict[str, Any] = {
    "schema_version": 1,
    "models": [
        {
            "model_id": "invented-org/kv-heavy",
            "quant": "Q4_K_M",
            "size_bytes": 4_000_000_000,
            "context_length": 32768,
            "kv_bytes_per_token": 200_000,
            "recurrent_bytes_per_slot": 0,
            "engines": ["llama.cpp"],
        },
        {
            "model_id": "invented-org/small",
            "quant": "Q4_K",
            "size_bytes": 3_000_000_000,
            "context_length": 1024,
            "kv_bytes_per_token": 1000,
            "recurrent_bytes_per_slot": 0,
            "engines": ["llama.cpp"],
        },
    ],
}


def scan_json(host: str, free_mib: int) -> str:
    """An invented rig's scan, as the one reader prints it.

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


def recurrent_header(path: str, size_bytes: int = SIZE_BYTES) -> dict[str, Any]:
    """An invented recurrent checkpoint header: per-slot state priced by slots.

    The recurrent state is sized so one slot fits the invented card and four
    slots do not, which is what makes ``--users`` change the fit.
    """
    header = fake_header(path, size_bytes)
    header.update(
        {
            "recurrent_blocks": list(range(24)),
            "n_recurrent": 24,
            "ssm_inner_size": 4096,
            "ssm_state_size": 4096,
            "ssm_conv_kernel": 0,
            "ssm_group_count": 0,
            "ssm_params_from": "ssm.* keys",
        }
    )
    return header


def ram_heavy_moe_header(path: str, size_bytes: int = SIZE_BYTES) -> dict[str, Any]:
    """An MoE whose expert spill exceeds the invented rig's 48 GiB of RAM.

    The card load stays tiny (1 GiB of non-expert weights plus the cache), so
    the only reason this checkpoint must not fit is the host-RAM gate.
    """
    header = fake_header(path, size_bytes)
    expert_bytes = 60 * (1024**3)
    nonexpert_bytes = 1_000_000_000
    header.update(
        {
            "size_bytes": expert_bytes + nonexpert_bytes,
            "bytes_experts": expert_bytes,
            "bytes_nonexpert": nonexpert_bytes,
            "bytes_total_tensors": expert_bytes + nonexpert_bytes,
        }
    )
    return header


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


def _is_scan_read(command: str) -> bool:
    """Whether a recorded ssh command is the shipped-scan line."""
    return command == gatelib.scan_read_command()


def _is_header_read(command: str) -> bool:
    """Whether a recorded ssh command is the shipped-reader header-read line."""
    return command.startswith("echo ") and _HEADER_READ_MIDDLE in command


def _header_path(command: str) -> str:
    """The single-quoted checkpoint path in a header-read line."""
    _blob, _sep, tail = command.partition(_HEADER_READ_MIDDLE)
    assert tail.startswith("'") and tail.endswith("'"), command
    return tail[1:-1]


_FIND_SUFFIX = " -maxdepth 1 -name '*.gguf' -print"


def _find_dir(command: str) -> str:
    """The single-quoted store directory in a discovery line."""
    assert command.startswith("find ") and command.endswith(_FIND_SUFFIX), command
    directory = command[len("find ") : -len(_FIND_SUFFIX)]
    assert directory.startswith("'") and directory.endswith("'"), command
    return directory[1:-1]


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

    def __init__(
        self,
        *reachable: str,
        header_builder: Any = fake_header,
        missing_dirs: tuple[str, ...] = (),
    ) -> None:
        self.reachable = set(reachable or (HOST,))
        self.ggufs = [CHECKPOINT]
        self.header_sizes: dict[str, int] = {}
        self.header_builder = header_builder
        self.missing_dirs = set(missing_dirs)
        self.commands: list[tuple[str, str]] = []

    def __call__(self, host: str, command: str) -> str:
        self.commands.append((host, command))
        if host not in self.reachable:
            raise scan_module.Unreachable(host)
        if _is_scan_read(command):
            return scan_json(host, FREE_MIB)
        if command.startswith("find ") and command.endswith(_FIND_SUFFIX):
            if _find_dir(command) in self.missing_dirs:
                raise scan_module.ScannerMissing(host)
            return "\n".join(self.ggufs) + "\n"
        if _is_header_read(command):
            path = _header_path(command)
            header = self.header_builder(path, self.header_sizes.get(path, SIZE_BYTES))
            return json.dumps([header]) + "\n"
        raise AssertionError(f"unexpected ssh command: {command!r}")


@pytest.fixture
def ssh(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(*reachable: str) -> RecordedSsh:
        recorder = RecordedSsh(*reachable)
        monkeypatch.setattr(scan_module, "_ssh", recorder)
        return recorder

    return install


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every model the plan asks, or probes for: none, so the list stays empty."""
    calls: list[str] = []

    def classify(*args: Any, **kwargs: Any) -> decision.Decision:
        calls.append("classify")
        raise AssertionError("recommend asked a model")

    def probe(*args: Any, **kwargs: Any) -> AvailabilityVerdict:
        calls.append("probe_endpoint")
        raise AssertionError("recommend probed for a model")

    monkeypatch.setattr(decision, "classify", classify)
    monkeypatch.setattr(availability, "probe_endpoint", probe)
    return calls


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install() -> dict[str, Any]:
        monkeypatch.setattr(
            recommend_module, "load_catalog", lambda *a, **k: FAKE_CATALOG
        )
        return FAKE_CATALOG

    return install


def run_and_parse(
    capsys: pytest.CaptureFixture[str],
    profile: str,
    users: str,
    *model_stores: str,
    hosts: tuple[str, ...] = (HOST,),
) -> tuple[int, Any]:
    """Drive the command, then parse the plan it printed to stdout."""
    argv: list[str] = [
        "recommend",
        "--profile",
        profile,
        "--users",
        users,
    ]
    for host in hosts:
        argv += ["--host", host]
    for store in model_stores:
        argv += ["--model-store", store]
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_recommend_accepts_every_profile(
    ssh: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The command exists, and every profile value is accepted.

    Each profile may be scaffolded or fully placed; the point here is that the
    CLI accepts every value and echoes the one it was given. The catalog holds
    one more invented entry, small with a long context, so a chat or agent unit
    has a model it fits at its 8k floor.
    """
    ssh()
    roomy = {
        "models": [
            *FAKE_CATALOG["models"],
            {
                "model_id": "invented-org/invented-long-context",
                "quant": "Q4_K_M",
                "size_bytes": 2_000_000_000,
                "context_length": 32768,
                "kv_bytes_per_token": 1000,
                "recurrent_bytes_per_slot": 0,
                "engines": ["llama.cpp"],
            },
        ]
    }
    monkeypatch.setattr(recommend_module, "load_catalog", lambda *a, **k: roomy)
    for profile in PROFILES:
        code, plan = run_and_parse(capsys, profile, "single", STORE_DIR)
        assert code == 0
        assert plan["profile"] == profile
        assert plan["users"] == 1


def test_recommend_accepts_a_numeric_user_count(
    ssh: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    ssh()
    code, plan = run_and_parse(capsys, "code", "3", STORE_DIR)
    assert code == 0
    assert plan["users"] == 3


def test_recommend_re_reads_the_rig_and_uses_measured_not_stored_numbers(
    ssh: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The plan's numbers are the rig's fresh measurements, never a stored spec's.

    The rig's file records a different free-VRAM figure (``STALE_MIB``); the
    command must re-read the rig over ssh and carry ``FREE_MIB`` into the plan,
    not ``STALE_MIB``.
    """
    recorder = ssh()
    stale = scan_module.Scan.from_json(scan_json(HOST, STALE_MIB))
    rigs = tmp_path / "rigs"
    rigs.mkdir()
    (rigs / f"{HOST}.json").write_text(records.rig_file(stale, HOST), encoding="utf-8")
    monkeypatch.setenv(records.RIGS_ENV, str(rigs))

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    assert any(_is_scan_read(command) for _host, command in recorder.commands)

    numbers = _numbers(plan)
    assert FREE_MIB in numbers
    assert AVAILABLE_RAM_GB in numbers
    assert SIZE_BYTES in numbers
    assert STALE_MIB not in numbers


def test_recommend_prefers_the_local_store_over_the_catalog(
    ssh: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fitting local checkpoint wins; the catalog is not consulted for it."""
    recorder = ssh()
    catalog()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
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


def test_recommend_placement_carries_the_measured_local_context_length(
    ssh: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The placement carries the window the local checkpoint was priced at.

    The plan's ``placement`` must state ``context_length``, the measured local
    header's ``n_ctx_train``, so the setup wizard can hand ``emit`` the same
    window it was priced at.
    """
    ssh()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    assert plan["source"] == "local-store"
    assert plan["placement"]["context_length"] == 65536


def test_recommend_placement_carries_the_shipped_catalog_context_length(
    ssh: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A catalog placement carries its shipped ``context_length``."""
    ssh()
    catalog()

    code, plan = run_and_parse(capsys, "code", "single")
    assert code == 0
    assert plan["source"] == "hf-catalog"
    assert plan["placement"]["context_length"] == 4096


def test_recommend_falls_back_to_the_catalog_when_no_store_is_given(
    ssh: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``--model-store`` the shipped catalog is the only source.

    Only the catalog entry that fits the measured free VRAM is assembled, so
    the plan carries the 4 GB dense entry and never the larger ``SIZE_BYTES``
    entry that does not fit ``FREE_MIB``.
    """
    ssh()
    catalog()

    code, plan = run_and_parse(capsys, "code", "single")
    assert code == 0
    assert plan["source"] == "hf-catalog"
    assert plan["decision"] == "deterministic"
    placement = plan["placement"]
    assert placement["model_id"] == "invented-org/invented-dense"
    assert placement["quant"]
    assert placement["size_bytes"] == 4_000_000_000


def test_recommend_falls_back_to_the_catalog_when_nothing_local_fits(
    ssh: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A store whose only checkpoint cannot fit is not a source of a placement."""
    recorder = ssh()
    recorder.header_sizes[CHECKPOINT] = 50_000_000_000
    catalog()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    assert plan["source"] == "hf-catalog"


def test_coding_places_and_the_other_profiles_are_scaffolded(
    ssh: Any, asked: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """``coding`` is honoured with a real placement; the profile that is not a
    use case is a stub (chat and agent place too, from their own candidates,
    in ``test_a_chat_setup_no_longer_plans_a_coding_model.py``).

    A real placement names a checkpoint and an engine, picked without a model.
    A scaffold names neither an engine nor a checkpoint and consults nothing.
    """
    ssh()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    rendered = _text(plan)
    assert CHECKPOINT in rendered
    assert any(engine in rendered for engine in ENGINES)
    assert asked == []
    assert plan["decision"] == "deterministic"

    for profile in ("other",):
        code, plan = run_and_parse(capsys, profile, "single", STORE_DIR)
        assert code == 0
        rendered = _text(plan)
        assert not any(engine in rendered for engine in ENGINES)
        assert asked == []
        assert plan["placement"] is None
        assert plan["decision"] is None


def test_recommend_reads_each_checkpoint_header_it_is_asked_about(
    ssh: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every checkpoint discovered in ``--model-store`` is read on the rig."""
    recorder = ssh()
    recorder.ggufs = [CHECKPOINT, OTHER]

    code, _ = run_and_parse(capsys, "code", "single", STORE_DIR)
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
    monkeypatch.setattr(ggufscan_module, "scan", _refuses_in_process_header_read)

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    assert plan["placement"]["checkpoint"] == CHECKPOINT
    assert SIZE_BYTES in _numbers(plan)


def test_recommend_picks_deterministically_and_asks_no_model(
    ssh: Any,
    asked: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The plan picks deterministically and says so.

    The plan carries only the measured numbers, records ``decision`` as
    ``deterministic``, and never asks or probes for a model.
    """
    ssh()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"] == "deterministic"
    assert asked == []
    numbers = _numbers(plan)
    assert FREE_MIB in numbers
    assert AVAILABLE_RAM_GB in numbers
    assert SIZE_BYTES in numbers


def test_recommend_deterministic_fallback_picks_the_largest_checkpoint_that_fits(
    ssh: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The deterministic rule is fixed: the largest fitting checkpoint wins."""
    recorder = ssh()
    recorder.ggufs = [CHECKPOINT, OTHER]
    recorder.header_sizes[CHECKPOINT] = SIZE_BYTES
    recorder.header_sizes[OTHER] = 3_000_000_000

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"] == "deterministic"
    assert plan["placement"]["checkpoint"] == CHECKPOINT
    assert plan["placement"]["size_bytes"] == SIZE_BYTES


def test_recommend_deterministic_catalog_fallback_picks_the_largest_that_fits(
    ssh: Any,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catalog fallback with no backend picks the largest entry that fits VRAM.

    ``invented-moe`` (``SIZE_BYTES``) does not fit ``FREE_MIB`` of free VRAM;
    ``invented-dense`` (4 GB) does, so the deterministic rule names the dense
    one and never the larger non-fitting entry.
    """
    ssh()
    catalog()

    code, plan = run_and_parse(capsys, "code", "single")
    assert code == 0
    assert plan["decision"] == "deterministic"
    assert plan["placement"]["model_id"] == "invented-org/invented-dense"
    assert plan["placement"]["size_bytes"] == 4_000_000_000


def test_recommend_ships_the_scan_and_does_not_require_mcgyvr(
    ssh: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The remote scan is the shipped ``python3 -`` script, not ``mcgyvr scan``.

    A fresh rig has ``python3`` but no mcgyvr installed; the scan must ship to
    the far end as bytes and answer through the same seam, so ``recommend``
    succeeds against a rig that only has python3.
    """
    recorder = ssh()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    scan_commands = [
        command for _host, command in recorder.commands if _is_scan_read(command)
    ]
    assert scan_commands, recorder.commands
    assert not any(
        command == "mcgyvr scan --json" for _host, command in recorder.commands
    )
    assert plan["unreachable"] == []
    assert plan["no_scanner"] == []
    assert plan["scan_failed"] == []


class ScanFailuresSsh:
    """A stand-in for ``mcgyvr.scan._ssh`` that answers per host by failure mode."""

    def __init__(self, modes: dict[str, str]) -> None:
        self.modes = modes
        self.commands: list[tuple[str, str]] = []

    def __call__(self, host: str, command: str) -> str:
        self.commands.append((host, command))
        mode = self.modes[host]
        if mode == "unreachable":
            raise scan_module.Unreachable(host)
        if mode == "no_scanner":
            raise scan_module.ScannerMissing(host)
        if mode == "scan_failed":
            return "not a scan\n"
        return scan_json(host, FREE_MIB)


def test_recommend_plan_distinguishes_the_three_scan_failure_modes(
    monkeypatch: pytest.MonkeyPatch,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ssh failure, no scanner and a failed scan land in different plan fields."""
    monkeypatch.setattr(
        scan_module,
        "_ssh",
        ScanFailuresSsh(
            {
                "ok-rig": "ok",
                "down-rig": "unreachable",
                "python-only-rig": "no_scanner",
                "bad-scan-rig": "scan_failed",
            }
        ),
    )
    catalog()

    code, plan = run_and_parse(
        capsys,
        "code",
        "single",
        hosts=("ok-rig", "down-rig", "python-only-rig", "bad-scan-rig"),
    )
    assert code == 0
    assert plan["unreachable"] == ["down-rig"]
    assert plan["no_scanner"] == ["python-only-rig"]
    assert plan["scan_failed"] == ["bad-scan-rig"]
    assert [rig["host"] for rig in plan["rigs"]] == ["ok-rig"]


def test_users_budget_the_placement_and_change_the_flags(
    monkeypatch: pytest.MonkeyPatch,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--users single`` and ``--users 4`` budget different processes.

    The recurrent checkpoint's per-slot state fits one slot and does not fit
    four, so four users fall back to the catalog and carry ``--parallel 4``;
    one user stays on the local checkpoint without ``--parallel``.
    """
    monkeypatch.setattr(
        scan_module,
        "_ssh",
        RecordedSsh(HOST, header_builder=recurrent_header),
    )
    catalog()

    single_code, single_plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    four_code, four_plan = run_and_parse(capsys, "code", "4", STORE_DIR)

    assert single_code == 0
    assert four_code == 0
    assert single_plan["source"] == "local-store"
    assert single_plan["placement"]["checkpoint"] == CHECKPOINT
    assert "--parallel" not in single_plan["placement"]["flags"]
    assert four_plan["source"] == "hf-catalog"
    assert four_plan["placement"]["model_id"] == "invented-org/invented-dense"
    assert four_plan["placement"]["flags"]["--parallel"] == "4"


def test_recommend_treats_a_missing_store_dir_as_empty_not_a_failure(
    ssh: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A store directory that does not exist on the rig contributes nothing.

    ``find '<missing>' ...`` exits non-zero, which the read-only ssh seam maps to
    ``ScannerMissing``. Discovery must read that as "this directory holds no
    checkpoints" and keep going with the store that does exist, never crash the
    whole plan the way a missing directory did before.
    """
    recorder = ssh()
    recorder.missing_dirs = {MISSING_STORE_DIR}

    code, plan = run_and_parse(capsys, "code", "single", MISSING_STORE_DIR, STORE_DIR)
    assert code == 0
    assert plan["source"] == "local-store"
    assert plan["placement"]["checkpoint"] == CHECKPOINT
    assert plan["unreachable"] == []
    assert plan["no_scanner"] == []
    assert plan["scan_failed"] == []


def test_recommend_catalog_budgets_kv_on_top_of_size(
    monkeypatch: pytest.MonkeyPatch,
    ssh: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A catalog entry that fits by size alone but not with its KV cache is out.

    ``kv-heavy`` is 4 GB, under the invented card's free VRAM, so a size-only
    fit would admit it; its shipped 32768-token KV budget pushes the total over,
    so the deterministic pick must name the smaller entry whose size+KV fits.
    """
    ssh()
    monkeypatch.setattr(
        recommend_module, "load_catalog", lambda *a, **k: KV_HEAVY_CATALOG
    )

    code, plan = run_and_parse(capsys, "code", "single")
    assert code == 0
    assert plan["source"] == "hf-catalog"
    assert plan["placement"]["model_id"] == "invented-org/small"
    assert "invented-org/kv-heavy" not in _text(plan)


def test_recommend_rejects_an_moe_whose_expert_spill_exceeds_host_ram(
    monkeypatch: pytest.MonkeyPatch,
    catalog: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An MoE that fits the card but not host RAM is not a local candidate.

    ``ram_heavy_moe_header`` spills 60 GiB of experts into a rig the scan
    reports with 48 GiB of available RAM, while its card load stays tiny. The
    fit must refuse it and fall back to the catalog rather than place a model
    whose resident expert weights the rig's RAM cannot hold.
    """
    monkeypatch.setattr(
        scan_module,
        "_ssh",
        RecordedSsh(HOST, header_builder=ram_heavy_moe_header),
    )
    catalog()

    code, plan = run_and_parse(capsys, "code", "single", STORE_DIR)
    assert code == 0
    assert plan["source"] == "hf-catalog"
    assert plan["placement"]["model_id"] == "invented-org/invented-dense"
    assert CHECKPOINT not in _text(plan)
