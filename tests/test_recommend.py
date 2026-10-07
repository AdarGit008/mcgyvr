"""The promise and contract of ``mcgyvr recommend``.

PROMISE
-------
``mcgyvr recommend`` is a read-only planner. It re-reads the rigs it is pointed
at over ssh — measuring free VRAM, available RAM, disk and bandwidth at that
moment rather than trusting any stored spec — and, for ``chat``, ``agent`` and
``coding``, sizes the units each rig would run with the product's serving
sizer (:mod:`mcgyvr.planner`), ranks the ones that fit, and, when the config
binds a ``jev.unit``, lets that unit name each rig's pick through
:func:`mcgyvr.decision.classify_for`. With no Jev unit bound, or one that does
not answer, each rig's first-ranked candidate is the pick (no board scores
them here, so the largest that fits) and the plan's ``decision`` says so.
Every number in the emitted plan is a measurement the rig or a file header
made, a figure the serving sizer derived from those, or a shipped constant;
none is invented. ``media-gen`` is accepted and plans no unit yet. The
deprecated ``--profile`` spellings are pinned by
``tests/test_recommend_takes_the_four_use_cases_and_warns_on_the_old_spellings.py``;
the plan's version 2 shape by
``tests/test_a_plan_is_version_2_and_says_who_decided_and_from_what.py``.

WHAT THIS TEST PINS
-------------------
The command is read-only: it reads a rig over the (read-only) ssh scan path —
``mcgyvr.scan.scan_over``'s transport, seen here as ``mcgyvr.scan._ssh`` — and
its plan carries the numbers that transport just measured, never the numbers of
a stored scan.

Models to place come from exactly one of two places, and ``models_from`` says
which:

* ``--model-store <dir>`` — checkpoint files are discovered (``*.gguf`` in that
  directory, over the same read-only ssh seam) and each header is read ON the
  rig, over the same seam, by shipping ``mcgyvr.serving.ggufscan`` to the rig
  as ``python3 -`` (the blob never comes back). When a discovered checkpoint
  fits, the plan places **only** from that store, and says the file is there.
* no store, or nothing local fits — the plan places from the model knowledge,
  injected here through ``mcgyvr.recommend.load_models``: each model with its
  file's header row, so it is sized by the same law as a file on the rig.
  Those units are downloads.

The seams this test substitutes are existing module attributes, chosen so the
command can be exercised without owning hardware:

* ``mcgyvr.scan._ssh`` — the ssh scan/detection transport (the same seam
  ``tests/test_remote_scan.py`` stubs); the header read and the ``*.gguf``
  discovery both answer through it;
* ``mcgyvr.decision.classify`` — the decision, reached through
  ``classify_for`` on the bound Jev unit; the tests that want it asked bind
  one with :data:`JEV_CONFIG`;
* ``mcgyvr.availability.probe_endpoint`` — the reachability probe that decides
  whether the Jev unit is there before it is consulted;
* ``mcgyvr.recommend.load_models`` — the model knowledge.

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

from mcgyvr import availability, cli, decision, planner
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.runner import TransportError
from mcgyvr.serving import gatelib
from mcgyvr.serving import ggufscan as ggufscan_module

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

USE_CASES = ("coding", "chat", "agent", "media-gen")
PLACED = ("coding", "chat", "agent")


def scan_json(host: str, free_mib: int) -> str:
    """An invented rig's scan, as the shipped self-contained scanner prints it.

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


def dense_header(
    path: str,
    size_bytes: int,
    *,
    context: int = 4096,
    kv_elems: int = 512,
) -> dict[str, Any]:
    """An invented dense checkpoint header: no expert, no MTP head."""
    header = fake_header(path, size_bytes)
    header.update(
        {
            "n_ctx_train": context,
            "bytes_experts": 0,
            "bytes_nonexpert": size_bytes,
            "placeable_blocks": [],
            "expert_blocks": [],
            "expert_bytes_by_block": {},
            "nextn_blocks": [],
            "nextn_predict_layers": 0,
            "n_expert": 0,
            "n_expert_used": 0,
            "kv_layers": [
                {"layer": b, "is_swa": False, "k_elems": kv_elems, "v_elems": kv_elems}
                for b in range(24)
            ],
        }
    )
    return header


def invented_model(model_id: str, header: Mapping[str, Any]) -> planner.Model:
    """An invented downloadable model, with the header row of its file."""
    file = Path(str(header["file"])).name
    return planner.Model(
        model_id=model_id,
        quant="Q4_K_M",
        file=file,
        size_bytes=int(header["size_bytes"]),
        context_length=int(header["n_ctx_train"]),
        geometry=dict(header),
        repo=f"{model_id}-GGUF",
        revision="3" * 40,
        sha256="4" * 64,
        sources={
            "size": f"hub-api:{model_id}",
            "context": f"hub-config:{model_id}",
            "geometry": f"gguf-header-range:{model_id}",
        },
    )


#: Invented model knowledge: an MoE that fits the invented card only with its
#: experts in RAM, and a small dense model that fits whole.
FAKE_LIBRARY = planner.Library(
    models=(
        invented_model(
            "invented-org/invented-moe",
            fake_header("invented-moe-Q4_K_M.gguf", SIZE_BYTES),
        ),
        invented_model(
            "invented-org/invented-dense",
            dense_header("invented-dense-Q4_K.gguf", 4_000_000_000),
        ),
    )
)

#: Knowledge whose larger model fits on size alone but not once the cache its
#: header prices at 32k per slot is added.
KV_HEAVY_LIBRARY = planner.Library(
    models=(
        invented_model(
            "invented-org/kv-heavy",
            dense_header(
                "kv-heavy-Q4_K_M.gguf", 6_000_000_000, context=32768, kv_elems=8192
            ),
        ),
        invented_model(
            "invented-org/small",
            dense_header("small-Q4_K.gguf", 3_000_000_000, context=1024),
        ),
    )
)


def _units(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [unit for rig in plan["rigs"].values() for unit in rig["units"]]


def _only(plan: Mapping[str, Any]) -> dict[str, Any]:
    (unit,) = _units(plan)
    return unit


def _top(plan: Mapping[str, Any]) -> dict[str, Any]:
    """The last rung of the plan's ladder: a coding plan's top rung."""
    by_name = {unit["name"]: unit for unit in _units(plan)}
    return by_name[plan["ladder"][-1]]


def by_path(path: str, size_bytes: int = SIZE_BYTES) -> dict[str, Any]:
    """The invented MoE at ``CHECKPOINT``, a dense model anywhere else."""
    if path == CHECKPOINT:
        return fake_header(path, size_bytes)
    return dense_header(path, size_bytes)


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


class RecordedClassify:
    """A stand-in for ``decision.classify``: records what it was asked, answers.

    By default it answers like a reachable backend: it names the first option
    of every question (one per rig). ``reachable=False`` refuses the way a
    backend that is not there refuses.
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
        answers: dict[str, Any] = {}
        for key, question in questions.items():
            first = next(iter(question.options), None)
            if first is not None:
                answers[key] = decision.ChoiceAnswer(
                    choice=first, probabilities={first: 1.0}, confidence=1.0
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


#: An invented setup that binds a Jev unit, the only unit ``recommend`` asks.
JEV_CONFIG = """\
units:
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- judge
jev:
  unit: judge
"""


@pytest.fixture
def jev_config(tmp_path: Path) -> str:
    """The path of a setup whose ``jev.unit`` is bound."""
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(JEV_CONFIG, encoding="utf-8")
    return str(path)


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(found: planner.Library | None = None) -> planner.Library:
        chosen = found if found is not None else FAKE_LIBRARY
        monkeypatch.setattr(recommend_module, "load_models", lambda: chosen)
        return chosen

    return install


def run_and_parse(
    capsys: pytest.CaptureFixture[str],
    use_case: str,
    users: str,
    *model_stores: str,
    hosts: tuple[str, ...] = (HOST,),
    config: str | None = None,
    extra: tuple[str, ...] = (),
) -> tuple[int, Any]:
    """Drive the command, then parse the plan it printed to stdout."""
    argv: list[str] = [
        "recommend",
        "--use-case",
        use_case,
        "--users",
        users,
    ]
    if config is not None:
        argv += ["--config", config]
    for host in hosts:
        argv += ["--host", host]
    for store in model_stores:
        argv += ["--model-store", store]
    code = cli.main([*argv, *extra])
    return code, json.loads(capsys.readouterr().out)


def test_recommend_accepts_every_use_case(
    ssh: Any, classify: Any, probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command exists, and all four use cases are accepted and echoed."""
    ssh()
    classify()
    probe()
    for use_case in USE_CASES:
        code, plan = run_and_parse(capsys, use_case, "single", STORE_DIR)
        assert code == 0
        assert plan["use_case"] == use_case
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
    assert any(_is_scan_read(command) for _host, command in recorder.commands)

    numbers = _numbers(plan)
    assert FREE_MIB in numbers
    assert AVAILABLE_RAM_GB in numbers
    assert SIZE_BYTES in numbers
    assert STALE_MIB not in numbers


def test_recommend_prefers_the_local_store_over_the_knowledge(
    ssh: Any,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fitting local checkpoint wins; the knowledge is not consulted for it."""
    recorder = ssh()
    classify()
    probe()
    library()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["models_from"] == "local-store"
    unit = _top(plan)
    assert unit["args"]["--model"] == CHECKPOINT
    assert unit["download"] == {
        "bytes": 0,
        "sha256": None,
        "present": True,
        "to": STORE_DIR,
    }
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    rendered = _text(plan)
    for model in FAKE_LIBRARY.models:
        assert model.model_id not in rendered


def test_recommend_falls_back_to_the_knowledge_when_no_store_is_given(
    ssh: Any,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without ``--model-store`` the model knowledge is the only source, and
    its units are downloads."""
    ssh()
    classify()
    probe(live=False)
    library()

    code, plan = run_and_parse(capsys, "coding", "single")
    assert code == 0
    assert plan["models_from"] == "knowledge"
    assert plan["decision"]["by"] == "deterministic"
    units = _units(plan)
    assert {u["model"]["id"] for u in units} <= {
        m.model_id for m in FAKE_LIBRARY.models
    }
    assert all(u["download"]["present"] is False for u in units)
    assert (
        sum(u["download"]["bytes"] for u in units)
        == plan["downloads"]["total_bytes"]
        > 0
    )


def test_recommend_falls_back_to_the_knowledge_when_nothing_local_fits(
    ssh: Any,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A store whose only checkpoint cannot fit is not a source of a unit."""
    recorder = ssh()
    recorder.header_builder = dense_header
    recorder.header_sizes[CHECKPOINT] = 50_000_000_000
    classify()
    probe(live=False)
    library()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    header_reads = [
        command for _host, command in recorder.commands if _is_header_read(command)
    ]
    assert header_reads, recorder.commands
    assert plan["models_from"] == "knowledge"


def test_the_text_use_cases_place_and_media_gen_plans_nothing_yet(
    ssh: Any,
    classify: Any,
    probe: Any,
    jev_config: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``chat``, ``agent`` and ``coding`` are placed; ``media-gen`` is read
    and plans no unit, and consults nothing."""
    ssh()
    decisions = classify()
    probe()

    for use_case in PLACED:
        decisions.calls.clear()
        code, plan = run_and_parse(
            capsys, use_case, "single", STORE_DIR, config=jev_config
        )
        assert code == 0
        assert _top(plan)["args"]["--model"] == CHECKPOINT
        assert decisions.calls
        assert plan["decision"]["by"] == "jev"

    decisions.calls.clear()
    code, plan = run_and_parse(
        capsys, "media-gen", "single", STORE_DIR, config=jev_config
    )
    assert code == 0
    assert _units(plan) == []
    assert plan["rigs"][HOST]["measured"]["cards"]
    assert not decisions.calls
    assert plan["decision"]["by"] == "none"


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
    assert _top(plan)["args"]["--model"] == CHECKPOINT
    assert SIZE_BYTES in _numbers(plan)


def test_recommend_with_no_backend_falls_back_deterministically(
    ssh: Any,
    classify: Any,
    probe: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No Jev unit: the plan picks deterministically, says so, and asks nothing."""
    ssh()
    decisions = classify()
    probe(live=False)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"]["by"] == "deterministic"
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
    """With no board to rank them, the largest fitting checkpoint is the pick."""
    recorder = ssh()
    recorder.ggufs = [OTHER, CHECKPOINT]
    recorder.header_builder = by_path
    recorder.header_sizes[CHECKPOINT] = SIZE_BYTES
    recorder.header_sizes[OTHER] = 3_000_000_000
    classify()
    probe(live=False)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["decision"]["by"] == "deterministic"
    unit = _top(plan)
    assert unit["args"]["--model"] == CHECKPOINT
    assert SIZE_BYTES in _numbers(plan)


def test_recommend_deterministic_knowledge_fallback_picks_the_largest_that_fits(
    ssh: Any,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The knowledge's MoE is larger than the card and fits with its experts in
    RAM; the rule names it, and its unit says how much went to RAM."""
    ssh()
    classify()
    probe(live=False)
    library()

    code, plan = run_and_parse(capsys, "coding", "single")
    assert code == 0
    assert plan["decision"]["by"] == "deterministic"
    unit = _top(plan)
    assert unit["model"]["id"] == "invented-org/invented-moe"
    assert unit["fit"]["ram_gib"] > 0
    assert unit["n_cpu_moe"] > 0
    assert unit["role"] == "sleeps-until-needed"
    fast = _units(plan)[0]
    assert fast["model"]["id"] == "invented-org/invented-dense"
    assert unit["swaps_with"] == [fast["name"]]


def test_recommend_with_a_reachable_jev_unit_says_jev_and_names_the_unit(
    ssh: Any,
    classify: Any,
    probe: Any,
    jev_config: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bound Jev unit answers the decision: the plan says ``jev`` and names it.

    Which unit is asked, and that no other is, is pinned by
    ``tests/test_recommend_asks_the_bound_jev_unit_and_no_other.py``.
    """
    ssh()
    decisions = classify()
    probe(live=True)

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR, config=jev_config)
    assert code == 0
    assert plan["decision"]["by"] == "jev"
    assert "'judge'" in plan["decision"]["why"]
    assert decisions.calls


def test_recommend_ships_the_scan_and_does_not_require_mcgyvr(
    ssh: Any, classify: Any, probe: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """The remote scan is the shipped ``python3 -`` script, not ``mcgyvr scan``.

    A fresh rig has ``python3`` but no mcgyvr installed; the scan must ship to
    the far end as bytes and answer through the same seam, so ``recommend``
    succeeds against a rig that only has python3.
    """
    recorder = ssh()
    classify()
    probe()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    scan_commands = [
        command for _host, command in recorder.commands if _is_scan_read(command)
    ]
    assert scan_commands, recorder.commands
    assert not any(
        command == "mcgyvr scan --json" for _host, command in recorder.commands
    )
    assert plan["unreachable"] == []


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


def test_recommend_plan_tells_the_three_scan_failure_modes_apart(
    monkeypatch: pytest.MonkeyPatch,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ssh failure, no scanner and a failed scan each say their own why."""
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
    classify()
    probe(live=False)
    library()

    code, plan = run_and_parse(
        capsys,
        "coding",
        "single",
        hosts=("ok-rig", "down-rig", "python-only-rig", "bad-scan-rig"),
    )
    assert code == 0
    why = {entry["host"]: entry["why"] for entry in plan["unreachable"]}
    assert set(why) == {"down-rig", "python-only-rig", "bad-scan-rig"}
    assert "ssh did not answer" in why["down-rig"]
    assert "python3" in why["python-only-rig"]
    assert "scan failed" in why["bad-scan-rig"]
    assert list(plan["rigs"]) == ["ok-rig"]


def test_users_are_the_strong_units_slots_and_change_what_fits(
    monkeypatch: pytest.MonkeyPatch,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--users single`` and ``--users 4`` size different chat processes.

    The recurrent checkpoint's per-slot state fits one slot and does not fit
    four, so four users fall back to the knowledge and get four slots; one
    user stays on the local checkpoint with one.
    """
    monkeypatch.setattr(
        scan_module,
        "_ssh",
        RecordedSsh(HOST, header_builder=recurrent_header),
    )
    classify()
    probe(live=False)
    library()

    single_code, single_plan = run_and_parse(capsys, "chat", "single", STORE_DIR)
    four_code, four_plan = run_and_parse(capsys, "chat", "4", STORE_DIR)

    assert single_code == 0
    assert four_code == 0
    assert single_plan["models_from"] == "local-store"
    assert _only(single_plan)["slots"] == 1
    assert four_plan["models_from"] == "knowledge"
    assert _only(four_plan)["slots"] == 4
    assert _only(four_plan)["args"]["--parallel"] == "4"


def test_recommend_treats_a_missing_store_dir_as_empty_not_a_failure(
    ssh: Any,
    classify: Any,
    probe: Any,
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
    classify()
    probe(live=False)

    code, plan = run_and_parse(capsys, "coding", "single", MISSING_STORE_DIR, STORE_DIR)
    assert code == 0
    assert plan["models_from"] == "local-store"
    assert _top(plan)["args"]["--model"] == CHECKPOINT
    assert plan["unreachable"] == []


def test_a_model_that_fits_by_size_and_not_with_its_cache_is_dropped_with_why(
    ssh: Any,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``kv-heavy`` is 6 GB, under the invented card's free VRAM; the cache its
    header prices at 32k per slot pushes it over, so the serving sizer refuses
    it as a top rung, awake or asleep, the plan names it under ``dropped``
    with the sizer's reason, and the ladder is the smaller model alone."""
    ssh()
    classify()
    probe(live=False)
    library(KV_HEAVY_LIBRARY)

    code, plan = run_and_parse(capsys, "coding", "single")
    assert code == 0
    assert _top(plan)["model"]["id"] == "invented-org/small"
    heavy = [d for d in plan["dropped"] if d["model"] == "invented-org/kv-heavy Q4_K_M"]
    assert heavy
    assert all("does not fit" in d["why"] for d in heavy)


def test_recommend_rejects_an_moe_whose_expert_spill_exceeds_host_ram(
    monkeypatch: pytest.MonkeyPatch,
    classify: Any,
    probe: Any,
    library: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An MoE that fits the card but not host RAM is not a local candidate.

    ``ram_heavy_moe_header`` spills 60 GiB of experts into a rig the scan
    reports with 48 GiB of available RAM, while its card load stays tiny. The
    serving sizer refuses it and the plan falls back to the knowledge rather
    than place a model whose resident expert weights the rig's RAM cannot hold.
    """
    monkeypatch.setattr(
        scan_module,
        "_ssh",
        RecordedSsh(HOST, header_builder=ram_heavy_moe_header),
    )
    classify()
    probe(live=False)
    library()

    code, plan = run_and_parse(capsys, "coding", "single", STORE_DIR)
    assert code == 0
    assert plan["models_from"] == "knowledge"
    assert CHECKPOINT not in _text(plan)
