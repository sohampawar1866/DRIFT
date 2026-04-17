---
phase: 02-trajectory-mission-planner
plan: 04
type: execute
wave: 2
depends_on: [02-02]
files_modified:
  - backend/mission/planner.py
  - backend/mission/tsp.py
  - backend/tests/unit/test_planner.py
  - backend/tests/integration/test_planner_synth.py
autonomous: true
requirements: [MISSION-02]
must_haves:
  truths:
    - "plan_mission never raises on degenerate inputs (D-09) — 0 detections, 1 detection, all-out-of-range, budget-exhausted, singleton"
    - "Greedy nearest-neighbor construction + 2-opt improvement (D-11)"
    - "Route is always closed: origin -> waypoints -> origin (D-10)"
    - "waypoints[0].order == 0; strict integer ordering 0..N-1"
    - "total_distance_km <= vessel_range_km AND total_hours <= hours (both budgets honored)"
    - "Budget-exhausted mid-tour returns visited prefix with partial route back to origin (D-09)"
    - "Per-waypoint arrival_hour = cumulative_distance_km / cfg.mission.avg_speed_kmh (D-13)"
    - "Returns schema-valid MissionPlan in all cases"
  artifacts:
    - path: backend/mission/tsp.py
      provides: "greedy_nearest_neighbor, two_opt, tour_distance_km"
      min_lines: 100
    - path: backend/mission/planner.py
      provides: "plan_mission with full budget enforcement + partial-prefix recovery"
      min_lines: 150
    - path: backend/tests/unit/test_planner.py
      provides: "5 edge case tests (MISSION-02 gate)"
      min_lines: 120
    - path: backend/tests/integration/test_planner_synth.py
      provides: "15-detection synthetic ForecastEnvelope full happy-path test"
      min_lines: 60
  key_links:
    - from: backend/mission/planner.py
      to: backend/mission/scoring.py
      via: "score_all(envelope, origin, cfg, vessel_range_km)"
      pattern: "score_all|priority_score"
    - from: backend/mission/planner.py
      to: backend/mission/tsp.py
      via: "greedy_nearest_neighbor + two_opt"
      pattern: "greedy_nearest_neighbor|two_opt"
    - from: backend/mission/planner.py
      to: backend/core/config.py
      via: "cfg.mission.avg_speed_kmh and cfg.mission.top_k"
      pattern: "avg_speed_kmh|top_k"
---

<objective>
Replace the Phase 1 `plan_mission` stub with a real priority-ranked greedy+2-opt TSP planner that honors vessel range AND time budget, never raises on degenerate inputs, and returns closed-route MissionPlans at all times.

Purpose: Ship MISSION-02, the second half of Phase 2's deliverables. All 5 edge cases (PITFALL M10) have dedicated unit tests; happy-path integration test uses synthetic 15-detection forecast.
Output: backend/mission/planner.py + backend/mission/tsp.py + unit + integration tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-trajectory-mission-planner/02-CONTEXT.md
@.planning/phases/02-trajectory-mission-planner/02-02-mission-scoring-PLAN.md
@backend/core/schemas.py
@backend/core/config.py
@backend/mission/planner.py
@backend/mission/scoring.py

<interfaces>
From backend/core/schemas.py (FROZEN):
```python
class MissionWaypoint(BaseModel):
    order: int                      # >= 0
    lon: float
    lat: float
    arrival_hour: float              # >= 0
    priority_score: float            # >= 0

class MissionPlan(BaseModel):
    waypoints: list[MissionWaypoint]
    route: Feature[LineString, dict]
    total_distance_km: float
    total_hours: float
    origin: tuple[float, float]
```

From backend/mission/scoring.py (Plan 02 output):
```python
def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float: ...
def detection_centroid(det: DetectionFeature) -> tuple[float, float]: ...
def score_all(envelope, origin, cfg, vessel_range_km) -> list[tuple[DetectionFeature, float]]: ...
```

Existing stub signature (planner.py) — preserve:
```python
def plan_mission(
    forecast: ForecastEnvelope,
    vessel_range_km: float = 200.0,
    hours: float = 8.0,
    origin: tuple[float, float] = (72.8, 18.9),
    cfg: Settings | None = None,
) -> MissionPlan: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TSP primitives (backend/mission/tsp.py) + unit tests</name>
  <files>backend/mission/tsp.py, backend/tests/unit/test_tsp.py</files>
  <read_first>
    - backend/mission/scoring.py (haversine_km)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-11 2-opt until convergence or N² cap)
  </read_first>
  <behavior>
    - Test 1: greedy_nearest_neighbor on 4 collinear points east of origin returns indices [0, 1, 2, 3] (monotonic east).
    - Test 2: two_opt on a known suboptimal tour (crossing segments) reduces total distance.
    - Test 3: tour_distance_km on closed tour (origin, A, B, origin) = haversine(O,A) + haversine(A,B) + haversine(B,O) ±0.01 km.
    - Test 4: two_opt on optimal tour returns same order (no improving swap).
    - Test 5: two_opt respects iteration cap — feed 50-point random tour, assert it returns within O(N²) iterations (bounded via a counter).
  </behavior>
  <action>
    Create **backend/mission/tsp.py**:

    ```python
    """TSP primitives: greedy nearest-neighbor + 2-opt improvement.

    All distances are great-circle (haversine) in km. 'Points' are (lon, lat)
    tuples. Tours are represented as ordered lists of point indices into a
    candidates array; the origin is prepended/appended at the route-building
    layer, NOT here.
    """
    from __future__ import annotations
    from typing import Sequence

    from backend.mission.scoring import haversine_km


    def tour_distance_km(
        origin: tuple[float, float],
        points: Sequence[tuple[float, float]],
        order: Sequence[int],
    ) -> float:
        """Closed tour: origin -> points[order[0]] -> ... -> points[order[-1]] -> origin."""
        if not order:
            return 0.0
        total = haversine_km(origin, points[order[0]])
        for i in range(len(order) - 1):
            total += haversine_km(points[order[i]], points[order[i+1]])
        total += haversine_km(points[order[-1]], origin)
        return total


    def greedy_nearest_neighbor(
        origin: tuple[float, float],
        points: Sequence[tuple[float, float]],
    ) -> list[int]:
        """Start at origin, always move to the nearest unvisited point."""
        if not points:
            return []
        remaining = set(range(len(points)))
        current = origin
        order: list[int] = []
        while remaining:
            nxt = min(remaining, key=lambda i: haversine_km(current, points[i]))
            order.append(nxt)
            remaining.remove(nxt)
            current = points[nxt]
        return order


    def two_opt(
        origin: tuple[float, float],
        points: Sequence[tuple[float, float]],
        order: list[int],
        max_iters: int | None = None,
    ) -> list[int]:
        """2-opt improvement: reverse sub-tours when distance drops.

        Runs until no improving swap is found OR max_iters (default N**2).
        """
        n = len(order)
        if n < 4:
            return list(order)
        cap = max_iters if max_iters is not None else n * n
        order = list(order)
        best_d = tour_distance_km(origin, points, order)
        improved = True
        iters = 0
        while improved and iters < cap:
            improved = False
            for i in range(n - 1):
                for j in range(i + 1, n):
                    if j - i == 1:
                        continue
                    new_order = order[:i] + order[i:j+1][::-1] + order[j+1:]
                    new_d = tour_distance_km(origin, points, new_order)
                    if new_d + 1e-9 < best_d:
                        order = new_order
                        best_d = new_d
                        improved = True
                    iters += 1
                    if iters >= cap:
                        break
                if iters >= cap:
                    break
        return order
    ```

    Create **backend/tests/unit/test_tsp.py** implementing Tests 1-5. For Test 2, use 4 points forming a bow-tie pattern where greedy can produce crossing segments; assert 2-opt improves. For Test 5, use `random.Random(0)` to seed deterministic points.
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/unit/test_tsp.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest backend/tests/unit/test_tsp.py -x -q` — all 5 tests pass
    - `grep -q "def greedy_nearest_neighbor" backend/mission/tsp.py` exits 0
    - `grep -q "def two_opt" backend/mission/tsp.py` exits 0
    - `grep -q "def tour_distance_km" backend/mission/tsp.py` exits 0
    - `grep -q "max_iters" backend/mission/tsp.py` exits 0 (D-11 iteration cap)
  </acceptance_criteria>
  <done>TSP module exports greedy_nearest_neighbor, two_opt (with iteration cap), tour_distance_km. 2-opt provably improves suboptimal tours and respects iteration bound.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: plan_mission with budget enforcement + 5 edge case tests + integration test</name>
  <files>backend/mission/planner.py, backend/tests/unit/test_planner.py, backend/tests/integration/test_planner_synth.py</files>
  <read_first>
    - backend/mission/planner.py (stub)
    - backend/mission/scoring.py
    - backend/mission/tsp.py (Task 1 output)
    - backend/core/schemas.py
    - backend/core/config.py (confirm avg_speed_kmh is present — Plan 01)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-09, D-10, D-11, D-12, D-13)
  </read_first>
  <behavior>
    5 edge cases (PITFALL M10, MISSION-02 gate):
    - **Test E1 (0 detections)**: empty source_detections → `plan.waypoints == []`; `plan.route.geometry.coordinates == [[lon0, lat0], [lon0, lat0]]`; `total_distance_km == 0.0`; `total_hours == 0.0`.
    - **Test E2 (1 detection)**: 1 detection at (72.9, 18.9), origin (72.8, 18.9); `len(plan.waypoints) == 1`; route coordinates has 3 points (origin, wp, origin); `waypoints[0].order == 0`; `total_distance_km > 0`; `total_hours = total_distance_km / avg_speed_kmh`.
    - **Test E3 (all out of range)**: vessel_range_km=10, 5 detections all >50 km from origin → `plan.waypoints == []`; shape matches E1.
    - **Test E4 (budget exhausted mid-tour)**: 10 detections spaced 30 km apart, vessel_range_km=120, hours=4 (avg_speed_kmh=20 → 80 km budget from time). After 2-3 waypoints the tour hits min(distance budget, time budget); remaining waypoints dropped; route returns to origin from last visited waypoint. Assert `total_distance_km <= 120 AND total_distance_km/20 <= 4` (both budgets).
    - **Test E5 (singleton top_k)**: `cfg.mission.top_k = 1`, 10 detections → at most 1 waypoint in plan (top-K filtering applied before TSP construction).

    Integration test:
    - **Test I1 (15-detection happy path)**: synthetic ForecastEnvelope with 15 detection polygons around Mumbai, origin (72.8, 18.9), vessel_range_km=200, hours=8. Assert: `len(plan.waypoints) >= 3`; `total_distance_km <= 200`; `total_hours <= 8`; `plan.waypoints[0].order == 0` and ordering is strict monotonic; `plan.route.geometry.type == "LineString"`; first and last coordinates in route == origin.
  </behavior>
  <action>
    Rewrite **backend/mission/planner.py** with this structure:

    ```python
    """plan_mission: priority-scored greedy + 2-opt TSP with budget enforcement.

    Contract (D-09, never raise):
      * 0 detections / all-out-of-range / top_k==0 => empty waypoints, degenerate
        LineString at origin, zero distance, zero hours.
      * Budget exhausted mid-tour => return visited prefix; partial route returns
        from last reachable waypoint to origin.
      * Route is always closed (origin -> waypoints -> origin, D-10).
    """
    from __future__ import annotations

    from backend.core.config import Settings
    from backend.core.schemas import (
        ForecastEnvelope,
        MissionPlan,
        MissionWaypoint,
    )
    from backend.mission.scoring import (
        detection_centroid,
        haversine_km,
        score_all,
    )
    from backend.mission.tsp import (
        greedy_nearest_neighbor,
        tour_distance_km,
        two_opt,
    )


    def _degenerate_plan(origin: tuple[float, float]) -> MissionPlan:
        lon, lat = origin
        return MissionPlan(
            waypoints=[],
            route={
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat], [lon, lat]],
                },
                "properties": {},
            },
            total_distance_km=0.0,
            total_hours=0.0,
            origin=(lon, lat),
        )


    def _build_plan_from_order(
        origin: tuple[float, float],
        detections_and_scores: list[tuple[tuple[float, float], float]],  # [(centroid, score), ...]
        order: list[int],
        avg_speed_kmh: float,
    ) -> MissionPlan:
        waypoints: list[MissionWaypoint] = []
        coords: list[list[float]] = [[origin[0], origin[1]]]
        cumulative_km = 0.0
        prev = origin
        for k, idx in enumerate(order):
            centroid, score = detections_and_scores[idx]
            leg = haversine_km(prev, centroid)
            cumulative_km += leg
            waypoints.append(MissionWaypoint(
                order=k,
                lon=centroid[0],
                lat=centroid[1],
                arrival_hour=cumulative_km / avg_speed_kmh,
                priority_score=score,
            ))
            coords.append([centroid[0], centroid[1]])
            prev = centroid
        # Return-to-origin leg
        if order:
            cumulative_km += haversine_km(prev, origin)
            coords.append([origin[0], origin[1]])
        else:
            coords.append([origin[0], origin[1]])

        total_hours = cumulative_km / avg_speed_kmh
        return MissionPlan(
            waypoints=waypoints,
            route={
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {},
            },
            total_distance_km=float(cumulative_km),
            total_hours=float(total_hours),
            origin=origin,
        )


    def _truncate_to_budget(
        origin: tuple[float, float],
        points: list[tuple[float, float]],
        order: list[int],
        vessel_range_km: float,
        hours: float,
        avg_speed_kmh: float,
    ) -> list[int]:
        """Walk the tour; stop when adding next waypoint + return-home would
        exceed either budget. Returns the visited prefix (possibly empty).
        """
        if not order:
            return []
        budget_km_time = hours * avg_speed_kmh
        budget_km = min(vessel_range_km, budget_km_time)
        kept: list[int] = []
        prev = origin
        cumulative = 0.0
        for idx in order:
            leg = haversine_km(prev, points[idx])
            return_leg = haversine_km(points[idx], origin)
            if cumulative + leg + return_leg > budget_km:
                break
            kept.append(idx)
            cumulative += leg
            prev = points[idx]
        return kept


    def plan_mission(
        forecast: ForecastEnvelope,
        vessel_range_km: float = 200.0,
        hours: float = 8.0,
        origin: tuple[float, float] = (72.8, 18.9),
        cfg: Settings | None = None,
    ) -> MissionPlan:
        cfg = cfg or Settings()
        avg_speed = cfg.mission.avg_speed_kmh

        # D-09: never raise on empty / degenerate inputs.
        if not forecast.source_detections.features:
            return _degenerate_plan(origin)

        # Score all detections per D-12 (via scoring.score_all).
        scored = score_all(forecast, origin, cfg, vessel_range_km)
        # Drop non-positive scores (e.g., fraction_plastic==0)
        scored = [(det, s) for det, s in scored if s > 0.0]
        if not scored:
            return _degenerate_plan(origin)

        # Top-K filter (D-12 knob retained from config).
        scored.sort(key=lambda t: t[1], reverse=True)
        top_k = cfg.mission.top_k
        if top_k is not None and top_k >= 0:
            scored = scored[:top_k]
        if not scored:
            return _degenerate_plan(origin)

        # Build centroid list paired with scores.
        candidates = [(detection_centroid(det), s) for det, s in scored]
        points = [c for c, _ in candidates]

        # Greedy + 2-opt (D-11).
        order = greedy_nearest_neighbor(origin, points)
        order = two_opt(origin, points, order)

        # Enforce budgets: drop tail that exceeds vessel_range_km OR time budget.
        order = _truncate_to_budget(origin, points, order,
                                    vessel_range_km, hours, avg_speed)
        if not order:
            return _degenerate_plan(origin)

        return _build_plan_from_order(origin, candidates, order, avg_speed)
    ```

    Create **backend/tests/unit/test_planner.py** implementing Tests E1-E5. Build minimal `ForecastEnvelope` per test with synthetic `DetectionFeatureCollection` (use tiny square polygons around target lon/lat, Polygon coords as `[[[lon-0.001, lat-0.001], [lon+0.001, lat-0.001], [lon+0.001, lat+0.001], [lon-0.001, lat+0.001], [lon-0.001, lat-0.001]]]`). DetectionProperties with fraction_plastic=0.3, conf_adj=0.8, area_m2=400.0. For E3, place detections 0.5° east (≈55 km) with vessel_range_km=10. Zero-frames envelope (frames=[]) is fine for unit tests since scoring falls back gracefully.

    Create **backend/tests/integration/test_planner_synth.py** implementing Test I1 — 15 detections on a 5×3 grid spanning 0.3°×0.2° around (72.8, 18.9), synthetic ForecastEnvelope with an empty frames list (planner does not require frames, scoring falls back).
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/unit/test_planner.py backend/tests/unit/test_tsp.py backend/tests/integration/test_planner_synth.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest backend/tests/unit/test_planner.py -x -q` — all 5 edge case tests pass
    - `python -m pytest backend/tests/integration/test_planner_synth.py -x -q` — happy path passes
    - `grep -q "greedy_nearest_neighbor" backend/mission/planner.py` exits 0
    - `grep -q "two_opt" backend/mission/planner.py` exits 0
    - `grep -q "_truncate_to_budget" backend/mission/planner.py` exits 0 (D-09 budget enforcement)
    - `grep -q "_degenerate_plan" backend/mission/planner.py` exits 0 (D-09 never-raise)
    - `grep -q "avg_speed_kmh" backend/mission/planner.py` exits 0 (D-13)
    - `grep -q "top_k" backend/mission/planner.py` exits 0
    - Module import clean: `python -c "from backend.mission.planner import plan_mission; from backend.core.schemas import ForecastEnvelope, DetectionFeatureCollection; fc=DetectionFeatureCollection(type='FeatureCollection', features=[]); fe=ForecastEnvelope(source_detections=fc, frames=[], windage_alpha=0.02); plan=plan_mission(fe); assert plan.waypoints==[]; print('OK')"` exits 0
  </acceptance_criteria>
  <done>plan_mission ships with greedy+2-opt, 5 edge cases green, 15-detection happy path green, both budgets (distance + time) enforced, partial-prefix recovery works, routes always closed.</done>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests/unit/test_tsp.py backend/tests/unit/test_planner.py backend/tests/integration/test_planner_synth.py -q` — all green
- Grep confirms D-09 never-raise + D-11 greedy+2-opt + D-13 avg_speed_kmh wired
- All 5 MISSION-02 edge cases have dedicated unit tests
</verification>

<success_criteria>
- MISSION-02 shipped: plan_mission replaces Phase 1 stub with real priority-scored TSP
- PITFALL M10 (5 TSP edge cases) all covered by tests
- D-10 (closed route) + D-11 (2-opt) + D-13 (avg_speed_kmh) provable via grep + tests
</success_criteria>

<output>
After completion, create `.planning/phases/02-trajectory-mission-planner/02-04-SUMMARY.md`.
</output>
