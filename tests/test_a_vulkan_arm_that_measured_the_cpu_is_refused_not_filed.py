"""A bench row is filed under the backend that ran, and a backend the image
declared but did not run is a refusal, not a number.

On 2026-09-02 the A3 arm (``GGML_VULKAN=ON``) filed four ``BENCH`` rows at
88-90 tok/s prefill. They were the six-core i5-9600K: ``libggml-vulkan.so``
dlopened, found no Vulkan device, and ggml fell back to the CPU backend without
a word. llama-bench's own report says ``backend: CPU`` on every entry, and the
step did not read it. The correction was written by hand afterwards
(``### CORRECTION arm=A3 ... measured_backend=cpu``).

So the parser now carries ``backend=`` from the report into every row, and
``_common.sh`` gains ``backend_verdict DECLARED MEASURED``: the image's own
``org.mcgyvr.build.backend`` label against what llama-bench reported. A
declared ``vulkan`` that measured ``CPU`` exits non-zero with the reason; an
image that declares nothing (the upstream ``server-cuda`` image, arm A1) is
not judged. ``3-llama-bench.sh`` files a ``refused`` row on that verdict
instead of ``BENCH`` rows.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests import onedoor

BENCH_SH = onedoor.KERNEL_ARMS / "3-llama-bench.sh"


def _parser_source() -> str:
    text = BENCH_SH.read_text(encoding="utf-8")
    head, _, rest = text.partition("<<'PY'\n")
    assert head, "3-llama-bench.sh does not embed its parser under <<'PY'"
    body, _, _ = rest.partition("\nPY\n")
    return body


def _entry(**override: object) -> dict[str, object]:
    base: dict[str, object] = {
        "build_commit": "d7a207411",
        "model_filename": "/models/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf",
        "model_type": "qwen2 3B Q4_K - Medium",
        "n_gpu_layers": 99,
        "flash_attn": 1,
        "n_prompt": 512,
        "n_gen": 0,
        "avg_ts": 90.5387,
        "stddev_ts": 0.226935,
        "samples_ts": [90.4, 90.6, 90.7],
        "backends": "CPU",
    }
    base.update(override)
    return base


def test_the_parser_carries_the_reported_backend_into_every_row(
    tmp_path: Path,
) -> None:
    parser = tmp_path / "parse.py"
    parser.write_text(_parser_source(), encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            [
                _entry(),
                _entry(n_prompt=0, n_gen=128, avg_ts=19.67, stddev_ts=0.13),
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["python3", str(parser), str(report)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    assert rows, result.stdout
    for row in rows:
        assert "backend=CPU" in row.split(), row


def _verdict(declared: str, measured: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            '. "$1"; backend_verdict "$2" "$3"',
            "bash",
            str(onedoor.COMMON_SH),
            declared,
            measured,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("declared", "measured"),
    [("vulkan", "CPU"), ("cuda", "CPU"), ("vulkan", "CUDA")],
)
def test_a_declared_backend_that_did_not_run_is_a_refusal(
    declared: str, measured: str
) -> None:
    result = _verdict(declared, measured)
    assert result.returncode != 0, (declared, measured, result.stderr)
    assert declared in result.stderr and measured in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("declared", "measured"),
    [("vulkan", "Vulkan"), ("cuda", "CUDA"), ("", "CPU"), ("", "CUDA")],
)
def test_a_backend_that_ran_as_declared_or_was_never_declared_passes(
    declared: str, measured: str
) -> None:
    result = _verdict(declared, measured)
    assert result.returncode == 0, (declared, measured, result.stderr)


def _report(backend: str) -> str:
    entries = []
    for fa in (0, 1):
        entries.append(_entry(flash_attn=fa, backends=backend))
        entries.append(
            _entry(flash_attn=fa, n_prompt=0, n_gen=128, avg_ts=19.6, backends=backend)
        )
    return json.dumps(entries)


def _bench_through_the_door(
    tmp_path: Path, *, declared: str, measured: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    """The real step 3 through the real door, against a docker on PATH whose
    image is labelled ``declared`` and whose llama-bench reports ``measured``."""
    import os
    import shutil

    campaign = "srv1-kernel-arms"
    root = onedoor.fixture_repo(tmp_path)
    shutil.copytree(
        onedoor.KERNEL_ARMS, root / "tools" / "runs" / "campaigns" / campaign
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    report = tmp_path / "report.json"
    report.write_text(_report(measured), encoding="utf-8")
    inspect = f'[{{"Id":"sha256:{onedoor.LOCAL_ID_HEX}","RepoDigests":[]}}]'
    # `ps` first: the run id carries the step name, so a looser match on
    # "llama-bench" would answer gate 7's `docker ps` with the report.
    stub = f"""#!/usr/bin/env bash
case "$*" in
  ps*) exit 0 ;;
  *org.mcgyvr.build.backend*) printf '%s\\n' '{declared}'; exit 0 ;;
  image*) printf '%s\\n' '{inspect}'; exit 0 ;;
  *"--entrypoint /app/llama-bench"*) cat '{report}'; exit 0 ;;
  *) exit 0 ;;
esac
"""
    docker = onedoor.executable(stubs / "docker", stub)
    models = tmp_path / "models" / "dense"
    models.mkdir(parents=True)
    (models / "Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf").write_bytes(b"gguf")
    env = onedoor.door_env(root, stubs, docker=docker)
    env["PATH"] = f"{stubs}{os.pathsep}{env['PATH']}"
    env["RUN_ARMS"] = "L3"
    env["RUN_MODELS_DIR"] = str(tmp_path / "models")
    env["RUN_RETRY_SLEEP"] = "0"
    result = onedoor.door(root, [campaign, "llama-bench", "--host", "srv1"], env)
    text = ""
    artifact = onedoor.envelope(root, campaign) / "srv1-llama-bench.tsv"
    if artifact.is_file():
        text = artifact.read_text(encoding="utf-8")
    return result, text


def test_the_bench_step_files_a_cpu_run_under_a_vulkan_tag_as_a_refusal(
    tmp_path: Path,
) -> None:
    """The 2026-09-02 A3 scenario, end to end: one REFUSED row that names both
    backends, no BENCH row, the bench goes on to ``### END`` and exits 0."""
    result, text = _bench_through_the_door(tmp_path, declared="vulkan", measured="CPU")
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    rows = [line.split("\t") for line in text.splitlines() if "\t" in line]
    kinds = sorted(r[2] for r in rows)
    assert kinds == ["REFUSED"], text
    refused = rows[0]
    assert "declared_backend=vulkan" in refused, text
    assert "measured_backend=CPU" in refused, text
    assert "tries=3" in refused, text
    assert any(line.startswith("### END") for line in text.splitlines()), text


def test_the_bench_step_files_bench_rows_when_the_declared_backend_ran(
    tmp_path: Path,
) -> None:
    result, text = _bench_through_the_door(tmp_path, declared="cuda", measured="CUDA")
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    rows = [line.split("\t") for line in text.splitlines() if "\t" in line]
    assert rows and all(r[2] == "BENCH" for r in rows), text
    assert all("backend=CUDA" in r for r in rows), text
