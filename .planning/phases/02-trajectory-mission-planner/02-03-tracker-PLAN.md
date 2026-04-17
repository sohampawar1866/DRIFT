---
phase: 02-trajectory-mission-planner
plan: 03
type: execute
wave: 2
depends_on: [02-01]
files_modified:
  - backend/physics/tracker.py
  - backend/physics/kde.py
  - backend/tests/integration/test_tracker_synth.py
  - backend/tests/unit/test_kde.py
autonomous: true
requirements: [PHYS-03, PHYS-04]
must_haves:
  truths:
    - "forecast_drift(detections, cfg) returns a pydantic-valid ForecastEnvelope with exactly 73 frames (hour 0..72)"
    - "Integration is in UTM meters via pyproj Transformer(4326 -> 326XX, always_xy=True) (PITFALL C4 / D-14)"
    - "Synthetic constant 0.5 m/s eastward current over 24h moves a seed particle 43.2 km +/- 1% (PHYS-04 GATE)"
    - "Zero-field test: particle stays within 100 m over 72 h (PHYS-04 GATE)"
    - "Beach-on-NaN: particles hitting NaN freeze at last valid position and are excluded from KDE (D-15)"
    - "density_polygons populated only at hours {24, 48, 72}; other frames carry empty FeatureCollection (D-06)"
    - "20 particles per detection with ±50 m Gaussian jitter in UTM meters at seed (D-08)"
    - "windage applied as v_total = v_current + 0.02 * v_wind (D-18)"
  artifacts:
    - path: backend/physics/tracker.py
      provides: "forecast_drift + _utm_transformer + _step_particle + _build_frame"
      min_lines: 200
    - path: backend/physics/kde.py
      provides: "kde_contour_polygons(positions_utm, levels, bandwidth) -> list[Polygon in WGS84]"
      min_lines: 80
    - path: backend/tests/integration/test_tracker_synth.py
      provides: "43.2 km / 24h test + zero-field 72h test + beach-on-NaN test"
      min_lines: 120
    - path: backend/tests/unit/test_kde.py
      provides: "KDE polygon smoke tests (single cluster, two clusters)"
      min_lines: 50
  key_links:
    - from: backend/physics/tracker.py
      to: backend/physics/env_data.py
      via: "EnvStack.interp_currents / interp_winds"
      pattern: "interp_currents|interp_winds"
    - from: backend/physics/tracker.py
      to: pyproj.Transformer
      via: "EPSG:4326 <-> EPSG:326XX with always_xy=True"
      pattern: "always_xy=True"
    - from: backend/physics/tracker.py
      to: backend/physics/kde.py
      via: "kde_contour_polygons for frames {24, 48, 72}"
      pattern: "kde_contour_polygons"
---

<objective>
Replace the Phase 1 `forecast_drift` stub with a real Euler Lagrangian tracker that integrates in UTM meters, applies windage α=0.02, freezes particles on NaN, and emits per-detection 90% + global 75% KDE density polygons at hours {24, 48, 72}. This plan **gates Phase 2 exit** via the synthetic 43.2 km test (PHYS-04).

Purpose: Deliver the physics core that Plan 05 (E2E + real-data smoke) depends on. Works against synthetic xarray fixtures (from Plan 01's EnvStack.from_synthetic) so no real CMEMS/ERA5 files are needed here.
Output: backend/physics/tracker.py, backend/physics/kde.py, integration + unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-trajectory-mission-planner/02-CONTEXT.md
@.planning/phases/02-trajectory-mission-planner/02-01-env-data-config-PLAN.md
@backend/core/schemas.py
@backend/core/config.py
@backend/physics/env_data.py
@backend/physics/tracker.py
@backend/ml/inference.py

<interfaces>
From backend/physics/env_data.py (Plan 01 output):
```python
@dataclass(frozen=True)
class EnvStack:
    currents: xr.Dataset
    winds: xr.Dataset
    t0_hours: float
    def interp_currents(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]: ...
    def interp_winds(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]: ...

def from_synthetic(currents: xr.Dataset, winds: xr.Dataset) -> EnvStack: ...
def load_env_stack(cmems_path: Path, era5_path: Path, horizon_hours: int = 72) -> EnvStack: ...
```

From backend/core/schemas.py (FROZEN):
```python
class ForecastFrame(BaseModel):
    hour: int                                  # 0..72
    particle_positions: list[tuple[float, float]]  # (lon, lat) WGS84
    density_polygons: FeatureCollection[Feature[Polygon, dict]]

class ForecastEnvelope(BaseModel):
    source_detections: DetectionFeatureCollection
    frames: list[ForecastFrame]
    windage_alpha: float                       # 0..0.1
```

Existing stub signature (tracker.py) — preserve:
```python
def forecast_drift(
    detections: DetectionFeatureCollection,
    cfg: Settings,
    env: EnvStack | None = None,   # NEW optional arg; if None, load from cfg paths
) -> ForecastEnvelope: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: KDE helper (backend/physics/kde.py) + unit tests</name>
  <files>backend/physics/kde.py, backend/tests/unit/test_kde.py</files>
  <read_first>
    - backend/core/schemas.py (ForecastFrame density_polygons type)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-06, D-07)
  </read_first>
  <behavior>
    - Test 1: single tight cluster of 100 particles at UTM (500000, 2000000), zone 43N — returns >=1 polygon; polygon in WGS84 contains the original lon/lat of cluster centroid.
    - Test 2: two distinct clusters 50 km apart — 90% isodensity returns >=2 polygons (one per cluster).
    - Test 3: <3 particles returns empty list (KDE undefined).
  </behavior>
  <action>
    Create **backend/physics/kde.py**:

    ```python
    """2D KDE -> isodensity polygons in WGS84.

    Pattern (D-07):
      1. sklearn.neighbors.KernelDensity with Gaussian kernel, Scott's bandwidth
         in meters (bandwidth = n^(-1/6) * std) -- safe default for UTM-meter inputs.
      2. Evaluate log-density on a 128x128 grid spanning positions_utm.
      3. Threshold at the density value enclosing `level` fraction of total mass.
      4. skimage.measure.find_contours -> shapely Polygon -> .buffer(0).
      5. Reproject each polygon UTM -> WGS84 via pyproj.Transformer.
    """
    from __future__ import annotations
    import numpy as np
    from pyproj import Transformer
    from shapely.geometry import Polygon
    from sklearn.neighbors import KernelDensity
    from skimage import measure


    def _scotts_bandwidth(positions: np.ndarray) -> float:
        n = max(positions.shape[0], 2)
        std = max(float(positions.std()), 1.0)   # meters
        return std * n ** (-1.0 / 6.0)


    def kde_contour_polygons(
        positions_utm: np.ndarray,    # (N, 2) meters in zone `utm_epsg`
        utm_epsg: int,
        level: float = 0.90,           # fraction of mass enclosed
        grid_size: int = 128,
        pad_m: float = 5000.0,
    ) -> list[Polygon]:
        """Return list of WGS84 shapely Polygons enclosing `level` of the density.

        Empty list if fewer than 3 positions or contour extraction fails.
        """
        if positions_utm.shape[0] < 3:
            return []
        bw = _scotts_bandwidth(positions_utm)
        kde = KernelDensity(kernel="gaussian", bandwidth=bw).fit(positions_utm)

        xmin, ymin = positions_utm.min(axis=0) - pad_m
        xmax, ymax = positions_utm.max(axis=0) + pad_m
        xs = np.linspace(xmin, xmax, grid_size)
        ys = np.linspace(ymin, ymax, grid_size)
        gx, gy = np.meshgrid(xs, ys)
        grid = np.column_stack([gx.ravel(), gy.ravel()])
        log_d = kde.score_samples(grid).reshape(grid_size, grid_size)
        d = np.exp(log_d)

        # Threshold enclosing `level` of mass: sort densities descending, cumsum,
        # pick the density value where cumulative mass crosses `level`.
        flat = d.ravel()
        order = np.argsort(flat)[::-1]
        cum = np.cumsum(flat[order])
        if cum[-1] <= 0:
            return []
        cutoff_idx = int(np.searchsorted(cum, level * cum[-1]))
        cutoff_idx = min(cutoff_idx, len(flat) - 1)
        threshold = float(flat[order[cutoff_idx]])

        # Contours in grid coordinates -> meters -> WGS84
        contours = measure.find_contours(d, level=threshold)
        if not contours:
            return []
        to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
        out: list[Polygon] = []
        for c in contours:
            if len(c) < 4:
                continue
            # c is (row, col) in grid indices; map back to meter coords.
            rows, cols = c[:, 0], c[:, 1]
            xm = xmin + cols / (grid_size - 1) * (xmax - xmin)
            ym = ymin + rows / (grid_size - 1) * (ymax - ymin)
            lons, lats = to_wgs.transform(xm, ym)
            try:
                poly = Polygon(list(zip(lons, lats)))
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_valid and not poly.is_empty:
                    out.append(poly)
            except Exception:
                continue
        return out
    ```

    Create **backend/tests/unit/test_kde.py** implementing Tests 1-3. For Test 1 pick UTM zone 43N (EPSG 32643) which covers Mumbai/Arabian Sea.
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/unit/test_kde.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest backend/tests/unit/test_kde.py -x -q` — all 3 tests pass
    - `grep -q "def kde_contour_polygons" backend/physics/kde.py` exits 0
    - `grep -q "KernelDensity" backend/physics/kde.py` exits 0
    - `grep -q "always_xy=True" backend/physics/kde.py` exits 0
  </acceptance_criteria>
  <done>KDE module returns WGS84 polygons or empty list; handles <3 particles; two-cluster case yields >=2 polygons.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Real Euler Lagrangian tracker + synthetic 43.2 km gate test</name>
  <files>backend/physics/tracker.py, backend/tests/integration/test_tracker_synth.py, backend/tests/integration/__init__.py (if missing)</files>
  <read_first>
    - backend/physics/tracker.py (current stub)
    - backend/physics/env_data.py (Plan 01 output)
    - backend/physics/kde.py (Task 1 output)
    - backend/core/schemas.py (ForecastEnvelope / ForecastFrame)
    - backend/core/config.py (PhysicsSettings)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-08, D-14, D-15, D-18)
    - backend/ml/inference.py (pyproj.Transformer usage pattern)
  </read_first>
  <behavior>
    - **Test 1 (GATE — PHYS-04 part A)**: synthetic EnvStack with uo=0.5 m/s constant, vo=0, u10=v10=0 over a bbox containing (72.8, 18.9). Seed 1 detection at (72.8, 18.9) with 1 particle (particles_per_detection=1 override via env var), dt=3600s, horizon=24. Final (lon, lat) moved east by 43.2 km ±1% (converted back to lon delta, at lat=18.9 this is ≈0.411° of longitude). Assert `abs(displacement_km - 43.2) / 43.2 < 0.01`.
    - **Test 2 (GATE — PHYS-04 part B)**: zero-field synthetic EnvStack (all zeros). Seed 1 particle at (72.8, 18.9). After 72 h, final position is within 100 m of start. (Note: with windage applied to zero wind, drift = 0; jitter is sampled once at seed, so this tests integration stability not jitter variance.)
    - **Test 3 (beach-on-NaN)**: synthetic EnvStack where currents become NaN east of longitude 73.0 (simulating coast). Seed particle at (72.8, 18.9), uo=1.0 m/s east. Particle drifts east; upon first NaN interpolation, it must freeze at last valid position. Final position is finite (no NaN in any frame). The frozen-after-NaN particle must NOT appear in the global KDE (count the positions fed to KDE per frame; frozen particle is excluded).
    - **Test 4 (schema roundtrip)**: `forecast_drift` output passes `ForecastEnvelope.model_validate_json(envelope.model_dump_json())` round-trip; exactly 73 frames; frames at hours {24, 48, 72} have non-empty density_polygons; other frames have empty FeatureCollection.
    - **Test 5 (windage alpha)**: synthetic currents=0, winds u10=10 m/s east, 24h — displacement = 0.02 * 10 * 86400 = 17.28 km east ±1%.
  </behavior>
  <action>
    Rewrite **backend/physics/tracker.py** with this structure:

    ```python
    """Euler Lagrangian tracker (PHYS-03, D-14 UTM-meter integration).

    Per-detection: seed N particles at polygon centroid with ±50 m Gaussian
    jitter in UTM meters (D-08). Integrate hourly (dt=3600s) in UTM meters
    over horizon hours (default 72). Apply windage v_total = v_current +
    alpha * v_wind (D-18, alpha=0.02). Beach-on-NaN: freeze particles that
    hit NaN currents, exclude from KDE (D-15).

    Density polygons (D-06): at hours {24, 48, 72}, emit per-detection 90%
    KDE plus global 75% KDE. All other frames carry empty FeatureCollection.
    """
    from __future__ import annotations
    from pathlib import Path

    import numpy as np
    import utm as utm_lib
    from geojson_pydantic import Feature, FeatureCollection
    from pyproj import Transformer
    from shapely.geometry import Point, Polygon, mapping, shape

    from backend.core.config import Settings
    from backend.core.schemas import (
        DetectionFeatureCollection,
        ForecastEnvelope,
        ForecastFrame,
    )
    from backend.physics.env_data import EnvStack, load_env_stack
    from backend.physics.kde import kde_contour_polygons


    DENSITY_HOURS = (24, 48, 72)
    PER_DET_LEVEL = 0.90
    GLOBAL_LEVEL = 0.75
    JITTER_M = 50.0


    def _utm_zone_from_lonlat(lon: float, lat: float) -> int:
        """Return EPSG code for the UTM zone containing (lon, lat)."""
        _, _, zone, _ = utm_lib.from_latlon(lat, lon)
        # Northern hemisphere ocean; all 4 AOIs are north of equator.
        return 32600 + zone  # e.g., 32643 for zone 43N


    def _make_transformers(utm_epsg: int) -> tuple[Transformer, Transformer]:
        to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
        return to_utm, to_wgs


    def _seed_particles_utm(
        centroid_utm: tuple[float, float],
        n: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Return (n, 2) UTM-meter array with Gaussian ±50 m jitter."""
        cx, cy = centroid_utm
        return np.column_stack([
            rng.normal(cx, JITTER_M, size=n),
            rng.normal(cy, JITTER_M, size=n),
        ])


    def _step_particle(
        p_utm: np.ndarray,       # (N, 2)
        alive: np.ndarray,        # (N,) bool
        t_hours: float,
        env: EnvStack,
        alpha: float,
        to_wgs: Transformer,
        dt_s: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Euler step in UTM meters. Particles hitting NaN are frozen (alive=False)."""
        new_p = p_utm.copy()
        new_alive = alive.copy()
        if not alive.any():
            return new_p, new_alive
        # Convert alive particles to WGS84 for env interp
        lons, lats = to_wgs.transform(p_utm[:, 0], p_utm[:, 1])
        for i in range(p_utm.shape[0]):
            if not alive[i]:
                continue
            uo, vo = env.interp_currents(float(lons[i]), float(lats[i]), t_hours)
            u10, v10 = env.interp_winds(float(lons[i]), float(lats[i]), t_hours)
            if not (np.isfinite(uo) and np.isfinite(vo)):
                new_alive[i] = False                # D-15 beach-on-NaN
                continue
            # Treat NaN wind as zero rather than beaching (coastal ERA5 rarely NaN)
            if not np.isfinite(u10): u10 = 0.0
            if not np.isfinite(v10): v10 = 0.0
            vx = float(uo) + alpha * float(u10)
            vy = float(vo) + alpha * float(v10)
            new_p[i, 0] += vx * dt_s
            new_p[i, 1] += vy * dt_s
        return new_p, new_alive


    def _empty_fc() -> FeatureCollection:
        return FeatureCollection(type="FeatureCollection", features=[])


    def _polygons_to_fc(polys: list[Polygon], density: float, scope: str) -> FeatureCollection:
        feats = []
        for poly in polys:
            feats.append(Feature(
                type="Feature",
                geometry=mapping(poly),
                properties={"density": density, "scope": scope},
            ))
        return FeatureCollection(type="FeatureCollection", features=feats)


    def _build_frame(
        hour: int,
        per_det_positions_utm: list[tuple[np.ndarray, np.ndarray, int]],  # [(pts, alive, utm_epsg), ...]
        to_wgs_per_det: list[Transformer],
    ) -> ForecastFrame:
        # Flatten positions for schema (all alive + frozen particles, in WGS84)
        wgs_positions: list[tuple[float, float]] = []
        for (pts, alive, _zone), to_wgs in zip(per_det_positions_utm, to_wgs_per_det):
            lons, lats = to_wgs.transform(pts[:, 0], pts[:, 1])
            for lon, lat in zip(lons, lats):
                wgs_positions.append((float(lon), float(lat)))

        if hour not in DENSITY_HOURS:
            return ForecastFrame(hour=hour, particle_positions=wgs_positions,
                                 density_polygons=_empty_fc())

        # Per-detection 90% KDE (alive only, D-15)
        per_det_features = []
        all_alive_utm: list[np.ndarray] = []
        global_zone: int | None = None
        for (pts, alive, zone) in per_det_positions_utm:
            alive_pts = pts[alive]
            if alive_pts.shape[0] >= 3:
                polys = kde_contour_polygons(alive_pts, utm_epsg=zone, level=PER_DET_LEVEL)
                for p in polys:
                    per_det_features.append(Feature(
                        type="Feature", geometry=mapping(p),
                        properties={"density": 1.0, "scope": "per_detection", "level": PER_DET_LEVEL},
                    ))
            if alive_pts.shape[0] > 0:
                all_alive_utm.append(alive_pts)
                if global_zone is None:
                    global_zone = zone  # use first detection's zone for global KDE

        # Global 75% KDE (pooled)
        if all_alive_utm and global_zone is not None:
            pooled = np.vstack(all_alive_utm)
            global_polys = kde_contour_polygons(pooled, utm_epsg=global_zone, level=GLOBAL_LEVEL)
            for p in global_polys:
                per_det_features.append(Feature(
                    type="Feature", geometry=mapping(p),
                    properties={"density": 1.0, "scope": "global", "level": GLOBAL_LEVEL},
                ))
        return ForecastFrame(
            hour=hour,
            particle_positions=wgs_positions,
            density_polygons=FeatureCollection(type="FeatureCollection", features=per_det_features),
        )


    def forecast_drift(
        detections: DetectionFeatureCollection,
        cfg: Settings,
        env: EnvStack | None = None,
    ) -> ForecastEnvelope:
        """Euler Lagrangian tracker over 72 h. See module docstring."""
        if env is None:
            env = load_env_stack(cfg.physics.cmems_path, cfg.physics.era5_path,
                                 cfg.physics.horizon_hours)
        rng = np.random.default_rng(42)
        n_particles = cfg.physics.particles_per_detection
        horizon = cfg.physics.horizon_hours
        dt_s = float(cfg.physics.dt_seconds)
        alpha = cfg.physics.windage_alpha

        # Per-detection state: centroid WGS84 -> UTM seed positions (n, 2), alive mask
        per_det_state: list[tuple[np.ndarray, np.ndarray, int]] = []
        per_det_transformers: list[tuple[Transformer, Transformer]] = []
        for det in detections.features:
            poly = shape(det.geometry.model_dump())
            c = poly.centroid
            utm_epsg = _utm_zone_from_lonlat(c.x, c.y)
            to_utm, to_wgs = _make_transformers(utm_epsg)
            cx, cy = to_utm.transform(c.x, c.y)
            pts_utm = _seed_particles_utm((cx, cy), n_particles, rng)
            alive = np.ones(n_particles, dtype=bool)
            per_det_state.append((pts_utm, alive, utm_epsg))
            per_det_transformers.append((to_utm, to_wgs))

        frames: list[ForecastFrame] = []
        # Hour 0 frame (initial positions)
        frames.append(_build_frame(0, per_det_state, [t[1] for t in per_det_transformers]))

        for hour in range(1, horizon + 1):
            for i in range(len(per_det_state)):
                pts_utm, alive, utm_epsg = per_det_state[i]
                _, to_wgs = per_det_transformers[i]
                new_pts, new_alive = _step_particle(
                    pts_utm, alive, float(hour - 1), env, alpha, to_wgs, dt_s,
                )
                per_det_state[i] = (new_pts, new_alive, utm_epsg)
            frames.append(_build_frame(hour, per_det_state, [t[1] for t in per_det_transformers]))

        return ForecastEnvelope(
            source_detections=detections,
            frames=frames,
            windage_alpha=alpha,
        )
    ```

    Create **backend/tests/integration/test_tracker_synth.py** implementing Tests 1-5 above:
      - Build synthetic xarray.Dataset via helpers (reuse patterns from test_env_data.py).
      - Use `backend.physics.env_data.from_synthetic` to build EnvStack.
      - Build a tiny DetectionFeatureCollection with 1 polygon centered at (72.8, 18.9), ~300 m square, with DetectionProperties(conf_raw=0.9, conf_adj=0.9, fraction_plastic=0.3, area_m2=400.0, age_days_est=0).
      - For Test 1, set `PHYSICS__PARTICLES_PER_DETECTION=1` via monkeypatching Settings in-test OR pass a cfg where `cfg.physics.particles_per_detection=1` (pydantic model copy: `cfg.model_copy(update={"physics": cfg.physics.model_copy(update={"particles_per_detection":1})})`) — but note 50 m jitter. For the 43.2 km assertion, subtract the known jitter-induced error by comparing the **mean** of many particles, OR seed rng with n=1 and set JITTER_M=0 temporarily by using particles_per_detection=50 and taking mean (more robust). Prefer: use 50 particles and assert mean displacement is 43.2 km ±1%.
      - Create `backend/tests/integration/__init__.py` if missing.
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/integration/test_tracker_synth.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest backend/tests/integration/test_tracker_synth.py -x -q` — all 5 tests pass
    - `grep -q "always_xy=True" backend/physics/tracker.py` exits 0 (UTM safety, PITFALL C4)
    - `grep -q "32600" backend/physics/tracker.py` exits 0 (UTM zone logic)
    - `grep -q "DENSITY_HOURS = (24, 48, 72)" backend/physics/tracker.py` exits 0
    - `grep -q "beach" backend/physics/tracker.py` exits 0 (D-15 annotated in code)
    - `grep -q "alpha \* " backend/physics/tracker.py` exits 0 (windage)
    - `python -m backend.physics $(ls MARIDA/patches/**/S2_*_0.tif | head -1 2>/dev/null || echo dummy.tif) --out /tmp/fc.json 2>&1 | head -20` — either succeeds or fails with a clear error about missing env files (NOT a schema error)
    - A fresh pytest run on backend/tests/integration/test_tracker_synth.py::test_synthetic_43km passes — this gates Phase 2 exit.
  </acceptance_criteria>
  <done>forecast_drift ships as a real Euler tracker. 43.2 km gate green. Zero-field stability green. Beach-on-NaN correctness green. Schema round-trip green. Density polygons populated at {24,48,72}, empty elsewhere.</done>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests/unit/test_kde.py backend/tests/integration/test_tracker_synth.py -q` — all green
- Synthetic 43.2 km test is the Phase 2 exit gate — no Plan 05 work starts until this passes
- No NaN in any ForecastFrame.particle_positions across all tests
</verification>

<success_criteria>
- PHYS-03 shipped: real tracker replacing Phase 1 stub
- PHYS-04 shipped: synthetic 43.2 km + zero-field tests both green
- PITFALL C4 (UTM units) provably handled — grep for always_xy=True
- PITFALL M2 (beach-on-NaN) provably handled — Test 3
- D-06 (density_polygons only at {24,48,72}) provably handled — Test 4
</success_criteria>

<output>
After completion, create `.planning/phases/02-trajectory-mission-planner/02-03-SUMMARY.md`.
</output>
