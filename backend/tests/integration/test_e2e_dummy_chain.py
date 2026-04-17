"""E2E chain test (D-19 scripted). Uses synthetic env to avoid NetCDF deps."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from backend.core.schemas import MissionPlan


def _has_marida() -> bool:
    sp = Path("MARIDA/splits/val_X.txt")
    if not sp.exists() or sp.read_text().strip() == "":
        return False
    first = sp.read_text().splitlines()[0].strip()
    if list(Path("MARIDA/patches").rglob(f"{first}.tif")):
        return True
    return bool(list(Path("MARIDA/patches").rglob(f"S2_{first}.tif")))


@pytest.mark.skipif(not _has_marida(), reason="MARIDA val split / patches not available")
def test_full_chain_dummy_synth_env(tmp_path):
    out = tmp_path / "plan.json"
    t0 = time.perf_counter()
    cp = subprocess.run(
        [sys.executable, "scripts/run_full_chain_dummy.py",
         "--use-synth-env", "--out", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    elapsed = time.perf_counter() - t0
    assert cp.returncode == 0, f"stderr:\n{cp.stderr}"
    assert out.exists()
    plan = MissionPlan.model_validate_json(out.read_text())
    assert plan.route.geometry.type == "LineString"
    assert elapsed < 20.0, f"wall-clock {elapsed:.2f}s exceeds 20s budget"
