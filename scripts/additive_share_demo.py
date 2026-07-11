#!/usr/bin/env python3
"""2-party additive-share ARITHMETIC DEMO -- feasibility probe only.

!!! THIS IS NOT A SECURE COMPUTATION !!!
------------------------------------------------------------------------------
This script demonstrates the *arithmetic shape* of a 2-party additive-sharing
comparison (does coverage count c cross threshold t?) using plaintext shares in
a single process. It exists only to confirm that the additive-share bookkeeping
is well-defined and reproducible on the target machine.

It is DELIBERATELY NOT any of the following, and must never be described as such:
  - a secure comparison protocol
  - a network MPC execution
  - a run against a malicious or even semi-honest adversary
  - accompanied by any composition / simulation-based security proof

Both "party" shares live in the same process; reconstruction is done in the
clear. A real deployment needs an actual MPC engine (e.g. MP-SPDZ) with a
network transport and a proof that composing the candidacy gate and the
threshold comparison meets the paper's leakage bound. That proof is ABSENT here.
------------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import json
import random
import sys

MODULUS = 2 ** 61 - 1  # a prime-ish field size for additive shares (demo only)


def additive_share(value: int, rng: random.Random):
    """Split `value` into two additive shares mod MODULUS (plaintext, in-process)."""
    s0 = rng.randrange(MODULUS)
    s1 = (value - s0) % MODULUS
    return s0, s1


def reconstruct(s0: int, s1: int) -> int:
    v = (s0 + s1) % MODULUS
    # map back to a signed-ish small integer domain for the demo
    return v if v < MODULUS // 2 else v - MODULUS


def compare_ge_via_shares(c: int, t: int, rng: random.Random) -> bool:
    """Compute 1[c >= t] by additively sharing (c - t) and reconstructing.

    NOTE: reconstruction happens in the clear here -- this leaks c-t entirely.
    A secure protocol would evaluate the sign WITHOUT reconstructing. This demo
    only checks arithmetic correctness, not privacy.
    """
    d = c - t
    d0, d1 = additive_share(d, rng)
    return reconstruct(d0, d1) >= 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--trials", type=int, default=1000)
    ap.add_argument("--threshold", type=int, default=4)
    ap.add_argument("--max-count", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="emit a JSON result line")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    mismatches = 0
    for _ in range(args.trials):
        c = rng.randint(0, args.max_count)
        got = compare_ge_via_shares(c, args.threshold, rng)
        want = c >= args.threshold
        if got != want:
            mismatches += 1

    ok = mismatches == 0
    result = {
        "demo": "additive_share_arithmetic_demo",
        "secure": False,
        "network_mpc": False,
        "composition_proof": "ABSENT",
        "note": "plaintext single-process shares; reconstruction leaks the value; "
                "NOT a secure comparison",
        "trials": args.trials,
        "threshold": args.threshold,
        "arithmetic_mismatches": mismatches,
        "arithmetic_correct": ok,
    }
    if args.json:
        print(json.dumps(result))
    else:
        print("2-party additive-share ARITHMETIC DEMO (NOT secure, no network, "
              "no composition proof)")
        print(f"  trials={args.trials} threshold={args.threshold} "
              f"arithmetic_mismatches={mismatches} correct={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
