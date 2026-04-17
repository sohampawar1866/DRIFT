# Phase 2: Trajectory + Mission Planner — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers two callable Python functions plus a one-shot data-fetch script:

1. `backend/physics/tracker.py::forecast_drift(detections, cfg) -> ForecastEnvelope` — Euler Lagrangian tracker integrating in UTM meters, 20 particles/detection, hourly dt over 72 h, windage α=0.02, CMEMS + ERA5 inputs. Emits ForecastFrame list with particle positions and density polygons at +24/+48/+72 h.
2. `backend/mission/planner.py::plan_mission(forecast, vessel_range_km, hours, origin, cfg) -> MissionPlan` — greedy nearest-neighbor TSP **with 2-opt improvement**, vessel range + time budget constraints, priority-scored waypoints, closed LineString route (origin → waypoints → origin).
3. `scripts/fetch_demo_env.py` — one-shot pre-stage script using `copernicusmarine.open_dataset()` + CDS API to write `data/env/cmems_currents_72h.nc` and `data/env/era5_winds_72h.nc`.

Phase 2 is **gated** by the synthetic 43.2 km / 24 h ±1% tracker test (PHYS-04). Full dummy-weight E2E chain (`run_inference → forecast_drift → plan_mission`) must complete without exceptions on one MARIDA patch with schema-valid outputs at every boundary.

**Out of Phase 2 (Phase 3):** GPX/PDF export (MISSION-03), real training weights (ML-05/06/07/08), pre-baked fallback JSONs (E2E-02), INFRA-05 kagglehub flow.

</domain>

<decisions>
## Implementation Decisions

### Env Data Sequencing

- **D-01:** **Parallel track.** Build tracker against inline synthetic xarray Dataset fixtures first (constant-field unit test + a realistic Indian-Ocean-shaped mock); build `scripts/fetch_demo_env.py` alongside. The real-data smoke test (PHYS-05) runs when the fetch completes. Rationale: decouples tracker work from credential/network flakes; keeps Phase 2 moving even if CMEMS auth hiccups.
- **D-02:** CMEMS product: **`GLOBAL_ANALYSISFORECAST_PHY_001_024`** (global 1/12° hourly, `uo`/`vo` surface eastward/northward water velocity). Verify `ds.uo.attrs["standard_name"] == "eastward_sea_water_velocity"` at load (PITFALL M5). Fetch via `copernicusmarine.open_dataset()` — NOT deprecated motuclient/OPeNDAP.
- **D-03:** ERA5 variant: **`reanalysis-era5-single-levels`** with variables `10m_u_component_of_wind` (u10) and `10m_v_component_of_wind` (v10). Hourly. CDS API via `cdsapi` client.
- **D-04:** Bbox: **union of 4 demo AOIs + 2° buffer** (Gulf of Mannar, Mumbai offshore, Bay of Bengal mouth, Arabian Sea gyre edge). Effective window ≈ `lon [68, 92]`, `lat [5, 22]`. Temporal window: **72 h** forward from a pinned start time. Each NetCDF must stay under 500 MB.
- **D-05:** Credentials flow from env vars: `COPERNICUSMARINE_SERVICE_USERNAME` / `COPERNICUSMARINE_SERVICE_PASSWORD`, and `CDSAPI_URL` / `CDSAPI_KEY` (or `~/.cdsapirc`). Script docstring documents both flows. Script fails loud if either is missing — never silently falls back to synthetic.

### Density Polygons (ForecastFrame.density_polygons)

- **D-06:** **Both local and global KDE.** Per-detection 90% isodensity contour (per-source envelope) **plus** a global 75% contour over all pooled particles at the frame timestamp. Populated only at frames `{24, 48, 72}`; other frames carry an empty FeatureCollection to stay schema-valid.
- **D-07:** KDE implementation: `sklearn.neighbors.KernelDensity` with Gaussian kernel. Bandwidth selection is **Claude's discretion** (likely Scott's rule translated to meters, or fixed meters empirically tuned). Contour extraction via `skimage.measure.find_contours` or `matplotlib._cntr` on a sampled grid, polygonized with Shapely + `.buffer(0)` fix.
- **D-08:** Particle jitter at seed: **±50 m Gaussian** in UTM meters (carry forward from REQ-PHYS-03). Seed particles at polygon centroid.

### Mission Planner — Edge Cases + Scoring

- **D-09:** **Never raise** on degenerate inputs. Contract:
  - 0 detections → `MissionPlan(waypoints=[], route=degenerate LineString at origin, total_distance_km=0, total_hours=0)`. Matches Phase 1 stub shape.
  - 1 detection → single waypoint; route is `origin → wp → origin` LineString.
  - All detections out of range → same shape as 0 detections (empty waypoints, degenerate route).
  - Budget exhausted mid-tour → return the **visited prefix** (strict honoring of `vessel_range_km` AND `hours`); include the partial route that returns to origin from the last reachable waypoint.
- **D-10:** Route is always closed (origin → ... → origin). `waypoints[0].order == 0`; strict integer ordering.
- **D-11:** Greedy **plus 2-opt**. Both ship in Phase 2 per REQ MISSION-02. 2-opt runs until no improving swap is found (or N² iteration cap to keep worst case bounded).
- **D-12:** Priority score retained from config (**Claude's discretion** for exact formula; config weights 0.5/0.3/0.2 stay):
  - `density` term = density value at the detection centroid in the +72 h global KDE (or local KDE if that's cleaner).
  - `accessibility` term = inverse normalized distance from origin (closer is better).
  - `convergence` term = ratio of `+72h density / +0h density` at the detection centroid (>1 means debris concentrating).
  - Final: `priority = conf_adj × area_m2 × fraction_plastic × weighted_sum(density, accessibility, convergence)`.

### Vessel Model

- **D-13:** Add `mission.avg_speed_kmh: 20.0` to `backend/config.yaml` (≈11 kt — typical Indian Coast Guard patrol cruise). `plan_mission` reads `cfg.mission.avg_speed_kmh` to convert distance to elapsed time; this also drives the `hours` budget gate. `MissionWaypoint.arrival_hour` is computed from `cumulative_distance_km / avg_speed_kmh`.

### Tracker — Fixed Invariants (carried from ROADMAP/REQUIREMENTS, locked here)

- **D-14:** Integrate in **UTM meters** via `pyproj.Transformer(EPSG:4326 → EPSG:326XX, always_xy=True)`. Pick UTM zone per AOI centroid (e.g., zone 43N for Arabian Sea / Mumbai; zone 44N for Bay of Bengal). Convert back to WGS84 only for schema output.
- **D-15:** **Beach-on-NaN:** if `interp_currents(lon, lat, t)` returns NaN for a particle at any step, freeze that particle's position at its last valid location for remaining frames and **exclude it from KDE** aggregation. No NaN ever appears in ForecastFrame output.
- **D-16:** Longitude normalization: at load, detect convention via `ds.longitude.min()/max()`; if in `[0, 360]`, remap to `[-180, 180]` via `((lon + 180) % 360) - 180` (PITFALL M4).
- **D-17:** Time-axis coverage check: assert CMEMS and ERA5 datasets each cover ≥ 72 h from the detection timestamp; clip horizon to `min(t_end_cmems, t_end_era5) - t_detect` if shorter.
- **D-18:** Windage: `v_total = v_current + 0.02 * v_wind`; verify wind components are eastward/northward (PITFALL M5).

### E2E Driver

- **D-19:** `scripts/run_full_chain_dummy.py` is a **parameterized CLI**:
  - `python scripts/run_full_chain_dummy.py [--patch <name>] [--origin LON LAT]`
  - Defaults: `--patch` = first entry in `MARIDA/splits/val_X.txt`; `--origin` = `72.8 18.9` (Mumbai).
  - Runs `run_inference → forecast_drift → plan_mission` sequentially; prints per-stage wall-clock; asserts pydantic validation at each boundary; exits non-zero on failure.
  - Target wall-clock < 20 s on CPU laptop (15 s is Phase 3's job; Phase 2 only proves the chain works).

### Claude's Discretion

- KDE bandwidth selection (Scott's rule in UTM meters vs fixed bandwidth) — empirical tuning during implementation.
- Exact `weighted_sum(density, accessibility, convergence)` normalization scheme (min-max per-batch vs absolute) — whichever yields stable, interpretable priority scores on the dummy E2E run.
- Choice between `skimage.measure.find_contours` vs `matplotlib` for KDE→polygon conversion.
- UTM zone picker heuristic (per-AOI lookup table vs auto `utm.from_latlon`).
- 2-opt stopping criterion (convergence vs iteration cap) — default to convergence with an N² cap as safety.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product + Scope
- `PRD.md` §4 (physics simplification rationale), §8.1 (model choice), §8.6 (tech stack lock), §12 (scope rule), §13 (H-timeline + feature freeze), §16 (risk mitigation — Euler fallback posture).
- `.planning/PROJECT.md` — Core Value, Constraints, Key Decisions (incl. scope rule).
- `.planning/REQUIREMENTS.md` — PHYS-01..PHYS-05, MISSION-01/02, Out-of-Scope table.
- `.planning/ROADMAP.md` Phase 2 section — success criteria (5 items, gating), risk flags (PITFALLs C4/M2/M3/M4/M5/M9/M10).

### Research (Phase 1)
- `.planning/research/STACK.md` — xarray + copernicusmarine-client + pyproj + sklearn.neighbors guidance.
- `.planning/research/PITFALLS.md` — CRS unit confusion (C4), beach-on-NaN (M2), time-axis (M3), longitude convention (M4), wind vector components (M5), rasterio artifacts (M9), TSP edges (M10).
- `.planning/research/ARCHITECTURE.md` — module boundary conventions.
- `.planning/phases/01-schema-foundation-dummy-inference/01-RESEARCH.md` — carried patterns (buffer(0), MIN_AREA_M2, pyproj usage).

### Existing Code (contracts not to break)
- `backend/core/schemas.py` — **FROZEN.** `ForecastEnvelope`, `ForecastFrame`, `MissionPlan`, `MissionWaypoint`. `extra="forbid", frozen=True`.
- `backend/core/config.py` — pydantic-settings loader; nested `PhysicsSettings`, `MissionSettings`; env-var override delimiter `__`.
- `backend/config.yaml` — `physics:` and `mission:` blocks already present; `mission.avg_speed_kmh` to be added per D-13.
- `backend/physics/tracker.py` (stub), `backend/physics/cli.py`, `backend/physics/__main__.py` — CLI entry wired.
- `backend/mission/planner.py` (stub), `backend/mission/cli.py`, `backend/mission/__main__.py` — CLI entry wired.
- `backend/ml/inference.py::run_inference` — Phase 1 shipped; Phase 2 tracker consumes its output unchanged.

### Codebase Maps
- `.planning/codebase/STACK.md`, `CONVENTIONS.md`, `STRUCTURE.md`, `TESTING.md`, `CONCERNS.md` — established patterns (snake_case, pydantic `frozen=True`, pytest integration test layout).

### External (library docs — consult via context7 during research/planning)
- `copernicusmarine` Python client docs — auth, `open_dataset`, subset API.
- `cdsapi` docs — ERA5 retrieval, request shape.
- `pyproj` Transformer `always_xy=True` usage.
- `sklearn.neighbors.KernelDensity` — Gaussian kernel, bandwidth.
- `shapely` 2.x `buffer(0)` fix + `.is_valid`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Frozen schemas** (`backend/core/schemas.py`): `ForecastEnvelope`, `ForecastFrame`, `MissionPlan`, `MissionWaypoint` — Phase 2 populates these; must not edit field shape.
- **Config loader** (`backend/core/config.py`): add `avg_speed_kmh` to `MissionSettings` (pydantic model) + `backend/config.yaml`. Env-var override comes for free via `MISSION__AVG_SPEED_KMH=30`.
- **CLI entrypoints** (`backend/physics/__main__.py`, `backend/mission/__main__.py`): shipped; Phase 2 replaces the stub call-through with the real implementation, no CLI-layer changes needed.
- **`backend/ml/inference.py::run_inference`**: Phase 1 output is schema-valid `DetectionFeatureCollection` — the tracker's direct input. `rasterio.features.shapes` + `.buffer(0)` + `MIN_AREA_M2` polygonization already solid.
- **Test layout** (`backend/tests/`, `backend/ml/test_inference.py`): pytest integration fixtures already present; Phase 2 mirrors this under `backend/physics/` and `tests/integration/`.

### Established Patterns
- **pydantic `frozen=True, extra="forbid"`** everywhere — Phase 2 modules must return only schema-compliant objects.
- **CLI style**: `python -m backend.physics <detections.json>` — argparse or typer, JSON I/O through stdin/stdout or file paths.
- **Env-var override delimiter**: `__` (e.g., `PHYSICS__WINDAGE_ALPHA=0.015`). Phase 2 unit tests can leverage this for parameter sweeps.
- **No `torch.compile`, no Hydra, no Lightning** (per REQUIREMENTS out-of-scope table).

### Integration Points
- `forecast_drift` consumes `DetectionFeatureCollection` from `run_inference` — no adapter layer.
- `plan_mission` consumes `ForecastEnvelope` — no adapter layer.
- `scripts/run_full_chain_dummy.py` chains all three; parameterized by `--patch` and `--origin`.
- `backend/api/routes.py` (mock endpoints) stays untouched per milestone scope.

### Creative Options Enabled
- Because schemas are frozen, Phase 2 can refactor internals aggressively without breaking Phase 1 or Phase 3.
- pytest-based synthetic xarray fixtures decouple tracker dev from real env-data availability — enables genuinely parallel work.

</code_context>

<specifics>
## Specific Ideas

- **Route is always closed** (origin → waypoints → origin) — explicit user-adjacent decision, surfaces in mission exports later.
- **Mumbai origin default** (72.8, 18.9) is referenced across stubs, ROADMAP tests, and the E2E driver — treat as a canonical demo origin even though any origin is valid.
- **Never-raise philosophy on mission planner**: the demo must not crash mid-pitch if detections go to zero on a difficult tile.
- **Fail-loud philosophy on fetch script**: missing creds / wrong dataset ID → exit non-zero with a clear message, never silent synthetic fallback.

</specifics>

<deferred>
## Deferred Ideas

- **GPX + PDF export** (MISSION-03) — Phase 3.
- **Pre-baked 4-AOI fallback JSONs** (E2E-02) — Phase 3 (H+28).
- **Priority-scoring parameter sweep / tuning UI** — post-milestone; weights stay at 0.5/0.3/0.2 until evidence says otherwise.
- **`torch.hub.load("marccoru/marinedebrisdetector")` baseline branch** — research already confirmed weights live on private Google Drive; optional Phase 2/3 bonus if a manual download happens.
- **Multi-AOI per-AOI env files (D-04 alternative)** — viable if the unioned NetCDF exceeds 500 MB; re-litigate only if file size budget is blown.
- **KDE bandwidth as user-tunable config** — hardcode first; promote to config only if Phase 3 demo tuning needs it.

### Reviewed Todos (not folded)
None — no pending todos at gsd:list-todos at context gathering time.

</deferred>

---

*Phase: 02-trajectory-mission-planner*
*Context gathered: 2026-04-17*
