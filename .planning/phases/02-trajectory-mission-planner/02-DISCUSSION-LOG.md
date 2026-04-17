# Phase 2: Trajectory + Mission Planner — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 02-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 02-trajectory-mission-planner
**Areas discussed:** env-fetch sequencing, density polygons, TSP edge cases, vessel speed, CMEMS product, AOI bbox, 2-opt, E2E driver

---

## Env-Fetch Sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Build fetch script first, block on real data | scripts/fetch_demo_env.py runs to completion before tracker work starts; risk: credential/network flakes stall Phase 2. | |
| Parallel: synthetic xarray fixtures + fetch script | Tracker built against inline synthetic xarray Datasets; fetch script in parallel; lower blocker risk. | ✓ |
| Synthetic only for Phase 2; fetch deferred to Phase 3 | Violates ROADMAP success-criterion 4. | |

**User's choice:** Parallel.
**Notes:** Decouples tracker dev from credential/network flakes.

## Density Polygons

| Option | Description | Selected |
|--------|-------------|----------|
| Per-detection KDE, 50%+90% contours | Per-source resolution, two levels. | |
| Global KDE over all particles, single level | Simpler, loses per-source resolution. | |
| Both — per-detection 90% + global 75% | Richer; feeds both local and aggregate signals into mission scoring. | ✓ |

**User's choice:** Both.
**Notes:** Mission convergence scoring wants global signal; visualization wants per-source envelope.

## TSP Edge Cases

| Option | Description | Selected |
|--------|-------------|----------|
| Empty-but-valid MissionPlan, never raise | 0 detections → empty waypoints + degenerate LineString. | |
| Raise typed MissionError | More correct but forces caller handling. | |
| Empty on 0 detections; partial (closest subset) on budget-exhaustion | Never raise, honor budgets strictly, return visited prefix. | ✓ |

**User's choice:** Empty-on-zero + partial-on-budget-exhaustion.
**Notes:** Preserves never-raise demo safety while giving meaningful partial results when budget runs out.

## Vessel Speed Model

| Option | Description | Selected |
|--------|-------------|----------|
| Config: mission.avg_speed_kmh (default 20) | Adds config key; user-tunable. | ✓ |
| Derived from vessel_range_km / hours | No new config; fragile if caller sets both inconsistently. | |
| Hardcoded constant in planner | Simplest; deferred tunability. | |

**User's choice:** Config with default 20 km/h.
**Notes:** ~11 kt Indian Coast Guard patrol cruise.

## CMEMS Product + ERA5 Variant

| Option | Description | Selected |
|--------|-------------|----------|
| GLOBAL_ANALYSISFORECAST_PHY_001_024 + ERA5 single-levels u10/v10 | Standard; covers all 4 AOIs; matches ROADMAP guidance. | ✓ |
| Regional IBI / Indian Ocean CMEMS + ERA5 same | Higher res regionally; fragmented dataset IDs. | |
| You decide | Researcher picks. | |

**User's choice:** GLOBAL_ANALYSISFORECAST_PHY_001_024 + ERA5 single-levels.
**Notes:** `uo`/`vo` eastward/northward; verify `standard_name` attr at load.

## AOI Bbox

| Option | Description | Selected |
|--------|-------------|----------|
| Union of 4 AOIs + 2° buffer, 72h window | lon ~68–92, lat ~5–22; stays under 500 MB. | ✓ |
| Full Indian Ocean basin | Over-fetches; may bust 500 MB budget. | |
| Per-AOI separate slices | Four smaller NetCDFs; more loader complexity. | |

**User's choice:** Union + 2° buffer, 72h.
**Notes:** Buffer handles particles drifting outside AOI box.

## 2-opt Improvement

| Option | Description | Selected |
|--------|-------------|----------|
| Both (greedy + 2-opt) in Phase 2 | Per REQ MISSION-02; ~30 lines added. | ✓ |
| Greedy only, 2-opt stretch | Defer polish to Phase 3. | |

**User's choice:** Both.
**Notes:** REQ MISSION-02 explicit.

## E2E Driver

| Option | Description | Selected |
|--------|-------------|----------|
| First val patch + Mumbai origin | Deterministic, minimal. | |
| Parameterized CLI args with val[0]/Mumbai defaults | Flexible for ad-hoc demos; same default behavior. | ✓ |
| You decide | Claude picks during planning. | |

**User's choice:** Parameterized CLI with defaults.
**Notes:** Flexibility for demo variations without code edits.

---

## Claude's Discretion

- KDE bandwidth selection (Scott's rule vs fixed meters).
- Exact normalization of `weighted_sum(density, accessibility, convergence)` in priority score.
- KDE→polygon converter (`skimage.measure.find_contours` vs matplotlib).
- UTM zone picker heuristic (per-AOI LUT vs auto `utm.from_latlon`).
- 2-opt stopping criterion (convergence vs iteration cap — default convergence with N² cap).

## Deferred Ideas

- GPX + PDF export (Phase 3 — MISSION-03).
- Pre-baked 4-AOI fallback JSONs (Phase 3 — E2E-02).
- Priority-scoring parameter sweep / UI — post-milestone.
- `marccoru/marinedebrisdetector` baseline branch — weights on private Drive; optional bonus.
- Per-AOI separate env NetCDFs — only if unioned file blows 500 MB.
- KDE bandwidth as user-tunable config — promote only if demo tuning demands it.
