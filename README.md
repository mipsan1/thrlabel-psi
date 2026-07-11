# ThrLabel-PSI --- Release-Layer Reference Simulation

Release-layer reference simulation and analytical cost model for
**ThrLabel-PSI: Over-Threshold Multiparty Labeled PSI for Cross-Institution
Fraud-Account Blacklist Sharing**.

> **Scope.** This artifact models only the parts of the protocol that determine
> **utility and leakage**: the deterministic candidacy filter, the noisy-threshold
> decision, output-stage clamped-count differential privacy, and label
> aggregation. The cryptographic layers (OPRF, OKVS, secret sharing) are omitted
> by design; by the simulation-privacy theorem they reveal nothing beyond the
> defined output. **All timing numbers are analytical projections, not
> cryptographic wall-clock measurements.** A measured C++ prototype is future work.

## Operating point

The manuscript reports the operating point **t = 4, k = 2** (threshold margin
`t >= k+2`). `eps_dp` is the **per-mechanism** budget: the noisy-threshold
comparison uses `eps_thr = eps_dp` and the output-count release uses
`eps_out = eps_dp`, so by basic composition the end-to-end membership budget is
`eps_tot = eps_thr + eps_out = 2*eps_dp`. The membership-probing guarantee is
`(eps_tot, delta)`-indistinguishable with
`delta = delta_out + delta_cand`, `delta_cand = 0.5*exp(-(t-2)*eps_thr)`.
The additive candidacy term is the tunable cost of a *deterministic* candidacy
filter (delta_cand = 0.409/0.184/0.068/0.009 at eps_dp = 0.1/0.5/1/2). The
empirical advantage column is tested against the per-channel noisy-threshold
bound `(e^eps_thr - 1)/(e^eps_thr + 1)`.

## Synthetic data model

- `n = 5` banks, `2000` accounts/bank.
- Fraud ring: `F = 350` accounts, each included by each bank w.p. `p_ring = 0.72`
  (truly cross-bank fraud accounts concentrate at high coverage).
- Benign coincidental overlaps: `G = 150` accounts, each held by exactly 2 banks.
- Remaining slots filled with per-bank singleton noise.
- 10 random seeds; results are seed-averaged.

## Reproduce

All entry points run from a clean checkout and write to `./outputs` by default
(override with `--output-dir` or `$THRLABEL_OUTPUT_DIR`). No path is hard-coded
to `/data`. See **REPRODUCIBILITY.md** for the full table/figure provenance map
and the exact commands for `tab:util` and `tab:designs`.

```bash
pip install -r requirements.txt
python sim.py              # main table (tab:util) + three designs (tab:designs) -> outputs/sim_results.json
python sim_thrlabel.py     # Table II/III + Findings (scenarios fraudring_t3, fraudring_t4)
python experiments.py      # RQ1-RQ4 CSVs (scenario coverage_t3)
python make_figures.py     # rq1_scaling.png (comm analytical), rq4_advantage.png (adv simulation)
python figs.py             # extra figures from outputs/sim_results.json
```

> **Provenance.** Communication (MB) is an **analytical** cost-model estimate.
> Membership-probing advantage is a **simulation** result. LAN/WAN seconds are
> **not** measured: `make_figures.py` is fail-closed and only draws a timing
> curve when given a real `--runtime-json` measurement file. All entry points
> accept `--output-dir`; `sim.py`/`sim_thrlabel.py` also accept `--seed`, `--n`,
> `--t`, `--set-size`, `--num-seeds`, `--scenario`/`--thresholds`, `--model-name`.

## Files

| file | purpose |
|------|---------|
| `sim.py` | fraud-ring main table + three designs + sweeps (scenario `fraudring_t4`) |
| `sim_thrlabel.py` | fraud-ring Table II/III + Findings (scenarios `fraudring_t3/t4`) |
| `datagen.py`, `protocol.py`, `attack.py`, `complexity.py` | coverage-model generator, release-layer model, probing attacker, analytical cost model |
| `experiments.py` | RQ1-RQ4 driver (scenario `coverage_t3`) |
| `make_figures.py`, `figs.py` | figure regeneration (fail-closed timing) |
| `kit_common.py` | output-dir resolution + named scenarios + provenance metadata |
| `tests/` | pytest suite (determinism, paths, tables, DP bounds, scenarios, smoke) |
| `scripts/` | macOS M3 feasibility + local-experiment runner + Korean README |
| `requirements.txt` / `requirements-dev.txt` / `pyproject.toml` | dependencies |

## License

MIT (research artifact).
