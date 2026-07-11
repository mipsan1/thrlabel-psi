"""
Experiment driver: produces RQ1-RQ4 tables and plots for the manuscript.

RQ1/RQ2  efficiency (analytical cost model, to be validated by M3 prototype)
RQ3       privacy-utility: FP/FN, precision/recall/F1 vs eps_dp
RQ4       probing resistance: empirical advantage vs eps_dp + theory bound

Outputs (under the resolved output dir, default ./outputs):
  rq3_utility.csv, rq4_advantage.csv, rq1_efficiency.csv
  rq3_utility.png, rq4_advantage.png, rq1_scaling.png
"""
from __future__ import annotations
import argparse
import csv
import os
import statistics
from typing import List

import datagen
import protocol
import attack
from complexity import CostModel
from kit_common import resolve_output_dir, get_scenario, metadata_block, write_json

# Resolved at run time (main); this scenario drives the coverage-model tables.
SCENARIO = get_scenario("coverage_t3")
OUT = None  # set by main() -> resolve_output_dir(); never hard-coded /data

EPS_GRID = [0.1, 0.5, 1.0, 2.0, float("inf")]


def _prf(released, truth):
    tp = len(released & truth)
    fp = len(released - truth)
    fn = len(truth - released)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return tp, fp, fn, precision, recall, f1


def rq3_utility(reps: int = 10, candidate_min_coverage: int = 1):
    """Privacy-utility vs eps_dp. Average over `reps` seeds, report mean +/- 95% CI.
    candidate_min_coverage=1 -> no filter (original); 2 -> design-fix filter."""
    rows = []
    for eps in EPS_GRID:
        f1s, precs, recs, fps, fns = [], [], [], [], []
        for r in range(reps):
            ds = datagen.generate(n_banks=5, accounts_per_bank=2000,
                                  threshold=3, n_shared_pool=400, seed=100 + r)
            out = protocol.run_protocol(ds, eps_dp=eps,
                                        candidate_min_coverage=candidate_min_coverage,
                                        seed=900 + r)
            tp, fp, fn, p, rc, f1 = _prf(out.released_set, ds.I_t)
            f1s.append(f1); precs.append(p); recs.append(rc); fps.append(fp); fns.append(fn)
        rows.append(dict(
            eps=("inf" if eps == float("inf") else eps),
            precision=_mci(precs), recall=_mci(recs), f1=_mci(f1s),
            mean_FP=round(statistics.mean(fps), 1), mean_FN=round(statistics.mean(fns), 1),
        ))
    suffix = "" if candidate_min_coverage <= 1 else f"_filt{candidate_min_coverage}"
    _write_csv(f"rq3_utility{suffix}.csv", rows,
               ["eps", "precision", "recall", "f1", "mean_FP", "mean_FN"])
    return rows


def _half(eps):
    return eps if eps == float("inf") else eps / 2.0


def rq3_utility_noisy(reps: int = 10, candidate_level: int = 2):
    """DP-SAFE two-stage utility. Total budget eps is SPLIT half/half between the
    candidacy gate (level 2) and the level-t decision, so total probing budget
    stays = eps (basic composition). No deterministic hard filter is used."""
    rows = []
    for eps in EPS_GRID:
        eg = _half(eps)
        f1s, precs, recs, fps, fns = [], [], [], [], []
        for r in range(reps):
            ds = datagen.generate(n_banks=5, accounts_per_bank=2000,
                                  threshold=3, n_shared_pool=400, seed=100 + r)
            out = protocol.run_protocol(ds, eps_dp=eg,
                                        candidate_level=candidate_level,
                                        eps_filter=eg, seed=900 + r)
            tp, fp, fn, p, rc, f1 = _prf(out.released_set, ds.I_t)
            f1s.append(f1); precs.append(p); recs.append(rc); fps.append(fp); fns.append(fn)
        rows.append(dict(
            eps=("inf" if eps == float("inf") else eps),
            precision=_mci(precs), recall=_mci(recs), f1=_mci(f1s),
            mean_FP=round(statistics.mean(fps), 1), mean_FN=round(statistics.mean(fns), 1),
        ))
    _write_csv("rq3_utility_noisy.csv", rows,
               ["eps", "precision", "recall", "f1", "mean_FP", "mean_FN"])
    return rows


def rq4_advantage_noisy():
    """Probing advantage against the DP-SAFE two-stage mechanism, budget split
    half/half. Advantage is compared against the bound for the TOTAL budget."""
    rows = []
    for eps in EPS_GRID:
        eg = _half(eps)
        adv, acc = attack.empirical_advantage_2stage(eps_gate=eg, eps_dec=eg,
                                                     t=3, candidate_level=2,
                                                     c_base=2, trials=40000, seed=7)
        bound = attack.theoretical_bound(eps, delta=0.0)
        rows.append(dict(
            eps=("inf" if eps == float("inf") else eps),
            attack_accuracy=round(acc, 4),
            empirical_advantage=round(adv, 4),
            theory_bound=round(bound, 4),
            within_bound=bool(adv <= bound + 0.02),
        ))
    _write_csv("rq4_advantage_noisy.csv", rows,
               ["eps", "attack_accuracy", "empirical_advantage", "theory_bound", "within_bound"])
    return rows


def rq4_advantage():
    """Empirical probing advantage vs theoretical bound."""
    rows = []
    for eps in EPS_GRID:
        adv, acc = attack.empirical_advantage(eps_dp=eps, t=3, c_base=2,
                                              trials=40000, seed=7)
        bound = attack.theoretical_bound(eps, delta=0.0)
        rows.append(dict(
            eps=("inf" if eps == float("inf") else eps),
            attack_accuracy=round(acc, 4),
            empirical_advantage=round(adv, 4),
            theory_bound=round(bound, 4),
            within_bound=bool(adv <= bound + 0.02),
        ))
    _write_csv("rq4_advantage.csv", rows,
               ["eps", "attack_accuracy", "empirical_advantage", "theory_bound", "within_bound"])
    return rows


def rq1_efficiency():
    """Analytical comm/compute across set sizes (per bank, padded to B=m)."""
    rows = []
    for m in [2**12, 2**14, 2**16, 2**18, 2**20]:
        cm = CostModel(n_banks=5, m=m)
        comm = cm.comm_bytes()
        comp = cm.compute_ops()
        rows.append(dict(
            set_size=m,
            per_bank_MB=comm["per_bank_MB"],
            total_MB=comm["total_MB"],
            total_sym_ops=comp["total_sym_ops"],
        ))
    _write_csv("rq1_efficiency.csv", rows,
               ["set_size", "per_bank_MB", "total_MB", "total_sym_ops"])
    return rows


def _mci(xs: List[float]) -> str:
    m = statistics.mean(xs)
    if len(xs) > 1:
        sd = statistics.stdev(xs)
        ci = 1.96 * sd / (len(xs) ** 0.5)
    else:
        ci = 0.0
    return f"{m:.3f}+/-{ci:.3f}"


def _write_csv(name, rows, fields):
    # Every table records its scenario so coverage_t3 output is never confused
    # with the fraud-ring (t=4) tables produced by sim.py.
    fields = ["scenario"] + list(fields)
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({"scenario": SCENARIO.name, **r})


def make_plots(rq3, rq4, rq1):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def eps_x(rows):
        return [(3.0 if r["eps"] == "inf" else float(r["eps"])) for r in rows]
    labels = [str(r["eps"]) for r in rq3]

    # RQ3
    fig, ax = plt.subplots(figsize=(6, 4))
    prec = [float(r["precision"].split("+/-")[0]) for r in rq3]
    rec = [float(r["recall"].split("+/-")[0]) for r in rq3]
    f1 = [float(r["f1"].split("+/-")[0]) for r in rq3]
    xs = list(range(len(labels)))
    ax.plot(xs, prec, "o-", label="Precision")
    ax.plot(xs, rec, "s-", label="Recall")
    ax.plot(xs, f1, "^-", label="F1")
    ax.set_xticks(xs); ax.set_xticklabels(labels)
    ax.set_xlabel("eps_dp"); ax.set_ylabel("score"); ax.set_ylim(0, 1.05)
    ax.set_title("RQ3: Privacy-Utility vs eps_dp"); ax.legend(); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "rq3_utility.png"), dpi=130)

    # RQ4
    fig, ax = plt.subplots(figsize=(6, 4))
    adv = [r["empirical_advantage"] for r in rq4]
    bnd = [min(1.0, r["theory_bound"]) for r in rq4]
    xs = list(range(len(labels)))
    ax.plot(xs, adv, "o-", label="Empirical advantage")
    ax.plot(xs, bnd, "x--", label="Theoretical bound")
    ax.set_xticks(xs); ax.set_xticklabels(labels)
    ax.set_xlabel("eps_dp"); ax.set_ylabel("advantage"); ax.set_ylim(0, 1.05)
    ax.set_title("RQ4: Probing Advantage vs Bound"); ax.legend(); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "rq4_advantage.png"), dpi=130)

    # RQ1 scaling
    fig, ax = plt.subplots(figsize=(6, 4))
    sizes = [r["set_size"] for r in rq1]
    mb = [r["total_MB"] for r in rq1]
    ax.plot(sizes, mb, "o-")
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xlabel("set size m (per bank)"); ax.set_ylabel("total comm (MB, model)")
    ax.set_title("RQ1: Communication scaling (analytical)"); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "rq1_scaling.png"), dpi=130)


def main(argv=None):
    global OUT
    ap = argparse.ArgumentParser(
        description="ThrLabel-PSI RQ1-RQ4 driver (scenario coverage_t3). "
        "RQ3/RQ4 are release-layer SIMULATION; RQ1 is an ANALYTICAL cost model "
        "(no wall-clock timing is produced here).")
    ap.add_argument("--output-dir", default=None,
                    help="output directory (default ./outputs or $THRLABEL_OUTPUT_DIR)")
    ap.add_argument("--reps", type=int, default=10,
                    help="seeds averaged per privacy-utility row (default 10)")
    args = ap.parse_args(argv)

    OUT = resolve_output_dir(args.output_dir)

    rq3_raw = rq3_utility(reps=args.reps, candidate_min_coverage=1)    # original (no filter)
    rq3_hard = rq3_utility(reps=args.reps, candidate_min_coverage=2)   # hard filter (leaky)
    rq3_noisy = rq3_utility_noisy(reps=args.reps, candidate_level=2)   # DP-SAFE two-stage
    rq4 = rq4_advantage()                                              # single-stage baseline
    rq4_noisy = rq4_advantage_noisy()                                 # DP-SAFE two-stage
    rq1 = rq1_efficiency()
    make_plots(rq3_noisy, rq4_noisy, rq1)   # DP-safe design is the headline plot

    write_json(os.path.join(OUT, "experiments_metadata.json"), metadata_block(
        scenario=SCENARIO, provenance="simulation",
        params=dict(reps=args.reps, eps_grid=[str(e) for e in EPS_GRID]),
        extra={"rq1_efficiency_provenance": "analytical",
               "note": "RQ3/RQ4 = simulation; RQ1 comm/compute = analytical CostModel; "
                       "no cryptographic wall-clock timing is measured."}))

    print("=== RQ3 privacy-utility  [NO FILTER, original] ===")
    for r in rq3_raw: print(r)
    print("\n=== RQ3 privacy-utility  [HARD FILTER c>=2, deterministic/leaky] ===")
    for r in rq3_hard: print(r)
    print("\n=== RQ3 privacy-utility  [DP-SAFE noisy gate @2, budget split] ===")
    for r in rq3_noisy: print(r)
    print("\n=== RQ4 probing advantage  [single-stage] ===")
    for r in rq4: print(r)
    print("\n=== RQ4 probing advantage  [DP-SAFE two-stage, total-budget bound] ===")
    for r in rq4_noisy: print(r)
    print("\n=== RQ1 efficiency (analytical) ===")
    for r in rq1: print(r)
    print(f"\nOutputs written to {OUT}")


if __name__ == "__main__":
    main()
