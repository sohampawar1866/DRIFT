---
plan: 02-03-tracker
phase: 02-trajectory-mission-planner
status: complete
completed: 2026-04-17
requirements_addressed: [PHYS-03, PHYS-04]
---

# Plan 02-03: tracker — SUMMARY

## One-liner

Shipped `backend/physics/tracker.py::forecast_drift` as a real Euler Lagrangian tracker (UTM-meter integration, windage α=0.02, beach-on-NaN freeze, per-detection 90% + global 75% KDE density polygons at hours {24,48,72}) — the PHYS-04 synthetic 43.2 km gate (Phase 2 exit criterion) passes.

## What shipped

- `backend/physics/kde.py` — `kde_contour_polygons(positions_utm, utm_epsg, level, grid_size, pad_m) -> list[Polygon in WGS84]` using `sklearn.neighbors.KernelDensity` (Gaussian, Scott's bandwidth) + `skimage.measure.find_contours`, reprojected via `pyproj.Transformer(always_xy=True)`.
- `backend/physics/tracker.py` — replaces the Phase 1 stub with:
  - `_utm_zone_from_lonlat(lon, lat) -> EPSG (32600+zone)` using the `utm` library.
  - `_seed_particles_utm(centroid, n, rng)` — ±50 m Gaussian jitter in UTM meters (D-08).
  - `_step_particle(p_utm, alive, t, env, alpha, to_wgs, dt_s)` — Euler step with beach-on-NaN freeze (D-15).
  - `_build_frame(hour, state, to_wgs_list)` — schema-valid ForecastFrame; density polygons only at `DENSITY_HOURS = (24, 48, 72)` (D-06).
  - `forecast_drift(detections, cfg, env=None)` — orchestrates horizon-length integration, returns 73-frame ForecastEnvelope.
- `backend/tests/unit/test_kde.py` — 3/3 green.
- `backend/tests/integration/test_tracker_synth.py` — 5/5 green.

## Tests

```
backend/tests/unit/test_kde.py::test_single_cluster_returns_polygon
backend/tests/unit/test_kde.py::test_two_clusters_two_polygons
backend/tests/unit/test_kde.py::test_fewer_than_three_particles_returns_empty

backend/tests/integration/test_tracker_synth.py::test_synthetic_43km                     ← PHYS-04 GATE
backend/tests/integration/test_tracker_synth.py::test_zero_field_stability              ← PHYS-04 GATE
backend/tests/integration/test_tracker_synth.py::test_beach_on_nan                      ← D-15
backend/tests/integration/test_tracker_synth.py::test_schema_roundtrip_and_density_hours ← D-06
backend/tests/integration/test_tracker_synth.py::test_windage_alpha                     ← D-18
```

All green. `test_synthetic_43km` is the **Phase 2 exit gate**: constant 0.5 m/s eastward current × 24 h → mean displacement 43.2 km ±1% across 50 particles.

## Key decisions honored

- **D-06** density polygons at {24,48,72} only; other frames carry empty FeatureCollection.
- **D-08** 20 particles × ±50 m Gaussian jitter in UTM meters.
- **D-14** UTM-meter integration via `pyproj.Transformer(always_xy=True)`; UTM zone from `utm.from_latlon`.
- **D-15** beach-on-NaN: NaN current → particle freezes, excluded from KDE.
- **D-18** windage α=0.02, `v_total = v_current + α * v_wind`.

## Files

**Created:** `backend/physics/kde.py`, `backend/tests/unit/test_kde.py`, `backend/tests/integration/test_tracker_synth.py`
**Modified:** `backend/physics/tracker.py` (stub → real implementation)
**Deps added:** `utm==0.8.1`

## Commits

- `kde.py + unit tests` (Task 1)
- `tracker.py + integration tests (PHYS-04 gate)` (Task 2)

## Invariants preserved

- `backend/core/schemas.py` — untouched (FROZEN).
- `backend/api/routes.py`, `backend/services/mock_data.py` — untouched (out of scope).
- Function signature `forecast_drift(detections, cfg, env=None)` — backwards-compatible with Phase 1 stub (added optional `env`).
