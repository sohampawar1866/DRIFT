---
phase: 01-schema-foundation-dummy-inference
plan: 05
subsystem: ml/inference
tags: [inference, sliding-window, cosine-stitch, polygonization, rasterio, shapely, pyproj, marida, schema-freeze, e2e]

requires:
  - phase: 01-02
    provides: "Frozen DetectionFeatureCollection / DetectionProperties + Settings loader"
  - phase: 01-03
    provides: "backend.ml.features.feature_stack (14-channel pure-numpy spectral source of truth)"
  - phase: 01-04
    provides: "DualHeadUNetpp + load_weights strategy loader (dummy branch with mask_head.bias=0.5) + 3 CLI entrypoints"
provides:
  - "backend.ml.inference.run_inference(tile_path, cfg) -> DetectionFeatureCollection"
  - "Sliding 256x256 window + stride 128 + cosine-Hann stitch (>=1e-3 floor) over arbitrary H,W rasters"
  - "rasterio.features.shapes(connectivity=4) + .buffer(0) + MIN_AREA_M2 filter + UTM->WGS84 reprojection AFTER area computation"
  - "Integration test: 3 hard assertions on a real MARIDA patch (schema round-trip, 0<n<500, properties in bounds)"
  - "End-to-end three-stage CLI chain: python -m backend.{ml|physics|mission} round-trips schema-valid JSON on a real S2 tile"
affects: [02-*, 03-*]

tech-stack:
  added: []
  patterns:
    - "Sliding-window cosine-Hann stitch with floor >=1e-3 to prevent div-by-zero at tile corners"
    - "Polygonization ordering: compute area in UTM BEFORE reprojection; reproject only the final vertex ring"
    - "BOA_ADD_OFFSET heuristic (bands.max() > 1.5) as defensive no-op for MARIDA, active branch for raw post-2022 L2A"
    - "Anchor-grid flush: append H-patch / W-patch tail anchors so last row/col is covered when H,W not divisible by stride"
    - "run_inference imports feature_stack + load_weights via explicit module paths (grep-provable single-source-of-truth link)"

key-files:
  created:
    - backend/ml/inference.py
    - backend/tests/integration/__init__.py
    - backend/tests/integration/test_inference_dummy.py
  modified:
    - .gitignore

key-decisions:
  - "Verbatim copy from RESEARCH.md Pattern 7; the bug density (cosine zero at edges, UTM vs WGS84 area, shapely invalid polys) makes paraphrasing dangerous"
  - "MIN_AREA_M2 filter runs on UTM-meter area (raw poly.area, since S2 tiles are UTM) BEFORE vertex reprojection to EPSG:4326 -- reverse order would require expensive geodesic area"
  - "BOA heuristic branch is a no-op on MARIDA (max=0.27 per Probe 1) but active for raw S2 L2A ingestion; Phase 1 ships it now to avoid a schema-affecting retrofit later"
  - "Integration test hard-asserts n > 0 (strict), depends on Plan 04's mask_head.bias=0.5 shift; if n==0 the failure message fingers weights.py, not inference.py"

patterns-established:
  - "Sliding-window + cosine stitch + polygonization pattern usable by Phase 3 real-weight inference as-is (YAML flip to our_real is the only change)"
  - "Anchor-grid flush idiom for arbitrary (H,W) input rasters vs fixed patch size"
  - "Schema-valid E2E CLI chain as a Phase 1 exit gate: ml -> physics -> mission all round-trip JSON even when physics/mission are empty stubs"

requirements-completed: [ML-04]

duration: 5min
completed: 2026-04-17
---

# Phase 01 Plan 05: run_inference Orchestrator Summary

**Shipped `backend/ml/inference.py::run_inference` -- the Phase 1 exit gate. A real MARIDA patch now flows through sliding-window dummy inference, cosine-Hann stitch, rasterio.features.shapes polygonization with buffer(0) + MIN_AREA_M2 filter, UTM->WGS84 reprojection, and out as a schema-valid DetectionFeatureCollection. Integration test + end-to-end CLI chain (ml -> physics -> mission) both pass; ML__WEIGHTS_SOURCE=our_real env override correctly routes to the Phase 3 NotImplementedError branch.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-17T11:36:54Z
- **Completed:** 2026-04-17T11:42Z
- **Tasks:** 2 of 2
- **Files created:** 3 (inference.py, integration/__init__.py, integration/test_inference_dummy.py)
- **Files modified:** 1 (.gitignore -- local scratch dir)

## Accomplishments

- `backend/ml/inference.py` (211 lines) shipped verbatim from RESEARCH.md Pattern 7, wiring:
  - `_read_tile_bands` with BOA_ADD_OFFSET heuristic (defensive no-op for MARIDA).
  - `_cosine_window_2d` with `np.maximum(w2d, 1e-3)` floor (PITFALL 7 fix for corner div-by-zero).
  - `_sliding_forward` with anchor-grid flush (handles arbitrary (H,W) vs fixed 256x256 patch).
  - `_polygonize` with `connectivity=4`, `.buffer(0)`, `MIN_AREA_M2` filter, UTM-area-before-WGS84-reproject ordering.
  - `run_inference` public entrypoint calling `feature_stack` (Plan 03) + `load_weights` (Plan 04) by explicit module path.
- `backend/tests/integration/test_inference_dummy.py` with 3 hard assertions on a real MARIDA patch:
  - Schema round-trip via `model_dump_json` -> `model_validate_json` byte-equal.
  - `0 < n < 500` strict polygon count (lower bound guaranteed by mask_head.bias=0.5 from Plan 04).
  - Every property in declared bounds (conf_raw/conf_adj/fraction in [0,1], area >= 200, age=0, cls=="plastic").
- All 3 integration tests **PASSED** in 20.08 s against `MARIDA/patches/S2_1-12-19_48MYU/S2_1-12-19_48MYU_0.tif` (found via the sample_tile fixture). On the sampled patch the dummy inference emitted **1 polygon**, comfortably within `0 < n < 500`.
- End-to-end three-stage CLI chain **WORKS**:
  - `python -m backend.ml <marida-patch> --out det.json` -> `ML stage OK, 1 polygons` (schema-valid DetectionFC)
  - `python -m backend.physics det.json --out fc.json` -> `Physics stage OK, 0 frames` (schema-valid stub)
  - `python -m backend.mission fc.json --out plan.json` -> `Mission stage OK, 0 waypoints` (schema-valid stub)
- Env-var override verification **WORKS**: `ML__WEIGHTS_SOURCE=our_real python -m backend.ml ...` raises `NotImplementedError: our_real weights arrive in Phase 3 via kagglehub. Flip cfg.ml.weights_source only after Phase 3 training completes.` -- proves INFRA-04 end-to-end: YAML -> Settings -> env override -> strategy switch -> NotImplementedError branch.

## Task Commits

1. **Task 1: backend/ml/inference.py** -- `e30021d` (feat)
2. **Task 2: integration test + E2E CLI verification + .gitignore** -- `ed108de` (test)

## Files Created/Modified

- `backend/ml/inference.py` -- 211 lines, the Phase 1 orchestrator.
- `backend/tests/integration/__init__.py` -- empty package marker.
- `backend/tests/integration/test_inference_dummy.py` -- 78 lines, 3 pytest tests.
- `.gitignore` -- appended `.tmp_e2e/` (local scratch dir for E2E chain).

## Decisions Made

- **Verbatim copy from RESEARCH.md Pattern 7.** Every knob in this file is load-bearing (cosine floor 1e-3, connectivity=4, buffer(0), UTM area before WGS84 reproject, BOA heuristic, anchor-grid flush). Paraphrasing any of these would have required re-deriving the correctness proof; copying the known-good implementation was the correct call.
- **Strict `n > 0` assertion in the polygon-count test** depends on the `mask_head.bias.data.fill_(0.5)` shift in Plan 04. The error message in the test explicitly points at `backend/ml/weights.py` so a Plan 04 regression (bias reverts to 0.0 -> sigmoid ~0.5 -> threshold+area filter drops everything) fails the test with clear attribution.
- **MIN_AREA_M2 filter uses raw `poly.area`** because S2 tiles are in UTM meter CRS; area is directly in m2. Reversing the order (reproject to WGS84 first, then compute area) would require `pyproj.Geod` geodesic integration and a ~100x slowdown with no accuracy benefit for sub-km patches.
- **BOA_ADD_OFFSET heuristic branch stays in Phase 1** even though MARIDA never triggers it (Probe 1 confirmed max=0.271). Adding it retroactively in Phase 3 when live L2A tiles are ingested would be a schema-irrelevant but inference-affecting change -- better to ship it defensive-as-a-no-op now.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `/tmp/` path resolves to non-existent `C:\tmp\` on Windows Python**

- **Found during:** Task 2 Step 4 (E2E CLI chain)
- **Issue:** The plan's Step 4 script used `/tmp/det.json` paths. Git Bash's `/tmp` maps to `C:\Users\offic\AppData\Local\Temp`, but Python's `Path('/tmp/...')` resolves to literal `C:\tmp\` which does not exist on this machine. First CLI invocation failed with `FileNotFoundError: [Errno 2] No such file or directory: '/tmp/det.json'`.
- **Fix:** Switched E2E chain to a local `.tmp_e2e/` directory in the repo root; added `.tmp_e2e/` to `.gitignore` so scratch files are never committed. All three CLI stages then round-tripped successfully.
- **Files modified:** `.gitignore` (added `.tmp_e2e/`)
- **Commit:** `ed108de`

### Out-of-scope / noted, not fixed

- Pre-existing `botocore` / `urllib3` deprecation warnings in pytest output -- legacy deps from anaconda base, not Phase 1 scope.
- The `torchaudio 2.2.2` vs `torch 2.7.0` compatibility warning continues to be noise; Phase 1 does not import torchaudio.

## Authentication Gates

None encountered.

## Verification

- `grep "from backend.ml.features import feature_stack" backend/ml/inference.py` -- matches (single-source-of-truth link proven)
- `grep "from backend.ml.weights import load_weights" backend/ml/inference.py` -- matches
- `grep "connectivity=4" backend/ml/inference.py` -- matches (PITFALL M9)
- `grep "buffer(0)" backend/ml/inference.py` -- matches (PITFALL M9)
- `grep "np.maximum(w2d, 1e-3)" backend/ml/inference.py` -- matches (PITFALL 7 cosine floor)
- `grep "bands.max() > 1.5" backend/ml/inference.py` -- matches (PITFALL C1)
- `grep "EPSG:4326" backend/ml/inference.py` -- matches (UTM -> WGS84 reproject)
- `_cosine_window_2d(256).shape == (256, 256)` and `.min() >= 1e-3` -- PASSES
- Integration test suite 3/3 PASSED in 20.08 s
- E2E CLI chain all three stages exit 0 and emit schema-valid JSON
- Env-var override raises `NotImplementedError` with "our_real" / "kagglehub" message

## Phase 1 Exit Criteria Status (ROADMAP.md)

1. DetectionProperties frozen schema committed (Plan 02) -- **DONE**
2. python -m backend.ml <patch> emits schema-valid FC (Plan 05) -- **DONE**
3. FDI Biermann unit test passes (Plan 03) -- **DONE**
4. Env override `ML__WEIGHTS_SOURCE` works (Plan 05 Step 5) -- **DONE**
5. All three CLI entrypoints parse args and load Settings (Plan 04 + Plan 05) -- **DONE**

## Requirements Closed

- **ML-04** -- Phase 1 inference: `run_inference(tile_path) -> DetectionFeatureCollection` with the full six-property schema (`conf_raw`, `conf_adj`, `fraction_plastic`, `area_m2`, `age_days_est`, `class`) on a real MARIDA patch via dummy weights. Freezes the contract for Phase 2 physics + Phase 3 real-weight swap.

**All 8 Phase 1 requirements now closed across Plans 01-05:**
- INFRA-01, INFRA-02, INFRA-03 (Plan 02)
- INFRA-04, INFRA-06, ML-03 (Plan 04)
- ML-01 (Plan 03)
- ML-04 (Plan 05, this one)

## Known Stubs

Inherited from Plan 04 and unchanged:

- `backend/physics/tracker.py::forecast_drift` -- empty-frames envelope. Real Euler Lagrangian tracker arrives in Phase 2.
- `backend/mission/planner.py::plan_mission` -- empty-waypoints plan with degenerate LineString. Real greedy+2-opt TSP arrives in Phase 2.

These are intentional Phase 1 stubs documented in their docstrings and Plan 04's SUMMARY; they do NOT prevent Phase 1 exit. Phase 2 will replace the bodies without touching any caller (signatures + schemas are stable and frozen).

No new stubs introduced in Plan 05. `run_inference` is fully wired and exercised end-to-end.

## Next Phase Readiness

- Phase 1 is **COMPLETE**. All 5 exit criteria met. Schema is FROZEN.
- Phase 2 can now implement `forecast_drift` body with a real Euler tracker, consuming `DetectionFeatureCollection` output from `run_inference` and emitting schema-valid `ForecastEnvelope`. The contract is locked, tested, and demonstrated in the E2E CLI chain.
- Phase 3 weight swap is a one-line YAML flip (`ml.weights_source: our_real`) once the `NotImplementedError` branch in `weights.py` is replaced with the kagglehub download + state_dict load. `run_inference` itself does not change.

## Self-Check: PASSED

- FOUND: `backend/ml/inference.py`
- FOUND: `backend/tests/integration/__init__.py`
- FOUND: `backend/tests/integration/test_inference_dummy.py`
- FOUND commit: `e30021d` (Task 1)
- FOUND commit: `ed108de` (Task 2)

---
*Phase: 01-schema-foundation-dummy-inference*
*Plan: 05*
*Completed: 2026-04-17*
