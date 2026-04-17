"""Fallback behavior tests -- no real weights or env data required.

Monkeypatches run_inference/forecast_drift/plan_mission to raise, writes a
synthetic valid prebake JSON to a tmp PREBAKE_DIR, and asserts the driver
swallows the exception + loads + schema-validates the fallback.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root on sys.path when pytest launches from elsewhere.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection
from scripts.parity_hash import parity_hash
from tests.fixtures.synthetic_mission import make_forecast_envelope, make_mission_plan


def _prebake(tmp_path: Path, aoi: str) -> Path:
    prebake = tmp_path / "prebaked"
    prebake.mkdir()
    # detections = empty valid FC
    (prebake / f"{aoi}_detections.json").write_text(json.dumps({
        "type": "FeatureCollection", "features": [],
    }))
    # forecast + mission from synthetic fixtures
    (prebake / f"{aoi}_forecast.json").write_text(make_forecast_envelope().model_dump_json())
    (prebake / f"{aoi}_mission.json").write_text(make_mission_plan().model_dump_json())
    return prebake


def test_live_success_returns_live_sources(tmp_path, monkeypatch):
    import scripts.run_full_chain_real as e2e

    empty_fc = DetectionFeatureCollection(type="FeatureCollection", features=[])
    fc_env = make_forecast_envelope()
    mission = make_mission_plan()

    monkeypatch.setattr("backend.ml.inference.run_inference",
                        lambda tile, cfg: empty_fc)
    monkeypatch.setattr("backend.physics.tracker.forecast_drift",
                        lambda det, cfg: fc_env)
    monkeypatch.setattr("backend.mission.planner.plan_mission",
                        lambda f, r, h, o, cfg: mission)

    result = e2e.run_chain("gulf_of_mannar", Path("nonexistent.tif"),
                           (78.9, 9.2), Settings())
    assert result["sources"] == {
        "detections": "live", "forecast": "live", "mission": "live",
    }


def test_silent_fallback_on_detection_failure(tmp_path, monkeypatch):
    import scripts.run_full_chain_real as e2e

    prebake = _prebake(tmp_path, "gulf_of_mannar")
    monkeypatch.setattr(e2e, "PREBAKE_DIR", prebake)

    def boom(*a, **kw):
        raise RuntimeError("simulated inference OOM")
    monkeypatch.setattr("backend.ml.inference.run_inference", boom)
    fc_env = make_forecast_envelope()
    mission = make_mission_plan()
    monkeypatch.setattr("backend.physics.tracker.forecast_drift",
                        lambda det, cfg: fc_env)
    monkeypatch.setattr("backend.mission.planner.plan_mission",
                        lambda f, r, h, o, cfg: mission)

    result = e2e.run_chain("gulf_of_mannar", Path("nonexistent.tif"),
                           (78.9, 9.2), Settings(), no_fallback=False)
    assert result["sources"]["detections"] == "fallback"
    assert result["sources"]["forecast"] == "live"
    assert result["sources"]["mission"] == "live"


def test_no_fallback_flag_reraises(tmp_path, monkeypatch):
    import scripts.run_full_chain_real as e2e

    prebake = _prebake(tmp_path, "gulf_of_mannar")
    monkeypatch.setattr(e2e, "PREBAKE_DIR", prebake)

    def boom(*a, **kw):
        raise RuntimeError("simulated inference OOM")
    monkeypatch.setattr("backend.ml.inference.run_inference", boom)

    with pytest.raises(RuntimeError, match="simulated inference OOM"):
        e2e.run_chain("gulf_of_mannar", Path("nonexistent.tif"),
                      (78.9, 9.2), Settings(), no_fallback=True)


def test_fallback_missing_raises_stage_failed(tmp_path, monkeypatch):
    import scripts.run_full_chain_real as e2e

    # Empty prebake dir -> no fallback file -> StageFailed
    prebake = tmp_path / "prebaked"
    prebake.mkdir()
    monkeypatch.setattr(e2e, "PREBAKE_DIR", prebake)

    def boom(*a, **kw):
        raise RuntimeError("x")
    monkeypatch.setattr("backend.ml.inference.run_inference", boom)

    with pytest.raises(e2e.StageFailed, match="no prebaked fallback"):
        e2e.run_chain("gulf_of_mannar", Path("nonexistent.tif"),
                      (78.9, 9.2), Settings(), no_fallback=False)


def test_fallback_invalid_schema_raises_stage_failed(tmp_path, monkeypatch):
    import scripts.run_full_chain_real as e2e

    prebake = tmp_path / "prebaked"
    prebake.mkdir()
    # Invalid JSON for DetectionFeatureCollection
    (prebake / "gulf_of_mannar_detections.json").write_text('{"not": "a fc"}')
    monkeypatch.setattr(e2e, "PREBAKE_DIR", prebake)

    def boom(*a, **kw):
        raise RuntimeError("x")
    monkeypatch.setattr("backend.ml.inference.run_inference", boom)

    with pytest.raises(e2e.StageFailed, match="fallback schema invalid"):
        e2e.run_chain("gulf_of_mannar", Path("nonexistent.tif"),
                      (78.9, 9.2), Settings(), no_fallback=False)


def test_parity_hash_stable_across_runs():
    m1 = make_mission_plan()
    m2 = make_mission_plan()
    assert parity_hash(m1) == parity_hash(m2)
    assert len(parity_hash(m1)) == 64
