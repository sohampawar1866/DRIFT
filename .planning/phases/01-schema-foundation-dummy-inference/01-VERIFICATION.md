---
phase: 01-schema-foundation-dummy-inference
verified: 2026-04-17T00:00:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 1: Schema Foundation + Dummy Inference — Verification Report

**Phase Goal:** Freeze the `DetectionProperties` pydantic contract in git and ship a `run_inference(tile) -> DetectionFeatureCollection` that returns schema-valid GeoJSON on random-initialized weights — unblocking Phase 2 physics + mission modules immediately.

**Verified:** 2026-04-17
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `DetectionProperties` frozen, `extra="forbid"`, 6 required fields, `class` aliased, round-trip test passes | VERIFIED | `backend/core/schemas.py:12-32` has `extra="forbid", frozen=True, populate_by_name=True` and all 6 fields with `class` alias; `tests/unit/test_schemas.py` — 5/5 tests pass including `test_feature_collection_round_trip` over 10 features |
| 2 | `python -m backend.ml <MARIDA_patch>` emits pydantic-valid FC; every polygon has 6 props, `conf_raw` finite in [0,1], `area_m2 >= MIN_AREA_M2` | VERIFIED | End-to-end run against `MARIDA/patches/S2_1-12-19_48MYU/S2_1-12-19_48MYU_0.tif` produced valid FC JSON; `tests/integration/test_inference_dummy.py` — 3/3 tests pass (schema round-trip, polygon count sane, properties in bounds including `area_m2 >= cfg.ml.min_area_m2`) |
| 3 | `features.py` FDI Biermann 2020 reference within 0.001; single source of truth for `feature_stack` | VERIFIED | `tests/unit/test_features.py::test_fdi_biermann_reference` passes (EXPECTED_FDI=0.01859 within tolerance 0.001). `feature_stack` defined only in `backend/ml/features.py:69`; imported by `backend/ml/inference.py:29`. Note: `dataset.py` (Phase 3/ML-02) not yet created, so the "invoked from both" clause is partially applicable — current sole consumer is inference.py which is correct for Phase 1 scope |
| 4 | `config.py` loads `config.yaml` via pydantic-settings with nested `MLSettings`/`PhysicsSettings`/`MissionSettings`; env-var override works | VERIFIED | `backend/core/config.py:54-79` defines `Settings(BaseSettings)` with `YamlConfigSettingsSource`, `env_nested_delimiter="__"`, nested sub-models; `tests/unit/test_config.py` — 4/4 tests pass including `test_env_override_ml_weights_source` and `test_env_override_nested_physics` |
| 5 | CLI entrypoints run: `python -m backend.ml`, `python -m backend.physics`, `python -m backend.mission` — all parse args, load Settings, call module function | VERIFIED | All three `--help` invocations succeed; full chain executed: `python -m backend.ml <tile> --out detections.json` → `python -m backend.physics detections.json --out forecast.json` → `python -m backend.mission forecast.json --out mission.json` all produced valid output; physics/mission are stubs (empty FC/empty waypoints) as Phase 1 permits |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/core/schemas.py` | `DetectionProperties` frozen pydantic + FC/Forecast/Mission companions | VERIFIED | 71 lines; all 4 required schemas present (DetectionProperties, DetectionFeatureCollection, ForecastEnvelope, MissionPlan); `model_config = ConfigDict(extra="forbid", frozen=True)` |
| `backend/core/config.py` | pydantic-settings loading `config.yaml` + env-nested delimiter | VERIFIED | 79 lines; `settings_customise_sources` override present (the PITFALL 8 fix — YAML wouldn't load without it) |
| `backend/config.yaml` | YAML driving nested settings | VERIFIED | 25 lines; ml/physics/mission sections present |
| `backend/ml/features.py` | Pure-numpy FDI/NDVI/PI + feature_stack (single source of truth) | VERIFIED | 83 lines; Biermann 2020 COEF_FDI constant matches reference; feature_stack drops excess channels |
| `backend/ml/model.py` | DualHeadUNetpp with SMP UnetPlusPlus, resnet18 encoder, in_channels=14, SCSE attention | VERIFIED | 35 lines; matches ML-03 spec; scse decoder attention, dual heads (mask_logit + fraction) |
| `backend/ml/weights.py` | Strategy-pattern loader, dummy branch with seeded init + bias shift for non-empty outputs | VERIFIED | 51 lines; `torch.manual_seed(42)`, conv1-dead-init assertion, `mask_head.bias.data.fill_(0.5)` to guarantee non-empty dummy output; marccoru/our_real raise NotImplementedError |
| `backend/ml/inference.py` | `run_inference(tile, cfg) -> DetectionFeatureCollection` with sliding window + cosine stitch + polygonization | VERIFIED | 212 lines; connectivity=4 per PITFALL M9, `.buffer(0)` fix, UTM area, WGS84 reprojection |
| `backend/ml/cli.py` + `__main__.py` | CLI entrypoint | VERIFIED | `python -m backend.ml --help` works |
| `backend/physics/tracker.py` + cli.py | Stub `forecast_drift` returning schema-valid empty envelope | VERIFIED | Stub returns `ForecastEnvelope(source_detections=detections, frames=[], windage_alpha=cfg.physics.windage_alpha)` — JSON-roundtrips |
| `backend/mission/planner.py` + cli.py | Stub `plan_mission` returning schema-valid empty plan | VERIFIED | Stub returns degenerate LineString MissionPlan — schema-valid |
| `backend/pyproject.toml` | `requires-python = ">=3.10,<3.13"` per PITFALL mi2 | VERIFIED | `requires-python = ">=3.11,<3.13"` (within allowed range) |
| `.gitignore` | `MARIDA/`, `*.pth`, `*.ckpt` | VERIFIED | All three patterns present |
| `backend/tests/unit/test_schemas.py` | round-trip + extra-forbid + alias + frozen + bounds | VERIFIED | 5/5 tests pass |
| `backend/tests/unit/test_features.py` | Biermann FDI reference | VERIFIED | 7/7 tests pass |
| `backend/tests/unit/test_config.py` | YAML load + env override | VERIFIED | 4/4 tests pass |
| `backend/tests/integration/test_inference_dummy.py` | MARIDA dummy-inference round-trip + bounds | VERIFIED | 3/3 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| inference.py | features.feature_stack | import | WIRED | `from backend.ml.features import feature_stack` at line 29; invoked at line 193 |
| inference.py | weights.load_weights | import | WIRED | Line 30 import; called at line 196 |
| inference.py | schemas (DetectionFeature, DetectionFeatureCollection, DetectionProperties) | import | WIRED | Lines 24-28; all three used in `_polygonize` and `run_inference` |
| cli.py (ml) | inference.run_inference | lazy import | WIRED | Line 34 lazy import inside main(); called at line 38 |
| cli.py (physics) | tracker.forecast_drift | import | WIRED | Line 12; called line 24 |
| cli.py (mission) | planner.plan_mission | import | WIRED | Line 12; called line 29 |
| config.py | config.yaml | YamlConfigSettingsSource | WIRED | `settings_customise_sources` override present — verified via `test_yaml_loaded_by_default` passing |
| weights.py | model.DualHeadUNetpp | import | WIRED | Instantiated with `cfg.ml.in_channels` at line 21 |
| YAML → env override | ML__WEIGHTS_SOURCE | `env_nested_delimiter="__"` | WIRED | Verified by `test_env_override_ml_weights_source` and `test_env_override_nested_physics` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `run_inference` output | `features` list | `_polygonize(prob, frac, ...)` from real sliding-window forward over real MARIDA tile bands | Yes — E2E run on `S2_1-12-19_48MYU_0.tif` produced a FeatureCollection with ≥1 valid feature (confirmed by 0 < N < 500 assertion) | FLOWING |
| `forecast_drift` (stub) | `frames` | Hardcoded `[]` | No (intentional Phase 1 stub — Phase 2 replaces) | STATIC (by design, documented in docstring and ROADMAP SC5) |
| `plan_mission` (stub) | `waypoints` | Hardcoded `[]` + degenerate LineString | No (intentional Phase 1 stub — Phase 2 replaces) | STATIC (by design) |

Phase 1 ROADMAP Success Criterion #5 explicitly permits physics+mission to be stubs: "physics+mission can be stubs returning empty FC at this point; ML must do real polygonization." ML pipeline produces real data; stubs are acceptable.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `pytest backend/tests/ -x` | 19 passed, 0 failed | PASS |
| ML CLI help | `python -m backend.ml --help` | Usage printed | PASS |
| Physics CLI help | `python -m backend.physics --help` | Usage printed | PASS |
| Mission CLI help | `python -m backend.mission --help` | Usage printed | PASS |
| Full E2E chain on real MARIDA tile | `python -m backend.ml S2_1-12-19_48MYU_0.tif --out /tmp/detections.json && python -m backend.physics … && python -m backend.mission …` | All three stages produced schema-valid JSON (42+46+25 lines); no exceptions | PASS |

### Requirements Coverage

All 8 Phase 1 requirement IDs declared in ROADMAP cross-referenced against REQUIREMENTS.md and plan frontmatter.

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| INFRA-01 | Frozen `DetectionProperties` pydantic, extra=forbid, frozen=True, 6 fields, aliased class | SATISFIED | `backend/core/schemas.py:12-32`; `test_schemas.py` 5/5 pass |
| INFRA-02 | Typed `DetectionFeatureCollection` + Forecast/Mission companions via geojson-pydantic | SATISFIED | `schemas.py:36-71`; round-trip passes |
| INFRA-03 | `config.py` pydantic-settings + `config.yaml` + env `__` delimiter | SATISFIED | `config.py`; `test_config.py` 4/4 pass |
| INFRA-04 | Strategy-pattern weight loader switching on `cfg.ml.weights_source` | SATISFIED | `weights.py:16-51` dispatches dummy/marccoru/our_real |
| INFRA-06 | CLI entrypoints `python -m backend.{ml,physics,mission}` | SATISFIED | All three `--help` and full chain invocations verified |
| ML-01 | `features.py` FDI/NDVI/PI + Biermann 2020 unit test | SATISFIED | `features.py` + `test_features.py::test_fdi_biermann_reference` passes |
| ML-03 | `model.py` UnetPlusPlus resnet18 in_channels=14 + dual heads + SCSE attention + conv1 std assert | SATISFIED | `model.py:19-28` + `weights.py:25-28` assertion on `conv1.weight.std() > 1e-4` |
| ML-04 | `inference.py` sliding-window + cosine stitch + polygonization (connectivity=4, buffer(0), MIN_AREA_M2) with `dummy` weights | SATISFIED | `inference.py` 212 lines; integration test 3/3 pass on real MARIDA tile |

No orphaned requirements: REQUIREMENTS.md maps exactly INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-06, ML-01, ML-03, ML-04 to Phase 1 — identical to the set provided.

### Anti-Patterns Found

Scanned all Phase 1 files in `backend/core/`, `backend/ml/`, `backend/physics/`, `backend/mission/`, `backend/tests/`:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/physics/tracker.py` | 14-22 | Stub returning `frames=[]` | Info | Intentional Phase 1 stub, documented in docstring and ROADMAP SC5; Phase 2 replaces |
| `backend/mission/planner.py` | 18-32 | Stub returning `waypoints=[]` + degenerate LineString | Info | Intentional Phase 1 stub, documented; Phase 2 replaces |

No blocker or warning anti-patterns. TODO/FIXME/placeholder comments: none found. Hardcoded `[]` in production ML code path: none. Console-log-only handlers: none (not applicable to Python ML module).

### Human Verification Required

None. All Phase 1 success criteria are automatable and have been verified programmatically.

### Gaps Summary

No gaps. Phase 1 is complete:

- Schema contract is frozen in git (`DetectionProperties` with `frozen=True, extra="forbid"`, 6 fields including aliased `class`, round-trip verified over 10 samples).
- `run_inference` runs end-to-end on a real MARIDA tile (`S2_1-12-19_48MYU_0.tif`) with dummy weights, producing a schema-valid `DetectionFeatureCollection` with polygons meeting `area_m2 >= MIN_AREA_M2` and all pydantic bounds.
- FDI Biermann 2020 reference test passes within the 0.001 tolerance.
- Pydantic-settings loads `config.yaml` correctly (with the critical `settings_customise_sources` override per PITFALL 8); env-nested overrides work (`ML__WEIGHTS_SOURCE`, `PHYSICS__WINDAGE_ALPHA`).
- All three CLI entrypoints (`python -m backend.{ml,physics,mission}`) execute the full dummy-branch chain.
- Physics and Mission modules are stubs by explicit ROADMAP design; they return schema-valid empty envelopes so the chain JSON-roundtrips cleanly — exactly what Phase 2 needs to start work in parallel.

All 8 Phase 1 requirement IDs (INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-06, ML-01, ML-03, ML-04) are satisfied with code-level evidence and passing tests (19/19).

Minor note (non-blocking): SC#3 describes `feature_stack` being "invoked from both `dataset.py` and `inference.py`". `backend/ml/dataset.py` does not exist yet because ML-02 is Phase 3, not Phase 1. The single-source-of-truth invariant still holds — `feature_stack` is defined exactly once in `backend/ml/features.py`, and the sole current consumer (`inference.py`) imports from there. Phase 3's `dataset.py` MUST import from the same module; if it reimplements the function locally, that would be a Phase 3 regression the verifier should catch then.

Phase 1 is ready to support Phase 2 (physics + mission) work in parallel.

---

_Verified: 2026-04-17_
_Verifier: Claude (gsd-verifier)_
