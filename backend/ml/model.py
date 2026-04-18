"""UnetPlusPlus with ResNet-18 encoder, SCSE decoder attention, dual heads.

Design: one shared decoder (16-channel feature map) -> two 1x1 Conv2d heads
    - mask_head: plastic binary probability logit (sigmoid at inference)
    - frac_head: fractional-cover regression (sigmoid, [0,1])

v4 (matches train_.py v4): every BatchNorm2d in the backbone is replaced
with GroupNorm at construction. This kills the train/val running-stats
poisoning that caused val_iou=0 in v3, and is the SAME transform applied
during training so the checkpoint loads cleanly.
"""
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


def _convert_bn_to_gn(module: nn.Module, num_groups: int = 8) -> nn.Module:
    """Recursively replace nn.BatchNorm2d with nn.GroupNorm. No running stats =
    train/eval behave identically. Must match train_.py::convert_bn_to_gn."""
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
            _convert_bn_to_gn(child, num_groups)
    return module


class DualHeadUNetpp(nn.Module):
    def __init__(self, in_channels: int = 14, decoder_channels_out: int = 16,
                 use_groupnorm: bool = True):
        super().__init__()
        self.backbone = smp.UnetPlusPlus(
            encoder_name="resnet18",
            encoder_weights="imagenet",
            in_channels=in_channels,
            classes=decoder_channels_out,   # feature map, not final prediction
            activation=None,
            decoder_attention_type="scse",  # spatial + channel squeeze-excite
        )
        if use_groupnorm:
            _convert_bn_to_gn(self.backbone, num_groups=8)
        self.mask_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)
        self.frac_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        feats = self.backbone(x)                                  # (B, 16, H, W)
        return {
            "mask_logit": self.mask_head(feats),                   # (B, 1, H, W)
            "fraction": torch.sigmoid(self.frac_head(feats)),      # (B, 1, H, W) in [0,1]
        }
