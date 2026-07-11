"""Unit tests: DP bounds, deterministic seeds, scenario separation, output paths."""
import json
import math
import os

import pytest

import attack
import datagen
import protocol
from complexity import CostModel
import kit_common


# ---------------- DP bound calculations ----------------

@pytest.mark.parametrize("eps", [0.1, 0.5, 1.0, 2.0])
def test_theoretical_bound_matches_closed_form(eps):
    got = attack.theoretical_bound(eps)
    want = (math.exp(eps) - 1) / (math.exp(eps) + 1)
    assert got == pytest.approx(want)
    assert 0.0 <= got <= 1.0


def test_theoretical_bound_infinite():
    assert attack.theoretical_bound(float("inf")) == 1.0


def test_tanh_identity_of_bound():
    # (e^e-1)/(e^e+1) == tanh(e/2); sim.py analytic_bounds relies on this.
    for eps in (0.1, 1.0, 3.0):
        assert attack.theoretical_bound(eps) == pytest.approx(math.tanh(eps / 2.0))


def test_delta_cand_formula_and_monotonicity():
    import sim
    # delta_cand = 0.5*exp(-(t-2)*eps); decreasing in t and in eps.
    prev = None
    for t in (3, 4, 5, 7):
        ab = sim.analytic_bounds(1.0, t)
        assert ab["delta_cand"] == pytest.approx(0.5 * math.exp(-(t - 2) * 1.0))
        if prev is not None:
            assert ab["delta_cand"] < prev
        prev = ab["delta_cand"]
    # documented values at t=4
    for eps, exp in [(0.1, 0.409), (0.5, 0.184), (1.0, 0.068), (2.0, 0.009)]:
        assert sim.analytic_bounds(eps, 4)["delta_cand"] == pytest.approx(exp, abs=5e-4)


def test_empirical_advantage_within_bound():
    for eps in (0.5, 1.0, 2.0):
        adv, acc = attack.empirical_advantage(eps_dp=eps, t=4, c_base=3,
                                              trials=20000, seed=7)
        assert 0.0 <= adv <= attack.theoretical_bound(eps) + 0.03
        assert 0.5 <= acc <= 1.0


# ---------------- deterministic seeds ----------------

def test_datagen_deterministic():
    a = datagen.generate(seed=123)
    b = datagen.generate(seed=123)
    assert a.I_t == b.I_t
    assert len(a.union()) == len(b.union())


def test_attack_deterministic_same_seed():
    r1 = attack.empirical_advantage(eps_dp=1.0, t=4, c_base=3, trials=5000, seed=7)
    r2 = attack.empirical_advantage(eps_dp=1.0, t=4, c_base=3, trials=5000, seed=7)
    assert r1 == r2


def test_sim_thrlabel_build_counts_deterministic():
    import sim_thrlabel
    c1 = sim_thrlabel.build_counts(42)
    c2 = sim_thrlabel.build_counts(42)
    assert (c1 == c2).all()


# ---------------- scenario separation ----------------

def test_scenarios_distinct_models_and_thresholds():
    s4 = kit_common.get_scenario("fraudring_t4")
    s3 = kit_common.get_scenario("coverage_t3")
    assert s4.data_model == "fraud_ring" and s4.threshold == 4
    assert s3.data_model == "coverage" and s3.threshold == 3
    assert s4.name != s3.name


def test_unknown_scenario_rejected():
    with pytest.raises(SystemExit):
        kit_common.get_scenario("does_not_exist")


def test_metadata_provenance_validation():
    with pytest.raises(ValueError):
        kit_common.metadata_block(scenario=None, provenance="bogus")
    md = kit_common.metadata_block(
        scenario=kit_common.get_scenario("fraudring_t4"), provenance="simulation")
    assert md["provenance"] == "simulation"
    assert md["scenario"]["name"] == "fraudring_t4"


# ---------------- output-dir resolution (never /data) ----------------

def test_resolve_output_dir_explicit(tmp_path):
    d = kit_common.resolve_output_dir(str(tmp_path / "out"))
    assert os.path.isdir(d)
    assert d.startswith(str(tmp_path))


def test_resolve_output_dir_env(tmp_path, monkeypatch):
    monkeypatch.setenv("THRLABEL_OUTPUT_DIR", str(tmp_path / "envout"))
    d = kit_common.resolve_output_dir(None)
    assert d.startswith(str(tmp_path))


def test_no_hardcoded_data_path_in_sources():
    root = os.path.dirname(os.path.dirname(__file__))
    for fn in ["sim.py", "experiments.py", "figs.py", "make_figures.py", "sim_thrlabel.py"]:
        src = open(os.path.join(root, fn)).read()
        assert "/data/" not in src, f"{fn} still references /data/"


# ---------------- analytical cost model ----------------

def test_cost_model_monotone_and_positive():
    prev = 0.0
    for m in [2 ** 12, 2 ** 16, 2 ** 20]:
        mb = CostModel(n_banks=5, m=m).comm_bytes()["total_MB"]
        assert mb > prev
        prev = mb


# ---------------- protocol release-layer sanity ----------------

def test_protocol_no_noise_matches_ground_truth():
    ds = datagen.generate(seed=1)
    out = protocol.run_protocol(ds, eps_dp=float("inf"), candidate_min_coverage=1)
    assert out.released_set == ds.I_t
