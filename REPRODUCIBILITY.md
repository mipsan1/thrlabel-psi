# Reproducibility

This artifact is a **release-layer simulation + analytical cost model**. It does
**not** contain a cryptographic implementation (no OPRF/OKVS/secret sharing), so
it produces **no cryptographic wall-clock measurements**. Every number is one of:

| provenance | meaning |
|---|---|
| `simulation` | Monte-Carlo / release-layer simulation output (seeded, deterministic) |
| `analytical` | closed-form or cost-model output (e.g. communication bytes, DP bounds) |
| `illustrative_projection` | hand-set numbers used only for illustration; **never** a measurement |
| `measurement` | real measured wall-clock — only present if a prototype produced it |

Each output file carries a metadata block (`sim_results.json`,
`thrlabel_tables.json`, `experiments_metadata.json`, `figures_metadata.json`) that
records the `scenario` and `provenance`. CSV tables carry a `scenario` column.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate     # optional
pip install -r requirements.txt                         # runtime deps
pip install -r requirements-dev.txt                     # + pytest for the tests
# or, editable install with dev extras:
pip install -e ".[dev]"
```

All entry points run from a clean checkout and write to `./outputs` by default
(override with `--output-dir` or the `THRLABEL_OUTPUT_DIR` env var). No path is
hard-coded to `/data` anymore.

## Named scenarios

The repo has **two distinct synthetic data models**; they are now explicit named
scenarios so their tables are never confused (see `kit_common.py`):

| scenario | data model | operating point | produced by |
|---|---|---|---|
| `fraudring_t4` | cross-bank fraud-ring | t=4, k=2 (headline) | `sim.py`, `sim_thrlabel.py` |
| `fraudring_t3` | cross-bank fraud-ring | t=3 | `sim_thrlabel.py` |
| `coverage_t3` | coverage-weighted planted intersection (`datagen.py`) | t=3 | `experiments.py` |

## Reproducing the paper tables/figures

### `tab:util` — main utility & probing table (n=5, t=4, k=2, 10 seeds)

Scenario `fraudring_t4`, provenance `simulation` (columns P/R/F1 and empirical
`emp_adv`) + `analytical` (bounds `thr_only`, `full_dp`, `delta_cand`, `full_plus`).

```bash
python sim.py --output-dir ./outputs           # writes outputs/sim_results.json (key: "main")
```

The `main` array in `outputs/sim_results.json` holds one row per
`eps in {0.1,0.5,1.0,2.0}` with fields:
`precision, recall, f1, emp_adv, thr_only, full_dp, delta_cand, full_plus`.
The empirical advantage row is `0.05, 0.20, 0.32, 0.43` (Finding 3).

### `tab:designs` — three-design precision comparison (n=5, t=4, 10 seeds)

Scenario `fraudring_t4`, provenance `simulation`. Same run as above; the `designs`
array of `outputs/sim_results.json` holds `naive / noisy_gate / det` precision per
epsilon. Design (ii) `det` is the adopted design and its precision matches the
Precision column of `tab:util`.

```bash
python sim.py --output-dir ./outputs           # writes outputs/sim_results.json (key: "designs")
```

A compact, human-readable rendering of both tables (with an explicit `scenario`
field and the `adv_closed_form`/`bound`/`delta_cand` analytical columns) is also
produced by:

```bash
python sim_thrlabel.py --output-dir ./outputs  # writes outputs/thrlabel_tables.json
```

### RQ3/RQ4 CSV tables (coverage model, t=3)

Scenario `coverage_t3`, provenance `simulation` (RQ3/RQ4) + `analytical` (RQ1).

```bash
python experiments.py --output-dir ./outputs   # writes rq3_*.csv, rq4_*.csv, rq1_efficiency.csv
```

### Figures

```bash
python make_figures.py --output-dir ./outputs  # rq1_scaling.png (comm=analytical), rq4_advantage.png (adv=simulation)
python figs.py         --output-dir ./outputs  # rq4_advantage.png, tsweep.png, nsweep.png (needs sim_results.json first)
```

**Timing figures are fail-closed.** `make_figures.py` does **not** plot LAN/WAN
seconds unless you pass a real measurement file:

```bash
python make_figures.py --output-dir ./outputs --runtime-json path/to/measured_runtime.json
```

with schema:

```json
{"provenance": "measurement",
 "points": [{"set_size": 4096, "lan_s": 0.11, "wan_s": 1.12}]}
```

If you only want an explicitly-labelled, non-measured illustration, pass
`--illustrative-timing`; the curve is then drawn as
`illustrative_projection (NOT measured)` and must not be cited as a result.

## Determinism

All simulations use fixed seeds. `python sim.py` reproduces the committed
`sim_results.json` byte-for-byte in the numeric fields (verified by
`tests/test_repro.py`). Use `--seed N` to shift the seed for robustness checks.

## Tests

```bash
pytest            # seeds, output paths, table consistency, DP bounds, scenario separation, smoke tests
```
