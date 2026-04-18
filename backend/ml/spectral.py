"""Spectral gating policy for polygon acceptance and confidence adjustment.

This module centralizes spectral post-processing so inference code remains
focused on geometry extraction and schema adaptation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolygonSpectralStats:
    fdi_mean: float
    ndvi_mean: float
    pi_mean: float


@dataclass(frozen=True)
class PolygonGateDecision:
    accept: bool
    confidence_gate: float
    confidence_adjusted: float
    age_days_est: int
    reject_reason: str | None = None


# Stricter policy than the previous inline gate.
# Hard floors/caps are reject rules; soft bounds down-rank confidence.
FDI_HARD_FLOOR = -0.020
NDVI_HARD_CEILING = 0.280
PI_HARD_FLOOR = 0.420

FDI_SOFT_FLOOR = 0.000
NDVI_SOFT_CEILING = 0.120
PI_SOFT_FLOOR = 0.500


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def estimate_age_days(stats: PolygonSpectralStats) -> int:
    """Estimate age proxy from spectral signatures.

    Lower FDI and elevated NDVI usually indicate longer exposure.
    """
    raw = (0.22 - stats.fdi_mean) * 70.0 + max(0.0, stats.ndvi_mean - 0.10) * 60.0
    return int(round(_clamp(raw, 0.0, 90.0)))


def gate_polygon(conf_raw: float, stats: PolygonSpectralStats) -> PolygonGateDecision:
    """Apply strict acceptance and confidence penalties from spectral means."""
    if stats.fdi_mean <= FDI_HARD_FLOOR:
        return PolygonGateDecision(
            accept=False,
            confidence_gate=0.0,
            confidence_adjusted=0.0,
            age_days_est=estimate_age_days(stats),
            reject_reason="fdi_hard_floor",
        )
    if stats.ndvi_mean >= NDVI_HARD_CEILING:
        return PolygonGateDecision(
            accept=False,
            confidence_gate=0.0,
            confidence_adjusted=0.0,
            age_days_est=estimate_age_days(stats),
            reject_reason="ndvi_hard_ceiling",
        )
    if stats.pi_mean <= PI_HARD_FLOOR:
        return PolygonGateDecision(
            accept=False,
            confidence_gate=0.0,
            confidence_adjusted=0.0,
            age_days_est=estimate_age_days(stats),
            reject_reason="pi_hard_floor",
        )

    gate = 1.0
    if stats.fdi_mean < FDI_SOFT_FLOOR:
        gate *= 0.65
    if stats.ndvi_mean > NDVI_SOFT_CEILING:
        gate *= 0.60
    if stats.pi_mean < PI_SOFT_FLOOR:
        gate *= 0.75

    if stats.fdi_mean >= 0.020 and stats.ndvi_mean <= 0.080 and stats.pi_mean >= 0.580:
        gate *= 1.05

    conf_adj = _clamp(conf_raw * gate, 0.0, 1.0)
    return PolygonGateDecision(
        accept=True,
        confidence_gate=gate,
        confidence_adjusted=conf_adj,
        age_days_est=estimate_age_days(stats),
        reject_reason=None,
    )
