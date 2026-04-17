"""Environmental bio-fouling decay (OceanTrace).

Plastic detection confidence fades with time as biological growth
attaches and changes the spectral signature. The decay time-constant
`tau` is environment-dependent: warmer water + more chlorophyll
(productive water) → faster bio-growth → smaller tau → faster fade.
Cooler / oligotrophic water → larger tau → slower fade.

Calibration (rough — refine empirically when training works):
- Base tau = 168 h (7 days) at neutral conditions (chl=0.3 mg/m3, sst=20C)
- chl_factor: 0.5x at chl >= 0.6 (very productive), 3x at chl <= 0.1 (oligotrophic)
- sst_factor: 0.5x at sst >= 30C (warm), 2.5x at sst <= 10C (cool)
"""
from __future__ import annotations

import math

TAU_BASE_HOURS: float = 168.0
CHL_NEUTRAL: float = 0.3
SST_NEUTRAL: float = 20.0
CHL_FACTOR_MIN: float = 0.5
CHL_FACTOR_MAX: float = 3.0
SST_FACTOR_MIN: float = 0.5
SST_FACTOR_MAX: float = 2.5
SST_DECAY_K: float = 15.0


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def tau_environmental(chl_mg_m3: float, sst_c: float) -> float:
    """Return decay time-constant in hours for given Chl-a + SST."""
    chl = max(chl_mg_m3, 0.01)
    chl_factor = _clip(CHL_NEUTRAL / chl, CHL_FACTOR_MIN, CHL_FACTOR_MAX)
    sst_factor = _clip(math.exp(-(sst_c - SST_NEUTRAL) / SST_DECAY_K),
                       SST_FACTOR_MIN, SST_FACTOR_MAX)
    return TAU_BASE_HOURS * chl_factor * sst_factor


def adjust_confidence(
    conf_raw: float,
    age_hours: float,
    chl_mg_m3: float = CHL_NEUTRAL,
    sst_c: float = SST_NEUTRAL,
) -> float:
    """conf_adj = conf_raw * exp(-age / tau(chl, sst)). Clamps to [0, 1]."""
    if age_hours <= 0:
        return _clip(conf_raw, 0.0, 1.0)
    tau = tau_environmental(chl_mg_m3, sst_c)
    decayed = conf_raw * math.exp(-age_hours / tau)
    return _clip(decayed, 0.0, 1.0)
