"""
Probing / membership-inference attack simulation -> EMPIRICAL ADVANTAGE.

Threat model (manuscript Sec. 6): an adversary corrupts k banks and wants to
learn whether a specific honest bank contributed a target account x*. This is
the standard DP membership experiment on neighboring datasets D0, D1 that
differ in exactly one honest bank's membership of x*.

Procedure:
  - Fix the coverage of x* from the k corrupted banks (adversary's own input).
  - World 0: one specific honest bank does NOT have x*  -> c = c_base
  - World 1: that honest bank DOES have x*             -> c = c_base + 1
    (constructed so the decision boundary c == t is straddled, the hardest,
     most-leaky case for the defender.)
  - The adversary observes the release M (noisy threshold decision, and if
    released, the clamped noisy count) and guesses the world via the optimal
    likelihood-ratio test.

Empirical advantage = 2 * (attack_accuracy - 0.5), matching the manuscript.
Compared against the theoretical bound (e^eps - 1)/(e^eps + 1) + delta.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Tuple

from protocol import laplace


def _release(c: float, t: int, eps_dp: float, clamp_max: int, rng: random.Random):
    """Return observable release for a single target under the protocol.
    Observable = (decided_in: bool, clamped_count or None)."""
    if eps_dp == float("inf"):
        decided = c >= t
        return (decided, (int(round(c)) if decided else None))
    scale = 1.0 / eps_dp
    noisy_dec = c + laplace(scale, rng)
    decided = noisy_dec >= t
    cnt = None
    if decided:
        noisy_cnt = c + laplace(scale, rng)
        cnt = int(max(0, min(clamp_max, round(noisy_cnt))))
    return (decided, cnt)


def _laplace_pdf(x: float, mu: float, scale: float) -> float:
    return math.exp(-abs(x - mu) / scale) / (2 * scale)


def empirical_advantage(
    eps_dp: float,
    t: int = 3,
    c_base: int = 2,          # coverage in world 0 (straddles boundary c_base+1 == t when t = c_base+1)
    clamp_max: int = 5,
    trials: int = 20000,
    seed: int = 7,
    use_count: bool = True,
) -> Tuple[float, float]:
    """Return (empirical_advantage, attack_accuracy).

    Optimal attacker: observes release, computes likelihood ratio between
    world1 (c = c_base+1) and world0 (c = c_base), guesses the larger.
    """
    rng = random.Random(seed)
    c0, c1 = float(c_base), float(c_base + 1)

    if eps_dp == float("inf"):
        # No noise: decision perfectly reveals which side of the boundary.
        # world0: c0 vs t ; world1: c1 vs t. If exactly one is >= t, advantage=1.
        d0 = c0 >= t
        d1 = c1 >= t
        acc = 1.0 if d0 != d1 else 0.5
        return (2 * (acc - 0.5), acc)

    scale = 1.0 / eps_dp
    correct = 0
    for _ in range(trials):
        world = rng.randint(0, 1)
        c = c1 if world == 1 else c0
        decided, cnt = _release(c, t, eps_dp, clamp_max, rng)

        # Likelihood of this observation under each world (marginalize noise).
        # P(decided | c) = P(c + Lap >= t) = tail of Laplace.
        def p_decided(cc):
            z = (t - cc)
            if z <= 0:
                return 1 - 0.5 * math.exp(-z / scale) if False else (1 - 0.5 * math.exp(z / scale))
            return 0.5 * math.exp(-z / scale)
        # careful, rewrite cleanly below
        def tail_ge(cc):
            # P(cc + L >= t) with L ~ Lap(0,scale)
            z = t - cc
            if z <= 0:
                return 1 - 0.5 * math.exp(-abs(z) / scale)
            return 0.5 * math.exp(-abs(z) / scale)

        p0 = tail_ge(c0) if decided else (1 - tail_ge(c0))
        p1 = tail_ge(c1) if decided else (1 - tail_ge(c1))

        if decided and use_count and cnt is not None:
            # Multiply by likelihood of the clamped count (approx via pdf at cnt).
            p0 *= max(1e-12, _laplace_pdf(cnt, c0, scale))
            p1 *= max(1e-12, _laplace_pdf(cnt, c1, scale))

        guess = 1 if p1 > p0 else (0 if p0 > p1 else rng.randint(0, 1))
        if guess == world:
            correct += 1

    acc = correct / trials
    return (2 * (acc - 0.5), acc)


def theoretical_bound(eps_dp: float, delta: float = 0.0) -> float:
    if eps_dp == float("inf"):
        return 1.0
    return (math.exp(eps_dp) - 1) / (math.exp(eps_dp) + 1) + delta


def _tail_ge(level: float, cc: float, scale: float) -> float:
    """P(cc + Lap(0,scale) >= level)."""
    z = level - cc
    if z <= 0:
        return 1 - 0.5 * math.exp(-abs(z) / scale)
    return 0.5 * math.exp(-abs(z) / scale)


def empirical_advantage_2stage(
    eps_gate: float,
    eps_dec: float,
    t: int = 3,
    candidate_level: int = 2,
    c_base: int = 2,
    clamp_max: int = 5,
    trials: int = 40000,
    seed: int = 7,
    use_count: bool = True,
):
    """Empirical advantage against the DP-SAFE two-stage mechanism.

    Attacker observes the full view: (gate_pass, decided, count).
      Stage 1 (candidacy gate): pass iff c + Lap(1/eps_gate) >= candidate_level
      Stage 2 (decision):       release iff c + Lap(1/eps_dec) >= t
    Total probing budget = eps_gate + eps_dec (basic composition); we compare
    the empirical advantage against the bound at that TOTAL budget.
    """
    rng = random.Random(seed)
    c0, c1 = float(c_base), float(c_base + 1)
    inf = float("inf")

    if eps_gate == inf and eps_dec == inf:
        def obs(cc):
            g = cc >= candidate_level
            d = g and (cc >= t)
            return (g, d)
        o0, o1 = obs(c0), obs(c1)
        acc = 1.0 if o0 != o1 else 0.5
        return (2 * (acc - 0.5), acc)

    sg = 1.0 / eps_gate
    sd = 1.0 / eps_dec
    correct = 0
    for _ in range(trials):
        world = rng.randint(0, 1)
        c = c1 if world == 1 else c0
        gate_pass = (c + laplace(sg, rng)) >= candidate_level
        decided = False
        cnt = None
        if gate_pass:
            decided = (c + laplace(sd, rng)) >= t
            if decided:
                cnt = int(max(0, min(clamp_max, round(c + laplace(sd, rng)))))

        def like(cc):
            pg = _tail_ge(candidate_level, cc, sg)
            if not gate_pass:
                return 1 - pg
            pd = _tail_ge(t, cc, sd)
            if not decided:
                return pg * (1 - pd)
            val = pg * pd
            if use_count and cnt is not None:
                val *= max(1e-12, _laplace_pdf(cnt, cc, sd))
            return val

        p0, p1 = like(c0), like(c1)
        guess = 1 if p1 > p0 else (0 if p0 > p1 else rng.randint(0, 1))
        if guess == world:
            correct += 1

    acc = correct / trials
    return (2 * (acc - 0.5), acc)
