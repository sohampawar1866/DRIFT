"""Model definitions for DRIFT inference/training.

`OurRealUNetPP` is the production runtime model used with
`backend/ml/checkpoints/our_real.pth`.
`DualHeadUNetpp` is kept as a legacy training artifact for backward
compatibility in older experiments.
"""
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


class OurRealUNetPP(nn.Module):
    """Runtime architecture matching the shipped `our_real.pth` checkpoint.

    The checkpoint is a single-head SMP UnetPlusPlus model. We expose the API
    expected by inference (`mask_logit` and `fraction`) and derive `fraction`
    from the mask probability because the checkpoint has only one output head.
    """

    def __init__(self, in_channels: int = 12, prediction_threshold: float | None = None):
        super().__init__()
        self.model = smp.UnetPlusPlus(
            encoder_name="resnet34",
            encoder_weights=None,
            in_channels=in_channels,
            classes=1,
            activation=None,
            decoder_attention_type=None,
        )
        self.prediction_threshold = prediction_threshold

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        logits = self.model(x)
        return {
            "mask_logit": logits,
            "fraction": torch.sigmoid(logits),
        }


class DualHeadUNetpp(nn.Module):
    def __init__(self, in_channels: int = 14, decoder_channels_out: int = 16):
        super().__init__()
        self.backbone = smp.UnetPlusPlus(
            encoder_name="resnet18",
            encoder_weights="imagenet",
            in_channels=in_channels,
            classes=decoder_channels_out,   # feature map, not final prediction
            activation=None,
            decoder_attention_type="scse",  # spatial + channel squeeze-excite
        )
        self.mask_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)
        self.frac_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        feats = self.backbone(x)                                  # (B, 16, H, W)
        return {
            "mask_logit": self.mask_head(feats),                   # (B, 1, H, W)
            "fraction": torch.sigmoid(self.frac_head(feats)),      # (B, 1, H, W) in [0,1]
        }
