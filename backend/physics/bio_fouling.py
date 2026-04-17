"""Biological Algae Deposition & Fouling Module.

Calculates the 'bio-fouling' accumulation on marine debris based on 
Sea Surface Temperature (SST) and Chlorophyll-a levels.
"""
from __future__ import annotations

import math
import logging

import xarray as xr

logger = logging.getLogger(__name__)

def calculate_biofouling_decay(
    confidence_raw: float,
    age_days: float,
    avg_sst: float,
    avg_chl: float,
    tau_base: float = 30.0,
    uncertainty_level: float = 0.15
) -> dict:
    """Adjusts confidence based on environmental growth factors.
    
    Formula: confidence_adj = confidence_raw * exp(-age / tau_eff)
    Returns: {conf_adj, k_factor, confidence_low, confidence_high}
    """
    # Normalized environmental factors
    temp_factor = max(0.5, min(2.0, avg_sst / 25.0))
    chl_factor = max(0.5, min(2.0, (avg_chl + 0.1) / 1.0))
    
    # Effective tau (half-life in days)
    tau_eff = tau_base / (temp_factor * chl_factor)
    k = 1.0 / tau_eff  # Decay constant
    
    decay = math.exp(-age_days * k)
    
    # NEW: Mechanical Fragmentation Factor (Phase 3 refinement)
    # Debris older than 30 days breaks into smaller pieces, reducing detection confidence exponentially.
    frag_penalty = 1.0
    if age_days > 30:
        # Penalty grows quadratically with age past 30 days
        frag_penalty = math.exp(-((age_days - 30) / 45.0)**2)
    
    conf_adj = confidence_raw * decay * frag_penalty
    
    # Uncertainty modeling (stochastic variance)
    # Increases with fragmentation and environmental intensity
    var = (age_days / 60.0) * uncertainty_level * (temp_factor * chl_factor) / frag_penalty
    conf_low = max(0, conf_adj * (1.0 - var))
    conf_high = min(1.0, conf_adj * (1.0 + var))

    return {
        "conf_adj": round(conf_adj, 4),
        "k": round(k, 4),
        "conf_range": [round(conf_low, 4), round(conf_high, 4)],
        "temp_avg": avg_sst,
        "chl_avg": avg_chl
    }

def analyze_path_fouling(
    env_stack, 
    path_coords: list[tuple[float, float]], 
    start_hour: int = 0
) -> dict:
    """Walks the drift path and calculates effective fouling components."""
    temps = []
    # Fetch live chlorophyll if available
    try:
        # Assuming env_stack might have chl or we use a reasonable proxy
        chl_val = env_stack.currents.get("chl", 0.5)
        if hasattr(chl_val, "values"): chl_val = float(chl_val.mean())
    except:
        chl_val = 0.5
    
    for i, (lon, lat) in enumerate(path_coords):
        t_hour = start_hour + i
        try:
            temp = env_stack.interp_sst(lon, lat, t_hour)
            temps.append(temp)
        except:
            pass
            
    avg_sst = sum(temps) / len(temps) if temps else 25.0
    return {
        "avg_sst": round(float(avg_sst), 2),
        "avg_chl": round(float(chl_val), 3),
    }
