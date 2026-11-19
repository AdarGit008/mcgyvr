"""The CPU's flags and clock are read on Linux, macOS and Windows.

The whole scan's ``cpu_detail`` holds the CPU flags the engine's builds are
chosen by, each true or false as the system answered, and the highest clock
the system states. Linux answers from /proc/cpuinfo (a flag its line leaves out
is one the CPU lacks), macOS from a sysctl name per flag (a name it does not
know is unknown), Windows from IsProcessorFeaturePresent (zero may mean "not
detectable", so only a present flag is taken). A flag nobody answered for is
unknown, never false, and a flag of the other arch is never listed.

The machines are invented; the flag names are the public ones each system
prints.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from tests.machine_shapes import host_scan_document, host_shape


def _detail(label: str, **changes: Any) -> dict[str, Any]:
    machine = dataclasses.replace(host_shape(label), **changes)
    detail = host_scan_document(machine)["cpu_detail"]
    assert isinstance(detail, dict)
    return detail


def test_a_linux_x86_cpu_is_read_from_its_flags_line() -> None:
    from mcgyvr.serving import rigscan

    detail = _detail(
        "linux-one-card",
        cpu_flags=("sse4_2", "avx", "avx2", "fma", "f16c", "avx512f", "avx512_vnni"),
        cpu_max_mhz=4500,
    )
    flags = detail["flags"]
    assert set(flags) == set(rigscan.X86_FLAGS)
    assert flags["avx2"] is True and flags["avx512_vnni"] is True
    assert flags["avx_vnni"] is False and flags["amx_int8"] is False
    assert detail["flags_from"] == "/proc/cpuinfo flags"
    assert (detail["max_mhz"], detail["max_mhz_from"]) == (
        4500,
        "cpufreq cpuinfo_max_freq",
    )


def test_a_linux_arm_cpu_is_read_from_its_features_line() -> None:
    detail = _detail("linux-one-card", arm=True, cpu_flags=("dotprod", "fp16", "i8mm"))
    flags = detail["flags"]
    assert set(flags) == {
        "dotprod",
        "fp16",
        "sve",
        "sve2",
        "i8mm",
        "bf16",
        "sme",
        "sme2",
    }
    assert flags["dotprod"] is True and flags["fp16"] is True
    assert flags["sve"] is False and flags["sme2"] is False
    assert detail["flags_from"] == "/proc/cpuinfo Features"


def test_half_of_the_fp16_pair_on_linux_arm_is_no_fp16() -> None:
    from unittest import mock

    from tests import machine_shapes

    original = machine_shapes._cpuinfo_flags
    with mock.patch.object(
        machine_shapes,
        "_cpuinfo_flags",
        lambda machine: original(machine).replace(" asimdhp", ""),
    ):
        detail = _detail("linux-one-card", arm=True, cpu_flags=("fp16",))
    assert detail["flags"]["fp16"] is False


def test_a_linux_cpu_with_no_flags_line_has_its_flags_unknown() -> None:
    from mcgyvr.scan import Scan

    document = host_scan_document(host_shape("linux-one-card"))
    assert document["cpu_detail"]["flags"] == {}
    assert document["cpu_detail"]["flags_from"] is None
    assert document["cpu_detail"]["max_mhz"] is None
    detail = Scan.from_json(json.dumps(document)).cpu_detail
    assert detail is not None and detail.has("avx2") is None


def test_apple_silicon_answers_each_flag_by_its_sysctl_name() -> None:
    detail = _detail("unified-laptop", cpu_flags=("dotprod", "fp16", "i8mm", "bf16"))
    flags = detail["flags"]
    assert flags["dotprod"] is True and flags["bf16"] is True
    assert flags["sme"] is False
    # The kernel has no SVE name: unknown, not false.
    assert "sve" not in flags and "sve2" not in flags
    assert detail["flags_from"] == "sysctl hw.optional"
    assert detail["max_mhz"] is None and detail["max_mhz_from"] is None


def test_an_intel_mac_answers_its_flags_and_clock_by_sysctl() -> None:
    detail = _detail(
        "mac-without-unified",
        cpu_flags=("sse4_2", "avx", "avx2", "fma", "f16c", "bmi2"),
        cpu_max_mhz=3600,
    )
    flags = detail["flags"]
    assert flags["avx"] is True and flags["avx2"] is True
    assert flags["avx512f"] is False
    # macOS names no VNNI, BF16 or AMX flag: unknown.
    assert "avx_vnni" not in flags and "amx_int8" not in flags
    assert (detail["max_mhz"], detail["max_mhz_from"]) == (
        3600,
        "sysctl hw.cpufrequency_max",
    )


def test_windows_takes_only_the_flags_it_says_are_present() -> None:
    detail = _detail(
        "windows-one-card",
        cpu_flags=("sse4_2", "avx", "avx2"),
        cpu_max_mhz=3800,
    )
    assert detail["flags"] == {"sse4_2": True, "avx": True, "avx2": True}
    assert detail["flags_from"] == "IsProcessorFeaturePresent"
    assert (detail["max_mhz"], detail["max_mhz_from"]) == (
        3800,
        "Win32_Processor MaxClockSpeed",
    )


def test_a_windows_arm_cpu_is_asked_its_arm_flags() -> None:
    detail = _detail("windows-no-modules", arm=True, cpu_flags=("dotprod", "fp16"))
    assert detail["flags"] == {"dotprod": True, "fp16": True}


def test_windows_with_no_flag_present_and_no_clock_has_both_unknown() -> None:
    detail = host_scan_document(host_shape("windows-one-card"))["cpu_detail"]
    assert detail == {
        "flags": {},
        "flags_from": None,
        "max_mhz": None,
        "max_mhz_from": None,
    }


def test_the_windows_feature_call_is_unknown_off_windows() -> None:
    from mcgyvr.serving import rigscan

    assert rigscan._processor_feature(39) is None


@pytest.mark.parametrize("mhz", [0, 10**7])
def test_a_clock_out_of_any_range_is_unknown(mhz: int) -> None:
    detail = _detail("windows-one-card", cpu_max_mhz=mhz)
    assert detail["max_mhz"] is None and detail["max_mhz_from"] is None
