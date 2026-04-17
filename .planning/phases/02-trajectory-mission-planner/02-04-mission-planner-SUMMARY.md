---
plan: 02-04-mission-planner
phase: 02-trajectory-mission-planner
status: complete
completed: 2026-04-17
requirements_addressed: [MISSION-02]
---

# Plan 02-04: mission-planner — SUMMARY

## One-liner

Shipped `backend/mission/planner.py::plan_mission` as a real priority-ranked greedy + 2-opt TSP planner with dual-budget enforcement (vessel_range_km AND hours), never-raise contract on degenerate inputs, and always-closed route — all 5 MISSION-02 edge cases (PITFALL M10) plus the 15-detection happy path are green.

## What shipped

- `backend/mission/tsp.py` — pure TSP primitives (from Task 1): `greedy_nearest_neighbor`, `two_opt` (with N² iteration cap), `tour_distance_km`.
- `backend/mission/planner.py` — replaces Phase 1 stub:
  - `_degenerate_plan(origin)` — schema-valid empty plan at origin (D-09 never-raise).
  - `_build_plan_from_order(...)` — assembles closed route (D-10) + waypoints with `arrival_hour = cumulative_km / avg_speed_kmh` (D-13).
  - `_truncate_to_budget(origin, points, order, vessel_range_km, hours, avg_speed_kmh)` — prefix truncation honoring `min(vessel_range_km, hours * avg_speed_kmh)`.
  - `plan_mission(forecast, vessel_range_km=200, hours=8, origin=(72.8, 18.9), cfg=None)` — scoring → top_k filter → greedy NN → 2-opt → budget truncation → assemble plan.
- `backend/tests/unit/test_planner.py` — 5/5 edge cases green.
- `backend/tests/integration/test_planner_synth.py` — 15-detection happy path green.

## Tests

```
backend/tests/unit/test_tsp.py::*                                 (5/5 green — Task 1)
backend/tests/unit/test_planner.py::test_E1_zero_detections       ← D-09
backend/tests/unit/test_planner.py::test_E2_single_detection      ← closed 3-point route
backend/tests/unit/test_planner.py::test_E3_all_out_of_range      ← budget truncation
backend/tests/unit/test_planner.py::test_E4_budget_exhausted_mid_tour ← dual budget
backend/tests/unit/test_planner.py::test_E5_singleton_top_k       ← top_k filter
backend/tests/integration/test_planner_synth.py::test_I1_fifteen_detection_happy_path
```

## Key decisions honored

- **D-09** never raise on 0 detections / all-out-of-range / top_k==0 / budget-exhausted-mid-tour.
- **D-10** route always closed: `origin → waypoints → origin` LineString.
- **D-11** greedy nearest-neighbor followed by 2-opt (with N² iteration cap) — both ship.
- **D-12** priority from `scoring.score_all(envelope, origin, cfg, vessel_range_km)`; non-positive scores dropped.
- **D-13** `arrival_hour = cumulative_distance_km / cfg.mission.avg_speed_kmh` (default 20).

## Files

**Created:** `backend/mission/tsp.py`, `backend/tests/unit/test_tsp.py`, `backend/tests/unit/test_planner.py`, `backend/tests/integration/test_planner_synth.py`
**Modified:** `backend/mission/planner.py` (stub → real implementation)

## Commits

- `tsp.py + unit tests` (Task 1)
- `planner.py + unit + integration tests` (Task 2)

## Invariants preserved

- `backend/core/schemas.py` — untouched (FROZEN).
- Function signature `plan_mission(forecast, vessel_range_km=200, hours=8, origin=(72.8, 18.9), cfg=None)` — unchanged from Phase 1 stub.
