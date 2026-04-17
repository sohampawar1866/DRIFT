---
phase: 01-schema-foundation-dummy-inference
plan: 04
subsystem: ml/physics/mission
tags: [model, smp, unetplusplus, scse, weight-loader, strategy-pattern, cli, argparse, stubs, schema-valid]

requires:
  - phase: 01-01
    provides: "backend package skeleton + Phase 1 deps (torch 2.7.0+cpu, smp 0.5.0) installed; resnet18 ImageNet encoder cache primed at HuggingFace hub"
  - phase: 01-02
    provides: "Frozen schemas (DetectionFeatureCollection, ForecastEnvelope, MissionPlan) + Settings loader"
  - phase: 01-03
    provides: "backend/ml/ package with features.py; confirms pure-numpy spectral index source of truth"
provides:
  - "DualHeadUNetpp (UNet++ resnet18 encoder, SCSE decoder attention, dual 1x1 Conv heads: mask_head + frac_head)"
  - "load_weights(Settings) strategy loader — dummy branch fully working; marccoru_baseline + our_real branches raise NotImplementedError"
  - "Dead-init sanity check: conv1.weight.std() > 1e-4 (observed 0.028, tiled-pretrained regime, comfortably above threshold)"
  - "mask_head bias preset to 0.5 (guarantees non-empty polygons on dummy-weight inference so Plan 05 strict n > 0 test passes)"
  - "3 CLI entrypoints: python -m backend.{ml,physics,mission} with argparse and --help wired"
  - "ml/cli.py uses LAZY import of run_inference so --help works in Wave 2 before Plan 05 creates inference.py"
  - "Phase 1 stub forecast_drift returning schema-valid ForecastEnvelope with frames=[]"
  - "Phase 1 stub plan_mission returning schema-valid MissionPlan with waypoints=[] and degenerate LineString at origin"
affects: [01-05, 02-*, 03-*]

tech-stack:
  added: []
  patterns:
    - "Strategy pattern for weight sourcing (dummy | marccoru_baseline | our_real): YAML flag routes to branches; unimplemented branches fail-loud via NotImplementedError"
    - "Lazy imports inside CLI main() functions so --help works in modules whose siblings are not yet built (Wave 2 / Wave 3 split)"
    - "Schema-valid empty stubs (not raise): stubs return valid pydantic models so the full CLI chain round-trips JSON before real implementations land"
    - "python -m backend.X pattern: cli.py defines main(), __main__.py is a one-line trampoline"
    - "Degenerate LineString GeoJSON (two identical coordinates) used for schema-valid empty route placeholder"

key-files:
  created:
    - backend/ml/model.py
    - backend/ml/weights.py
    - backend/ml/cli.py
    - backend/ml/__main__.py
    - backend/physics/__init__.py
    - backend/physics/tracker.py
    - backend/physics/cli.py
    - backend/physics/__main__.py
    - backend/mission/__init__.py
    - backend/mission/planner.py
    - backend/mission/cli.py
    - backend/mission/__main__.py
  modified: []

key-decisions:
  - "DualHeadUNetpp emits dict {mask_logit, fraction} (sigmoid already applied to fraction); mask logit stays raw so Plan 05 can threshold freely"
  - "mask_head bias preset to 0.5 (not 0.0) — without this shift, sigmoid(random-logit) is noisy around 0.5 and the threshold+area filter in Plan 05 could drop everything"
  - "Non-dummy weight branches raise NotImplementedError (not return dummy silently) — the strategy switch must be loud"
  - "ml/cli.py lazy-imports run_inference inside main() so --help works in Wave 2 before Plan 05 creates inference.py"
  - "Physics/mission stubs return schema-valid empty envelopes (not raise) so the full CLI chain ml -> physics -> mission round-trips JSON cleanly before Phase 2"
  - "Mission route placeholder is a degenerate LineString (two identical origin points) — valid GeoJSON, no Shapely special-casing needed"

patterns-established:
  - "Strategy weight loader with fail-loud unimplemented branches"
  - "Lazy import inside CLI main() for cross-wave module dependencies"
  - "Schema-valid-empty stubs returning pydantic models instead of raising"

requirements-completed: [INFRA-04, INFRA-06, ML-03]

duration: 2min
completed: 2026-04-17
---

# Phase 01 Plan 04: Model + Weight Loader + CLIs + Stubs Summary

**Shipped DualHeadUNetpp (UNet++ resnet18 + SCSE + dual heads), the strategy weight loader (dummy works, other branches fail-loud), three CLI entrypoints (`python -m backend.{ml,physics,mission}`), and schema-valid Phase 1 stubs for `forecast_drift` and `plan_mission` — every piece of the dummy pipeline wired up except the actual inference orchestration (which lands in Plan 05).**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-17T11:31:57Z
- **Completed:** 2026-04-17T11:34:05Z
- **Tasks:** 2 of 2
- **Files created:** 12 (2 ml source, 2 ml cli, 4 physics, 4 mission)

## Accomplishments

- `backend/ml/model.py` — `DualHeadUNetpp` class verbatim from RESEARCH.md Pattern 5. `smp.UnetPlusPlus(resnet18, imagenet, in_channels=14, classes=16, decoder_attention_type='scse')` + two 1x1 Conv heads. Forward returns `{mask_logit, fraction}` dict; fraction already sigmoid-applied.
- `backend/ml/weights.py` — strategy loader. `dummy` branch: seeds torch, instantiates model, asserts `conv1.weight.std() > 1e-4` (observed 0.028, tiled-pretrained), presets `mask_head.bias` to 0.5 for non-empty polygons, returns in `.eval()` mode. `marccoru_baseline` + `our_real` branches raise `NotImplementedError` with specific guidance. Unknown values raise `ValueError`.
- `backend/ml/cli.py` + `__main__.py` — `python -m backend.ml tile.tif [--out path]` with lazy import of `run_inference` so `--help` works even though `backend/ml/inference.py` does not yet exist (Plan 05, Wave 3).
- `backend/physics/{__init__,tracker,cli,__main__}.py` — stub `forecast_drift(fc, cfg)` returns `ForecastEnvelope(source_detections=fc, frames=[], windage_alpha=cfg.physics.windage_alpha)`. CLI `python -m backend.physics det.json [--out path]` parses the detection FC, pipes through stub, emits envelope JSON.
- `backend/mission/{__init__,planner,cli,__main__}.py` — stub `plan_mission(envelope, ...)` returns `MissionPlan(waypoints=[], route=<degenerate LineString at origin>, total_distance_km=0, total_hours=0, origin=(lon,lat))`. CLI `python -m backend.mission forecast.json [--vessel-range-km N] [--hours N] [--origin lon,lat] [--out path]`.
- All three CLIs exit 0 on `--help`. All three CLI tools accept input from the previous stage's JSON output, so the chain `ml | physics | mission` will round-trip cleanly once Plan 05 lands `run_inference`.

## Task Commits

1. **Task 1: model.py + weights.py** — `1edbf87` (feat)
2. **Task 2: 3 CLI entrypoints + physics/mission stubs** — `9c556a4` (feat)

## Files Created/Modified

All 12 files listed in `key-files.created`. None modified.

## Verification

- `DualHeadUNetpp()` instantiates; `encoder.conv1.weight.std() = 0.0282` (>> 1e-4 threshold).
- `DualHeadUNetpp()(torch.zeros(1, 14, 64, 64))` returns dict with both `mask_logit` and `fraction` keys.
- `load_weights(Settings())` returns a module in `.eval()` mode.
- `ML__WEIGHTS_SOURCE=our_real python -c '…load_weights(Settings())'` raises `NotImplementedError` with Phase-3-kagglehub message.
- `python -m backend.ml --help` exits 0 (lazy import of `run_inference` does NOT trigger on `--help`).
- `python -m backend.physics --help` exits 0.
- `python -m backend.mission --help` exits 0.
- `forecast_drift(empty_fc, Settings())` returns `ForecastEnvelope` with `frames == []`.
- `plan_mission(envelope, cfg=Settings())` returns `MissionPlan` with `waypoints == []` and route coords length 2.

## Decisions Made

- Mask head stays raw logits (Plan 05 threshold-and-filter logic decides); fraction head sigmoid is baked into the model forward (it's bounded by construction).
- `mask_head.bias = 0.5` bias preset is critical for Phase 1 dummy demo: without it, random-weight sigmoid yields mean ~0.5 and the Plan 05 `threshold + min_area` filter can nuke every polygon, breaking the strict `n > 0` integration assertion.
- Non-dummy branches raise rather than fall back to dummy: the strategy switch must be unambiguous. Flipping YAML to a weight source we haven't built should produce a loud error, not silent wrong output.
- Lazy-import pattern inside `ml/cli.py:main()` — NOT at module top level — is the right Wave 2/Wave 3 split: `--help` and `argparse.ArgumentParser` run without touching `backend.ml.inference`, which does not exist until Plan 05 commits.
- Physics and mission stubs return schema-valid empty envelopes instead of raising. This lets the full CLI chain round-trip JSON before the real implementations land, and it gives Plan 05's end-to-end smoke test a deterministic post-ML stage to pipe into.
- Mission route uses a degenerate LineString (two identical origin points) — valid GeoJSON per the spec (LineString requires >=2 positions), schema-validates cleanly through `Feature[LineString, dict]`, no Shapely special-casing needed for the stub.

## Deviations from Plan

None — plan executed exactly as written. Code blocks in the plan were copied verbatim; all acceptance criteria met on first run (conv1 std = 0.028 matches Probe 3's prediction, `ML__WEIGHTS_SOURCE=our_real` raises correctly, all three `--help` commands exit 0, stubs schema-validate).

## Authentication Gates

None encountered.

## Known Stubs

Intentional Phase 1 stubs (documented in plan; real implementations scheduled):

- `backend/physics/tracker.py::forecast_drift` — returns empty-frames `ForecastEnvelope`. Real Euler Lagrangian tracker (UTM-meter integration, 20 particles per detection, 72 h horizon, CMEMS + ERA5) arrives in Phase 2.
- `backend/mission/planner.py::plan_mission` — returns empty-waypoints `MissionPlan` with degenerate LineString. Real greedy + 2-opt TSP planner with priority scoring and vessel-range/time-budget constraints arrives in Phase 2.

Both stubs return schema-valid pydantic models; downstream consumers will not discover they are stubs until they inspect `.frames` or `.waypoints`. Documented here and in the code docstrings.

Also pending (Wave 3, Plan 05):

- `backend/ml/inference.py::run_inference` — does not yet exist. `backend/ml/cli.py` imports it lazily inside `main()`; `python -m backend.ml --help` works, but `python -m backend.ml tile.tif` exits with code 2 and the message "Error: inference module not available yet" until Plan 05 commits.

## Next Phase Readiness

- Plan 05 can now:
  - `from backend.ml.weights import load_weights` → returns a ready-to-eval model with biased mask head.
  - Write `backend/ml/inference.py::run_inference(tile_path, cfg) -> DetectionFeatureCollection` knowing the CLI (`backend/ml/cli.py`) will wire it up automatically via the lazy import.
  - Pipe `run_inference` output through `forecast_drift` (stub) and `plan_mission` (stub) to demonstrate the full end-to-end chain returning schema-valid output — Phase 1 core value unlocked.
- Phase 2 physics and mission planners can replace the stub bodies without touching any caller: signatures, return types, and CLI argparse are all stable.
- Phase 3 weight swap is a one-line YAML flip (`weights_source: our_real`) once the `NotImplementedError` is replaced with kagglehub-download-and-load code.

## Self-Check: PASSED

- FOUND: `backend/ml/model.py`
- FOUND: `backend/ml/weights.py`
- FOUND: `backend/ml/cli.py`
- FOUND: `backend/ml/__main__.py`
- FOUND: `backend/physics/__init__.py`
- FOUND: `backend/physics/tracker.py`
- FOUND: `backend/physics/cli.py`
- FOUND: `backend/physics/__main__.py`
- FOUND: `backend/mission/__init__.py`
- FOUND: `backend/mission/planner.py`
- FOUND: `backend/mission/cli.py`
- FOUND: `backend/mission/__main__.py`
- FOUND commit: `1edbf87` (Task 1)
- FOUND commit: `9c556a4` (Task 2)

---
*Phase: 01-schema-foundation-dummy-inference*
*Plan: 04*
*Completed: 2026-04-17*
