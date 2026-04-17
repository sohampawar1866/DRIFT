"""Spectral Analysis Service for detection validation.

Calculates Floating Debris Index (FDI) and NDVI using Sentinel-2 bands
to validate that polygons possess the expected spectral signatures 
of marine plastics vs algae vs organic matter.
"""
from __future__ import annotations

import numpy as np
import rasterio

def calculate_fdi(nir: np.ndarray, red_edge: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """Floating Debris Index (FDI) simplified.
    
    FDI = NIR - (RE + (SWIR - RE) * W)
    where W is a wavelength-based interpolation factor.
    """
    # Placeholder W factor for Sentinel-2 B8 (842nm), B6 (740nm), B11 (1610nm)
    # W = (lambda_NIR - lambda_RE) / (lambda_SWIR - lambda_RE)
    # W approx (842 - 740) / (1610 - 740) approx 0.117
    W = 0.117
    return nir - (red_edge + (swir - red_edge) * W)

def calculate_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Normalized Difference Vegetation Index."""
    denom = nir + red
    denom[denom == 0] = 1e-6
    return (nir - red) / denom

def calculate_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Normalized Difference Water Index."""
    denom = green + nir
    denom[denom == 0] = 1e-6
    return (green - nir) / denom

def validate_spectral_signature(
    patch_bands: np.ndarray, 
    threshold_fdi: float = 0.01,
    filter_veg: bool = True
) -> dict:
    """Analyze a multi-band patch to see if it looks like plastic.
    
    Bands expected in order: [B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12] (standard MARIDA)
    """
    # MARIDA mapping: B4=Red(2), B3=Green(1), B8=NIR(6), B6=RE1(4), B11=SWIR1(8)
    # Note: indexes are 0-based
    green = patch_bands[1]
    red = patch_bands[2]
    re = patch_bands[4]
    nir = patch_bands[6]
    swir = patch_bands[8]
    
    fdi = calculate_fdi(nir, re, swir)
    ndvi = calculate_ndvi(nir, red)
    
    # Plastic typically has high FDI but low NDVI (unlike algae)
    avg_fdi = float(np.mean(fdi))
    avg_ndvi = float(np.mean(ndvi))
    
    is_valid = avg_fdi > threshold_fdi
    if filter_veg and avg_ndvi > 0.3:
        # High NDVI suggests organic vegetation/algae bloom rather than plastic
        is_valid = False
        
    return {
        "is_valid": is_valid,
        "fdi": avg_fdi,
        "ndvi": avg_ndvi,
        "class_est": "plastic" if is_valid else "organic_algae"
    }
