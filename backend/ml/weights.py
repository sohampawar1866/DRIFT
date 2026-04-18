"""Real-checkpoint weight loader for DRIFT inference."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

from backend.core.config import Settings
from backend.ml.model import OurRealUNetPP

CHECKPOINT_DIR = Path("backend/ml/checkpoints")
DEFAULT_OUR_REAL_PATH = CHECKPOINT_DIR / "our_real.pth"


def _strip_module_prefix(sd: dict[str, Any]) -> dict[str, Any]:
    if sd and all(k.startswith("module.") for k in sd.keys()):
        return {k[len("module."):]: v for k, v in sd.items()}
    return sd


def _strip_model_prefix(sd: dict[str, Any]) -> dict[str, Any]:
    if sd and all(k.startswith("model.") for k in sd.keys()):
        return {k[len("model."):]: v for k, v in sd.items()}
    return sd


def _checkpoint_threshold(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("threshold")
    if value is None:
        return None
    if torch.is_tensor(value):
        value = value.item()
    try:
        scalar = float(value)
    except Exception:
        return None
    return scalar if 0.0 < scalar < 1.0 else None


def _unwrap_checkpoint(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict) and "state_dict" in obj and isinstance(obj["state_dict"], dict):
        return obj["state_dict"]
    if isinstance(obj, dict):
        tensor_items = {k: v for k, v in obj.items() if torch.is_tensor(v)}
        if tensor_items:
            return tensor_items
    raise ValueError(
        f"Unrecognized checkpoint shape: type={type(obj).__name__}, "
        f"keys_sample={list(obj.keys())[:5] if isinstance(obj, dict) else 'n/a'}. "
        "Expected raw state_dict or {'state_dict': ...} wrapper."
    )


def _resolve_checkpoint_path(cfg: Settings) -> Path:
    configured = Path(cfg.ml.checkpoint_path)
    if configured.exists():
        return configured
    fallback = DEFAULT_OUR_REAL_PATH
    if configured == fallback and fallback.exists():
        return fallback
    raise FileNotFoundError(
        "our_real checkpoint missing. Expected file: "
        f"{configured}. "
        "Set ml.checkpoint_path (or ML__CHECKPOINT_PATH) to a valid .pth/.pt file."
    )


def load_weights(cfg: Settings) -> nn.Module:
    import json
    source = cfg.ml.weights_source
    if source != "our_real":
        raise ValueError(
            f"Unsupported weights_source={source!r}. This backend only supports 'our_real'."
        )

    ckpt_path = _resolve_checkpoint_path(cfg)
    try:
        raw = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    except Exception as e:
        raise RuntimeError(f"torch.load(weights_only=True) failed on {ckpt_path}: {e}") from e

    sd = _unwrap_checkpoint(raw)
    sd = _strip_module_prefix(sd)
    sd.pop("threshold", None)
    sd = _strip_model_prefix(sd)

    prediction_threshold = _checkpoint_threshold(raw)

    metrics_path = ckpt_path.parent / "metrics.json"
    if metrics_path.exists():
        try:
            with metrics_path.open("r", encoding="utf-8") as f:
                metrics_data = json.load(f)
                if "best_threshold" in metrics_data:
                    prediction_threshold = float(metrics_data["best_threshold"])
        except Exception as e:
            print(f"Warning: Failed to read best_threshold from {metrics_path}: {e}")

    model = OurRealUNetPP(
        in_channels=cfg.ml.in_channels,
        prediction_threshold=prediction_threshold,
    )
    try:
        model.model.load_state_dict(sd, strict=True)
    except RuntimeError as e:
        sample_keys = list(sd.keys())[:10]
        raise RuntimeError(
            "State-dict mismatch for our_real checkpoint. "
            f"checkpoint={ckpt_path}, in_channels={cfg.ml.in_channels}, "
            f"sample_keys={sample_keys}. Original error: {e}"
        ) from e
    return model.eval()
