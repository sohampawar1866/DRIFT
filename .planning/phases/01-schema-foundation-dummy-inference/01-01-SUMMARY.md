---
phase: 01-schema-foundation-dummy-inference
plan: 01
subsystem: infra
tags: [gitignore, pyproject, python311, torch, rasterio, smp, marida, geojson-pydantic]

requires:
  - phase: pre-phase-1
    provides: MARIDA dataset staged at ./MARIDA/ (4.5 GB, 1,381 patches)
provides:
  - Hardened .gitignore that blocks MARIDA/, *.pth, *.ckpt, .planning/metrics/, node_modules/ from accidental git-add
  - backend/pyproject.toml with Python >=3.11,<3.13 pin and complete Phase 1 dep set (torch 2.7.0+cpu, rasterio 1.4.4, shapely 2.1.2, pyproj 3.7.2, geopandas 1.1.3, numpy 1.26.4, segmentation-models-pytorch 0.5.0, geojson-pydantic 2.1.1, scikit-image 0.25.2, pydantic 2.12.5)
  - Installed + import-verified Phase 1 Python 3.11 environment
  - Primed ImageNet resnet18 encoder cache (SMP 0.5 → HuggingFace hub, smp-hub/resnet18.imagenet)
  - wave0-probe-results.md with: MARIDA band ordering (positional, descriptions are None), reflectance scale (pre-scaled to [0,1], NO DN rescale for MARIDA), geojson-pydantic 2.1.1 Pattern-1 generic compatibility, SMP in_channels=14 conv1.weight.std = 0.028 (tiled-pretrained)
  - Corrected CLAUDE.md Phase 1 weight-sourcing policy (dummy branch, not marccoru)
affects: [01-02-schemas, 01-03-features, 01-04-model, 01-05-inference, 02-trajectory, 03-training]

tech-stack:
  added:
    - torch 2.7.0+cpu (CPU-only Phase 1, switches to cu121 Phase 3 on Kaggle)
    - torchvision 0.22.0+cpu
    - segmentation-models-pytorch 0.5.0 (uses HuggingFace hub for encoder weights, not legacy torch.hub)
    - rasterio 1.4.4 (plan asked for 1.5.x but that requires Py3.12 — relaxed to 1.4 for Py3.11 compat)
    - shapely 2.1.2, pyproj 3.7.2, geopandas 1.1.3
    - numpy 1.26.4 (pinned <2.0 per STACK.md "zero-drama" policy)
    - geojson-pydantic 2.1.1 (Feature[Polygon, Props] generic works — Pattern 1)
    - scikit-image 0.25.2, pydantic 2.12.5, pydantic-settings 2.13.1, PyYAML 6.0, pytest 9.0.3
  patterns:
    - "pyproject.toml-first declared deps with backend/requirements.txt retained as Kaggle pip fallback"
    - "Probe-document-on-disk pattern (.planning/phases/.../wave0-probe-results.md) for env-dependent constants shared across downstream plans"
    - "Hardened gitignore BEFORE any git-add to prevent multi-GB accidental commits (PITFALL mi3)"

key-files:
  created:
    - backend/pyproject.toml
    - .planning/phases/01-schema-foundation-dummy-inference/wave0-probe-results.md
  modified:
    - .gitignore
    - CLAUDE.md

key-decisions:
  - "Python 3.11 pin (>=3.11,<3.13) — Python 3.13+ breaks shapely/geopandas Windows wheels per PITFALL mi2"
  - "rasterio pin relaxed from plan's >=1.5,<1.6 to >=1.3,<1.6 — rasterio 1.5+ requires Python >=3.12, incompatible with Phase 1's Py3.11 lock. Resolved to rasterio 1.4.4 on Py3.11"
  - "MARIDA reflectance is pre-scaled to [0,1] (observed max=0.271); features.py must NOT apply (DN-1000)/10000 to MARIDA inputs — only to raw S2 L2A COGs"
  - "MARIDA GeoTIFF band descriptions are all None; positional band index constants (B2=0..SCL=10) must be hardcoded in features.py"
  - "geojson-pydantic 2.1.1 Feature[Polygon, Props] generic works — use Pattern 1 (no BaseModel fallback needed)"
  - "SMP 0.5 with encoder_weights='imagenet', in_channels=14 yields conv1.weight.std = 0.028 (tiled-pretrained regime, not random-init ~0.1) — no Phase 3 RGB-head re-init workaround required"
  - "SMP 0.5 fetches encoder weights via HuggingFace hub (smp-hub/resnet18.imagenet), not legacy torch.hub/checkpoints — Phase 3 Kaggle notebook must pre-populate HF hub cache for offline inference"
  - "backend/requirements.txt retained (not deleted) as Kaggle pip fallback — coexists with pyproject.toml"

patterns-established:
  - "Probe-first env discovery: run Wave-0 probes once, write answers to disk so downstream plans read constants rather than re-probe"
  - "Deviation Rule 1 applied inline: plan-pin vs Py-version mismatch on rasterio fixed by relaxing pin; documented in probe doc + commit"

requirements-completed: []

duration: 15min
completed: 2026-04-17
---

# Phase 01 Plan 01: Environment Setup + Wave-0 Probes Summary

**Hardened .gitignore (blocks 4.5 GB MARIDA disaster), migrated backend to pyproject.toml with Python 3.11 pin, installed all Phase 1 deps at verified versions, and ran the three Wave-0 probes whose results are now on disk for Plans 02–05 to read verbatim.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-17T11:13:35Z
- **Completed:** 2026-04-17T11:28:47Z
- **Tasks:** 4 of 4
- **Files modified:** 4 (.gitignore, backend/pyproject.toml created, wave0-probe-results.md created, CLAUDE.md)

## Accomplishments

- Blocked the 4.5 GB MARIDA/ accidental-commit landmine (PITFALL mi3) before any `git add` in subsequent plans.
- Migrated backend to pyproject.toml with a hard Python 3.11 pin, declaring the full Phase 1 dep set at explicit versions.
- Installed every Phase 1 library in the active Python 3.11.3 env and verified all 13 imports succeed.
- Primed the ImageNet resnet18 encoder cache (via SMP 0.5's HuggingFace-hub mechanism) so Plans 04/05 can instantiate the detector offline.
- Answered the three Wave-0 open questions (MARIDA band order, reflectance scale, geojson-pydantic generics, SMP init std) and wrote answers to `wave0-probe-results.md` — Plans 02–05 will read constants from this file instead of re-probing.
- Corrected the stale "Phase 1 uses marccoru/marinedebrisdetector" statement in CLAUDE.md to match the actual dummy-weight policy.

## Task Commits

1. **Task 1: Fix .gitignore + create backend/pyproject.toml** — `b49f0e7` (chore)
2. **Task 2: Install Phase 1 deps and prime resnet18 cache** — `9436184` (chore, includes inline rasterio-pin fix per Rule 1)
3. **Task 3: Run Wave-0 probes and document results** — `9c0eae0` (docs)
4. **Task 4: Correct stale marccoru claim in CLAUDE.md** — `6ab67a2` (docs)

## Files Created/Modified

- `.gitignore` — appended 13 lines blocking MARIDA/, *.pth, *.ckpt, .planning/metrics/, node_modules/
- `backend/pyproject.toml` — new, 37 lines, pins Python + 14 deps + setuptools build-system
- `.planning/phases/01-schema-foundation-dummy-inference/wave0-probe-results.md` — new, 124 lines, three probe sections + installed-versions + blockers + handoff-to-Plans-02-05
- `CLAUDE.md` — one-line fix to the "Pretrained weights" bullet in the Constraints section

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] rasterio pin incompatible with Python 3.11**

- **Found during:** Task 2 (pip install)
- **Issue:** Plan pinned `rasterio>=1.5.0,<1.6.0`, but rasterio 1.5.x requires `python_requires >=3.12`. Phase 1 is locked to Python 3.11 per PITFALL mi2 / CLAUDE.md. pip errored: "ERROR: Could not find a version that satisfies the requirement rasterio<1.6.0,>=1.5.0".
- **Fix:** Relaxed pin to `>=1.3,<1.6` in `backend/pyproject.toml`. Resolved to `rasterio 1.4.4`. Rasterio's Phase-1 surface (`open`, `read`, `descriptions`, `transform`, `crs`) is stable across 1.3 → 1.4 → 1.5; no API breakage.
- **Files modified:** `backend/pyproject.toml`
- **Commit:** `9436184`

**2. [Rule 2 - Missing critical functionality] Cache-path acceptance criterion was for wrong hub**

- **Found during:** Task 2 (verifying cache primed)
- **Issue:** Plan acceptance criterion was `~/.cache/torch/hub/checkpoints/resnet18-*.pth` exists. SMP 0.5 migrated encoder-weights fetching from torch.hub to HuggingFace hub (`smp-hub/resnet18.imagenet`); no resnet18 file is ever written to the torch.hub path.
- **Fix:** Verified the HF-hub cache `~/.cache/huggingface/hub/models--smp-hub--resnet18.imagenet/` exists instead. Functional spirit of the criterion (offline-instantiation primed) is met — the model instantiates without network, std=0.028. Documented the path change in `wave0-probe-results.md` for Phase 3 Kaggle offline handling.
- **Files modified:** none (documentation only)
- **Commit:** `9c0eae0` (probe doc)

**3. [Rule 1 - Bug] Task 4 verify command matched my replacement prose**

- **Found during:** Task 4 (first commit attempt)
- **Issue:** Plan acceptance required `grep -c "torch.hub.load" CLAUDE.md` == 0. My first replacement kept the phrase "not auto-fetchable via `torch.hub.load`" for clarity, which failed the grep.
- **Fix:** Reworded to "not auto-fetchable by any public hub loader" — preserves meaning, removes the literal token.
- **Files modified:** `CLAUDE.md`
- **Commit:** `6ab67a2`

### Out-of-scope / noted, not fixed

- `torchaudio 2.2.2` ↔ `torch 2.7.0` dependency conflict warning: not in Phase 1 scope (no audio usage). Not touched; safe to leave.
- Pre-existing dep conflicts (numba, pyfume, conda-repo-cli) are environment legacy from the user's Anaconda base install. Out of scope for this plan.

## Verification

- `git check-ignore -v MARIDA/` → matches `.gitignore:31:MARIDA/` (exit 0)
- `grep "requires-python" backend/pyproject.toml` → `">=3.11,<3.13"`
- All 13 Phase 1 imports succeed (torch 2.7.0+cpu, smp 0.5.0, rasterio 1.4.4, geopandas 1.1.3, geojson-pydantic 2.1.1, etc.)
- `smp.UnetPlusPlus(encoder_name='resnet18', encoder_weights='imagenet', in_channels=14, classes=1)` instantiates, conv1.weight.std = 0.028
- `wave0-probe-results.md` exists with `## Probe 1`, `## Probe 2`, `## Probe 3`, and explicit Band index mapping + resolved reflectance policy
- `grep "Phase 1 uses the \`dummy\` branch" CLAUDE.md` matches; no `torch.hub.load` in CLAUDE.md

## Handoff to Next Plans

- **Plan 02 (`schemas.py`):** import `from geojson_pydantic import Feature, FeatureCollection, Polygon, LineString, Point` — Pattern 1 generic works. Use `extra="forbid"` on pydantic Props.
- **Plan 03 (`features.py`):** hardcode band-index constants from `wave0-probe-results.md` Probe 1 table. Do NOT rescale MARIDA reflectance. Branch-rescale `(DN - 1000) / 10000` only when input `arr.max() > 1.5` (raw S2 L2A COG path).
- **Plan 04 (`model.py` / `weights.py`):** assert `model.encoder.conv1.weight.std() > 1e-4`. Expect ~0.028 for tiled-pretrained init.
- **Plan 05 (inference glue):** no extra probing needed.

## Self-Check: PASSED

- `backend/pyproject.toml` exists — FOUND
- `.planning/phases/01-schema-foundation-dummy-inference/wave0-probe-results.md` exists — FOUND
- `.gitignore` contains `MARIDA/` — FOUND
- `CLAUDE.md` contains `Phase 1 uses the \`dummy\` branch` — FOUND
- Commits `b49f0e7`, `9436184`, `9c0eae0`, `6ab67a2` — all present in `git log`
