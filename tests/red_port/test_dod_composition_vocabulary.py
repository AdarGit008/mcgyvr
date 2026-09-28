"""S12 — one `Verdict` and one `Outcome` on the composition path.

On the composition path (``route``, ``verify``, ``availability``, ``escalate``)
``route.Verdict`` and ``escalate.Outcome`` are the single meaning of each word; the
others are ``AvailabilityVerdict``, ``ReviewVerdict`` and ``ReviewOutcome``.

The guard below holds both halves: the distinct names exist, and ``availability`` and
``verify`` export no bare ``Verdict`` or ``Outcome``.
"""

from __future__ import annotations


def test_the_composition_path_names_its_verdicts_distinctly() -> None:
    from mcgyvr.availability import AvailabilityVerdict
    from mcgyvr.route import Verdict
    from mcgyvr.verify import ReviewVerdict

    assert len({AvailabilityVerdict, ReviewVerdict, Verdict}) == 3


def test_the_composition_path_names_its_outcomes_distinctly() -> None:
    from mcgyvr.escalate import Outcome
    from mcgyvr.verify import ReviewOutcome

    assert len({ReviewOutcome, Outcome}) == 2


def test_the_bare_names_no_longer_leak_from_verify_and_availability() -> None:
    import mcgyvr.availability as availability
    import mcgyvr.verify as verify

    assert not hasattr(availability, "Verdict"), "availability still exports `Verdict`"
    assert not hasattr(verify, "Verdict"), "verify still exports `Verdict`"
    assert not hasattr(verify, "Outcome"), "verify still exports `Outcome`"
