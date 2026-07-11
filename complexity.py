"""
Analytical complexity model for RQ1/RQ2 (communication & computation).

We cannot run the full crypto stack (libOTe SilentVOLE + RR22 OPRF + RB-OKVS +
(2,2) secret sharing) inside this sandbox, so runtime in seconds is NOT
measured here. Instead we provide a transparent BIG-O-with-constants cost model
that the M3 prototype will validate. This lets us populate the RQ1/RQ2 tables
with model estimates now, and swap in measured wall-clock later.

All formulas are per the manuscript's protocol description.
  n      : number of banks
  m      : set size per bank (after fixed-B padding, m = B)
  lambda : computational security (bits), default 128
  sigma  : statistical security (bits), default 40
  w      : OKVS expansion factor (RB-OKVS ~ 1.28)
  L      : label payload bits per item (fraud one-hot + risk + time bucket)
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CostModel:
    n_banks: int
    m: int                     # padded set size per bank (= B)
    lam: int = 128             # computational security bits
    sigma: int = 40            # statistical security bits
    okvs_w: float = 1.28       # RB-OKVS expansion
    label_bits: int = 32       # payload per item

    # ---- Communication (bytes) ----
    def comm_bytes(self) -> dict:
        # OPRF (RR22 / VOLE-based): ~ (lam + sigma) bits per item, amortized.
        oprf_bits_per_item = self.lam + self.sigma
        # OKVS encoding sent to servers: w * m entries of (lam) bits each.
        okvs_bits = self.okvs_w * self.m * self.lam
        # (2,2) secret-shared value payload: 2 shares * label_bits per item.
        share_bits = 2 * self.label_bits * self.m
        per_bank_bits = oprf_bits_per_item * self.m + okvs_bits + share_bits
        total_bits = per_bank_bits * self.n_banks
        # Server-server comparison traffic: secure compare ~ (lam) bits/item over union.
        union_est = self.m * self.n_banks  # loose upper bound (no dedup)
        compare_bits = self.lam * union_est
        total_bits += compare_bits
        return dict(
            per_bank_MB=round(per_bank_bits / 8 / 1e6, 3),
            total_MB=round(total_bits / 8 / 1e6, 3),
            compare_MB=round(compare_bits / 8 / 1e6, 3),
        )

    # ---- Computation (symmetric-op counts, as a runtime proxy) ----
    def compute_ops(self) -> dict:
        # OPRF evaluations: O(m) PRF calls per bank.
        oprf_ops = self.m * self.n_banks
        # OKVS encode/decode: O(m) field ops per bank (RB-OKVS is linear).
        okvs_ops = self.okvs_w * self.m * self.n_banks
        # Secure comparison for noisy threshold: O(union) comparisons.
        cmp_ops = self.m * self.n_banks
        total = oprf_ops + okvs_ops + cmp_ops
        return dict(
            oprf_ops=int(oprf_ops),
            okvs_ops=int(okvs_ops),
            cmp_ops=int(cmp_ops),
            total_sym_ops=int(total),
        )
