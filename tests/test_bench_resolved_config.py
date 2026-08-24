"""The resolved serving configuration, and the refusal it makes possible (#358).

**The canary this file exists for is the last item of #358's definition of done:**
*"two rows differing only in a resolved field, and the contrast declines them. A
gate nobody has watched refuse is a gate nobody knows works."* That case is
:func:`test_two_rows_differing_only_in_a_resolved_field_are_refused`, and it does
not build its two digests from fixtures — it computes them from the two rigs'
own startup logs and ``/server_info`` payloads, committed under
``records/evidence/2026-08-24-resolved-config/``.

**What those two payloads are.** One image digest
(``vllm/vllm-openai:v0.26.0``), one model, one identical argument list
(``--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16
--enforce-eager``), launched on srv1 and on srv2 on 2026-08-24. Both servers
answer ``vllm 0.26.0``. srv1 resolved ``TRITON_ATTN`` and the torch sampler;
srv2 resolved ``FLASH_ATTN`` and FlashInfer. Nothing in the record could say so
before this issue, and `serving_semantic_sha256` — the digest taken over
``/server_info`` — cannot say so now: that surface carries
``linear_backend='auto'`` on both and no attention or sampler key at all.

**A correction to #358's body, which this measurement supersedes.** The issue
states the divergence as srv1 ``float16`` against srv2 ``bfloat16``. On this
model both rigs resolve ``torch.float16``; the dtype claim came from a different
cell in the phase-0 evidence and does not hold for the 1.5B AWQ pair. The
divergence is real and it is the attention backend and the sampler, which is
what the canary keys on.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence" / "2026-08-24-resolved-config"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fingerprint() -> Any:
    return _by_path(
        "serving_fingerprint", REPO / "tools" / "bench" / "serving" / "fingerprint.py"
    )


@pytest.fixture(scope="module")
def identity() -> Any:
    return _by_path("bench_identity_r", REPO / "tools" / "bench" / "identity.py")


def _rig(fingerprint: Any, host: str, asked: dict[str, Any] | None = None) -> Any:
    """The resolved block for one rig, computed from its committed readings."""
    log = (EVIDENCE / f"{host}-startup.log").read_text(errors="replace")
    info = json.loads((EVIDENCE / f"{host}-server_info.json").read_text())
    return fingerprint.resolved(
        log_lines=log.splitlines(),
        config=info["vllm_config"],
        asked=asked or {},
    )


# --- the canary -------------------------------------------------------------


def test_two_rows_differing_only_in_a_resolved_field_are_refused(
    fingerprint: Any, identity: Any
) -> None:
    """#358's last box, watched refusing.

    The two rows are identical in every keyed field — same model, same endpoint,
    same build string, same bar, same round — and differ only in the digest of
    what their engines resolved. Before this issue the pair was a contrast the
    guard would have compared and reported.
    """
    srv1, srv2 = _rig(fingerprint, "srv1"), _rig(fingerprint, "srv2")
    assert srv1["serving_resolved_sha256"] != srv2["serving_resolved_sha256"]

    def row(condition: str, digest: str) -> dict[str, Any]:
        return {
            "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ",
            "endpoint": "http://rig:8000",
            "serving_build": "vllm 0.26.0 via docker",
            "protocol": "openai",
            "tier": "bench-py",
            "condition": condition,
            "greedy_temperature": 0.0,
            "max_output_tokens": 2048,
            "tasks_sha256": {"function_implementation": "abc123"},
            "gate_rungs": ["scope", "secrets", "structured", "adapters", "acceptance"],
            "round": "r1-commissioning",
            "product_sha256": "ed508e61",
            "serving_resolved_sha256": digest,
        }

    pair = [
        row("stock", srv1["serving_resolved_sha256"]),
        row("planonly", srv2["serving_resolved_sha256"]),
    ]
    with pytest.raises(identity.IdentityError, match="serving_resolved_sha256"):
        identity.require_comparable(pair)

    # And the same two rows ARE compared once they resolved alike — otherwise
    # the case above would pass against a guard that refuses everything.
    same = [
        row("stock", srv1["serving_resolved_sha256"]),
        row("planonly", srv1["serving_resolved_sha256"]),
    ]
    identity.require_comparable(same)


def test_the_build_string_alone_would_have_compared_them(fingerprint: Any) -> None:
    """Why the field had to be added rather than the existing one relied on.

    Both rigs answer the same version, and both were reached through the same
    launcher in this pair — so even #358's own `serving_build` fix does not
    separate them. The instrument differed below the name.
    """
    srv1, srv2 = _rig(fingerprint, "srv1"), _rig(fingerprint, "srv2")
    assert srv1["resolved"]["attention_backend"]["value"] == "TRITON_ATTN"
    assert srv2["resolved"]["attention_backend"]["value"] == "FLASH_ATTN"
    assert srv1["resolved"]["sampler_path"]["value"] == "torch"
    assert srv2["resolved"]["sampler_path"]["value"] == "flashinfer"


def test_the_asked_for_digest_cannot_see_the_difference(fingerprint: Any) -> None:
    """The measurement that made a second digest necessary rather than a wider one.

    `/server_info` differs across the two hosts only in KV sizing, an instance
    nonce, and the iteration order of a set of layer names. Every field the
    kernels are chosen by is either absent from it or carries the policy word
    `auto`. So no amount of widening the asked-for pin reaches the divergence.
    """
    payloads = {
        host: json.loads((EVIDENCE / f"{host}-server_info.json").read_text())[
            "vllm_config"
        ]
        for host in ("srv1", "srv2")
    }
    for host, config in payloads.items():
        assert config["kernel_config"]["linear_backend"] == "auto", host
        assert config["kernel_config"]["moe_backend"] == "auto", host
        flat = json.dumps(config)
        assert "attention_backend" not in flat, host
        assert "sampler" not in flat.lower(), host


# --- what a resolved field is, and what it is not ---------------------------


def test_every_declared_field_is_read_or_the_digest_refuses(fingerprint: Any) -> None:
    """Absence is not agreement, one level in.

    A digest computed over ``{"attention_backend": null}`` is a value two servers
    can share while running different kernels. So a field the engine did not
    state leaves the digest null, and `require_comparable` refuses the row.
    """
    empty = fingerprint.resolved(log_lines=[], config={}, asked={})
    assert empty["serving_resolved_sha256"] is None
    assert "no digest was computed" in empty["refused"]
    for field in fingerprint.RESOLVED_READS:
        assert field in empty["refused"], field

    # A log without the engine's kernel lines is not rescued by a full config.
    info = json.loads((EVIDENCE / "srv1-server_info.json").read_text())
    half = fingerprint.resolved(log_lines=[], config=info["vllm_config"], asked={})
    assert half["serving_resolved_sha256"] is None
    assert "attention_backend" in half["refused"]


def test_the_srv1_sampler_is_read_from_a_fallback_sentence(fingerprint: Any) -> None:
    """The read that a single-shape grep turned into an absence.

    The 2026-08-24 sweep matched ``FlashInfer for top`` and so saw srv2's sampler
    and not srv1's. srv1 states its sampler as a fallback WITH the engine's
    reason, and reading only the success shape loses both.
    """
    srv1 = _rig(fingerprint, "srv1")
    entry = srv1["resolved"]["sampler_path"]
    assert entry["value"] == "torch"
    assert "unsupported compute capability 7.5" in entry["line"]
    assert entry["resolved_by_engine"] is True


def test_a_policy_only_field_says_so(fingerprint: Any) -> None:
    """`kv_cache_dtype` is in the digest and is not evidence of agreement.

    The engine restates it as the policy it was handed and never as the outcome
    it reached, on both `/server_info` and the startup log. Declared, so a reader
    is not left to infer it from a value that looks resolved.
    """
    srv1 = _rig(fingerprint, "srv1")
    entry = srv1["resolved"]["kv_cache_dtype"]
    assert entry["value"] == "auto"
    assert entry["resolved_by_engine"] is False
    assert "never as the outcome" in entry["limit"]
    assert "kv_cache_dtype" in fingerprint.RESOLVED_POLICY_ONLY


# --- asked against resolved (#358 box 5) ------------------------------------


def test_a_backend_that_was_asked_for_and_not_honoured_is_recorded(
    fingerprint: Any,
) -> None:
    """ADR-0027 D2's shape: the value, and the engine's reason it is not the ask."""
    block = _rig(fingerprint, "srv1", asked={"VLLM_ATTENTION_BACKEND": "FLASHINFER"})
    assert len(block["disagreements"]) == 1
    (found,) = block["disagreements"]
    assert found["field"] == "attention_backend"
    assert found["asked"] == "FLASHINFER"
    assert found["resolved"] == "TRITON_ATTN"
    assert "TRITON_ATTN attention backend" in found["reason"]
    assert block["resolved"]["attention_backend"]["agrees"] is False


def test_an_honoured_ask_is_not_a_disagreement(fingerprint: Any) -> None:
    """The direction a naive equality test gets wrong.

    `--dtype float16` is honoured by an engine that reports `torch.float16`, and
    a run that asked for the backend it got must not be flagged.
    """
    block = _rig(
        fingerprint,
        "srv1",
        asked={"VLLM_ATTENTION_BACKEND": "TRITON_ATTN", "--dtype": "float16"},
    )
    assert block["disagreements"] == []
    assert block["resolved"]["dtype"]["agrees"] is True


def test_a_policy_word_is_never_read_as_agreement(fingerprint: Any) -> None:
    """`auto` must not vouch for whatever it produced."""
    block = _rig(fingerprint, "srv1", asked={"--dtype": "auto"})
    assert block["resolved"]["dtype"]["agrees"] is None
    assert block["disagreements"] == []


def test_every_uncompared_field_says_why(fingerprint: Any) -> None:
    """Not-compared and nobody-wrote-the-comparison are two different states.

    A bare ``None`` in :data:`RESOLVED_ASKED_BY` says neither, so each one owes a
    reason and the test holds the two lists to each other.
    """
    uncompared = {f for f, a in fingerprint.RESOLVED_ASKED_BY.items() if a is None}
    assert uncompared == set(fingerprint.RESOLVED_NOT_COMPARED)
    block = _rig(fingerprint, "srv1")
    for field in uncompared:
        assert block["resolved"][field]["not_compared"]


def test_the_declared_fields_and_their_sources_agree(fingerprint: Any) -> None:
    """Every declared field is reachable, and nothing is declared twice over."""
    assert set(fingerprint.RESOLVED_READS) == set(fingerprint.RESOLVED_ASKED_BY)
    from_log = {f for f, r in fingerprint.RESOLVED_READS.items() if r == "startup log"}
    signatures = {f for f, _, _ in fingerprint.RESOLVED_SIGNATURES}
    assert signatures == from_log
    from_config = set(fingerprint.RESOLVED_READS) - from_log
    assert set(fingerprint.RESOLVED_PATHS) == from_config


def test_the_key_carries_the_resolved_digest_and_not_the_asked_one(
    identity: Any,
) -> None:
    """Which of the two pins the guard reads, stated as a check.

    `serving_semantic_sha256` stays on the row and out of the key: it was
    byte-identical across two engines running different kernels, so keying on it
    would be keying on a field that has already been shown not to separate them.
    """
    assert "serving_resolved_sha256" in identity.KEY
    assert "serving_semantic_sha256" not in identity.KEY
    assert "serving_resolved_sha256" in identity.GROUPS["server"]
