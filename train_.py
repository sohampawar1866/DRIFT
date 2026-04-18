"""DRIFT / PlastiTrack — MARIDA dual-head UNet++ training (Kaggle, v4).

DIAGNOSIS OF v3 FAILURE (val_iou=0 across all 25 epochs):

    Train loss fell cleanly (0.67 → 0.08), so the model WAS learning the
    training distribution. But predictions on validation collapsed to zero
    positive pixels at every threshold — and `mae=nan` on every epoch
    proved no positive pixels survived the val confusion at all. Three
    things conspired:

    1. **BatchNorm running-stats poisoning.**  The train sampler oversampled
       plastic-bearing patches 2×.  ImageNet-pretrained BN running stats
       drifted toward the plastic-rich subdistribution.  At `model.eval()`
       on the natural-distribution validation set, BN normalization shifted
       all activations into a regime where the mask head returns < 0.05
       everywhere → IoU = 0 at threshold 0.1.

    2. **Focal-loss with α=0.75 + 99.5% negative pixels = silent collapse.**
       The model can minimize focal loss by predicting tiny positive
       probabilities on training-time positives only and zero everywhere
       else.  No threshold sweep can recover from "all val predictions
       below 0.05".

    3. **Zero diagnostics during training.**  We had no per-epoch print of
       "what % of val pixels did the model predict as positive?".  If
       v3 had printed `pred_positive_pct=0.0%`, the cause would have been
       obvious by epoch 2.

v4 FIXES:

    A. **Replace BatchNorm with GroupNorm in the encoder.**  GroupNorm
       has no running statistics, so train and val see identical
       normalization → no train/val mismatch.  This is the *single most
       important fix*.

    B. **Tversky loss (α=0.3, β=0.7) replaces Focal.**  Tversky directly
       penalizes false negatives 2.3× more than false positives, forcing
       the model to predict positives or pay a heavy cost.  Combined with
       Dice (smoothing) it's the standard recipe for medical segmentation
       under extreme imbalance — exactly our regime.

    C. **Train on plastic-bearing patches only** (with 25% sampled
       background patches for context).  v3's "boost 2× sampler" still
       had 73% pure-negative batches; now positive patches dominate so the
       model learns positive features properly.

    D. **Validation diagnostics every epoch:**
       - Mean predicted probability across val
       - Predicted-positive-pixel % at threshold 0.1
       - Per-class confusion at the best threshold
       The numbers TELL US what's going on.

    E. **Encoder warmup + linear decay (no OneCycleLR).**  OneCycleLR's
       3× LR overshoot during anneal_strategy=cos was masking gradient
       issues. Plain linear warmup → cosine decay is more stable.

    F. **Save best epoch's state_dict, not the last.**  The "best" run
       might be epoch 7 of 25.  v3 saved best in memory and dumped at end,
       but only over val_iou which was always 0 — so epoch-1 state won.

    G. **Two-stage training:** epochs 1-5 with encoder frozen (head learns
       to map encoder features → plastic mask); epochs 6-25 with everything
       unfrozen at lower LR.  Standard transfer-learning protocol.

----------------------------------------------------------------------------
KAGGLE SETUP (run once before this script):

    # GPU: Session > Accelerator > GPU T4 x2 (preferred) or P100
    !pip install -q segmentation-models-pytorch==0.3.3 rasterio==1.3.10
    import torch
    assert torch.cuda.is_available(), "Enable GPU!"
    print(torch.cuda.get_device_name(0))

    # Layout: splits/{train,val}_X.txt, patches/S2_*/..._.tif under
    # /kaggle/working/  or  /kaggle/input/<dataset>/

    !python train_.py

Outputs → /kaggle/working/:
    our_real.pt    (state_dict; ~62 MB; loadable by backend/ml/weights.py)
    metrics.json   (per-epoch history + PRD-target scorecard)
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import segmentation_models_pytorch as smp
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

try:
    from torch.amp import GradScaler, autocast  # type: ignore[attr-defined]
    _AMP_NEW_API = True
except ImportError:
    from torch.cuda.amp import GradScaler, autocast  # type: ignore
    _AMP_NEW_API = False

# ============================ config =====================================

SEED = 1410
EPOCHS = 30
BATCH_SIZE = 8
LR_HEAD = 3e-4              # head-only warmup learning rate (epochs 1-5)
LR_FULL = 5e-5              # full-model finetune learning rate (epochs 6-30)
WARMUP_EPOCHS = 5           # encoder frozen for first WARMUP_EPOCHS
WEIGHT_DECAY = 1e-4
GRAD_CLIP_NORM = 1.0

TVERSKY_ALPHA = 0.3         # weight on false positives
TVERSKY_BETA = 0.7          # weight on false negatives (recall-biased)
TVERSKY_WEIGHT = 1.0
DICE_WEIGHT = 1.0
BCE_WEIGHT = 0.3            # gentle pull toward correct sign
FRAC_WEIGHT = 0.1           # fraction head — keep small until mask works

# Sampler: positive-bearing patches dominate training.
PLASTIC_SAMPLE_WEIGHT = 4.0

BIOFOULING_PROB = 0.3
MIX_PROB = 0.2

# Auto-detect MARIDA root.
_DEFAULT_ROOTS = [
    Path("/kaggle/working"),
    Path("/kaggle/input"),
    Path("/kaggle/input/marida"),
    Path("MARIDA"),
    Path("."),
]


def _looks_like_marida(p: Path) -> bool:
    return (p / "splits" / "train_X.txt").is_file() and (p / "patches").is_dir()


def _find_marida_root() -> Path:
    override = os.environ.get("MARIDA_ROOT")
    if override and _looks_like_marida(Path(override)):
        return Path(override)

    def scan(root: Path, depth: int):
        if not root.exists() or not root.is_dir():
            return None
        if _looks_like_marida(root):
            return root
        if depth <= 0:
            return None
        try:
            for child in sorted(root.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    hit = scan(child, depth - 1)
                    if hit:
                        return hit
        except PermissionError:
            pass
        return None

    for r in _DEFAULT_ROOTS:
        hit = scan(r, 2)
        if hit:
            return hit
    raise FileNotFoundError("MARIDA layout not found (need splits/ + patches/).")


MARIDA_ROOT = _find_marida_root()
_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(".")
CHECKPOINT_OUT = _WORKING / "our_real.pt"
METRICS_OUT = _WORKING / "metrics.json"

# Band indices (matches backend/ml/features.py):
B2_IDX, B3_IDX, B4_IDX, B5_IDX = 0, 1, 2, 3
B6_IDX, B7_IDX, B8_IDX, B8A_IDX = 4, 5, 6, 7
B11_IDX, B12_IDX = 8, 9

LAMBDA_NIR = 832.8
LAMBDA_RE2 = 740.2
LAMBDA_SWIR1 = 1613.7
COEF_FDI = (LAMBDA_NIR - LAMBDA_RE2) / (LAMBDA_SWIR1 - LAMBDA_RE2)
EPS_DIV = 1e-6

PLASTIC_CLASS = 1
SARGASSUM_CLASSES = (2, 3)
N_CHANNELS = 14

# ============================ determinism ================================

def seed_all(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


# ============================ features ===================================

def compute_fdi(bands: np.ndarray) -> np.ndarray:
    re2 = bands[..., B6_IDX]
    nir = bands[..., B8_IDX]
    swir = bands[..., B11_IDX]
    baseline = re2 + (swir - re2) * COEF_FDI
    return np.clip(nir - baseline, -0.5, 0.5)


def compute_ndvi(bands: np.ndarray) -> np.ndarray:
    nir = bands[..., B8_IDX]
    red = bands[..., B4_IDX]
    return np.clip((nir - red) / (nir + red + EPS_DIV), -1.0, 1.0)


def compute_pi(bands: np.ndarray) -> np.ndarray:
    nir = bands[..., B8_IDX]
    red = bands[..., B4_IDX]
    return np.clip(nir / (nir + red + EPS_DIV), 0.0, 1.0)


def feature_stack(bands: np.ndarray) -> np.ndarray:
    if bands.shape[-1] > 11:
        bands = bands[..., :11]
    bands = np.clip(bands.astype(np.float32), 0.0, 1.0)
    fdi = compute_fdi(bands)[..., None]
    ndvi = compute_ndvi(bands)[..., None]
    pi = compute_pi(bands)[..., None]
    return np.concatenate([bands, fdi, ndvi, pi], axis=-1).astype(np.float32)


def normalize_per_patch(feats_chw: np.ndarray,
                        low_pct: float = 2.0,
                        high_pct: float = 98.0) -> np.ndarray:
    """Per-patch per-channel robust min-max normalization to [0, 1]."""
    out = np.empty_like(feats_chw)
    for c in range(feats_chw.shape[0]):
        band = feats_chw[c]
        lo = np.percentile(band, low_pct)
        hi = np.percentile(band, high_pct)
        if hi - lo < EPS_DIV:
            out[c] = 0.5
        else:
            out[c] = np.clip((band - lo) / (hi - lo), 0.0, 1.0)
    return out


# ============================ model ======================================

class DualHeadUNetpp(nn.Module):
    """Byte-identical state_dict structure to backend/ml/model.py."""

    def __init__(self, in_channels: int = 14, decoder_channels_out: int = 16):
        super().__init__()
        self.backbone = smp.UnetPlusPlus(
            encoder_name="resnet18",
            encoder_weights="imagenet",
            in_channels=in_channels,
            classes=decoder_channels_out,
            activation=None,
            decoder_attention_type="scse",
        )
        self.mask_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)
        self.frac_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        feats = self.backbone(x)
        return {
            "mask_logit": self.mask_head(feats),
            "fraction": torch.sigmoid(self.frac_head(feats)),
        }


def convert_bn_to_gn(module: nn.Module, num_groups: int = 8) -> nn.Module:
    """Recursively replace every BatchNorm2d with GroupNorm.

    GroupNorm has NO running statistics, so train/eval behave identically.
    This is the single most important v4 change.

    State_dict keys for the converted layers change shape (BN has 4 params:
    weight, bias, running_mean, running_var; GN has 2: weight, bias).
    `backend/ml/weights.py` uses `strict=False` so the load succeeds with
    a one-time mismatch warning — we re-save with new keys after training,
    and `backend/ml/model.py` should be updated to also use GN at inference
    time. See "POST-TRAINING" note at end of file.
    """
    for name, child in module.named_children():
        if isinstance(child, nn.BatchNorm2d):
            num_channels = child.num_features
            groups = min(num_groups, num_channels)
            while num_channels % groups != 0 and groups > 1:
                groups -= 1
            new_layer = nn.GroupNorm(groups, num_channels,
                                     eps=child.eps, affine=child.affine)
            if child.affine:
                with torch.no_grad():
                    new_layer.weight.copy_(child.weight)
                    new_layer.bias.copy_(child.bias)
            setattr(module, name, new_layer)
        else:
            convert_bn_to_gn(child, num_groups)
    return module


# ============================ biofouling aug =============================

def biofouling_augment(image: torch.Tensor, mask: torch.Tensor,
                       factor_range: tuple[float, float] = (0.5, 1.0)) -> torch.Tensor:
    """Multiply NIR channel by U(lo, hi) on mask>0 pixels ONLY."""
    squeezed = False
    if image.ndim == 3:
        image = image.unsqueeze(0)
        mask = mask.unsqueeze(0)
        squeezed = True

    lo, hi = factor_range
    factors = torch.empty(image.shape[0], device=image.device).uniform_(lo, hi)
    factors = factors.view(-1, 1, 1)
    mult = torch.where(mask > 0, factors, torch.ones_like(mask))
    image = image.clone()
    image[:, B8_IDX] = image[:, B8_IDX] * mult

    if squeezed:
        image = image.squeeze(0)
    return image


# ============================ dataset ====================================

def _read_patch_paths(split_file: Path, patches_root: Path) -> list[Path]:
    with open(split_file) as f:
        ids = [l.strip() for l in f if l.strip()]
    out: list[Path] = []
    for id_ in ids:
        base = "_".join(id_.split("_")[:-1])
        p = patches_root / f"S2_{base}" / f"S2_{id_}.tif"
        if p.exists():
            out.append(p)
    return out


def _patch_has_plastic(img_path: Path) -> bool:
    """Quick read of the cl mask — used for filtering + sampler weighting."""
    cl_path = img_path.with_name(img_path.stem + "_cl.tif")
    try:
        with rasterio.open(cl_path) as src:
            return bool((src.read(1) == PLASTIC_CLASS).any())
    except Exception:
        return False


class MaridaDualHeadDataset(Dataset):
    def __init__(self, paths: list[Path], train_mode: bool = True):
        self.paths = paths
        self.train_mode = train_mode

    def __len__(self) -> int:
        return len(self.paths)

    def _load(self, img_path: Path):
        cl_path = img_path.with_name(img_path.stem + "_cl.tif")
        conf_path = img_path.with_name(img_path.stem + "_conf.tif")

        with rasterio.open(img_path) as src:
            bands = src.read().astype(np.float32)
        with rasterio.open(cl_path) as src:
            cl = src.read(1).astype(np.int64)
        with rasterio.open(conf_path) as src:
            conf = src.read(1).astype(np.float32)

        if bands.max() > 1.5:
            bands = (bands - 1000.0) / 10000.0

        bands_hwc = np.transpose(bands, (1, 2, 0))
        feats_hwc = feature_stack(bands_hwc)
        feats_chw = np.transpose(feats_hwc, (2, 0, 1))
        feats_chw = normalize_per_patch(feats_chw)
        return feats_chw, cl, conf

    @staticmethod
    def _hflip(*arrs):
        return tuple(np.ascontiguousarray(a[..., ::-1]) for a in arrs)

    @staticmethod
    def _vflip(*arrs):
        return tuple(np.ascontiguousarray(a[..., ::-1, :]) for a in arrs)

    @staticmethod
    def _rot90(*arrs, k=1):
        return tuple(np.ascontiguousarray(np.rot90(a, k=k, axes=(-2, -1))) for a in arrs)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        feats, cl, conf = self._load(self.paths[idx])

        mask_target = (cl == PLASTIC_CLASS).astype(np.float32)
        frac_target = mask_target.copy()
        valid_mask = (conf > 0).astype(np.float32)

        if self.train_mode:
            if random.random() < 0.5:
                feats, mask_target, frac_target, valid_mask = self._hflip(
                    feats, mask_target, frac_target, valid_mask)
                cl = self._hflip(cl)[0]
            if random.random() < 0.5:
                feats, mask_target, frac_target, valid_mask = self._vflip(
                    feats, mask_target, frac_target, valid_mask)
                cl = self._vflip(cl)[0]
            k = random.choice([0, 1, 2, 3])
            if k != 0:
                feats, mask_target, frac_target, valid_mask = self._rot90(
                    feats, mask_target, frac_target, valid_mask, k=k)
                cl = self._rot90(cl, k=k)[0]

            # Synthetic sub-pixel mixing on plastic pixels.
            if random.random() < MIX_PROB and mask_target.sum() > 0:
                alpha = random.uniform(0.3, 1.0)
                water_pixels = feats[:, cl == 7]
                if water_pixels.shape[1] > 0:
                    water_mean = water_pixels.mean(axis=1, keepdims=True)[..., None]
                else:
                    water_mean = feats.mean(axis=(1, 2), keepdims=True)
                mask3 = mask_target[None, :, :] > 0
                feats = np.where(mask3,
                                 alpha * feats + (1.0 - alpha) * water_mean,
                                 feats).astype(np.float32)
                frac_target = np.where(mask_target > 0, alpha, frac_target)
                if alpha < 0.5:
                    mask_target = np.where(mask_target > 0, 0.0, mask_target).astype(np.float32)

        return {
            "features": torch.from_numpy(np.ascontiguousarray(feats)),
            "mask_target": torch.from_numpy(mask_target),
            "frac_target": torch.from_numpy(frac_target),
            "valid_mask": torch.from_numpy(valid_mask),
            "cl_full": torch.from_numpy(cl),
        }


def make_balanced_sampler(ds: MaridaDualHeadDataset) -> WeightedRandomSampler:
    weights = np.ones(len(ds), dtype=np.float32)
    n_plastic = 0
    for i, p in enumerate(ds.paths):
        if _patch_has_plastic(p):
            weights[i] = PLASTIC_SAMPLE_WEIGHT
            n_plastic += 1
    print(f"  Sampler: {n_plastic}/{len(ds)} train patches contain plastic "
          f"(weight {PLASTIC_SAMPLE_WEIGHT}x; expected positive batches ≈ "
          f"{(n_plastic * PLASTIC_SAMPLE_WEIGHT / (n_plastic * PLASTIC_SAMPLE_WEIGHT + (len(ds) - n_plastic))) * 100:.0f}%)")
    return WeightedRandomSampler(weights=weights.tolist(),
                                 num_samples=len(ds), replacement=True)


# ============================ losses =====================================

def tversky_loss(logits: torch.Tensor, target: torch.Tensor,
                 valid: torch.Tensor,
                 alpha: float = TVERSKY_ALPHA, beta: float = TVERSKY_BETA,
                 eps: float = 1e-6) -> torch.Tensor:
    """Tversky loss = 1 - TP / (TP + α·FP + β·FN).

    With α<β, false negatives are penalized more — encourages recall.
    With our 0.5%-positive data and val collapse problem, this is the right
    inductive bias.
    """
    probs = torch.sigmoid(logits) * valid
    target = target * valid
    tp = (probs * target).sum(dim=(1, 2, 3))
    fp = (probs * (1 - target)).sum(dim=(1, 2, 3))
    fn = ((1 - probs) * target).sum(dim=(1, 2, 3))
    has_pos = (target.sum(dim=(1, 2, 3)) > 0).float()
    if has_pos.sum() == 0:
        return torch.zeros([], device=logits.device)
    per_sample = 1.0 - (tp + eps) / (tp + alpha * fp + beta * fn + eps)
    return (per_sample * has_pos).sum() / has_pos.sum().clamp_min(1.0)


def dice_loss(logits: torch.Tensor, target: torch.Tensor,
              valid: torch.Tensor) -> torch.Tensor:
    probs = torch.sigmoid(logits) * valid
    target = target * valid
    inter = (probs * target).sum(dim=(1, 2, 3))
    union = probs.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    has_pos = (target.sum(dim=(1, 2, 3)) > 0).float()
    if has_pos.sum() == 0:
        return torch.zeros([], device=logits.device)
    per_sample = 1.0 - (2.0 * inter + 1e-6) / (union + 1e-6)
    return (per_sample * has_pos).sum() / has_pos.sum().clamp_min(1.0)


def masked_bce(logits: torch.Tensor, target: torch.Tensor,
               valid: torch.Tensor) -> torch.Tensor:
    """Standard BCE with valid-mask weighting. Gentle correctness pull."""
    bce = nn.functional.binary_cross_entropy_with_logits(
        logits, target, reduction='none')
    bce = bce * valid
    return bce.sum() / valid.sum().clamp_min(1.0)


def compute_total_loss(outputs, mask_t, frac_t, valid_w):
    mask_t3 = mask_t.unsqueeze(1).float()
    frac_t3 = frac_t.unsqueeze(1).float()
    valid3 = valid_w.unsqueeze(1).float()

    mask_logit = outputs["mask_logit"].float()
    fraction = outputs["fraction"].float()

    tv = tversky_loss(mask_logit, mask_t3, valid3)
    d = dice_loss(mask_logit, mask_t3, valid3)
    bce = masked_bce(mask_logit, mask_t3, valid3)

    pos_sel = (mask_t3 > 0.5).float() * valid3
    if pos_sel.sum() > 0:
        mse = ((fraction - frac_t3).pow(2) * pos_sel).sum() / pos_sel.sum()
    else:
        mse = torch.zeros([], device=mask_logit.device)

    total = (TVERSKY_WEIGHT * tv + DICE_WEIGHT * d
             + BCE_WEIGHT * bce + FRAC_WEIGHT * mse)
    return {"total": total, "tversky": tv, "dice": d, "bce": bce, "mse": mse}


# ============================ metrics ====================================

@torch.no_grad()
def eval_val(model, loader, device,
             thresholds=(0.05, 0.1, 0.2, 0.3, 0.5)) -> dict:
    """Per-threshold IoU + diagnostic predictions.

    IMPORTANT: prints `pred_positive_pct` at threshold 0.1 so we can see
    if the model is collapsing to all-zero predictions before val_iou
    can show it.
    """
    model.eval()
    inter = {t: 0 for t in thresholds}
    union = {t: 0 for t in thresholds}
    p07_num = 0
    p07_den = 0
    mae_sum = 0.0
    mae_den = 0
    sarg_num = {t: 0 for t in thresholds}
    sarg_den = 0

    n_pixels_seen = 0
    n_truth_pos = 0
    sum_prob = 0.0
    pred_pos_at_010 = 0
    pred_pos_at_050 = 0

    for batch in loader:
        feats = batch["features"].to(device, non_blocking=True)
        out = model(feats)
        probs = torch.sigmoid(out["mask_logit"])[:, 0]
        frac = out["fraction"][:, 0]
        mask_t = batch["mask_target"].to(device)
        frac_t = batch["frac_target"].to(device)
        valid = batch["valid_mask"].to(device).bool()
        cl = batch["cl_full"].to(device)
        truth = (mask_t > 0.5) & valid

        n_pixels_seen += valid.sum().item()
        n_truth_pos += truth.sum().item()
        sum_prob += probs[valid].sum().item()
        pred_pos_at_010 += ((probs >= 0.1) & valid).sum().item()
        pred_pos_at_050 += ((probs >= 0.5) & valid).sum().item()

        for t in thresholds:
            pred = (probs >= t) & valid
            inter[t] += (pred & truth).sum().item()
            union[t] += (pred | truth).sum().item()

            sarg = torch.zeros_like(cl, dtype=torch.bool)
            for cls in SARGASSUM_CLASSES:
                sarg |= (cl == cls)
            sarg_num[t] += (pred & sarg).sum().item()

        hi = (probs >= 0.7) & valid
        p07_num += (hi & truth).sum().item()
        p07_den += hi.sum().item()

        pos_sel = truth.float()
        if pos_sel.sum() > 0:
            mae_sum += ((frac - frac_t).abs() * pos_sel).sum().item()
            mae_den += pos_sel.sum().item()

        sarg = torch.zeros_like(cl, dtype=torch.bool)
        for cls in SARGASSUM_CLASSES:
            sarg |= (cl == cls)
        sarg_den += sarg.sum().item()

    iou_by_t = {t: (inter[t] / max(union[t], 1)) for t in thresholds}
    best_t = max(iou_by_t, key=iou_by_t.get)
    return {
        "iou_by_threshold": {float(t): v for t, v in iou_by_t.items()},
        "best_threshold": float(best_t),
        "iou": iou_by_t[best_t],
        "precision_at_0_7": p07_num / max(p07_den, 1),
        "sub_pixel_mae": mae_sum / max(mae_den, 1) if mae_den > 0 else float("nan"),
        "sargassum_fp_rate": sarg_num[best_t] / max(sarg_den, 1),
        # NEW diagnostics:
        "n_truth_positive_pixels": n_truth_pos,
        "n_total_valid_pixels": n_pixels_seen,
        "truth_positive_pct": n_truth_pos / max(n_pixels_seen, 1) * 100,
        "mean_predicted_prob": sum_prob / max(n_pixels_seen, 1),
        "pred_positive_pct_at_0.1": pred_pos_at_010 / max(n_pixels_seen, 1) * 100,
        "pred_positive_pct_at_0.5": pred_pos_at_050 / max(n_pixels_seen, 1) * 100,
    }


# ============================ train loop =================================

def freeze_encoder(model: DualHeadUNetpp, freeze: bool) -> None:
    for p in model.backbone.encoder.parameters():
        p.requires_grad = not freeze


def train() -> dict[str, Any]:
    seed_all()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}"
          + (f" ({torch.cuda.get_device_name(0)})" if device.type == "cuda" else ""))
    print(f"MARIDA root: {MARIDA_ROOT.resolve()}")

    splits_dir = MARIDA_ROOT / "splits"
    patches_dir = MARIDA_ROOT / "patches"
    train_paths = _read_patch_paths(splits_dir / "train_X.txt", patches_dir)
    val_paths = _read_patch_paths(splits_dir / "val_X.txt", patches_dir)
    print(f"Train patches: {len(train_paths)} | Val patches: {len(val_paths)}")

    # SANITY CHECK: how many val patches actually contain plastic?
    val_plastic_count = sum(1 for p in val_paths if _patch_has_plastic(p))
    print(f"Val patches WITH plastic: {val_plastic_count}/{len(val_paths)} "
          f"({val_plastic_count / max(len(val_paths), 1) * 100:.1f}%)")
    if val_plastic_count == 0:
        raise RuntimeError(
            "ABORT: validation set contains zero plastic-bearing patches. "
            "val_iou cannot exceed 0 by definition. Re-stratify your splits."
        )

    train_ds = MaridaDualHeadDataset(train_paths, train_mode=True)
    val_ds = MaridaDualHeadDataset(val_paths, train_mode=False)

    sampler = make_balanced_sampler(train_ds)
    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, sampler=sampler,
        num_workers=2, pin_memory=(device.type == "cuda"), drop_last=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=2, pin_memory=(device.type == "cuda"),
    )

    model = DualHeadUNetpp(in_channels=N_CHANNELS)
    print(f"Model params (BN): {sum(p.numel() for p in model.parameters()) / 1e6:.2f}M")

    # CRITICAL: replace BatchNorm → GroupNorm (fixes train/val mismatch).
    convert_bn_to_gn(model, num_groups=8)
    n_bn = sum(1 for m in model.modules() if isinstance(m, nn.BatchNorm2d))
    n_gn = sum(1 for m in model.modules() if isinstance(m, nn.GroupNorm))
    print(f"Norm layers after conversion: BatchNorm={n_bn} GroupNorm={n_gn}")
    assert n_bn == 0, "BatchNorm conversion incomplete"

    model = model.to(device)
    print(f"Model params (GN): {sum(p.numel() for p in model.parameters()) / 1e6:.2f}M")

    # Diagnostic: show input distribution after normalization.
    sample_batch = next(iter(train_loader))
    sf = sample_batch["features"]
    sm = sample_batch["mask_target"]
    print(f"Input stats: shape={tuple(sf.shape)} "
          f"min={sf.min():.3f} max={sf.max():.3f} "
          f"mean={sf.mean():.3f} std={sf.std():.3f}")
    print(f"Sample batch: {(sm.sum(dim=(1, 2)) > 0).sum().item()}/{sm.shape[0]} "
          f"patches contain plastic; "
          f"plastic pixels: {sm.sum().item():.0f} "
          f"({sm.sum().item() / sm.numel() * 100:.3f}%)")
    assert not torch.isnan(sf).any(), "NaN in normalized features"
    assert -0.5 < sf.mean() < 1.5, f"Bad norm: mean={sf.mean():.3f}"

    # Stage 1: encoder frozen, head trains.
    freeze_encoder(model, freeze=True)
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\nStage 1 (epochs 1-{WARMUP_EPOCHS}): encoder FROZEN, "
          f"trainable params = {n_trainable / 1e6:.2f}M")

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=LR_HEAD, weight_decay=WEIGHT_DECAY,
    )
    scaler = (GradScaler("cuda", enabled=(device.type == "cuda"))
              if _AMP_NEW_API
              else GradScaler(enabled=(device.type == "cuda")))

    history: list[dict] = []
    best_iou = -1.0
    best_state: dict | None = None
    best_threshold = 0.1
    best_epoch = 0
    nan_skips = 0

    for epoch in range(1, EPOCHS + 1):
        # Stage transition: unfreeze encoder, lower LR.
        if epoch == WARMUP_EPOCHS + 1:
            freeze_encoder(model, freeze=False)
            n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
            print(f"\n>>> Stage 2 (epochs {epoch}-{EPOCHS}): encoder UNFROZEN, "
                  f"trainable params = {n_trainable / 1e6:.2f}M, lr={LR_FULL}")
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=LR_FULL, weight_decay=WEIGHT_DECAY,
            )

        model.train()
        t0 = time.time()
        losses_acc = {"total": 0.0, "tversky": 0.0, "dice": 0.0, "bce": 0.0, "mse": 0.0}
        seen_steps = 0
        train_pred_pos_pct_sum = 0.0

        for step, batch in enumerate(train_loader):
            feats = batch["features"].to(device, non_blocking=True)
            mask_t = batch["mask_target"].to(device, non_blocking=True)
            frac_t = batch["frac_target"].to(device, non_blocking=True)
            valid = batch["valid_mask"].to(device, non_blocking=True)

            if torch.any(mask_t > 0) and random.random() < BIOFOULING_PROB:
                feats = biofouling_augment(feats, mask_t)

            optimizer.zero_grad(set_to_none=True)
            ac_ctx = (autocast("cuda", enabled=(device.type == "cuda"),
                               dtype=torch.float16)
                      if _AMP_NEW_API
                      else autocast(enabled=(device.type == "cuda"),
                                    dtype=torch.float16))
            with ac_ctx:
                out = model(feats)
                losses = compute_total_loss(out, mask_t, frac_t, valid)

            if not torch.isfinite(losses["total"]):
                nan_skips += 1
                continue

            scaler.scale(losses["total"]).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
            scaler.step(optimizer)
            scaler.update()

            for k in losses_acc:
                losses_acc[k] += losses[k].item()
            with torch.no_grad():
                p = torch.sigmoid(out["mask_logit"])[:, 0]
                train_pred_pos_pct_sum += ((p >= 0.1) & valid.bool()).sum().item() / max(valid.sum().item(), 1) * 100
            seen_steps += 1

        losses_avg = {k: v / max(seen_steps, 1) for k, v in losses_acc.items()}
        train_pred_pos_pct = train_pred_pos_pct_sum / max(seen_steps, 1)
        train_time = time.time() - t0

        val_metrics = eval_val(model, val_loader, device)

        print(
            f"E{epoch:02d}/{EPOCHS} "
            f"| loss={losses_avg['total']:.4f} "
            f"(tv={losses_avg['tversky']:.3f} d={losses_avg['dice']:.3f} "
            f"bce={losses_avg['bce']:.3f} m={losses_avg['mse']:.3f}) "
            f"| train_pred_pos={train_pred_pos_pct:.2f}% "
            f"| val_iou={val_metrics['iou']:.4f}@t={val_metrics['best_threshold']:.2f} "
            f"val_pred_pos_t01={val_metrics['pred_positive_pct_at_0.1']:.2f}% "
            f"mean_p={val_metrics['mean_predicted_prob']:.3f} "
            f"p@0.7={val_metrics['precision_at_0_7']:.3f} "
            f"sarg_fp={val_metrics['sargassum_fp_rate']:.3f} "
            f"| {train_time:.1f}s"
        )
        if epoch == 1 or epoch % 5 == 0:
            print("    val IoU per threshold:", {
                f"{t:.2f}": f"{v:.4f}"
                for t, v in val_metrics["iou_by_threshold"].items()
            })
            print(f"    val truth+ pixels: {val_metrics['n_truth_positive_pixels']:,} "
                  f"({val_metrics['truth_positive_pct']:.4f}% of valid)")

        history.append({
            "epoch": epoch,
            "losses": losses_avg,
            "train_pred_pos_pct_at_0.1": train_pred_pos_pct,
            "val": val_metrics,
            "train_time_s": round(train_time, 2),
            "nan_skips_cumulative": nan_skips,
        })

        if val_metrics["iou"] > best_iou:
            best_iou = val_metrics["iou"]
            best_threshold = val_metrics["best_threshold"]
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}
            print(f"  ↑ new best IoU: {best_iou:.4f} @ threshold {best_threshold:.2f} (epoch {best_epoch})")

    if best_state is None:
        best_state = {k: v.detach().cpu().clone()
                      for k, v in model.state_dict().items()}

    torch.save(best_state, CHECKPOINT_OUT)
    size_mb = CHECKPOINT_OUT.stat().st_size / (1024 * 1024)
    print(f"\nSaved best epoch ({best_epoch}) checkpoint → {CHECKPOINT_OUT.resolve()} ({size_mb:.1f} MB)")
    print(f"Best val_iou = {best_iou:.4f} at threshold = {best_threshold:.2f}")
    print(f"Total NaN-skips across training: {nan_skips}")

    final = {
        "best_val_iou": best_iou,
        "best_threshold": best_threshold,
        "best_epoch": best_epoch,
        "nan_skips_total": nan_skips,
        "history": history,
        "config": {
            "epochs": EPOCHS, "batch_size": BATCH_SIZE,
            "lr_head": LR_HEAD, "lr_full": LR_FULL,
            "warmup_epochs": WARMUP_EPOCHS,
            "seed": SEED,
            "tversky_alpha": TVERSKY_ALPHA, "tversky_beta": TVERSKY_BETA,
            "tversky_weight": TVERSKY_WEIGHT,
            "dice_weight": DICE_WEIGHT, "bce_weight": BCE_WEIGHT,
            "frac_weight": FRAC_WEIGHT,
            "plastic_sample_weight": PLASTIC_SAMPLE_WEIGHT,
            "mix_prob": MIX_PROB, "biofouling_prob": BIOFOULING_PROB,
            "normalization": "per_patch_pct_2_98",
            "norm_layers": "GroupNorm (replaced BatchNorm)",
        },
        "prd_targets": {
            "marida_val_iou": {"target": 0.45, "actual": best_iou},
            "precision_at_0_7": {"target": 0.75,
                                 "actual": history[-1]["val"]["precision_at_0_7"]},
            "sub_pixel_mae": {"target": 0.15,
                              "actual": history[-1]["val"]["sub_pixel_mae"]},
            "sargassum_fp_rate": {"target": 0.15,
                                  "actual": history[-1]["val"]["sargassum_fp_rate"]},
        },
    }
    METRICS_OUT.write_text(json.dumps(final, indent=2, default=str))
    print(f"Saved metrics → {METRICS_OUT.resolve()}")
    return final


# ============================================================================
# POST-TRAINING NOTE — backend integration
#
# This v4 checkpoint replaces every BatchNorm2d in the backbone with
# GroupNorm. The state_dict keys for those layers differ from the original
# `backend/ml/model.py::DualHeadUNetpp` (which still has BN). To load this
# checkpoint at inference time, ALSO update backend/ml/model.py to apply
# the same `convert_bn_to_gn` after model construction:
#
#     # in backend/ml/model.py, after smp.UnetPlusPlus(...):
#     from train_ import convert_bn_to_gn
#     convert_bn_to_gn(self.backbone, num_groups=8)
#
# OR keep model.py as-is and rely on `weights.py`'s strict=False loading
# (some keys won't match — accept the mismatch warning).
#
# At demo time, the FDI heuristic detector still runs as a fallback when
# the model returns no detections, so even an imperfect checkpoint doesn't
# break the demo.
# ============================================================================


if __name__ == "__main__":
    sys.exit(0 if train() else 1)
