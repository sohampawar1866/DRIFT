---
phase: 01-schema-foundation-dummy-inference
plan: 03
subsystem: ml/features
tags: [features, spectral-indices, FDI, NDVI, PI, numpy, tdd]
requires: []
provides:
  - "backend.ml.features.compute_fdi"
  - "backend.ml.features.compute_ndvi"
  - "backend.ml.features.compute_pi"
  - "backend.ml.features.feature_stack"
  - "backend.ml.features.{B2,B3,B4,B5,B6,B7,B8,B8A,B11,B12}_IDX"
  - "backend.ml.features.COEF_FDI"
affects:
  - "Plan 05 inference.py (will import feature_stack)"
  - "Phase 3 dataset.py (will import feature_stack to prevent train/serve skew)"
tech_added: []
patterns:
  - "Pure-numpy, zero-ML-deps module as single source of truth for spectral index math"
  - "Centralized band-index constants for single-point update when probe refines ordering"
  - "TDD: Biermann reference pixel as the non-negotiable unit test for ML-01"
key_files:
  created:
    - "backend/ml/__init__.py"
    - "backend/ml/features.py"
    - "backend/tests/__init__.py"
    - "backend/tests/unit/__init__.py"
    - "backend/tests/unit/test_features.py"
  modified: []
decisions:
  - "Fall back to MARIDA documented band ordering (B2..SCL) because wave0-probe-results.md was not present at authoring time; indices are centralized in one module so a later probe result requires a single-point edit"
  - "FDI tolerance tightened to 0.001 (from ROADMAP's 0.005) — code path is deterministic numpy, so a tighter bound gives earlier signal if wavelengths ever drift"
metrics:
  duration_seconds: 87
  completed_at: "2026-04-17T11:15:17Z"
  tasks_completed: 1
  files_created: 5
  files_modified: 0
  commits: 2
  tests_added: 7
  tests_passing: 7
requirements: [ML-01]
---

# Phase 1 Plan 3: Spectral Feature Module Summary

Shipped `backend/ml/features.py` — a pure-numpy module that computes FDI (Biermann 2020), NDVI, and PI (Themistocleous 2020) and assembles the 14-channel `(H, W, 11 bands + FDI + NDVI + PI)` tensor consumed downstream by inference and training. The Biermann reference-pixel FDI test passes within 0.001 tolerance, locking down the math for both the Phase 1 dummy inference path and the Phase 3 real training loop so they cannot drift.

## What Was Built

- **`backend/ml/features.py`** — 83-line pure-numpy module.
  - `compute_fdi(bands)` — Biermann 2020 eq. 2. Interpolates the NIR baseline between RE2 (B6) and SWIR1 (B11) using S2 central wavelengths; `COEF_FDI ≈ 0.10601`.
  - `compute_ndvi(bands)` — `(NIR − Red) / (NIR + Red + eps)`.
  - `compute_pi(bands)` — `NIR / (NIR + Red + eps)`.
  - `feature_stack(bands)` — accepts `(H, W, N)` with `N ≥ 11`; drops SCL/extras; returns `(H, W, 14)` float32.
  - Band index constants `B2_IDX..B12_IDX` using MARIDA documented ordering.
- **`backend/tests/unit/test_features.py`** — 7 unit tests covering the Biermann reference pixel, FDI zero case, NDVI/PI water-pixel ranges, feature_stack shape/dtype, SCL drop, and finite-values guarantee.
- **Package markers** — `backend/ml/__init__.py`, `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`.

## TDD Flow

| Phase | Commit | Tests |
|-------|--------|-------|
| RED   | `089ae7a` test(01-03): add failing tests | 7 tests authored; collection fails on `ModuleNotFoundError: backend.ml.features` |
| GREEN | `6051a0c` feat(01-03): implement features | 7/7 passing in 0.59 s |
| REFACTOR | skipped | implementation is the minimal clean form |

## Acceptance Criteria

- [x] `backend/ml/features.py` exists and imports cleanly (`python -c "from backend.ml.features import compute_fdi, feature_stack, B6_IDX"` → `OK 4`).
- [x] `test_fdi_biermann_reference` passes — the non-negotiable ML-01 exit criterion.
- [x] All 7 unit tests pass.
- [x] `COEF_FDI` constant present.
- [x] `compute_fdi`, `feature_stack` functions present.
- [x] Band index constants (`B4_IDX=2`, `B6_IDX=4`, `B8_IDX=6`, `B11_IDX=8`) present, match MARIDA documented ordering.

## Key Decisions

- **MARIDA documented band ordering used (fallback)**: `.planning/phases/01-schema-foundation-dummy-inference/wave0-probe-results.md` was not present at authoring time. Per the plan's Step 2 instructions, fell back to the documented ordering `[B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12, SCL]`. Because all consumers (training dataset, inference) import these constants from this one module, a future probe result requires only a single-point edit here — no risk of train/serve skew.
- **Tolerance 0.001 on the Biermann FDI test** (vs. 0.005 in ROADMAP): the computation is deterministic pure-numpy, so a tighter bound gives earlier signal if wavelengths or the coefficient are ever tampered with.
- **Single source of truth, pure-numpy**: zero torch/sklearn deps. Safe to import in the most minimal serving environment.

## Deviations from Plan

None — plan executed exactly as written. Fallback path for missing `wave0-probe-results.md` was explicitly authorized in the plan's Step 2.

## Requirements Closed

- **ML-01** — Feature engineering module (FDI/NDVI/PI + 14-channel stack) with Biermann 2020 reference pixel unit test.

## Files Changed

- Created: `backend/ml/__init__.py`, `backend/ml/features.py`, `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/unit/test_features.py`

## Known Stubs

None. Both training and inference can import `feature_stack` directly; no placeholder data paths.

## Self-Check: PASSED

- FOUND: `backend/ml/__init__.py`
- FOUND: `backend/ml/features.py`
- FOUND: `backend/tests/__init__.py`
- FOUND: `backend/tests/unit/__init__.py`
- FOUND: `backend/tests/unit/test_features.py`
- FOUND commit: `089ae7a` (RED)
- FOUND commit: `6051a0c` (GREEN)
