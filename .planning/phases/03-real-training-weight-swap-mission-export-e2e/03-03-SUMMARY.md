---
phase: 03-real-training-weight-swap-mission-export-e2e
plan: 03
subsystem: e2e
tags: [fallback, parity-hash, e2e-driver, determinism, demo-safety]
requires:
  - path: "backend/core/schemas.py"
    from: "Phase 1 (frozen contracts)"
  - path: "tests/fixtures/synthetic_mission.py"
    from: "Phase 3 Plan 02 (synthetic MissionPlan/ForecastEnvelope factories)"
provides:
  - path: "scripts/parity_hash.py"
    for: "D-14 parity hashing consumed by Plan 06 parity tests"
  - path: "scripts/run_full_chain_real.py"
    for: "Phase 3 E2E driver with silent auto-fallback (D-12)"
  - path: "tests/test_fallback.py"
    for: "Regression guard on the fallback escape-hatch behavior"
affects:
  - path: "data/prebaked/"
    how: "Defines the expected filename convention `{aoi}_{stage}.json` consumed by the driver (Plan 06 will populate)"
tech_stack:
  added: []
  patterns:
    - "Silent auto-fallback wrapper `_with_fallback(stage_name, aoi, live_fn, schema_cls, *, no_fallback)` -> `(result, elapsed_s, source)`"
    - "Schema-revalidate-on-reload: every prebake JSON is parsed through `schema_cls.model_validate` before being returned -- never trust stale disk"
    - "Deterministic parity hash = SHA-256(json.dumps(normalize_floats(model.model_dump(), 6), sort_keys=True))"
    - "Lazy imports in run_chain so `--help` does not pay ML startup cost"
key_files:
  created:
    - "scripts/parity_hash.py"
    - "scripts/run_full_chain_real.py"
    - "tests/test_fallback.py"
  modified: []
decisions:
  - "Added `_ROOT` sys.path shim to both scripts so they run as `python scripts/foo.py` AND are importable as `scripts.foo` (mirrors run_full_chain_dummy.py pattern)."
  - "parity_hash uses `separators=(',', ':')` for minimal canonical form -- deterministic and smaller than default whitespace-padded JSON."
  - "Exposed `parity_hash_json(raw_json_string)` in addition to `parity_hash(model)` so prebake reloads can be hashed without first re-parsing through pydantic."
  - "StageFailed is raised from _with_fallback -- caller (_main) translates to exit code 2; tests exercise it directly for clearer assertions."
metrics:
  duration_min: 7
  completed: "2026-04-17"
  tasks_total: 3
  tasks_done: 3
  commits: 3
---

# Phase 3 Plan 3: E2E Fallback Infrastructure + Parity Hash Summary

Shipped the Phase 3 demo-safety net: a silent auto-fallback wrapper at every stage boundary of `run_full_chain_real.py`, a deterministic SHA-256 parity hash helper (D-14), and six monkeypatch-based tests proving live-success, silent-fallback, `--no-fallback` re-raise, missing-prebake, and corrupt-prebake paths all behave as specified.

## Objective Met

Fallback infrastructure is complete and testable before Plan 06 runs: (a) `scripts/run_full_chain_real.py` wraps all three stages (`run_inference`, `forecast_drift`, `plan_mission`) in `_with_fallback`, schema-revalidates every prebake JSON before returning, supports `--no-fallback` for debugging, and exits 2 when live fails AND fallback is missing/invalid; (b) `scripts/parity_hash.py` exports `parity_hash`, `parity_hash_json`, and `normalize_floats` with stable 64-char hex output; (c) `tests/test_fallback.py` has 6 tests all passing in 14.07 s.

## What Was Built

### Task 1 — `scripts/parity_hash.py` (commit `d0d9476`)
- `normalize_floats(obj, ndigits=6)` recursively rounds every float in dicts/lists/tuples; handles scalar passthrough.
- `parity_hash(model)` = SHA-256 of `json.dumps(normalize_floats(model.model_dump()), sort_keys=True, separators=(',',':'))`; returns 64-char hex.
- `parity_hash_json(raw_json_string)` for use on prebake reloads (no pydantic round-trip required).
- Self-check verified: two successive `parity_hash(make_mission_plan())` calls produced identical hash `e8ad4d8927754ed1…`; `normalize_floats({'a': 1.234567891234})` rounded to `1.234568`; `normalize_floats({'b': [0.1+0.2]})` correctly collapses 0.30000000000000004 → 0.3.

### Task 2 — `scripts/run_full_chain_real.py` (commit `d701368`)
- `_with_fallback(stage_name, aoi, live_fn, schema_cls, *, no_fallback)` helper returns `(result, elapsed_s, source)` where `source ∈ {"live", "fallback"}`.
- On live success: logs `[OK] stage=... elapsed=...` and returns live result.
- On live exception: if `no_fallback=True`, re-raises; else logs `[FALLBACK] stage=... aoi=... reason=<ExcClass>: <msg>`, loads `data/prebaked/{aoi}_{stage}.json`, schema-validates via `schema_cls.model_validate`, returns validated fallback.
- Missing prebake file → `StageFailed` ("no prebaked fallback at …"); corrupt JSON / schema mismatch → `StageFailed` ("fallback schema invalid").
- `run_chain(aoi, tile_path, origin, cfg, *, no_fallback)` chains all three stages and returns `{detections, forecast, mission, timings, sources}`.
- CLI: `--tile`, `--aoi`, `--origin LON LAT`, `--no-fallback`, `--out-dir`. Lazy imports keep `--help` instantaneous.
- Verified `python scripts/run_full_chain_real.py --help` exits 0 with expected flags; module imports cleanly as `scripts.run_full_chain_real`.

### Task 3 — `tests/test_fallback.py` (commit `5c399e9`)
Six tests, all PASSED in 14.07 s:
1. `test_live_success_returns_live_sources` — monkeypatches all three stages to return valid pydantic objects; asserts `sources == {detections:"live", forecast:"live", mission:"live"}`.
2. `test_silent_fallback_on_detection_failure` — inference raises `RuntimeError("simulated inference OOM")`; forecast + mission live; asserts `sources.detections == "fallback"`, others `"live"`.
3. `test_no_fallback_flag_reraises` — with `no_fallback=True`, the `RuntimeError` propagates up through `run_chain`.
4. `test_fallback_missing_raises_stage_failed` — empty prebake dir → `StageFailed` with "no prebaked fallback".
5. `test_fallback_invalid_schema_raises_stage_failed` — writes `{"not":"a fc"}` as `gulf_of_mannar_detections.json`; asserts `StageFailed` with "fallback schema invalid".
6. `test_parity_hash_stable_across_runs` — two fresh `make_mission_plan()` calls hash identical; output length 64.

## Deviations from Plan

**None structural — plan executed exactly as written.**

Minor portability additions (not deviations in behavior):
- Added `sys.path` root-insert shim at the top of both scripts so they are runnable as `python scripts/foo.py` in addition to being importable from the project root. This mirrors the existing pattern in `scripts/run_full_chain_dummy.py` and is necessary on Windows/Git-Bash where `PYTHONPATH` is not auto-set.
- Added `sys.path` shim to `tests/test_fallback.py` as defensive insurance for non-root pytest invocations; pytest with `rootdir` auto-discovery already handles this, so it is a no-op in the standard case.

## Integration Notes

- **Plan 06 consumption:** Plan 06 (`prebake generation + parity tests`) must write three files per AOI at `data/prebaked/{aoi}_{detections|forecast|mission}.json`, matching `DetectionFeatureCollection`, `ForecastEnvelope`, and `MissionPlan` schemas respectively. Plan 06's parity tests should import from `scripts.parity_hash` and hash both the live and fallback outputs with the same `ndigits=6`.
- **Fallback filename convention:** `PREBAKE_DIR / f"{aoi}_{stage_name}.json"` where `stage_name ∈ {"detections","forecast","mission"}`. Any change requires synchronous edit to both the driver and the prebake generator.
- **Determinism gate:** parity_hash matches across runs ONLY if the underlying pydantic models are byte-identical modulo 6-decimal fp drift. Callers must set CPU determinism (`torch.set_num_threads(1)`, `torch.use_deterministic_algorithms(True)`, fixed seeds 1410) per Phase 3 research §Pitfall 8 before generating prebakes.

## Acceptance Criteria Check

- [x] `python -c "from scripts.parity_hash import parity_hash"` exits 0.
- [x] `parity_hash(same_model)` returns identical 64-char hex across two calls.
- [x] `normalize_floats({'a': 1.234567891234})['a'] == 1.234568`.
- [x] `python scripts/run_full_chain_real.py --help` exits 0 showing all 5 flags.
- [x] `_with_fallback` has 4 occurrences (1 def + 3 call sites).
- [x] `schema_cls.model_validate` gate present.
- [x] `[FALLBACK]` log line present.
- [x] `class StageFailed` present.
- [x] All 6 tests in `tests/test_fallback.py` PASS.

## Commits

| Task | Hash      | Message                                                               |
| ---- | --------- | --------------------------------------------------------------------- |
| 1    | `d0d9476` | feat(03-03): add parity_hash helper for deterministic model hashing   |
| 2    | `d701368` | feat(03-03): add run_full_chain_real with silent auto-fallback (D-12) |
| 3    | `5c399e9` | test(03-03): fallback behavior + parity hash stability tests          |

## Self-Check: PASSED

- Files verified on disk: `scripts/parity_hash.py` ✓, `scripts/run_full_chain_real.py` ✓, `tests/test_fallback.py` ✓.
- Commits verified in `git log`: `d0d9476` ✓, `d701368` ✓, `5c399e9` ✓.
- Tests verified green: `pytest tests/test_fallback.py` → 6 passed.
