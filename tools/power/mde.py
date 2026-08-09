"""Paired-design power arithmetic for the floor bench.

Every arm on the bench (ADR-0018 Q1) compares two conditions over the *same*
tasks, so the test is McNemar's and the quantity that carries the power is not
the task count. It is the number of tasks whose verdict actually *differs*
between the two conditions — the discordant pairs. Tasks that pass under both,
or fail under both, contribute exactly nothing: they are not weak evidence of a
small effect, they are absent from the test statistic.

That is why nominal *n* is the wrong denominator for sizing an instrument, and
why the folk arithmetic "halving the detectable effect costs 4x the tasks" is
optimistic by however far the discordance rate sits below 1.

Two rates, kept distinct throughout:

``psi``    the **discordance rate** — P(a task's verdict differs between the two
           conditions). Estimated per *contrast*, and a property of the
           (instrument, lever) pair, never of the task set alone.
``delta``  the **net effect** — P(fail->pass) - P(pass->fail), which is what a
           pass-rate table reports as a difference.

``psi >= |delta|`` always, and the gap between them is churn: tasks that flip in
both directions and cancel in the headline number while still costing power.

Small-*n* honesty
-----------------
The textbook normal approximation is not usable at the sizes this repository
owns. Under the exact conditional test a contrast with ``m`` discordant pairs has
a best-case two-sided p of ``2 / 2**m``, so **m >= 6 is a hard floor**: below it
no effect of any magnitude reaches p < 0.05, and an asymptotic formula will
quote a minimum detectable effect anyway. Everything here respects that wall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache

ALPHA = 0.05
POWER = 0.80

# Below this many discordant pairs the exact test cannot reach ALPHA at any
# effect size: the whole conditional null has too little mass to spend.
MIN_DISCORDANT = 6

# Above this many discordant pairs the conditional binomial is summed by normal
# approximation with a continuity correction rather than term by term. At m in
# the hundreds that agrees with the exact sum to well past the precision any
# sizing decision uses, and it is what keeps required_n affordable at n in the
# tens of thousands. Exactness is preserved where it decides anything — the
# MIN_DISCORDANT wall and every contrast this repository has actually measured.
EXACT_M_LIMIT = 400


def _log_binom_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return -math.inf
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


@cache
def exact_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for ``b`` gains against ``c`` losses.

    Summed in log space: ``comb(m, i) / 2**m`` is the natural way to write it and
    overflows the float conversion once ``m`` passes ~1000.
    """
    m = b + c
    if m == 0:
        return 1.0
    k = min(b, c)
    terms = [_log_binom_pmf(i, m, 0.5) for i in range(k + 1)]
    peak = max(terms)
    tail = peak + math.log(math.fsum(math.exp(t - peak) for t in terms))
    return min(1.0, 2.0 * math.exp(tail))


@cache
def critical_k(m: int, alpha: float = ALPHA) -> int | None:
    """Largest ``k`` with ``min(b, c) <= k`` rejecting at ``alpha``.

    ``None`` when no split of ``m`` discordant pairs rejects — the
    ``m < MIN_DISCORDANT`` wall. Walks *down* from the centre so the cost is
    O(sqrt(m)) rather than O(m): the threshold sits about ``z * sqrt(m) / 2``
    below ``m / 2``, and the binomial is stepped by its own pmf ratio.
    """
    if m < MIN_DISCORDANT:
        return None
    # Seed the walk at the centre, where the symmetric binomial's CDF is known
    # in closed form: exactly 0.5 for odd m, and 0.5 + pmf(m/2)/2 for even m.
    k = m // 2
    log_pmf_k = _log_binom_pmf(k, m, 0.5)
    cdf = 0.5 if m % 2 else 0.5 + math.exp(log_pmf_k) / 2.0
    while k >= 0:
        if 2.0 * cdf < alpha:
            return k
        # Step down: P(X <= k-1) = P(X <= k) - pmf(k), pmf(k-1) = pmf(k)*k/(m-k+1)
        cdf -= math.exp(log_pmf_k)
        log_pmf_k += math.log(k) - math.log(m - k + 1)
        k -= 1
    return None


def _reject_prob(m: int, theta: float, alpha: float) -> float:
    """P(reject | m discordant pairs), with gains ~ Binomial(m, theta)."""
    k = critical_k(m, alpha)
    if k is None:
        return 0.0
    if m <= EXACT_M_LIMIT:
        lower = math.fsum(math.exp(_log_binom_pmf(b, m, theta)) for b in range(k + 1))
        upper = math.fsum(
            math.exp(_log_binom_pmf(b, m, theta)) for b in range(m - k, m + 1)
        )
        return min(1.0, lower + upper)
    mean = m * theta
    sd = math.sqrt(m * theta * (1.0 - theta))
    if sd == 0.0:
        return 1.0 if (mean <= k or mean >= m - k) else 0.0
    lower = _norm_cdf((k + 0.5 - mean) / sd)
    upper = 1.0 - _norm_cdf((m - k - 0.5 - mean) / sd)
    return min(1.0, lower + upper)


def exact_power(n: int, psi: float, delta: float, alpha: float = ALPHA) -> float:
    """Power of the two-sided McNemar test at ``n`` paired tasks.

    Conditions on the discordant count — ``m ~ Binomial(n, psi)``, and given
    ``m`` the gains are ``Binomial(m, (psi + delta) / (2 * psi))`` — so the cost
    is a sum over ``m`` rather than over the whole (b, c) grid.
    """
    if n <= 0 or psi <= 0.0 or psi > 1.0 or abs(delta) > psi:
        return 0.0
    theta = (psi + delta) / (2.0 * psi)

    sd = math.sqrt(n * psi * (1.0 - psi))
    lo = max(MIN_DISCORDANT, int(n * psi - 10.0 * sd) - 1)
    hi = min(n, math.ceil(n * psi + 10.0 * sd) + 1)

    total = 0.0
    for m in range(lo, hi + 1):
        log_pm = _log_binom_pmf(m, n, psi)
        if log_pm < -60.0:
            continue
        total += math.exp(log_pm) * _reject_prob(m, theta, alpha)
    return min(1.0, total)


def required_n(
    delta: float,
    psi: float,
    power: float = POWER,
    alpha: float = ALPHA,
    cap: int = 100_000,
) -> int | None:
    """Smallest paired *n* reaching ``power`` for a net effect of ``delta``.

    ``None`` means ``cap`` tasks are not enough, which is a real answer about the
    bar rather than a failure of the search.
    """
    if delta <= 0.0 or psi < delta or psi > 1.0:
        return None
    if exact_power(cap, psi, delta, alpha) < power:
        return None
    lo, hi = 1, cap
    while lo < hi:
        mid = (lo + hi) // 2
        if exact_power(mid, psi, delta, alpha) >= power:
            hi = mid
        else:
            lo = mid + 1
    return lo


def detectable_delta(
    n: int, psi: float, power: float = POWER, alpha: float = ALPHA
) -> float | None:
    """Smallest net effect ``n`` tasks resolve, quantised to whole tasks.

    Quantised on purpose: an instrument cannot report an effect finer than one
    task, and a continuous minimum-detectable-effect hides that. ``None`` means
    no effect is detectable at any size.
    """
    if n <= 0 or psi <= 0.0:
        return None
    for k in range(1, n + 1):
        delta = k / n
        if delta > psi:
            return None
        if exact_power(n, psi, delta, alpha) >= power:
            return delta
    return None


@dataclass(frozen=True)
class Contrast:
    """One measured two-condition comparison over a paired task set."""

    label: str
    n: int
    gained: int  # fail -> pass
    lost: int  # pass -> fail

    @property
    def discordant(self) -> int:
        return self.gained + self.lost

    @property
    def psi(self) -> float:
        return self.discordant / self.n

    @property
    def net(self) -> int:
        return self.gained - self.lost

    @property
    def delta(self) -> float:
        return self.net / self.n

    @property
    def p_value(self) -> float:
        return exact_p(self.gained, self.lost)

    @property
    def can_ever_reject(self) -> bool:
        """Whether *any* split of this many discordant pairs could reach alpha.

        False is a finding rather than an error: it says the contrast was
        unresolvable before the model was ever dispatched, so its p-value
        reports nothing about the lever.
        """
        return critical_k(self.discordant, ALPHA) is not None
