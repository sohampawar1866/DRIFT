"""Weight loader — dispatches on cfg.ml.weights_source.

Phase 1: 'dummy' (random init + mask_head bias shift).
Phase 3: 'our_real' (user-supplied local checkpoint per D-01/D-02).
'marccoru_baseline' remains not implemented (optional bonus only).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn

from backend.core.config import Settings
from backend.ml.model import DualHeadUNetpp

CHECKPOINT_DIR = Path("backend/ml/checkpoints")
OUR_REAL_CANDIDATES: tuple[Path, ...] = (
    CHECKPOINT_DIR / "our_real.pt",
    CHECKPOINT_DIR / "our_real.pth",
    CHECKPOINT_DIR / "our_real.pkl",
)


def _strip_module_prefix(sd: dict[str, Any]) -> dict[str, Any]:
    if sd and all(k.startswith("module.") for k in sd.keys()):
        return {k[len("module."):]: v for k, v in sd.items()}
    return sd


def _unwrap_checkpoint(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict) and "state_dict" in obj and isinstance(obj["state_dict"], dict):
        return obj["state_dict"]
    if isinstance(obj, dict) and obj and all(
        hasattr(v, "shape") or hasattr(v, "dtype") for v in obj.values()
    ):
        return obj
    raise ValueError(
        f"Unrecognized checkpoint shape: type={type(obj).__name__}, "
        f"keys_sample={list(obj.keys())[:5] if isinstance(obj, dict) else 'n/a'}. "
        "Expected raw state_dict or {'state_dict': ...} wrapper. "
        "Training script must save with torch.save(model.state_dict(), path), "
        "NOT torch.save(model, path)."
    )


def _find_checkpoint() -> Path:
    for p in OUR_REAL_CANDIDATES:
        if p.exists():
            return p
    expected = ", ".join(str(p) for p in OUR_REAL_CANDIDATES)
    raise FileNotFoundError(
        f"our_real checkpoint missing. Searched: {expected}. "
        "User must deliver a .pt/.pth/.pkl file (state_dict saved via "
        "torch.save(model.state_dict(), path)), OR switch "
        "ml.weights_source back to 'dummy' in backend/config.yaml."
    )


def load_weights(cfg: Settings) -> nn.Module:
    source = cfg.ml.weights_source

    if source == "dummy":
        torch.manual_seed(cfg.ml.dummy_seed)
        model = DualHeadUNetpp(in_channels=cfg.ml.in_channels)
        assert model.backbone.encoder.conv1.weight.std().item() > 1e-4, (
            "conv1 dead-init -- SMP did not adapt weights for in_channels=14. "
            "See RESEARCH.md 'Pitfall 4: SMP in_channels=14 Dead Init'."
        )
        with torch.no_grad():
            model.mask_head.bias.data.fill_(0.5)
        return model.eval()

    if source == "marccoru_baseline":
        raise NotImplementedError(
            "marccoru_baseline weights require manual Google Drive download. "
            "Phase 1 default is 'dummy'. See PITFALLS.md and STATE.md."
        )

    if source == "our_real":
        ckpt_path = _find_checkpoint()
        try:
            raw = torch.load(ckpt_path, map_location="cpu", weights_only=True)
        except Exception as e:
            raise RuntimeError(
                f"torch.load(weights_only=True) failed on {ckpt_path}: {e}. "
                "User must re-save the checkpoint as "
                "`torch.save(model.state_dict(), path)`, NOT `torch.save(model, path)`. "
                "We do NOT disable weights_only for untrusted input."
            ) from e

        sd = _unwrap_checkpoint(raw)
        sd = _strip_module_prefix(sd)

        model = DualHeadUNetpp(in_channels=cfg.ml.in_channels)
        missing, unexpected = model.load_state_dict(sd, strict=False)
        if missing or unexpected:
            raise RuntimeError(
                "State-dict key mismatch:\n"
                f"  missing ({len(missing)}): {list(missing)[:10]}\n"
                f"  unexpected ({len(unexpected)}): {list(unexpected)[:10]}\n"
                "Training script's model class does not match "
                "backend/ml/model.py::DualHeadUNetpp. "
                "See D-03.1 in .planning/phases/03-real-training-weight-swap-mission-export-e2e/03-CONTEXT.md."
            )
        return model.eval()

    raise ValueError(f"Unknown weights_source: {source!r}")
