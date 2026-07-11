#!/usr/bin/env python3
"""Release-layer reference simulation for the revised ThrLabel-PSI paper.

Models ONLY the release-layer parts that determine utility and leakage:
  - deterministic candidacy filter (c >= 2)
  - noisy threshold decision b = 1[c + Lap(1/eps_thr) >= t]
  - output-stage clamped-count DP
Cryptographic layers (OPRF, OKVS, sharing) are omitted by design.

Generates:
  - main utility/probing table (n=5, t=4, k=2)
  - three-design precision comparison
  - sweeps over n, t, per-bank set size
  - analytical bounds (threshold-channel, full composed DP, delta_cand)
"""
import argparse
import os
import numpy as np
import csv, math, json

from kit_common import (
    resolve_output_dir,
    get_scenario,
    metadata_block,
    write_json,
)

# Module-level RNG; reseeded from the CLI in main() so runs are deterministic.
RNG = np.random.default_rng(20260710)

def lap(scale, size=None):
    return RNG.laplace(0.0, scale, size)

def build_world(n, B, F, p_ring, G, seed):
    """Return dict tag-> count c across n banks, using a fraud-ring model.
    - F cross-bank fraud accounts, each bank participates w.p. p_ring
    - G benign coincidental two-bank overlaps (exactly 2 banks)
    - remaining capacity filled with independent singletons (c=1)
    """
    r = np.random.default_rng(seed)
    counts = {}
    tag = 0
    # fraud ring accounts
    for f in range(F):
        c = 0
        for _ in range(n):
            if r.random() < p_ring:
                c += 1
        if c >= 1:
            counts[('ring', f)] = c
    # benign 2-bank overlaps
    for g in range(G):
        counts[('ben', g)] = 2
    # singletons to fill: total submissions ~ n*B
    total_sub = n * B
    used = sum(counts.values())
    n_singletons = max(0, total_sub - used)
    for s in range(n_singletons):
        counts[('sing', s)] = 1
    return counts

def true_positive_set(counts, t):
    return {k for k, c in counts.items() if c >= t}

def released_set(counts, t, eps_thr, deterministic_candidacy=True,
                 noisy_gate=False, eps_gate=None):
    """Apply candidacy gate + noisy threshold; return set of released tags."""
    released = set()
    for k, c in counts.items():
        # candidacy gate
        if deterministic_candidacy:
            if c < 2:
                continue
        elif noisy_gate:
            if c + lap(1.0/eps_gate) < 2:
                continue
        # else naive: no gate
        # noisy threshold
        if c + lap(1.0/eps_thr) >= t:
            released.add(k)
    return released

def prf(counts, t, eps_thr, design, eps_gate=None, reps=1):
    """Average precision/recall/F1 over reps."""
    tp_set = true_positive_set(counts, t)
    Ps, Rs, Fs = [], [], []
    for _ in range(reps):
        if design == 'naive':
            rel = released_set(counts, t, eps_thr, deterministic_candidacy=False)
        elif design == 'noisy':
            rel = released_set(counts, t, eps_thr, deterministic_candidacy=False,
                               noisy_gate=True, eps_gate=eps_gate)
        else:  # deterministic
            rel = released_set(counts, t, eps_thr, deterministic_candidacy=True)
        tp = len(rel & tp_set)
        fp = len(rel - tp_set)
        fn = len(tp_set - rel)
        prec = tp/(tp+fp) if (tp+fp) > 0 else 1.0
        rec = tp/(tp+fn) if (tp+fn) > 0 else 1.0
        f1 = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0.0
        Ps.append(prec); Rs.append(rec); Fs.append(f1)
    return np.mean(Ps), np.mean(Rs), np.mean(Fs)

def empirical_probing_advantage(t, eps_thr, eps_out, trials=200000):
    """Optimal likelihood-ratio attacker straddling c=t-1 vs c=t boundary.
    Observation = (bit b, and if b=1 the clamped noisy count).
    Advantage = 2*balanced_accuracy - 1 of the Bayes-optimal test
    under equal priors, estimated by Monte Carlo with analytic LR.
    """
    c0, c1 = t-1, t
    # Simulate observations under each hypothesis and score by exact log-LR.
    def gen(c):
        b = (c + lap(1.0/eps_thr, trials) >= t).astype(int)
        # noisy count released only if b==1
        cnt = np.where(b == 1, np.clip(c + lap(1.0/eps_out, trials), 0, None), np.nan)
        return b, cnt
    b0, cnt0 = gen(c0)
    b1, cnt1 = gen(c1)
    # Bayes-optimal decision via log-likelihood ratio log p(obs|c1)-p(obs|c0)
    def loglik(b, cnt, c):
        # P(b=1|c)=P(Lap>=t-c); density of clamped count approximated by laplace pdf
        p1 = 0.5*math.exp(-eps_thr*max(0, t-c)) if (t-c) > 0 else 1-0.5*math.exp(-eps_thr*max(0, c-t))
        # careful: P(Lap(1/e) >= u) = 0.5 exp(-e u) for u>=0; =1-0.5 exp(e u) for u<0
        u = t - c
        if u >= 0:
            p1 = 0.5*math.exp(-eps_thr*u)
        else:
            p1 = 1 - 0.5*math.exp(eps_thr*u)
        ll = np.where(b == 1, math.log(p1), math.log(1-p1))
        # count contribution when b==1
        mask = (b == 1) & ~np.isnan(cnt)
        # laplace pdf around c with scale 1/eps_out (ignore clamp density mass; fine for interior)
        pdf = -eps_out*np.abs(cnt - c) + math.log(eps_out/2.0)
        ll = ll + np.where(mask, pdf, 0.0)
        return ll
    llr0 = loglik(b0, cnt0, c1) - loglik(b0, cnt0, c0)
    llr1 = loglik(b1, cnt1, c1) - loglik(b1, cnt1, c0)
    # decide c1 if llr>0
    tpr = np.mean(llr1 > 0) + 0.5*np.mean(llr1 == 0)
    fpr = np.mean(llr0 > 0) + 0.5*np.mean(llr0 == 0)
    adv = tpr - fpr
    return max(0.0, adv)

def analytic_bounds(eps_dp, t):
    eps_thr = eps_dp; eps_out = eps_dp; eps_tot = eps_thr+eps_out
    thr_only = math.tanh(eps_thr/2.0)      # (e^e-1)/(e^e+1)
    full_dp = math.tanh(eps_tot/2.0)
    delta_cand = 0.5*math.exp(-(t-2)*eps_thr)
    return dict(eps_thr=eps_thr, eps_out=eps_out, eps_tot=eps_tot,
                thr_only=thr_only, full_dp=full_dp, delta_cand=delta_cand,
                full_plus=min(1.0, full_dp+delta_cand))

def run(n, t, B, F, p_ring, G, seeds, eps_list, base_seed):
    # ---------------- MAIN TABLE (default n=5, t=4, k=2) ----------------
    main_rows = []
    for eps in eps_list:
        Ps, Rs, Fs = [], [], []
        for sd in seeds:
            counts = build_world(n, B, F, p_ring, G, seed=base_seed + 1000 + sd)
            p, r, f = prf(counts, t, eps, 'deterministic', reps=1)
            Ps.append(p); Rs.append(r); Fs.append(f)
        adv = empirical_probing_advantage(t, eps, eps)
        ab = analytic_bounds(eps, t)
        main_rows.append(dict(eps=eps, precision=np.mean(Ps), recall=np.mean(Rs),
                              f1=np.mean(Fs), emp_adv=adv, **ab))

    print(f'=== MAIN (n={n},t={t},k=2) ===')
    for row in main_rows:
        print(f"eps={row['eps']:.1f} P={row['precision']:.2f} R={row['recall']:.2f} "
              f"F1={row['f1']:.2f} emp_adv={row['emp_adv']:.2f} thr_only={row['thr_only']:.3f} "
              f"full_dp={row['full_dp']:.3f} dcand={row['delta_cand']:.3f} full+={row['full_plus']:.3f}")

    # ---------------- THREE DESIGNS ----------------
    design_rows = []
    for eps in eps_list:
        naive_p, noisy_p, det_p = [], [], []
        for sd in seeds:
            counts = build_world(n, B, F, p_ring, G, seed=base_seed + 2000 + sd)
            naive_p.append(prf(counts, t, eps, 'naive', reps=3)[0])
            noisy_p.append(prf(counts, t, eps, 'noisy', eps_gate=eps, reps=3)[0])
            det_p.append(prf(counts, t, eps, 'deterministic', reps=3)[0])
        design_rows.append(dict(eps=eps, naive=np.mean(naive_p),
                                noisy=np.mean(noisy_p), det=np.mean(det_p)))
    print('\n=== THREE DESIGNS (precision) ===')
    for row in design_rows:
        print(f"eps={row['eps']:.1f} naive={row['naive']:.2f} noisy_gate={row['noisy']:.2f} det={row['det']:.2f}")

    # ---------------- SWEEP over n (t=4,k=2,eps=1) ----------------
    sweep_n = []
    for nn in [3, 5, 7, 10]:
        Ps, Rs, Fs = [], [], []
        for sd in seeds:
            counts = build_world(nn, B, 350, 0.72, G, seed=base_seed + 3000 + sd)
            p, r, f = prf(counts, min(4, nn), 1.0, 'deterministic', reps=1)
            Ps.append(p); Rs.append(r); Fs.append(f)
        sweep_n.append(dict(n=nn, t=min(4, nn), precision=np.mean(Ps),
                            recall=np.mean(Rs), f1=np.mean(Fs)))
    print('\n=== SWEEP n (eps=1,t=min(4,n),k=2) ===')
    for row in sweep_n:
        print(f"n={row['n']} t={row['t']} P={row['precision']:.2f} R={row['recall']:.2f} F1={row['f1']:.2f}")

    # ---------------- SWEEP over t (n=10,eps=1) ----------------
    sweep_t = []
    for tt in [3, 4, 5, 7]:
        Ps, Rs, Fs = [], [], []
        for sd in seeds:
            counts = build_world(10, B, 350, 0.72, G, seed=base_seed + 4000 + sd)
            p, r, f = prf(counts, tt, 1.0, 'deterministic', reps=1)
            Ps.append(p); Rs.append(r); Fs.append(f)
        ab = analytic_bounds(1.0, tt)
        sweep_t.append(dict(t=tt, precision=np.mean(Ps), recall=np.mean(Rs),
                            f1=np.mean(Fs), delta_cand=ab['delta_cand']))
    print('\n=== SWEEP t (n=10,eps=1,k=2) ===')
    for row in sweep_t:
        print(f"t={row['t']} P={row['precision']:.2f} R={row['recall']:.2f} F1={row['f1']:.2f} dcand={row['delta_cand']:.3f}")

    # ---------------- SWEEP over set size B (n=5,t=4,eps=1) ----------------
    sweep_B = []
    for BB in [2000, 10000, 50000]:
        Ps, Rs, Fs = [], [], []
        for sd in seeds[:5]:
            counts = build_world(5, BB, int(350*BB/2000), 0.72, int(150*BB/2000), seed=base_seed + 5000 + sd)
            p, r, f = prf(counts, 4, 1.0, 'deterministic', reps=1)
            Ps.append(p); Rs.append(r); Fs.append(f)
        sweep_B.append(dict(B=BB, precision=np.mean(Ps), recall=np.mean(Rs), f1=np.mean(Fs)))
    print('\n=== SWEEP set size B (n=5,t=4,eps=1) ===')
    for row in sweep_B:
        print(f"B={row['B']} P={row['precision']:.2f} R={row['recall']:.2f} F1={row['f1']:.2f}")

    return dict(main=main_rows, designs=design_rows, sweep_n=sweep_n,
                sweep_t=sweep_t, sweep_B=sweep_B)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="ThrLabel-PSI release-layer fraud-ring simulation "
        "(scenario fraudring_t4). All outputs are release-layer SIMULATION "
        "results; no cryptographic wall-clock is measured.")
    ap.add_argument("--output-dir", default=None,
                    help="output directory (default ./outputs or $THRLABEL_OUTPUT_DIR)")
    ap.add_argument("--scenario", default="fraudring_t4",
                    choices=["fraudring_t4", "fraudring_t3"],
                    help="named scenario (fraud-ring model); sets default t")
    ap.add_argument("--seed", type=int, default=0,
                    help="base seed offset added to per-block seeds (default 0)")
    ap.add_argument("--n", type=int, default=5, help="number of banks for main table")
    ap.add_argument("--t", type=int, default=None,
                    help="threshold for main table (default from scenario)")
    ap.add_argument("--set-size", type=int, default=2000, dest="B",
                    help="per-bank set size B for main table (default 2000)")
    ap.add_argument("--num-seeds", type=int, default=10,
                    help="number of seeds to average (default 10)")
    ap.add_argument("--model-name", default="fraud_ring",
                    help="data model name recorded in metadata (default fraud_ring)")
    args = ap.parse_args(argv)

    scen = get_scenario(args.scenario)
    t = args.t if args.t is not None else scen.threshold
    n, B = args.n, args.B
    F, p_ring, G = 350, 0.72, 150
    seeds = list(range(args.num_seeds))
    eps_list = [0.1, 0.5, 1.0, 2.0]

    global RNG
    RNG = np.random.default_rng(20260710 + args.seed)

    out = run(n, t, B, F, p_ring, G, seeds, eps_list, args.seed)
    out["metadata"] = metadata_block(
        scenario=scen,
        provenance="simulation",
        params=dict(n=n, t=t, k=2, B=B, F=F, p_ring=p_ring, G=G,
                    num_seeds=args.num_seeds, base_seed=args.seed,
                    model_name=args.model_name, eps_list=eps_list),
    )

    out_dir = resolve_output_dir(args.output_dir)
    path = os.path.join(out_dir, "sim_results.json")
    write_json(path, out)
    print(f'\nsaved {path}')


if __name__ == "__main__":
    main()
