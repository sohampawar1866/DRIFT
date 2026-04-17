"""Weight-swap + checkpoint-loader tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from backend.core.config import Settings
from backend.ml.model import DualHeadUNetpp
from backend.ml.weights import (
    _strip_module_prefix,
    _unwrap_checkpoint,
    load_weights,
)


@pytest.fixture
def tmp_checkpoint(tmp_path, monkeypatch):
    import backend.ml.weights as w
    new_dir = tmp_path / "checkpoints"
    new_dir.mkdir()
    monkeypatch.setattr(w, "CHECKPOINT_DIR", new_dir)
    monkeypatch.setattr(w, "OUR_REAL_CANDIDATES", (
        new_dir / "our_real.pt",
        new_dir / "our_real.pth",
        new_dir / "our_real.pkl",
    ))
    return new_dir


def _reference_state_dict() -> dict:
    m = DualHeadUNetpp(in_channels=14)
    return {k: v.clone() for k, v in m.state_dict().items()}


def test_dummy_branch_unchanged():
    cfg = Settings()
    cfg = cfg.model_copy(update={"ml": cfg.ml.model_copy(update={"weights_source": "dummy"})})
    m = load_weights(cfg)
    assert isinstance(m, DualHeadUNetpp)
    assert not m.training


def test_our_real_missing_file_errors(tmp_checkpoint):
    cfg = Settings()
    cfg = cfg.model_copy(update={"ml": cfg.ml.model_copy(update={"weights_source": "our_real"})})
    with pytest.raises(FileNotFoundError, match="our_real checkpoint missing"):
        load_weights(cfg)


def test_our_real_loads_raw_state_dict(tmp_checkpoint):
    sd = _reference_state_dict()
    torch.save(sd, tmp_checkpoint / "our_real.pt")
    cfg = Settings()
    cfg = cfg.model_copy(update={"ml": cfg.ml.model_copy(update={"weights_source": "our_real"})})
    m = load_weights(cfg)
    assert isinstance(m, DualHeadUNetpp)
    assert not m.training
    ref_key = "mask_head.weight"
    assert torch.allclose(m.state_dict()[ref_key], sd[ref_key])


def test_our_real_loads_wrapped_dict(tmp_checkpoint):
    sd = _reference_state_dict()
    torch.save({"state_dict": sd, "epoch": 10, "optimizer": {}},
               tmp_checkpoint / "our_real.pt")
    cfg = Settings()
    cfg = cfg.model_copy(update={"ml": cfg.ml.model_copy(update={"weights_source": "our_real"})})
    m = load_weights(cfg)
    assert isinstance(m, DualHeadUNetpp)


def test_our_real_strips_module_prefix(tmp_checkpoint):
    sd = _reference_state_dict()
    sd_prefixed = {"module." + k: v for k, v in sd.items()}
    torch.save(sd_prefixed, tmp_checkpoint / "our_real.pt")
    cfg = Settings()
    cfg = cfg.model_copy(update={"ml": cfg.ml.model_copy(update={"weights_source": "our_real"})})
    m = load_weights(cfg)
    assert isinstance(m, DualHeadUNetpp)


def test_our_real_key_mismatch_raises(tmp_checkpoint):
    sd = _reference_state_dict()
    sd["bogus_extra_key.weight"] = torch.zeros(1)
    torch.save(sd, tmp_checkpoint / "our_real.pt")
    cfg = Settings()
    cfg = cfg.model_copy(update={"ml": cfg.ml.model_copy(update={"weights_source": "our_real"})})
    with pytest.raises(RuntimeError, match="State-dict key mismatch"):
        load_weights(cfg)


def test_strip_module_prefix_only_strips_when_all_match():
    sd = {"module.a": 1, "module.b": 2}
    out = _strip_module_prefix(sd)
    assert out == {"a": 1, "b": 2}
    sd_mixed = {"module.a": 1, "b": 2}
    assert _strip_module_prefix(sd_mixed) == sd_mixed


def test_unwrap_checkpoint_rejects_garbage():
    with pytest.raises(ValueError, match="Unrecognized checkpoint shape"):
        _unwrap_checkpoint(42)
    with pytest.raises(ValueError, match="Unrecognized checkpoint shape"):
        _unwrap_checkpoint({"not_state_dict": "garbage", "x": 1})
