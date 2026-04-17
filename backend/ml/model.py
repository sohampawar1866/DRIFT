"""UnetPlusPlus with ResNet-18 encoder, SCSE decoder attention, dual heads.

Design: one shared decoder (16-channel feature map) -> two 1x1 Conv2d heads
    - mask_head: plastic binary probability logit (sigmoid at inference)
    - frac_head: fractional-cover regression (sigmoid, [0,1])

SCSE (spatial + channel squeeze-excite) is supplied by smp via
`decoder_attention_type="scse"` (cleaner than wrapping the encoder stem and
zero LOC for the Phase 1 budget; see RESEARCH.md Decision 5).
"""
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


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
