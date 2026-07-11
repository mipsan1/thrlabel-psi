"""Reproducibility: sim.py reproduces committed sim_results.json numerics."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(__file__))


def _numeric_close(a, b, tol=1e-9, path=""):
    if isinstance(a, dict):
        for k in a:
            if k == "metadata":
                continue
            assert k in b, f"missing key {path}/{k}"
            _numeric_close(a[k], b[k], tol, path + "/" + k)
    elif isinstance(a, list):
        assert len(a) == len(b), f"length mismatch at {path}"
        for i, (x, y) in enumerate(zip(a, b)):
            _numeric_close(x, y, tol, f"{path}[{i}]")
    elif isinstance(a, (int, float)):
        assert abs(a - b) <= tol, f"value mismatch at {path}: {a} != {b}"
    else:
        assert a == b, f"value mismatch at {path}: {a!r} != {b!r}"


def test_sim_reproduces_committed_results(tmp_path):
    import sim
    sim.main(["--output-dir", str(tmp_path)])
    new = json.load(open(tmp_path / "sim_results.json"))
    committed = json.load(open(os.path.join(ROOT, "sim_results.json")))
    for key in ("main", "designs", "sweep_n", "sweep_t", "sweep_B"):
        _numeric_close(committed[key], new[key], path=key)


def test_sim_records_scenario_metadata(tmp_path):
    import sim
    sim.main(["--output-dir", str(tmp_path)])
    data = json.load(open(tmp_path / "sim_results.json"))
    assert data["metadata"]["scenario"]["name"] == "fraudring_t4"
    assert data["metadata"]["provenance"] == "simulation"


def test_sim_main_finding3_empirical_advantage(tmp_path):
    import sim
    sim.main(["--output-dir", str(tmp_path)])
    data = json.load(open(tmp_path / "sim_results.json"))
    adv = [round(r["emp_adv"], 2) for r in data["main"]]
    assert adv == [0.05, 0.20, 0.32, 0.43]
