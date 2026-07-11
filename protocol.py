"""
Functional simulation of the ThrLabel-PSI protocol's INFORMATION-RELEASE layer.

What this models (and what it does NOT):
- We do NOT re-implement OPRF / OKVS / (2,2) secret sharing. Those layers are
  proven to reveal nothing beyond the protocol's defined output (see manuscript
  Sec. 6). They do not affect correctness or the privacy-utility tradeoff.
- We DO model exactly the part that determines utility and leakage: the
  threshold decision c(x) >= t computed under differential-privacy noise, plus
  the output-stage clamped-count release and label aggregation.

Four-layer defense (manuscript Sec. 4.4) reproduced here:
  (1) threshold margin  t >= k + 2      -> enforced/checked by caller
  (2) submission cap B + audit          -> fixed-B dummy padding at input
  (3) output-stage DP: M(c) = clamp(c + Lap(1/eps_dp))  (released count)
  (4) noisy threshold: SecureCompare(c + Lap(1/eps_dp) >= t)  (decision)
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from datagen import Dataset, FRAUD_TYPES, N_TIME_BUCKETS


def laplace(scale: float, rng: random.Random) -> float:
    """Sample Laplace(0, scale) via inverse-CDF."""
    u = rng.random() - 0.5
    # sign(u) * -scale * ln(1 - 2|u|)
    import math
    return -scale * (1 if u >= 0 else -1) * math.log(1 - 2 * abs(u))


@dataclass
class ProtocolOutput:
    released_set: Set[str]                 # accounts decided >= t (noisy)
    released_count: Dict[str, int]         # clamped noisy count per released acct
    aggregated_label: Dict[str, dict]      # majority fraud type + mean risk, etc.


def run_protocol(
    ds: Dataset,
    eps_dp: float,
    clamp_max: Optional[int] = None,
    candidate_min_coverage: int = 1,
    candidate_level: Optional[int] = None,
    eps_filter: Optional[float] = None,
    seed: int = 12345,
) -> ProtocolOutput:
    """Execute the release layer over the candidate accounts.

    eps_dp = inf  ->  no noise (ideal-functionality baseline).

    candidate_min_coverage (design fix for the FP-collapse finding):
      Only items whose coverage >= this floor enter the noisy-threshold
      decision. This reflects the protocol's INTRINSIC structure -- an item
      held by a single bank never produces a cross-party OKVS match, so it is
      never a candidate. Setting the floor >= 2 removes the huge mass of
      unique (c=1) non-members that otherwise accumulate false positives.

      DP note: the filter boundary (floor) is kept strictly below the DP
      threshold t (with a margin), so the neighboring-dataset changes that
      matter for the c ~ t decision remain fully inside the noised region;
      the deterministic filter only affects far-sub-threshold items.
    """
    rng = random.Random(seed)
    t = ds.threshold
    n = ds.n_banks
    if clamp_max is None:
        clamp_max = n
    no_noise = (eps_dp == float("inf"))
    scale = 0.0 if no_noise else 1.0 / eps_dp

    released_set: Set[str] = set()
    released_count: Dict[str, int] = {}
    aggregated_label: Dict[str, dict] = {}

    # Candidate set.
    #  - candidate_min_coverage: HARD filter (deterministic; leaks c >= floor).
    #  - candidate_level + eps_filter: DP-SAFE noisy gate. An item proceeds to
    #    the level-t decision only if  c + Lap(1/eps_filter) >= candidate_level.
    #    This is a second noisy-threshold DP mechanism; by composition the total
    #    probing budget is (eps_filter + eps_dp). Because the gate sits at a low
    #    level (2) while the protected probing boundary is at t, the two
    #    neighboring worlds near t both clear the gate with near-equal prob.
    filt_scale = None
    if candidate_level is not None and eps_filter is not None and eps_filter != float("inf"):
        filt_scale = 1.0 / eps_filter
    for x, c in ds.coverage.items():
        if c < candidate_min_coverage:
            continue
        if candidate_level is not None:
            gate_noisy = c + (laplace(filt_scale, rng) if filt_scale is not None else 0.0)
            if gate_noisy < candidate_level:
                continue
        # (4) noisy threshold decision
        noisy_for_decision = c + (0.0 if no_noise else laplace(scale, rng))
        if noisy_for_decision >= t:
            released_set.add(x)
            # (3) output-stage DP clamped count (independent noise draw)
            noisy_for_count = c + (0.0 if no_noise else laplace(scale, rng))
            released_count[x] = int(max(0, min(clamp_max, round(noisy_for_count))))
            aggregated_label[x] = _aggregate_labels(ds, x)

    return ProtocolOutput(released_set, released_count, aggregated_label)


def _aggregate_labels(ds: Dataset, x: str) -> dict:
    """Majority fraud type, mean risk score, modal time bucket across banks."""
    ftypes: List[int] = []
    risks: List[int] = []
    buckets: List[int] = []
    for b in range(ds.n_banks):
        lab = ds.labels[b].get(x)
        if lab is not None:
            ftypes.append(lab.fraud_type)
            risks.append(lab.risk_score)
            buckets.append(lab.time_bucket)
    if not ftypes:
        return {}
    maj = max(set(ftypes), key=ftypes.count)
    modal_bucket = max(set(buckets), key=buckets.count)
    return dict(
        fraud_type=FRAUD_TYPES[maj],
        mean_risk=round(sum(risks) / len(risks), 1),
        time_bucket=modal_bucket,
        n_reports=len(ftypes),
    )


def fixed_b_padding_overhead(ds: Dataset, B: int) -> Dict[str, int]:
    """Layer (2): each bank pads its set to a fixed size B with dummy items.
    Returns per-bank dummy counts (0 if a bank already exceeds B -> capped)."""
    out = {}
    for i, s in enumerate(ds.bank_sets):
        out[f"bank_{i}"] = max(0, B - len(s))
    return out
