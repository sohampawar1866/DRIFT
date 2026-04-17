---
phase: 03-real-training-weight-swap-mission-export-e2e
plan: 02
subsystem: mission
tags: [export, gpx, geojson, pdf, reportlab, matplotlib]
requires:
  - path: "backend/core/schemas.py (MissionPlan, ForecastEnvelope — FROZEN)"
    from: "Phase 1"
  - path: "data/basemap/ne_10m_coastline_indian_eez.shp"
    from: "03-01"
  - path: "backend/requirements.txt (reportlab>=4.2,<5.0)"
    from: "03-01"
provides:
  - path: "backend/mission/export.py"
    for: "MISSION-03 deliverable + Plan 03-05 E2E chain export stage"
    exports: ["export_gpx", "export_geojson", "export_pdf", "_build_currents_table_rows"]
  - path: "tests/fixtures/synthetic_mission.py"
    for: "Reusable MissionPlan + ForecastEnvelope fixtures for any export/E2E test"
    exports: ["make_mission_plan", "make_forecast_envelope"]
  - path: "python -m backend.mission.export CLI"
    for: "Live judge-facing demo command"
affects: []
tech_stack:
  added:
    - "matplotlib.use('Agg') at module import (headless-safe)"
    - "reportlab.platypus flowables (SimpleDocTemplate, Image, Table, Paragraph)"
    - "xml.etree.ElementTree for GPX 1.1 (no gpxpy dependency)"
  patterns:
    - "Module-scope warm-up figure (throwaway) so first export_pdf clears the 3 s warm budget"
    - "ET.register_namespace('', GPX_NS) before serialisation — GPX emits without ns0: prefix"
    - "Module-cached coastline GeoDataFrame (_COASTLINE) — single read per process"
    - "Oceanographic bearing convention (atan2(u,v), 0=N, 90=E) for currents-table direction"
key_files:
  created:
    - "backend/mission/export.py"
    - "tests/__init__.py"
    - "tests/fixtures/__init__.py"
    - "tests/fixtures/synthetic_mission.py"
    - "tests/test_export.py"
  modified: []
decisions:
  - "Dropped wind columns from the D-09 currents table — ForecastFrame has no u10/v10 field; fabricating them would violate honesty principle. Caption documents the limitation and the +0h->+72h nearest-particle displacement derivation."
  - "Tests placed at repo-root `tests/` (per plan) rather than existing `backend/tests/` layout — plan was explicit and Plan 03-05 will depend on `tests.fixtures.synthetic_mission` import path."
  - "CLI lives inside export.py (guarded by `if __name__ == '__main__'`) so `python -m backend.mission.export` resolves without editing the pre-existing `backend/mission/__main__.py`."
  - "matplotlib warm-up is a module-level throwaway `plt.figure(figsize=(1,1))` + `plt.close(_warm)` — simplest way to force backend init before first `export_pdf` call."
metrics:
  duration_min: 4
  completed: "2026-04-17"
  tasks_total: 3
  tasks_done: 3
  commits: 3
---

# Phase 3 Plan 2: Mission Export (GPX / GeoJSON / PDF) Summary

Shipped three pure export functions (`export_gpx`, `export_geojson`, `export_pdf`) plus a `python -m backend.mission.export` CLI that turn a FROZEN `MissionPlan` into Google-Earth-openable GPX, RFC-7946 GeoJSON (< 500 KB), and a one-page A4 PDF briefing (< 1 MB, < 3 s warm) with a D-09 per-waypoint currents-summary table derived from +0h->+72h nearest-particle displacement. Closes `MISSION-03`.

## Objective Met

All seven export tests pass (`python -m pytest tests/test_export.py -v`): GPX round-trips under the default GPX 1.1 namespace with per-waypoint `<wpt>` and per-coord `<trkpt>`; GeoJSON round-trips to an identical `MissionPlan`; warm PDF generates in < 3 s, stays under 1 MB, survives 10 back-to-back calls with no matplotlib figure leak, and gracefully handles zero waypoints. D-09 currents table is wired as a second `Table` flowable in the PDF story with finite |v| + bearing values for every waypoint. CLI smoke-tested end-to-end for all three formats.

## What Was Built

### Task 1 — Synthetic fixtures (commit `22e15ce`)
- `tests/fixtures/synthetic_mission.py::make_mission_plan(n=15)` returns a pydantic-valid `MissionPlan` with a northwestward Mumbai-origin walk (0.05 deg lon, 0.04 deg lat per step), closed LineString, 6.2 km legs, ETA = cum/20 kmh, descending priority scores.
- `make_forecast_envelope()` returns a 4-frame `ForecastEnvelope` at hours {0, 24, 48, 72}. Each frame has 5 particles drifting 0.01 deg east per 24h (so the D-09 currents table gets non-zero magnitudes to render). +72 frame carries one density polygon around the origin.
- Added `tests/__init__.py` + `tests/fixtures/__init__.py` to make them package-importable from both tests and the Plan 03-05 E2E harness.

### Task 2 — `backend/mission/export.py` + `tests/test_export.py` (commit `50b2fbb`)
- **export_gpx:** hand-rolled GPX 1.1 via `xml.etree.ElementTree`. Single `<trk>` from `mission.route.geometry.coordinates`, one `<wpt>` per waypoint (`WP{order:02d}` name, `priority=... eta_h=...` desc). `ET.register_namespace("", GPX_NS)` at module import so output uses the default namespace (no `ns0:` prefix — Google Earth compat per RESEARCH Pitfall 5).
- **export_geojson:** `mission.model_dump_json(indent=2)` → file. Validates back to an equal `MissionPlan`.
- **export_pdf:** reportlab `SimpleDocTemplate` (A4 portrait, 1.5 cm margins) with title + matplotlib-rendered map PNG (11x9 cm) + waypoint `Table` + currents `Table` (when forecast supplied) + fuel summary paragraph (`2.5 L/km`) + footer. Matplotlib is forced to `Agg` before pyplot import; a throwaway `plt.figure(figsize=(1,1))` warm-up runs at module import. `plt.close(fig)` in `_render_map_png` prevents figure leaks across repeated calls.
- **D-09 currents table (_build_currents_table_rows):** for each waypoint, find nearest particle in frame[0], look up the same-index particle in frame[-1], convert degree displacement -> m/s using `cos(mean_lat)` longitude scaling, emit `|v| (m/s)` + oceanographic bearing (`atan2(u,v)`, 0=N, 90=E). Wind columns deliberately omitted — documented in PDF caption.
- **Tests (7/7 passed in 7.19s):**
  - `test_gpx_roundtrip` — 15 `<wpt>` + N `<trkpt>` + default-namespace root tag, no `ns0:`.
  - `test_geojson_roundtrip_and_size` — < 500 KB and `model_validate_json` equality.
  - `test_pdf_warm_latency_and_size` — < 1 MB, `%PDF-` magic, < 3 s second call.
  - `test_pdf_no_figure_leak` — 10 calls, `plt.get_fignums() <= 2`.
  - `test_pdf_empty_waypoints` — `n=0` MissionPlan still yields a valid PDF.
  - `test_currents_table_rows_shape_and_finite` — header + N rows, 3 columns, finite values, `0 <= dir < 360`.
  - `test_pdf_includes_currents_table_flowable` — monkeypatched `SimpleDocTemplate.build` captures story; >= 2 `Table` flowables when forecast supplied.

### Task 3 — CLI (commit `4ca0b46`)
- Appended `_cli()` + `if __name__ == "__main__": raise SystemExit(_cli())` to `backend/mission/export.py`.
- `argparse` with `--mission` (required), `--forecast` (optional), `--format {gpx,geojson,pdf}` (required), `--out` (required).
- `backend/mission/__main__.py` **not touched** (verified: `git diff HEAD -- backend/mission/__main__.py` empty; file does not appear in any commit diff from this plan).
- Smoke test: all three formats wrote non-empty files (gpx=2500 B, geojson=3603 B, pdf=70,347 B on a 15-waypoint mission with forecast).

## Deviations from Plan

None. Plan executed exactly as written. No Rule 1/2/3 fixes, no architectural decisions, no auth gates, no checkpoint interruptions.

## Verification Results

| Check | Result |
| --- | --- |
| `python -m pytest tests/test_export.py -v` | 7 passed, 0 failed, 7.19 s |
| `matplotlib.use("Agg")` appears before `import matplotlib.pyplot` | line 28 vs line 30 (correct order) |
| `ET.register_namespace("", GPX_NS)` present | line 53 |
| `plt.close(fig)` present | line 188 (in `_render_map_png`) |
| `FUEL_L_PER_KM = 2.5` present | line 48 |
| `COASTLINE_PATH = Path("data/basemap/ne_10m_coastline_indian_eez.shp")` present | line 46 |
| `_build_currents_table_rows` — def + call | def line 135, call line 238 |
| `Currents Summary` appears in PDF heading | line 235 |
| `python -c "from backend.mission.export import export_gpx, export_geojson, export_pdf"` | exit 0 |
| `python -m backend.mission.export --help` | prints usage, exit 0 |
| CLI gpx/geojson/pdf all produce non-empty files | gpx=2500, geojson=3603, pdf=70347 bytes |
| `git diff HEAD -- backend/mission/__main__.py` | empty (untouched) |
| `git log --stat -- backend/mission/__main__.py` since 03-01 | no commits from this plan |

## Commits

| Task | Commit | Message |
| --- | --- | --- |
| 1 | `22e15ce` | `test(03-02): add synthetic MissionPlan + ForecastEnvelope fixtures` |
| 2 | `50b2fbb` | `feat(03-02): mission export (GPX/GeoJSON/PDF) with D-09 currents table` |
| 3 | `4ca0b46` | `feat(03-02): add CLI to backend.mission.export (python -m invocation)` |

## Downstream Unblocks

- **Plan 03-05 (E2E test):** can now call `export_gpx/geojson/pdf` inside the < 15 s latency budget. Reusable fixtures at `tests/fixtures/synthetic_mission.py` are available for the E2E harness.
- **Demo script:** judges can live-invoke `python -m backend.mission.export --mission m.json --forecast f.json --format pdf --out brief.pdf` on a prebaked mission.
- **MISSION-03 requirement:** closed.

## Known Stubs

None. All functions are fully wired. The only deliberate omission is the wind columns in the D-09 currents table — this is documented in the PDF caption and in decisions above, because `ForecastFrame` schema carries no u10/v10 field. This is not a stub; it is a schema-honest choice that is locked until a future phase extends `ForecastFrame`.

## Self-Check: PASSED

- `backend/mission/export.py` — FOUND
- `tests/__init__.py` — FOUND
- `tests/fixtures/__init__.py` — FOUND
- `tests/fixtures/synthetic_mission.py` — FOUND
- `tests/test_export.py` — FOUND
- Commit `22e15ce` — FOUND
- Commit `50b2fbb` — FOUND
- Commit `4ca0b46` — FOUND
- `backend/mission/__main__.py` — NOT modified (verified via empty git diff)
