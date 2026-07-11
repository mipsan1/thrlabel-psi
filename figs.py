import argparse, json, math, os, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from kit_common import resolve_output_dir


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Render figures from sim.py's sim_results.json (scenario "
        "fraudring_t4). Fail-closed: refuses to plot if the results file is absent.")
    ap.add_argument('--output-dir', default=None,
                    help='directory holding sim_results.json and receiving PNGs '
                         '(default ./outputs or $THRLABEL_OUTPUT_DIR)')
    ap.add_argument('--input', default=None,
                    help='explicit path to sim_results.json (overrides --output-dir)')
    args = ap.parse_args(argv)

    OUT = resolve_output_dir(args.output_dir)
    res_path = args.input or os.path.join(OUT, 'sim_results.json')
    if not os.path.exists(res_path):
        sys.exit(f"figs.py: results file not found: {res_path}\n"
                 f"Run `python sim.py --output-dir {OUT}` first to generate it.")
    res = json.load(open(res_path))

    # ---- Fig RQ4 revised: emp adv vs threshold-only bound AND full composed bound ----
    eps = [r['eps'] for r in res['main']]
    emp = [r['emp_adv'] for r in res['main']]
    thr_only = [r['thr_only'] for r in res['main']]
    full_dp = [r['full_dp'] for r in res['main']]
    full_plus = [r['full_plus'] for r in res['main']]

    plt.figure(figsize=(6.4, 4.2))
    plt.plot(eps, full_plus, 's-', color='#6a1b9a', label=r'Full theorem bound $\tanh(\varepsilon_{tot}/2)+\delta_{cand}$')
    plt.plot(eps, full_dp, '^--', color='#c62828', label=r'Composed DP bound $\tanh(\varepsilon_{tot}/2)$')
    plt.plot(eps, thr_only, 'o--', color='#ef6c00', label=r'Per-channel threshold bound $\tanh(\varepsilon_{thr}/2)$')
    plt.plot(eps, emp, 'D-', color='#1565c0', label='Empirical probing advantage')
    plt.xlabel(r'DP budget $\varepsilon_{dp}$ (per channel)')
    plt.ylabel('Membership-probing advantage')
    plt.title('RQ4 --- empirical advantage vs. per-channel and full bounds (t=4, k=2)')
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8, loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'rq4_advantage.png'), dpi=150)
    plt.close()
    print('wrote rq4_advantage.png')

    # ---- Fig: threshold sweep, F1 and delta_cand (n=10, eps=1) ----
    ts = [r['t'] for r in res['sweep_t']]
    f1 = [r['f1'] for r in res['sweep_t']]
    dc = [r['delta_cand'] for r in res['sweep_t']]

    fig, ax1 = plt.subplots(figsize=(6.4, 4.2))
    ax1.plot(ts, f1, 'o-', color='#2e7d32', label='F1 (utility)')
    ax1.set_xlabel('Threshold t')
    ax1.set_ylabel('F1', color='#2e7d32')
    ax1.tick_params(axis='y', labelcolor='#2e7d32')
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, alpha=0.3)
    ax2 = ax1.twinx()
    ax2.plot(ts, dc, 's--', color='#c62828', label=r'$\delta_{cand}=\frac{1}{2} e^{-(t-2)\varepsilon_{thr}}$')
    ax2.set_ylabel(r'$\delta_{cand}$', color='#c62828')
    ax2.tick_params(axis='y', labelcolor='#c62828')
    ax2.set_ylim(0, 0.25)
    plt.title(r'Threshold sweep: utility vs. candidacy-boundary leakage (n=10, $\varepsilon_{dp}=1$)')
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1+lines2, labels1+labels2, fontsize=8, loc='center right')
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'tsweep.png'), dpi=150)
    plt.close()
    print('wrote tsweep.png')

    # ---- Fig: participant sweep n, F1 ----
    ns = [r['n'] for r in res['sweep_n']]
    f1n = [r['f1'] for r in res['sweep_n']]
    pn = [r['precision'] for r in res['sweep_n']]
    rn = [r['recall'] for r in res['sweep_n']]
    plt.figure(figsize=(6.4, 4.2))
    plt.plot(ns, pn, 'o-', label='Precision')
    plt.plot(ns, rn, 's-', label='Recall')
    plt.plot(ns, f1n, '^-', label='F1')
    plt.xlabel('Number of participating banks n (t=min(4,n))')
    plt.ylabel('Utility')
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)
    plt.title(r'Participant sweep ($\varepsilon_{dp}=1$, k=2)')
    plt.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'nsweep.png'), dpi=150)
    plt.close()
    print('wrote nsweep.png')


if __name__ == "__main__":
    main()
