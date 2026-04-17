---
phase: 02-trajectory-mission-planner
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/mission/scoring.py
  - backend/tests/unit/test_scoring.py
autonomous: true
requirements: [MISSION-01]
must_haves:
  truths:
    - "priority_score(detection, origin, forecast) returns a finite non-negative float for every valid detection"
    - "Score includes conf_adj, area_m2, fraction_plastic multiplicative base terms (REQ MISSION-01)"
    - "Score includes weighted_sum(density, accessibility, convergence) per D-12 with weights from config"
    - "Zero-density / zero-distance / missing-KDE edge cases return defined finite values, never NaN"
    - "Convergence term = +72h density / +0h density at detection centroid (D-12)"
  artifacts:
    - path: backend/mission/scoring.py
      provides: "priority_score, compute_density_at, normalize_accessibility, convergence_ratio"
      min_lines: 120
    - path: backend/tests/unit/test_scoring.py
      provides: "Unit tests for scoring building blocks + end-to-end priority"
      min_lines: 100
  key_links:
    - from: backend/mission/scoring.py
      to: backend/core/schemas.py
      via: "ForecastEnvelope + DetectionFeature imports"
      pattern: "from backend.core.schemas import"
    - from: backend/mission/scoring.py
      to: backend/core/config.py
      via: "cfg.mission.weight_density/weight_accessibility/weight_convergence"
      pattern: "cfg\\.mission\\.weight_"
---

<objective>
Build the priority-scoring primitives that Plan 04 (planner) consumes to rank detections. MISSION-01 is self-contained (no tracker dependency) because it reads the ForecastEnvelope's density_polygons rather than recomputing KDE.

Purpose: Isolate scoring math so TSP planner logic (Plan 04) stays focused on tour construction. Pure-function, fully testable in isolation against synthetic ForecastEnvelope fixtures.
Output: backend/mission/scoring.py + unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-trajectory-mission-planner/02-CONTEXT.md
@backend/core/schemas.py
@backend/core/config.py

<interfaces>
From backend/core/schemas.py (FROZEN):
```python
class DetectionProperties(BaseModel):
    conf_raw: float
    conf_adj: float
    fraction_plastic: float
    area_m2: float
    age_days_est: int
    cls: Literal["plastic"]

DetectionFeature = Feature[Polygon, DetectionProperties]
DetectionFeatureCollection = FeatureCollection[DetectionFeature]

class ForecastFrame(BaseModel):
    hour: int
    particle_positions: list[tuple[float, float]]
    density_polygons: FeatureCollection[Feature[Polygon, dict]]

class ForecastEnvelope(BaseModel):
    source_detections: DetectionFeatureCollection
    frames: list[ForecastFrame]
    windage_alpha: float
```
Only frames with hour in {24, 48, 72} carry populated density_polygons (D-06). Frame at hour=0 is treated as "initial density" — if no hour=0 frame exists, use the detection polygon itself as the unit-density reference.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: backend/mission/scoring.py + unit tests</name>
  <files>backend/mission/scoring.py, backend/tests/unit/test_scoring.py</files>
  <read_first>
    - backend/core/schemas.py
    - backend/core/config.py
    - backend/mission/planner.py (existing stub — understand downstream consumer)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-10, D-12)
  </read_first>
  <behavior>
    - Test 1: Zero detections — priority_score never called; helper `score_all(envelope, origin, cfg)` returns empty list.
    - Test 2: Single detection with conf_adj=0.8, area_m2=500, fraction_plastic=0.3 at (72.8, 18.9), origin (72.8, 18.9); with empty density_polygons the score must still be finite and > 0 (base multiplicative term 0.8*500*0.3 = 120 dominates).
    - Test 3: Accessibility monotonicity — two identical detections at different distances from origin, closer detection scores higher when weight_accessibility > 0.
    - Test 4: Convergence term — synthetic forecast with hour-72 density_polygon covering detection centroid at value 2.0 and hour-0 reference at 1.0 yields `convergence_ratio == 2.0` (debris concentrating).
    - Test 5: Missing hour-72 frame — convergence term falls back to 1.0 (no bonus, no penalty), score remains finite.
    - Test 6: haversine_km(origin, origin) == 0.0; haversine_km((0,0), (0,1)) ≈ 111.19 km (±0.1 km).
  </behavior>
  <action>
    Create **backend/mission/scoring.py** with this exact public surface:

    ```python
    """Priority scoring for mission waypoint ranking (REQ MISSION-01, D-12)."""
    from __future__ import annotations
    import math
    from typing import Iterable

    from shapely.geometry import Point, shape

    from backend.core.config import Settings
    from backend.core.schemas import DetectionFeature, ForecastEnvelope


    EARTH_RADIUS_KM = 6371.0088


    def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
        """Great-circle distance between (lon, lat) pairs in kilometers."""
        lon1, lat1 = math.radians(a[0]), math.radians(a[1])
        lon2, lat2 = math.radians(b[0]), math.radians(b[1])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


    def detection_centroid(det: DetectionFeature) -> tuple[float, float]:
        """Return (lon, lat) of polygon centroid in WGS84."""
        poly = shape(det.geometry.model_dump())
        c = poly.centroid
        return (c.x, c.y)


    def density_at(point: tuple[float, float], frame_polygons) -> float:
        """Sum of `density` property over polygons covering point.

        frame_polygons is a geojson FeatureCollection[Feature[Polygon, dict]].
        Each polygon feature may carry `properties.density` (float); missing =>
        treat as 1.0. Returns 0.0 if no polygon contains the point.
        """
        p = Point(point)
        total = 0.0
        for feat in frame_polygons.features:
            poly = shape(feat.geometry.model_dump())
            if poly.contains(p):
                total += float(feat.properties.get("density", 1.0))
        return total


    def convergence_ratio(
        point: tuple[float, float],
        envelope: ForecastEnvelope,
    ) -> float:
        """D-12: density(+72h) / density(+0h). Fallback 1.0 if either missing/zero."""
        hour_to_frame = {f.hour: f for f in envelope.frames}
        f72 = hour_to_frame.get(72)
        f0 = hour_to_frame.get(0)
        if f72 is None:
            return 1.0
        d72 = density_at(point, f72.density_polygons)
        d0 = density_at(point, f0.density_polygons) if f0 is not None else 1.0
        if d0 <= 0.0:
            return 1.0
        return d72 / d0


    def normalized_accessibility(
        distance_km: float,
        max_distance_km: float,
    ) -> float:
        """1.0 at origin, 0.0 at max_distance_km; linear. Clamped to [0, 1]."""
        if max_distance_km <= 0.0:
            return 1.0
        return max(0.0, 1.0 - min(distance_km, max_distance_km) / max_distance_km)


    def priority_score(
        det: DetectionFeature,
        origin: tuple[float, float],
        envelope: ForecastEnvelope,
        cfg: Settings,
        max_distance_km: float,
    ) -> float:
        """D-12 full formula:
            base = conf_adj * area_m2 * fraction_plastic
            weighted = w_d*density72 + w_a*access + w_c*convergence
            priority = base * weighted
        """
        centroid = detection_centroid(det)
        hour_to_frame = {f.hour: f for f in envelope.frames}
        f72 = hour_to_frame.get(72)
        density72 = density_at(centroid, f72.density_polygons) if f72 else 0.0
        access = normalized_accessibility(haversine_km(origin, centroid), max_distance_km)
        conv = convergence_ratio(centroid, envelope)

        w_d = cfg.mission.weight_density
        w_a = cfg.mission.weight_accessibility
        w_c = cfg.mission.weight_convergence
        weighted = w_d * density72 + w_a * access + w_c * conv

        props = det.properties
        base = props.conf_adj * props.area_m2 * props.fraction_plastic
        return float(base * weighted)


    def score_all(
        envelope: ForecastEnvelope,
        origin: tuple[float, float],
        cfg: Settings,
        vessel_range_km: float,
    ) -> list[tuple[DetectionFeature, float]]:
        """Return [(detection, score), ...] for every source detection.
        max_distance_km used for accessibility normalization = vessel_range_km.
        """
        return [
            (det, priority_score(det, origin, envelope, cfg, vessel_range_km))
            for det in envelope.source_detections.features
        ]
    ```

    Create **backend/tests/unit/test_scoring.py** implementing Tests 1-6. Helper: build minimal `ForecastEnvelope` with a tiny `DetectionFeatureCollection` (1-2 polygons near (72.8, 18.9)) and `ForecastFrame` objects for hour 0 and hour 72. Use `Feature(type="Feature", geometry=Polygon(...), properties={"density": 2.0})` for synthetic density polygons; properties dict is open-ended per schema.
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/unit/test_scoring.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest backend/tests/unit/test_scoring.py -x -q` — all 6 tests pass
    - `grep -q "def priority_score" backend/mission/scoring.py` exits 0
    - `grep -q "def haversine_km" backend/mission/scoring.py` exits 0
    - `grep -q "def convergence_ratio" backend/mission/scoring.py` exits 0
    - `grep -q "def score_all" backend/mission/scoring.py` exits 0
    - `grep -q "cfg.mission.weight_density" backend/mission/scoring.py` exits 0
    - `python -c "from backend.mission.scoring import priority_score, score_all, haversine_km, convergence_ratio; print('OK')"` exits 0
  </acceptance_criteria>
  <done>Scoring module exports haversine_km, detection_centroid, density_at, normalized_accessibility, convergence_ratio, priority_score, score_all. All 6 unit tests green. Zero dependency on tracker internals — consumes ForecastEnvelope via frozen schema only.</done>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests/unit/test_scoring.py -q` green
- `python -c "from backend.mission.scoring import score_all"` imports clean
</verification>

<success_criteria>
- priority_score is the single function Plan 04 calls for detection ranking
- D-12 formula implemented exactly: conf_adj * area_m2 * fraction_plastic * weighted_sum
- Edge cases (missing frames, zero density, zero distance) return finite values
</success_criteria>

<output>
After completion, create `.planning/phases/02-trajectory-mission-planner/02-02-SUMMARY.md`.
</output>
