"""
Synthetic dataset generator for ThrLabel-PSI experiments.

WHY SYNTHETIC (not real bank data):
- Efficiency metrics (comm/compute/runtime) depend ONLY on set sizes and
  structure, not on the actual content of account identifiers. Random 128-bit
  strings behave identically to real account numbers under the crypto layer.
- Privacy-utility metrics (FP/FN, precision/recall, empirical advantage)
  REQUIRE knowing the ground-truth intersection I_t, which we can only know if
  WE plant it. Hence synthetic data with controlled overlap is mandatory.

Notation (matches the manuscript):
  n            number of banks (participants)
  S_i          subset of universe U held by bank i
  c(x)         = |{i : x in S_i}|  (coverage count)
  t            threshold
  I_t          = {x : c(x) >= t}   (true positive shared fraud accounts)
  ell_i(x)     label of x at bank i: (fraud_type one-hot, risk_score, time_bucket)
"""
from __future__ import annotations
import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

FRAUD_TYPES = ["voice_phishing", "smishing", "loan_fraud", "romance_scam", "mule_account"]
N_TIME_BUCKETS = 8  # e.g. week-of-year buckets


@dataclass
class Label:
    fraud_type: int          # index into FRAUD_TYPES
    risk_score: int          # 0..100
    time_bucket: int         # 0..N_TIME_BUCKETS-1


@dataclass
class Dataset:
    n_banks: int
    threshold: int
    bank_sets: List[Set[str]]                       # S_1..S_n (account id strings)
    labels: List[Dict[str, Label]]                  # per-bank ell_i
    coverage: Dict[str, int]                        # c(x) over the union (ground truth)
    I_t: Set[str]                                   # ground-truth intersection
    shared_pool: Set[str]                           # all planted multi-bank accounts
    params: dict = field(default_factory=dict)

    def union(self) -> Set[str]:
        u: Set[str] = set()
        for s in self.bank_sets:
            u |= s
        return u


def _acct_id(rng: random.Random) -> str:
    """128-bit random account identifier (hex). Content is irrelevant to crypto."""
    return hashlib.sha256(str(rng.getrandbits(256)).encode()).hexdigest()[:32]


def generate(
    n_banks: int = 5,
    accounts_per_bank: int = 2000,
    threshold: int = 3,
    n_shared_pool: int = 400,
    coverage_dist: Tuple[float, ...] | None = None,
    seed: int = 0,
) -> Dataset:
    """Generate a synthetic multi-bank dataset with planted ground truth.

    coverage_dist: probability weights for coverage c in 1..n_banks for each
      account in the shared pool. If None, a distribution centered near the
      threshold is used so that positives and near-misses both appear
      (this stresses the noisy-threshold decision boundary).
    """
    rng = random.Random(seed)

    if coverage_dist is None:
        # Weight coverage counts 1..n; put mass around the threshold so the
        # boundary (c == t-1 vs c == t) is well represented.
        coverage_dist = tuple(
            1.0 + 2.0 * (1.0 / (1.0 + abs(c - threshold))) for c in range(1, n_banks + 1)
        )
    weights = list(coverage_dist)
    cov_values = list(range(1, n_banks + 1))

    bank_sets: List[Set[str]] = [set() for _ in range(n_banks)]
    labels: List[Dict[str, Label]] = [dict() for _ in range(n_banks)]
    coverage: Dict[str, int] = {}
    shared_pool: Set[str] = set()

    # 1) Plant shared-pool accounts with controlled coverage counts.
    for _ in range(n_shared_pool):
        x = _acct_id(rng)
        c = rng.choices(cov_values, weights=weights, k=1)[0]
        banks = rng.sample(range(n_banks), c)
        # All banks that see the same fraud account tend to agree on type,
        # but risk score / time bucket vary per bank (realistic noise).
        ftype = rng.randrange(len(FRAUD_TYPES))
        for b in banks:
            bank_sets[b].add(x)
            labels[b][x] = Label(
                fraud_type=ftype if rng.random() < 0.85 else rng.randrange(len(FRAUD_TYPES)),
                risk_score=min(100, max(0, int(rng.gauss(70, 15)))),
                time_bucket=rng.randrange(N_TIME_BUCKETS),
            )
        coverage[x] = c
        shared_pool.add(x)

    # 2) Fill each bank with unique legit/random accounts up to accounts_per_bank.
    for b in range(n_banks):
        while len(bank_sets[b]) < accounts_per_bank:
            x = _acct_id(rng)
            if x in coverage:
                continue
            bank_sets[b].add(x)
            coverage[x] = coverage.get(x, 0) + 1  # will be 1 (unique)
            labels[b][x] = Label(
                fraud_type=rng.randrange(len(FRAUD_TYPES)),
                risk_score=min(100, max(0, int(rng.gauss(40, 20)))),
                time_bucket=rng.randrange(N_TIME_BUCKETS),
            )

    I_t = {x for x, c in coverage.items() if c >= threshold}

    return Dataset(
        n_banks=n_banks,
        threshold=threshold,
        bank_sets=bank_sets,
        labels=labels,
        coverage=coverage,
        I_t=I_t,
        shared_pool=shared_pool,
        params=dict(
            n_banks=n_banks,
            accounts_per_bank=accounts_per_bank,
            threshold=threshold,
            n_shared_pool=n_shared_pool,
            seed=seed,
        ),
    )


if __name__ == "__main__":
    ds = generate()
    print("union size:", len(ds.union()))
    print("shared pool:", len(ds.shared_pool))
    print("|I_t| (ground truth positives):", len(ds.I_t))
    from collections import Counter
    print("coverage histogram (shared pool):",
          dict(sorted(Counter(ds.coverage[x] for x in ds.shared_pool).items())))
