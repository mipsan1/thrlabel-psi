#!/usr/bin/env python3
"""Regenerate the RQ1 (scaling) and RQ4 (probing advantage) figures.

HONESTY / PROVENANCE RULES enforced here (see feasibility audit):

  * Communication (MB) is computed from the ANALYTICAL ``CostModel`` in
    complexity.py and is labelled "analytical". It is a model estimate, not a
    measurement.

  * LAN/WAN wall-clock seconds are NOT measurements. This artifact contains no
    cryptographic prototype, so there is nothing to time. The runtime overlay is
    therefore FAIL-CLOSED: it is only drawn if a real measurement file is
    supplied via ``--runtime-json`` (schema below). Without it, no timing curve
    is produced. A hand-set illustrative projection can be drawn ONLY with the
    explicit ``--illustrative-timing`` flag, and it is then clearly labelled
    "illustrative_projection (NOT measured)".

  * RQ4 empirical advantage is computed by running the actual Monte-Carlo
    attacker in attack.py (SIMULATION), and compared to the closed-form
    analytical bound. No numbers are hard-coded.

Runtime measurement JSON schema (for --runtime-json), produced by a real
prototype / benchmark, e.g. via scripts/macos_feasibility.sh output:
    {"provenance": "measurement",
     "points": [{"set_size": 4096, "lan_s": ..., "wan_s": ...}, ...]}
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import attack
from complexity import CostModel
from kit_common import resolve_output_dir, get_scenario, metadata_block, write_json

SIZES = [2 ** 12, 2 ** 16, 2 ** 20]
EPS = [0.1, 0.5, 1.0, 2.0]


def analytical_comm_mb(sizes, n_banks=5):
    return [CostModel(n_banks=n_banks, m=m).comm_bytes()["total_MB"] for m in sizes]


def load_runtime(path):
    """Load a real runtime measurement file; fail loudly if malformed."""
    with open(path) as fh:
        data = json.load(fh)
    if data.get("provenance") != "measurement":
        sys.exit(f"make_figures.py: {path} is not a measurement file "
                 f"(provenance != 'measurement'); refusing to plot as timing.")
    pts = data.get("points", [])
    if not pts:
        sys.exit(f"make_figures.py: {path} contains no measurement points.")
    return pts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", default=None,
                    help="output directory (default ./outputs or $THRLABEL_OUTPUT_DIR)")
    ap.add_argument("--runtime-json", default=None,
                    help="path to a REAL runtime measurement JSON to overlay "
                         "on RQ1 (fail-closed: omitted => no timing curve)")
    ap.add_argument("--illustrative-timing", action="store_true",
                    help="draw a clearly-labelled illustrative (NON-measured) "
                         "timing curve; never use these as paper results")
    ap.add_argument("--attack-trials", type=int, default=40000,
                    help="Monte-Carlo trials for the RQ4 empirical attacker")
    args = ap.parse_args(argv)

    out_dir = resolve_output_dir(args.output_dir)
    scen = get_scenario("fraudring_t4")

    # ---------------- RQ1: analytical communication scaling ----------------
    comm = analytical_comm_mb(SIZES)
    fig, ax1 = plt.subplots(figsize=(5.6, 3.6))
    ax1.set_xscale('log', base=2)
    ax1.set_yscale('log')
    ax1.plot(SIZES, comm, 'o-', color='tab:blue',
             label='Communication (MB) [analytical]')

    timing_provenance = "none"
    if args.runtime_json:
        pts = load_runtime(args.runtime_json)
        xs = [p["set_size"] for p in pts]
        lan = [p["lan_s"] for p in pts]
        wan = [p["wan_s"] for p in pts]
        ax1.plot(xs, lan, 's--', color='tab:green', label='LAN time (s) [measured]')
        ax1.plot(xs, wan, '^--', color='tab:red', label='WAN time (s) [measured]')
        timing_provenance = "measurement"
    elif args.illustrative_timing:
        # Explicitly-requested, clearly-labelled non-measurements.
        lan = [0.11, 1.77, 28.34]
        wan = [1.12, 3.57, 42.76]
        ax1.plot(SIZES, lan, 's:', color='tab:green', alpha=0.7,
                 label='LAN time (s) [illustrative_projection, NOT measured]')
        ax1.plot(SIZES, wan, '^:', color='tab:red', alpha=0.7,
                 label='WAN time (s) [illustrative_projection, NOT measured]')
        timing_provenance = "illustrative_projection"
    else:
        print("make_figures.py: no --runtime-json supplied; RQ1 timing curve "
              "omitted (fail-closed). Communication MB is analytical.")

    ax1.set_xlabel('Per-bank set size')
    ax1.set_ylabel('Cost (log scale)')
    ax1.set_title('RQ1 --- communication scaling (analytical, n=5)')
    ax1.grid(True, which='both', ls=':', alpha=0.5)
    ax1.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'rq1_scaling.png'), dpi=150)
    plt.close(fig)

    # ---------------- RQ4: simulated advantage vs analytical bound ----------
    emp = []
    bound = []
    for e in EPS:
        adv, _acc = attack.empirical_advantage(eps_dp=e, t=4, c_base=3,
                                               trials=args.attack_trials, seed=7)
        emp.append(round(adv, 4))
        bound.append(round(min(1.0, attack.theoretical_bound(e)), 4))
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    ax.plot(EPS, bound, 'o-', color='tab:red',
            label=r'Analytical bound $(e^\varepsilon-1)/(e^\varepsilon+1)$')
    ax.plot(EPS, emp, 's--', color='tab:blue', label='Empirical advantage [simulation]')
    ax.set_xlabel(r'DP budget $\varepsilon_{dp}$')
    ax.set_ylabel('Membership-probing advantage')
    ax.set_title('RQ4 --- empirical advantage vs bound (t=4, k=2)')
    ax.grid(True, ls=':', alpha=0.5)
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'rq4_advantage.png'), dpi=150)
    plt.close(fig)

    write_json(os.path.join(out_dir, "figures_metadata.json"), metadata_block(
        scenario=scen, provenance="simulation",
        params=dict(sizes=SIZES, eps=EPS, attack_trials=args.attack_trials),
        extra={
            "rq1_comm_provenance": "analytical",
            "rq1_timing_provenance": timing_provenance,
            "rq4_advantage_provenance": "simulation",
            "rq4_bound_provenance": "analytical",
            "rq1_comm_MB": comm,
            "rq4_empirical_advantage": emp,
            "rq4_bound": bound,
        }))
    print(f"figures written to {out_dir} (timing provenance: {timing_provenance})")


if __name__ == "__main__":
    main()
