#!/usr/bin/env python3
"""Fraud-ring release-layer model: prints Table II/III and Findings 1-3 numbers.

Covers two NAMED scenarios of the SAME fraud-ring data model:
  - fraudring_t3 : threshold t=3
  - fraudring_t4 : threshold t=4 (headline operating point, k=2)

NOTE on columns: ``adv_closed_form`` is the CLOSED-FORM expression
``0.5*(1-e^-eps)`` (an analytical reference), NOT a Monte-Carlo empirical
advantage. The empirical Monte-Carlo attacker lives in attack.py / sim.py. The
``bound`` column is the analytical DP bound ``(e^eps-1)/(e^eps+1)``.
"""
import argparse
import os

import numpy as np

from kit_common import resolve_output_dir, get_scenario, metadata_block, write_json

# Domain-motivated release-layer synthetic model:
#  - fraud ring: F accounts truly circulating across banks (high cross-bank propensity p_ring)
#  - benign coincidental overlaps: G accounts each held by exactly 2 random banks
#  - singletons: fill each bank to `size`
N_BANKS=5; SIZE=2000; F=350; P_RING=0.72; G=150

def build_counts(seed):
    rng=np.random.default_rng(seed)
    ring=(rng.random((F,N_BANKS))<P_RING)
    c_ring=ring.sum(axis=1)
    ring_per_bank=ring.sum(axis=0)
    # benign pairs: each of G accounts assigned to 2 distinct banks
    pair_per_bank=np.zeros(N_BANKS,dtype=int)
    for _ in range(G):
        a,b=rng.choice(N_BANKS,size=2,replace=False)
        pair_per_bank[a]+=1; pair_per_bank[b]+=1
    singles=int(np.sum(np.maximum(SIZE-ring_per_bank-pair_per_bank,0)))
    counts=np.concatenate([c_ring[c_ring>=1], np.full(G,2), np.ones(singles,dtype=int)])
    return counts

def released(counts,t,eps,mode,rng):
    n=counts.size
    thr_ok=(counts+rng.laplace(0,1.0/eps,n))>=t if np.isfinite(eps) else counts>=t
    if mode=='naive': gate=np.ones(n,bool)
    elif mode=='det': gate=counts>=2
    elif mode=='noisygate':
        gate=(counts+rng.laplace(0,1.0/eps,n))>=2 if np.isfinite(eps) else counts>=2
    return thr_ok&gate

def prf(counts,t,eps,mode,seed):
    rng=np.random.default_rng(seed)
    rel=released(counts,t,eps,mode,rng); true=counts>=t
    tp=int((rel&true).sum()); nr=int(rel.sum()); nt=int(true.sum())
    p=tp/nr if nr else 0.0; r=tp/nt if nt else 0.0
    f=2*p*r/(p+r) if(p+r) else 0.0
    return p,r,f


def run(seeds, eps_grid, thresholds, base_seed):
    results = {}
    for t in thresholds:
        us=[build_counts(base_seed+s) for s in seeds]
        scen_name = f"fraudring_t{t}" if t in (3, 4) else f"fraudring_t{t}"
        union=int(np.mean([c.size for c in us]))
        it=int(np.mean([(c>=t).sum() for c in us]))
        print(f"=== t={t} (scenario {scen_name}) ===  union~{union}  |I_t|~{it}")
        rows=[]
        for eps in eps_grid:
            det=np.mean([prf(us[i],t,eps,'det',base_seed+100+i) for i in range(len(seeds))],axis=0)
            nai=np.mean([prf(us[i],t,eps,'naive',base_seed+200+i)[0] for i in range(len(seeds))])
            ng =np.mean([prf(us[i],t,eps,'noisygate',base_seed+300+i)[0] for i in range(len(seeds))])
            adv_cf=0.5*(1-np.exp(-eps)) if np.isfinite(eps) else 1.0
            bnd=(np.exp(eps)-1)/(np.exp(eps)+1) if np.isfinite(eps) else 1.0
            dcand=0.5*np.exp(-(t-2)*eps) if np.isfinite(eps) else 0.0
            e=('%.1f'%eps) if np.isfinite(eps) else 'inf'
            print(f"  eps={e}: P={det[0]:.2f} R={det[1]:.2f} F1={det[2]:.2f} | "
                  f"naive_P={nai:.2f} noisygate_P={ng:.2f} | "
                  f"adv_closed_form={adv_cf:.2f} bound={bnd:.3f} dcand={dcand:.3f}")
            rows.append(dict(scenario=scen_name, eps=e,
                             precision=float(det[0]), recall=float(det[1]), f1=float(det[2]),
                             naive_P=float(nai), noisygate_P=float(ng),
                             adv_closed_form=float(adv_cf), bound=float(bnd),
                             delta_cand=float(dcand)))
        results[scen_name]=dict(union=union, I_t=it, rows=rows)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fraud-ring release-layer tables (scenarios fraudring_t3/t4). "
        "All numbers are release-layer SIMULATION or ANALYTICAL closed forms; "
        "no cryptographic wall-clock is measured.")
    ap.add_argument("--output-dir", default=None,
                    help="output directory (default ./outputs or $THRLABEL_OUTPUT_DIR)")
    ap.add_argument("--thresholds", type=int, nargs="+", default=[3, 4],
                    help="thresholds / scenarios to run (default 3 4)")
    ap.add_argument("--num-seeds", type=int, default=10, help="seeds to average (default 10)")
    ap.add_argument("--seed", type=int, default=0, help="base seed offset (default 0)")
    ap.add_argument("--model-name", default="fraud_ring",
                    help="data model name recorded in metadata")
    args = ap.parse_args(argv)

    seeds=range(args.num_seeds)
    EPS=[0.1,0.5,1.0,2.0,np.inf]
    results = run(seeds, EPS, args.thresholds, args.seed)

    out_dir = resolve_output_dir(args.output_dir)
    payload = dict(scenarios=results,
                   metadata=metadata_block(
                       scenario=get_scenario("fraudring_t4"),
                       provenance="simulation",
                       params=dict(n_banks=N_BANKS, size=SIZE, F=F, p_ring=P_RING, G=G,
                                   thresholds=args.thresholds, num_seeds=args.num_seeds,
                                   base_seed=args.seed, model_name=args.model_name),
                       extra={"note": "adv_closed_form is analytical 0.5*(1-e^-eps), "
                                      "not Monte-Carlo; bound is analytical DP bound."}))
    path = os.path.join(out_dir, "thrlabel_tables.json")
    write_json(path, payload)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    main()
