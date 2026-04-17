# Phase 3: Real Training + Weight Swap + Mission Export + E2E — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the conversation that produced them.

**Date:** 2026-04-17
**Phase:** 03-real-training-weight-swap-mission-export-e2e
**Mode:** User-directed short-circuit (no gray-area selection)

---

## Conversation Summary

Claude presented 5 candidate gray areas for Phase 3:
1. PDF briefing design
2. Fallback activation policy
3. Training reproducibility & retry posture
4. Weight bundle UX on demo laptop
5. E2E < 15 s budget — degradation knobs order

**User response:** "ignore and write the context.md. Also you dont need to train the model I will give you the code just verify the code. I will also give you the pickle file of the trained model."

This collapsed the discussion — user short-circuited question selection AND delivered a material scope correction about training execution. Claude proceeded to write CONTEXT.md directly, applying the user's two directives plus pitfall-safe defaults for every other gray area.

---

## Scope Correction Captured

| Area | Original ROADMAP posture | User-directed posture |
|------|--------------------------|-----------------------|
| Training execution | Ship `backend/ml/train.py` to Kaggle, run 25 epochs, `kagglehub.model_upload` | User supplies training code + trained checkpoint. Claude reviews code + wires checkpoint. No Kaggle run by us. |
| Weight transfer | `kagglehub.model_download` → `~/.cache/kagglehub/` | Local file at `backend/ml/checkpoints/our_real.pt` (extension follows user's handoff). kagglehub becomes optional secondary path. |
| Metric targets on miss | Retrain (second "for keeps" attempt) | Log miss in `phase3.json`, continue. No retraining. |

---

## Defaults Applied (gray areas not discussed → Claude's defaults in CONTEXT.md)

| # | Gray area | Default chosen | Rationale |
|---|-----------|----------------|-----------|
| 1 | PDF briefing design | A4 portrait, 60/40 left-map/right-panels, offline Natural Earth coastline, matplotlib PNG → reportlab flowables, INCOIS-adjacent navy/cyan palette (Claude's discretion on exact colours) | Matches PRD §5/§8.6 (no headless Chrome) and offline-first demo posture. |
| 2 | Fallback activation | Automatic silent fallback on any E2E exception, `--no-fallback` escape hatch, `[FALLBACK]` log line per stage, MANIFEST.json freshness stamp | "Demo must not crash mid-pitch" — judges never see a stack trace. |
| 3 | Training reproducibility | User-supplied code + checkpoint; metric miss → log + continue, no retrain | User directive. |
| 4 | Weight bundle UX | Local file at `backend/ml/checkpoints/our_real.pt`, kagglehub demoted to optional secondary path or removed | User directive implies local handoff; offline-safe by default. |
| 5 | E2E < 15 s degradation order | (1) stride 128→192, (2) particles 20→10, (3) KDE 256²→128², (4) skip local-KDE +24/+48 (never drop +72) | +72 is the priority-scoring source — dropping it breaks mission quality. Other knobs are safe approximations. |

---

## Claude's Discretion (deferred to build-time)

- Exact PDF fonts, colour palette, margin tuning.
- `normalize_floats` precision for parity hashing (starting at 6 decimals).
- Whether `export_pdf` exposes a `style` parameter (lean: no, scope creep).
- Natural Earth coastline simplification tolerance (file size vs visual fidelity).

## Deferred Ideas (noted, not in scope)

- Running Kaggle training ourselves.
- `marccoru_baseline` weight branch.
- `export_pdf(style="full")` multi-page variant.
- Interactive / Mapbox-tile PDF basemap.
- FastAPI integration of export endpoint (next milestone).
- GPU parity in the byte-identical hash test.
- `--fallback` explicit CLI flag (rejected in favour of automatic fallback).
</content>
</invoke>