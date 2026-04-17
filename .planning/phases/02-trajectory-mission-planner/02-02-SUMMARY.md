---
phase: 02-trajectory-mission-planner
plan: 02
subsystem: mission
tags: [mission, scoring, priority, tsp-precursor]
dependency-graph:
  requires:
    - backend.core.schemas.ForecastEnvelope  # FROZEN
    - backend.core.schemas.DetectionFeature   # FROZEN
    - backend.core.config.Settings            # cfg.mission.weight_*
  provides:
    - backend.mission.scoring.priority_score
    - backend.mission.scoring.score_all
    - backend.mission.scoring.haversine_km
    - backend.mission.scoring.detection_centroid
    - backend.mission.scoring.density_at
    - backend.mission.scoring.convergence_ratio
    - backend.mission.scoring.normalized_accessibility
  affects:
    - 02-04 mission-planner (consumes score_all for greedy + 2-opt ranking)
tech-stack:
  added: []
  patterns:
    - "Pure shapely + math: no torch/rasterio/xarray deps in scoring module"
    - "Never-raise contract: edge cases return neutral (1.0) or zero, never NaN"
    - "Preserve input order: score_all does not sort; planner handles selection"
key-files:
  created:
    - backend/mission/scoring.py
    - backend/tests/unit/test_scoring.py
  modified: []
decisions:
  - "D-12 formula implemented exactly: priority = conf_adj * area_m2 * fraction_plastic * (w_d*density72 + w_a*access + w_c*convergence)"
  - "Density lookup uses shapely `covers` (closed polygon membership), not `contains`, so centroids on boundary still count"
  - "Accessibility is linear 1->0 over [0, max_distance_km] rather than inverse-distance; bounded and interpretable"
  - "Convergence fallback hierarchy: no +72h => 1.0; no +0h => reference treated as 1.0; d0<=0 => 1.0"
  - "score_all preserves source_detections order; planner (Plan 04) handles sort + selection"
metrics:
  duration: "2min"
  tasks: 1
  files: 2
  tests: 8
  completed: "2026-04-17"
requirements: [MISSION-01]
---

# Phase 02 Plan 02: Mission Scoring Summary

**One-liner:** D-12 priority scoring primitives (haversine, density lookup, accessibility, convergence) delivered as pure shapely+math functions with 8 passing unit tests; Plan 04's TSP planner can now call a single `score_all(envelope, origin, cfg, vessel_range_km)` to rank detections.

## What Shipped

- **`backend/mission/scoring.py`** (231 lines) — seven public functions implementing the full D-12 priority chain. Zero torch/rasterio/xarray imports; transitively safe to use from any layer.
- **`backend/tests/unit/test_scoring.py`** (206 lines) — 8 pytest tests covering zero detections, single-detection base-term dominance, accessibility monotonicity, exact convergence ratio, missing-+72h fallback, haversine sanity (zero + 1 deg lat ~= 111.19 km), density_at inside/outside, and normalized_accessibility bounds.

## Public Surface

```python
from backend.mission.scoring import (
    haversine_km,                # (lon,lat)x2 -> km
    detection_centroid,          # DetectionFeature -> (lon,lat)
    density_at,                  # point + frame_polygons -> float
    convergence_ratio,           # point + envelope -> float (>=0)
    normalized_accessibility,    # dist_km + max_km -> [0,1]
    priority_score,              # det + origin + env + cfg + max_km -> float
    score_all,                   # env + origin + cfg + vessel_km -> [(det, score)]
)
```

## Verification

```
python -m pytest backend/tests/unit/test_scoring.py -x -q
........                                                                 [100%]
8 passed in 0.48s

python -c "from backend.mission.scoring import priority_score, score_all, haversine_km, convergence_ratio, density_at, detection_centroid, normalized_accessibility; print('OK')"
OK
```

All acceptance-criteria greps pass (`def priority_score`, `def haversine_km`, `def convergence_ratio`, `def score_all`, `cfg.mission.weight_density`).

## Deviations from Plan

None — plan executed exactly as written. Two defensive additions beyond the spec:

1. **`haversine_km` guards against `math.sqrt` of tiny-negative floats** from rounding when the two points are identical. Spec requires `haversine_km(origin, origin) == 0.0`; the guard makes this bulletproof.
2. **`priority_score` clamps NaN/negative leaks to 0.0** as a last line of defense. By construction all inputs are `>= 0`, but a malformed `Settings` override (e.g. `MISSION__WEIGHT_DENSITY=-1`) shouldn't crash the planner.

Both are consistent with the plan's "never NaN, never raise" contract and required no new tests.

## Interaction with Frozen Schemas

Did NOT modify `backend/core/schemas.py`. The module consumes:

- `DetectionFeature.geometry` via `shape(geom.model_dump())` (shapely round-trip).
- `DetectionFeature.properties.{conf_adj, area_m2, fraction_plastic}` via attribute access.
- `ForecastEnvelope.frames` via `{f.hour: f for f in ...}` lookup, reading `f.density_polygons.features[i].properties["density"]`.

`ForecastFrame.density_polygons` is typed as `FeatureCollection[Feature[Polygon, dict]]`, so `properties` is an unstructured dict; the `density` key is a convention the scoring module reads leniently (missing => 1.0).

## Downstream Integration (Plan 04 preview)

Plan 04's planner will:

1. Call `score_all(envelope, origin, cfg, vessel_range_km)` -> `[(det, score), ...]`.
2. Sort descending by score, optionally truncate to `cfg.mission.top_k`.
3. Run greedy nearest-neighbor TSP respecting `vessel_range_km` + `hours * cfg.mission.avg_speed_kmh`.
4. Apply 2-opt improvement loop.
5. Build `MissionPlan(waypoints=..., route=LineString([origin, ...wps..., origin]), ...)`.

The scoring primitives above are the only things the planner needs from scoring; no tracker coupling.

## Known Stubs

None. No placeholder values, no empty-array paths that render in UI (this is a pure-math backend module).

## Commits

| Task | Phase | Commit    | Files                                            |
| ---- | ----- | --------- | ------------------------------------------------ |
| 1 RED   | test  | `99e64db` | `backend/tests/unit/test_scoring.py`             |
| 1 GREEN | feat  | `a5e83f4` | `backend/mission/scoring.py`                     |

## Self-Check: PASSED

- FOUND: `backend/mission/scoring.py` (231 lines, >= 120 min)
- FOUND: `backend/tests/unit/test_scoring.py` (206 lines, >= 100 min)
- FOUND: commit `99e64db` (test RED)
- FOUND: commit `a5e83f4` (feat GREEN)
- VERIFIED: `python -m pytest backend/tests/unit/test_scoring.py -x -q` -> 8 passed
- VERIFIED: import smoke test clean
- VERIFIED: `backend/core/schemas.py` untouched (FROZEN respected)
