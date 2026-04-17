"""MISSION-03 export tests (pure -- no real weights needed)."""
from __future__ import annotations
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from backend.core.schemas import MissionPlan
from backend.mission.export import (
    _build_currents_table_rows,
    export_geojson,
    export_gpx,
    export_pdf,
)
from tests.fixtures.synthetic_mission import make_forecast_envelope, make_mission_plan

GPX_NS = "{http://www.topografix.com/GPX/1/1}"


def test_gpx_roundtrip(tmp_path: Path) -> None:
    mission = make_mission_plan(n_waypoints=15)
    out = export_gpx(mission, tmp_path / "m.gpx")
    assert out.exists() and out.stat().st_size > 0
    raw = out.read_text(encoding="utf-8")
    assert "ns0:" not in raw, "default namespace not registered"
    root = ET.parse(out).getroot()
    assert root.tag == f"{GPX_NS}gpx"
    wpts = root.findall(f"{GPX_NS}wpt")
    assert len(wpts) == 15
    trkpts = root.findall(f"{GPX_NS}trk/{GPX_NS}trkseg/{GPX_NS}trkpt")
    assert len(trkpts) == len(mission.route.geometry.coordinates)
    assert wpts[0].find(f"{GPX_NS}name").text == "WP00"


def test_geojson_roundtrip_and_size(tmp_path: Path) -> None:
    mission = make_mission_plan(n_waypoints=15)
    out = export_geojson(mission, tmp_path / "m.geojson")
    assert out.stat().st_size < 500_000, out.stat().st_size
    restored = MissionPlan.model_validate_json(out.read_text(encoding="utf-8"))
    assert restored == mission


def test_pdf_warm_latency_and_size(tmp_path: Path) -> None:
    mission = make_mission_plan(n_waypoints=15)
    forecast = make_forecast_envelope()
    export_pdf(mission, forecast, tmp_path / "warm.pdf")  # warm-up
    t0 = time.perf_counter()
    out = export_pdf(mission, forecast, tmp_path / "m.pdf")
    elapsed = time.perf_counter() - t0
    assert out.stat().st_size < 1_000_000, out.stat().st_size
    assert out.read_bytes()[:5] == b"%PDF-", out.read_bytes()[:10]
    assert elapsed < 3.0, f"warm PDF took {elapsed:.2f}s (>3s budget)"


def test_pdf_no_figure_leak(tmp_path: Path) -> None:
    mission = make_mission_plan(n_waypoints=3)
    for i in range(10):
        export_pdf(mission, None, tmp_path / f"leak_{i}.pdf")
    assert len(plt.get_fignums()) <= 2, plt.get_fignums()


def test_pdf_empty_waypoints(tmp_path: Path) -> None:
    mission = make_mission_plan(n_waypoints=0)
    out = export_pdf(mission, None, tmp_path / "empty.pdf")
    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"


# ---------- M5: currents-table acceptance ----------
def test_currents_table_rows_shape_and_finite():
    mission = make_mission_plan(n_waypoints=5)
    forecast = make_forecast_envelope()
    rows = _build_currents_table_rows(mission, forecast)
    assert len(rows) == 1 + len(mission.waypoints)       # header + N rows
    assert rows[0] == ["#", "|v_current| (m/s)", "v_current dir (deg)"]
    for data_row in rows[1:]:
        assert len(data_row) == 3
        mag = float(data_row[1])
        direction = float(data_row[2])
        assert math.isfinite(mag) and mag >= 0.0
        assert math.isfinite(direction) and 0.0 <= direction < 360.0


def test_pdf_includes_currents_table_flowable(tmp_path: Path, monkeypatch):
    """The story passed to doc.build must contain >=2 Table flowables
    (waypoint table + currents table) when forecast is supplied."""
    from reportlab.platypus import SimpleDocTemplate, Table

    captured: list[list] = []
    orig_build = SimpleDocTemplate.build

    def spy_build(self, flowables, *a, **kw):
        captured.append(list(flowables))
        return orig_build(self, flowables, *a, **kw)

    monkeypatch.setattr(SimpleDocTemplate, "build", spy_build)
    mission = make_mission_plan(n_waypoints=5)
    forecast = make_forecast_envelope()
    export_pdf(mission, forecast, tmp_path / "withcurrents.pdf")
    assert captured, "doc.build never called"
    story = captured[-1]
    tables = [f for f in story if isinstance(f, Table)]
    assert len(tables) >= 2, f"expected >=2 tables, got {len(tables)}"
