# 03-04 Summary — our_real.pt training (PARTIAL: integration green, accuracy gap)

## Status: integration ✅ — accuracy ❌

User delivered `our_real.pt` (62 MB) on 2026-04-18. Checkpoint:
- Loads cleanly via `backend.ml.weights.load_weights("our_real")`
- State-dict keys match `DualHeadUNetpp` exactly (0 missing, 0 unexpected)
- Forward pass on `(1, 14, 256, 256)` returns `(1, 1, 256, 256)` mask logits
- Smoke-tested in `backend/ml/test_weights_load.py` — 2 passed

But the training itself did not converge to a usable model.

## Training metrics (from `metrics.json`)

| epoch | train_loss | val_iou (best threshold) | nan_skips |
|---|---|---|---|
| 1 | 0.672 | 0.000 @ 0.10 | 2 |
| 5 | 0.506 | 0.000 @ 0.10 | 6 |
| 10 | 0.347 | 0.000 @ 0.10 | 11 |
| 20 | 0.128 | 0.000 @ 0.10 | 19 |
| **25** | **0.080** | **0.000 @ 0.10** | **20** |

Loss falls cleanly. Val IoU is **0.0000 at every threshold {0.1–0.5} for
every epoch**. `precision_at_0.7 = 0`, `sub_pixel_mae = NaN`,
`sargassum_fp_rate = 0`.

This means the model has learned to **predict zero positive pixels** on
validation. Loss is low because Dice on all-zero predictions vs sparse
positives is small, and Focal on confident-negatives is small.

## Decision

**Do not promote `our_real.pt` to `ml.weights_source` for the demo.**
Keep `dummy` so silent-fallback chain produces realistic outputs.
Flipping is a one-line config change once training is fixed.

## Three concrete fixes for the next training run (priority order)

1. **Confirm val split contains plastic pixels.** Add one-line print
   before training: `total_pos = sum(t.sum().item() for _, t, _ in val_loader); print(f"VAL POSITIVE PIXELS: {total_pos}")`. If 0 or near-0,
   the split is broken — re-stratify so every val patch with class==1
   keeps its plastic mask.

2. **Apply `normalize_per_patch` inside the val loop.** Currently
   `train_.py` normalizes train batches but the val collate may use the
   raw arrays. Wrap both with the same transform.

3. **Replace `BatchNorm2d` with `GroupNorm(8, ...)`.** With the 2×
   plastic-boosted train sampler, BN running stats are biased toward the
   train distribution, and val (natural distribution) goes off-distribution.
   GroupNorm has no running stats — train/val mismatch disappears.

If 1 doesn't fix it, try 2 + 3 together.

## What was delivered (Phase 3 Plan 03-04 — partial)

| Task | Status |
|---|---|
| 1. Train UNet++ on MARIDA → state_dict | ✅ (artifact present, accuracy gap) |
| 2. Integrate via `backend.ml.weights.load_weights('our_real')` | ✅ (smoke test passes) |
| 3. D-03 static review | ✅ (state_dict keys match DualHeadUNetpp) |
| 4. Biofouling empirical test | ⏸️ deferred — superseded by env-driven bio_fouling.py (OceanTrace plan) |
| 5. ML-02 IoU gate | ❌ (val_iou=0 < 0.45 target) |
| 6. Re-eval → `.planning/metrics/phase3.json` | ⏸️ deferred until retraining |

Demo path stays on `dummy`. Re-training queued for next free Kaggle quota.
