"""Shared helpers for the ThrLabel-PSI reference simulation entry points.

Centralizes:
  - output-directory resolution (repo-relative default ``./outputs``)
  - named-scenario definitions so tables/figures always record which data
    model and operating point produced them
  - a small metadata block writer (records scenario, params, provenance)

Nothing here touches the (absent) cryptographic layer. Every number produced by
this artifact is either a release-layer *simulation* result or an *analytical*
cost-model result; the ``provenance`` field records which.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict

DEFAULT_OUTPUT_DIR = "outputs"


@dataclass(frozen=True)
class Scenario:
    """A named experimental scenario.

    ``data_model`` distinguishes the two synthetic generators that exist in this
    repo and that the feasibility audit flagged as inconsistent when left
    implicit:

      - ``fraud_ring``   : cross-bank fraud-ring generator (sim.py / sim_thrlabel.py)
      - ``coverage``     : coverage-weighted planted-intersection generator (datagen.py)
    """

    name: str
    data_model: str          # "fraud_ring" | "coverage"
    threshold: int           # operating-point t
    k: int                   # collusion parameter (for t >= k+2 margin bookkeeping)
    description: str


# The two operating points the manuscript relies on, kept explicitly distinct.
SCENARIOS: Dict[str, Scenario] = {
    "fraudring_t4": Scenario(
        name="fraudring_t4",
        data_model="fraud_ring",
        threshold=4,
        k=2,
        description="Fraud-ring generator, headline operating point t=4, k=2 "
        "(t >= k+2). Source of the t=4 main utility/probing table.",
    ),
    "fraudring_t3": Scenario(
        name="fraudring_t3",
        data_model="fraud_ring",
        threshold=3,
        k=1,
        description="Fraud-ring generator at t=3 (secondary operating point).",
    ),
    "coverage_t3": Scenario(
        name="coverage_t3",
        data_model="coverage",
        threshold=3,
        k=1,
        description="Coverage-weighted planted-intersection generator "
        "(datagen.py), threshold t=3. Source of the RQ3/RQ4 CSV tables.",
    ),
}


def get_scenario(name: str) -> Scenario:
    if name not in SCENARIOS:
        raise SystemExit(
            f"unknown scenario '{name}'. Known: {', '.join(sorted(SCENARIOS))}"
        )
    return SCENARIOS[name]


def resolve_output_dir(output_dir: str | None) -> str:
    """Return an absolute output directory, creating it if needed.

    Priority: explicit ``--output-dir`` > ``THRLABEL_OUTPUT_DIR`` env var >
    repo-relative ``./outputs``. Never writes to hard-coded ``/data``.
    """
    chosen = output_dir or os.environ.get("THRLABEL_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR
    chosen = os.path.abspath(chosen)
    os.makedirs(chosen, exist_ok=True)
    return chosen


def metadata_block(
    *,
    scenario: Scenario | None,
    provenance: str,
    params: Dict[str, Any] | None = None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a metadata dict recording scenario + provenance for any output.

    ``provenance`` must be one of:
      - ``"simulation"``            : Monte-Carlo / release-layer simulation output
      - ``"analytical"``            : closed-form / cost-model output (no wall-clock)
      - ``"illustrative_projection"``: hand-set illustrative numbers, NOT a measurement
      - ``"measurement"``           : real measured wall-clock (only if a measured file exists)
    """
    allowed = {"simulation", "analytical", "illustrative_projection", "measurement"}
    if provenance not in allowed:
        raise ValueError(f"provenance must be one of {allowed}, got {provenance!r}")
    md: Dict[str, Any] = {
        "provenance": provenance,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    if scenario is not None:
        md["scenario"] = asdict(scenario)
    if params:
        md["params"] = params
    if extra:
        md.update(extra)
    return md


def write_json(path: str, payload: Any) -> str:
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2, default=float)
    return path
