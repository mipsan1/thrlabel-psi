"""Smoke tests: every Python entry point runs end-to-end and writes outputs."""
import json
import os
import runpy
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))


def _run(module, argv):
    """Invoke a module's main(argv) if present, else exec as __main__."""
    old = sys.argv
    sys.argv = [module + ".py"] + argv
    try:
        mod = __import__(module)
        if hasattr(mod, "main"):
            mod.main(argv)
        else:
            runpy.run_module(module, run_name="__main__")
    finally:
        sys.argv = old


def test_datagen_smoke(capsys):
    runpy.run_path(os.path.join(ROOT, "datagen.py"), run_name="__main__")
    assert "I_t" in capsys.readouterr().out


def test_sim_smoke(tmp_path):
    _run("sim", ["--output-dir", str(tmp_path), "--num-seeds", "2"])
    assert (tmp_path / "sim_results.json").exists()


def test_sim_thrlabel_smoke(tmp_path):
    _run("sim_thrlabel", ["--output-dir", str(tmp_path), "--num-seeds", "2"])
    data = json.load(open(tmp_path / "thrlabel_tables.json"))
    assert set(data["scenarios"]) == {"fraudring_t3", "fraudring_t4"}
    for csv_row in data["scenarios"]["fraudring_t4"]["rows"]:
        assert csv_row["scenario"] == "fraudring_t4"


def test_experiments_smoke(tmp_path):
    _run("experiments", ["--output-dir", str(tmp_path), "--reps", "2"])
    for name in ["rq3_utility.csv", "rq4_advantage.csv", "rq1_efficiency.csv",
                 "experiments_metadata.json"]:
        assert (tmp_path / name).exists()
    # every CSV row carries the coverage_t3 scenario column
    import csv
    with open(tmp_path / "rq3_utility.csv") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(r["scenario"] == "coverage_t3" for r in rows)


def test_make_figures_failclosed_timing(tmp_path, capsys):
    _run("make_figures", ["--output-dir", str(tmp_path), "--attack-trials", "3000"])
    assert (tmp_path / "rq1_scaling.png").exists()
    assert (tmp_path / "rq4_advantage.png").exists()
    meta = json.load(open(tmp_path / "figures_metadata.json"))
    assert meta["rq1_timing_provenance"] == "none"
    assert meta["rq1_comm_provenance"] == "analytical"
    assert meta["rq4_advantage_provenance"] == "simulation"


def test_make_figures_measured_timing(tmp_path):
    rt = tmp_path / "rt.json"
    rt.write_text(json.dumps({"provenance": "measurement",
                              "points": [{"set_size": 4096, "lan_s": 0.1, "wan_s": 1.0},
                                         {"set_size": 65536, "lan_s": 1.7, "wan_s": 3.5}]}))
    _run("make_figures", ["--output-dir", str(tmp_path), "--attack-trials", "3000",
                          "--runtime-json", str(rt)])
    meta = json.load(open(tmp_path / "figures_metadata.json"))
    assert meta["rq1_timing_provenance"] == "measurement"


def test_make_figures_rejects_non_measurement(tmp_path):
    rt = tmp_path / "bad.json"
    rt.write_text(json.dumps({"provenance": "illustrative_projection", "points": [1]}))
    with pytest.raises(SystemExit):
        _run("make_figures", ["--output-dir", str(tmp_path), "--attack-trials", "3000",
                              "--runtime-json", str(rt)])


def test_figs_failclosed_without_results(tmp_path):
    with pytest.raises(SystemExit):
        _run("figs", ["--output-dir", str(tmp_path)])


def test_figs_after_sim(tmp_path):
    _run("sim", ["--output-dir", str(tmp_path), "--num-seeds", "2"])
    _run("figs", ["--output-dir", str(tmp_path)])
    for name in ["rq4_advantage.png", "tsweep.png", "nsweep.png"]:
        assert (tmp_path / name).exists()
