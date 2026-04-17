"""Smoke test for our_real.pt loading. No accuracy claim — only verifies
the user-supplied checkpoint loads with matching state-dict keys and
runs a forward pass without crashing."""
from __future__ import annotations

import pytest
import torch

from backend.core.config import Settings
from backend.ml.weights import load_weights, _find_checkpoint


def test_our_real_checkpoint_present():
    p = _find_checkpoint()
    assert p.exists(), f"checkpoint not found: {p}"
    assert p.stat().st_size > 1_000_000, "checkpoint suspiciously small"


def test_our_real_load_and_forward():
    cfg = Settings()
    cfg.ml.weights_source = "our_real"
    model = load_weights(cfg)
    model.eval()
    x = torch.zeros(1, cfg.ml.in_channels, 256, 256)
    with torch.no_grad():
        out = model(x)
    if isinstance(out, (tuple, list)):
        mask_logits = out[0]
    elif isinstance(out, dict):
        mask_logits = out.get("mask", out.get("mask_logits", next(iter(out.values()))))
    else:
        mask_logits = out
    assert mask_logits.shape[-2:] == (256, 256), f"unexpected shape {mask_logits.shape}"
