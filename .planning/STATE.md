# Project State: DRIFT / PlastiTrack — Backend Intelligence

**Initialized:** 2026-04-17
**Mode:** YOLO (coarse granularity, parallelization enabled)

## Project Reference

**Core Value:** `run_inference(tile) -> forecast_drift(detections) -> plan_mission(forecast)` produces a schema-valid cleanup mission from a real Sentinel-2 tile in < 15 s on a CPU laptop, with MARIDA IoU >= 0.45.

**Current focus:** Roadmap complete. Ready to plan Phase 1 (Schema Foundation + Dummy Inference).

**Scope boundary:** Intelligence layer only. No FastAPI wiring. No frontend. The existing `backend/api/routes.py` mock stays untouched.

## Current Position

**Phase:** 0 -> 1 (transition point)
**Plan:** None yet
**Status:** Roadmap approved; ready for `/gsd:plan-phase 1`
**Progress:** `[----------]` 0% (0 of 3 phases complete)

Phase completion tracking:
- [ ] Phase 1: Schema Foundation + Dummy Inference
- [ ] Phase 2: Trajectory + Mission Planner
- [ ] Phase 3: Real Training + Weight Swap + Mission Export + E2E

## Performance Metrics

Populated as phases complete.

| Phase | Plans Complete | Nodes Complete | Start | End | Duration |
|-------|---------------|----------------|-------|-----|----------|
| 1 | 0 | 0 | - | - | - |
| 2 | 0 | 0 | - | - | - |
| 3 | 0 | 0 | - | - | - |

### Detection Metrics (Phase 3 exit targets — PRD Section 11.1)

| Metric | Target | Actual |
|--------|--------|--------|
| MARIDA val IoU (binary plastic) | >= 0.45 | pending |
| Precision @ conf > 0.7 | >= 0.75 | pending |
| Sub-pixel fraction MAE (synthetic val) | <= 0.15 | pending |
| Sargassum (class 2/3) false-positive rate | <= 15% | pending |
| Inference latency (256x256 CPU) | <= 5 s | pending |

### Physics Metrics (Phase 2 exit targets)

| Metric | Target | Actual |
|--------|--------|--------|
| Synthetic 0.5 m/s eastward x 24h displacement | 43.2 km +/- 1% | pending |
| Zero-field 72 h displacement | < 100 m | pending |
| Real-data smoke (Gulf of Mannar) | all 10 particles in Indian Ocean basin | pending |

### Integration Metrics (Phase 3 exit targets — PRD Core Value)

| Metric | Target | Actual |
|--------|--------|--------|
| Full chain wall-clock (CPU laptop) | < 15 s | pending |
| Schema validity (all three public fns) | 100% pydantic validation pass | pending |
| PDF briefing size | < 1 MB | pending |
| PDF briefing generation latency | < 3 s | pending |
| Determinism | byte-identical on same seed | pending |

## Accumulated Context

### Key Decisions (carried forward)

| Decision | Phase | Rationale |
|----------|-------|-----------|
| Scope milestone to intelligence-only (no FastAPI wiring, no frontend) | Pre-roadmap | User instruction 2026-04-17: "plan about only the intelligence part. Leave the API and frontend" |
| Three-phase split: (1) Schema + Dummy, (2) Trajectory + Mission, (3) Real Training + Swap + Export + E2E | Roadmap | SUMMARY.md recommendation + PROJECT.md Key Decisions. Dummy-first de-risks schema drift before Kaggle GPU budget commits. |
| Phase 1 weights default = `dummy` (random init), NOT marccoru baseline | Phase 1 | PITFALLS.md: marccoru weights on private Google Drive since Aug 2024 — not auto-fetchable. `dummy` branch yields schema-valid outputs immediately, unblocks Phase 2. |
| UTM-meter Lagrangian integration, not lon/lat degrees | Phase 2 | PITFALL C4: degrees + m/s moves particles 55 km per second. UTM is the only safe integration frame. |
| Kaggle as training target (not Colab or local) | Phase 3 | Free P100/T4 GPU; notebook already scaffolded (`kaggle.yml`, `kernel-metadata.json`). GPU must be flipped `enable_gpu: true` before Phase 3 starts. |
| Euler Lagrangian tracker, alpha=0.02 windage, no Stokes drift | Phase 2 | PRD Section 4: 72 h horizons tolerate it. OpenDrift is overkill for 48 h build. |
| Biofouling: synthetic NIR x [0.5, 1.0] augmentation (40% of positives, on plastic-masked pixels only) + `conf_adj = conf_raw * exp(-age/30)` inference decay | Phase 3 | Defensible without over-claiming (PRD Section 8.4). |
| Schema freeze at end of Phase 1 | Phase 1 | PITFALL C5: schema drift between dummy and real output is the #1 cost-of-rewrite bug class. Any post-Phase-1 field edit requires explicit unfreeze. |
| UNet++ (resnet18 encoder) with SE attention + dual head over ViT/Segformer | Phase 3 | MARIDA 1,381 patches too small for ViT; UNet++ with pretrained encoder is the defensible sweet spot (PRD Section 8.1). |
| `kagglehub` model upload/download for checkpoint transfer | Phase 3 | PITFALL M12: git LFS is quota-fragile under hackathon pressure; GitHub 100 MB limit blocks `.pth` commits. kagglehub is auth-already-done and offline-cached at `~/.cache/kagglehub/`. |

### Risk Log (active)

| Risk | Phase | Status | Mitigation |
|------|-------|--------|------------|
| Schema drift between dummy and real inference outputs | 1 -> 3 | Open | Pydantic `extra="forbid"` validator at every stage boundary; tests/unit/test_schemas.py enforces round-trip; git-committed schema at Phase 1 exit |
| CMEMS + ERA5 NetCDFs not yet downloaded | 2 | Open (BLOCKER for Phase 2 real-data tests) | Run `scripts/fetch_demo_env.py` at H+0 in background; fallback: synthetic xarray fixtures in pytest if live fetch fails |
| Kaggle `enable_gpu: false` currently | 3 | Open (BLOCKER for Phase 3) | Flip to `true` in `kaggle.yml` **before Phase 3 starts**; first cell of notebook asserts `torch.cuda.is_available()` |
| Kaggle GPU assignment non-deterministic (P100 vs T4x2) | 3 | Open | No `torch.compile`, no `bfloat16`; use `fp16 autocast` + `GradScaler` only |
| marccoru weights on private Google Drive | Optional | Open | `dummy` is Phase 1 default, NOT marccoru; `marccoru_baseline` is optional Phase 2 bonus requiring manual Drive download; not on critical path |
| 24-48 h deadline + feature freeze at H+36 | All | Open | Runtime freeze at H+32; precomputed 4-AOI fallbacks by H+28; 60 s screen recording by H+36 |
| Demo laptop crash / Docker / CUDA | 3 demo | Open (PITFALL C7) | No Docker this milestone; no `pip install` after H+32; precomputed fallbacks at `data/prebaked/*.json`; fallback code path activates if live inference fails |
| MARIDA/ not in .gitignore (4.5 GB accidental push) | 1 | Open (mi3) | Fix at H+0 before any `git add`; add `MARIDA/`, `*.pth`, `*.ckpt` to `.gitignore` |
| S2 L2A BOA_ADD_OFFSET bug on post-2022-01-25 tiles | 1 | Open (C1) | Parse `BOA_ADD_OFFSET_VALUES_LIST` from scene metadata; unit test known water pixel B8 ~ 0.08 not ~ -0.02 |

### Todos (cross-phase)

Collected during research; addressed in their respective phases.

- [ ] **Phase 1 kickoff**: flip `kaggle.yml` `enable_gpu: true` (preparatory; actual use is Phase 3)
- [ ] **Phase 1 kickoff**: add `MARIDA/`, `*.pth`, `*.ckpt` to `.gitignore` BEFORE any `git add`
- [ ] **Phase 1 kickoff**: start `scripts/fetch_demo_env.py` in background (20-40 min CMEMS download)
- [ ] **Phase 1 kickoff**: verify MARIDA `.tif` descriptions via `rasterio.open(...).descriptions` to confirm 11-band ordering
- [ ] **Phase 3 kickoff**: read marccoru `hubconf.py` to confirm 12-band ordering (needed only if falling back to `marccoru_baseline`)
- [ ] **Phase 3 kickoff**: inspect `model.encoder.conv1.weight.std()` after `smp.UnetPlusPlus(in_channels=14)`; apply RGB-head init if random (~0.1), leave alone if tiled-pretrained (~0.02)
- [ ] **Phase 3 exit**: precompute 4-AOI fallback JSONs at `data/prebaked/*_{detections,forecast,mission}.json`
- [ ] **Phase 3 exit**: 60 s screen recording of successful end-to-end run

### Blockers

None at roadmap-complete state. Phase 1 is unblocked and ready to plan.

## Session Continuity

### Last Action
Roadmap created (`/gsd:new-project` orchestrator dispatched roadmapper; 3-phase structure approved; traceability validated at 25/25 mapped).

### Next Action
Run `/gsd:plan-phase 1` to decompose Phase 1 into executable plans. Start with the schema freeze (the unblocker for all Phase 2 parallel work).

### Files to Remember

| File | Purpose |
|------|---------|
| `.planning/PROJECT.md` | Core value, constraints, validated/active/out-of-scope requirements |
| `.planning/REQUIREMENTS.md` | 25 v1 requirements with traceability to phases |
| `.planning/ROADMAP.md` | 3-phase structure with success criteria and risk flags |
| `.planning/STATE.md` | This file — project memory across sessions |
| `.planning/research/SUMMARY.md` | Research synthesis (stack, features, architecture, pitfalls condensed) |
| `.planning/research/STACK.md` | Pinned library versions + Kaggle gotchas |
| `.planning/research/FEATURES.md` | T1-T13 table stakes, D1-D12 differentiators, anti-features |
| `.planning/research/ARCHITECTURE.md` | Module boundaries + frozen-schema discipline |
| `.planning/research/PITFALLS.md` | 18 pitfalls (7 critical + 10 moderate + 6 minor), phase-assigned |
| `.planning/codebase/` | Skeleton audit (STACK, INTEGRATIONS, ARCHITECTURE, STRUCTURE, CONVENTIONS, TESTING, CONCERNS) |
| `PRD.md` | Authoritative product requirements (540 lines) |
| `PPT_CONTENT.md` | Ideation deck content |
| `problem_statement.pdf` | Sankalp Bharat SKB_P5 official brief |
| `kaggle.yml` / `kernel-metadata.json` | Kaggle training kernel config (GPU flag flip required before Phase 3) |

### Context Budget

No context warnings yet. All research artifacts ready. Downstream `/gsd:plan-phase 1` invocation can proceed without additional research.

---

*STATE.md initialized: 2026-04-17 (after roadmap creation)*
*Next update: when `/gsd:plan-phase 1` completes*
