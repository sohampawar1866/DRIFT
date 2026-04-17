"""Environmental Data Service (PHYS-02-LIVE).

Fetches live currents, winds, SST, and Chlorophyll on-demand based on 
detection coordinates using copernicusmarine and cdsapi.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import xarray as xr
import numpy as np
from dotenv import load_dotenv

from backend.core.config import Settings
from backend.physics.env_data import EnvStack, from_synthetic, load_env_stack

load_dotenv()
logger = logging.getLogger(__name__)

class BBox(NamedTuple):
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float

class EnvService:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.env_dir = Path("backend/data/env")
        self.env_dir.mkdir(parents=True, exist_ok=True)

    def _get_bbox(self, lons: list[float], lats: list[float], buffer: float = 1.0) -> BBox:
        return BBox(
            lon_min=min(lons) - buffer,
            lat_min=min(lats) - buffer,
            lon_max=max(lons) + buffer,
            lat_max=max(lats) + buffer
        )

    def fetch_live_stack(self, lons: list[float], lats: list[float], start_time: datetime | None = None) -> EnvStack:
        """Fetch real-time PHY and BIO data for the given coordinates."""
        if start_time is None:
            # Default to now - 1 day to ensure availability
            start_time = datetime.utcnow() - timedelta(days=1)
        
        end_time = start_time + timedelta(days=self.cfg.physics.active_horizon_days)
        bbox = self._get_bbox(lons, lats)
        
        # Unique ID for caching based on bbox and date
        cache_id = f"{bbox.lon_min:.1f}_{bbox.lat_min:.1f}_{start_time.strftime('%Y%m%d')}"
        cmems_file = self.env_dir / f"cmems_{cache_id}.nc"
        era5_file = self.env_dir / f"era5_{cache_id}.nc"

        try:
            if not cmems_file.exists():
                self._download_cmems(bbox, start_time, end_time, cmems_file)
            
            if not era5_file.exists():
                self._download_era5(bbox, start_time, end_time, era5_file)
            
            return load_env_stack(cmems_file, era5_file, horizon_hours=self.cfg.physics.active_horizon_days * 24)
        
        except Exception as e:
            logger.warning(f"Live fetch failed: {e}. Falling back to synthetic.")
            return self._get_synthetic_fallback()

    def _download_cmems(self, bbox: BBox, start: datetime, end: datetime, out_path: Path):
        import copernicusmarine
        logger.info(f"Downloading CMEMS PHY for {bbox}")
        
        # We fetch currents (uo, vo) and SST (thetao)
        ds = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            variables=["uo", "vo", "thetao"],
            minimum_longitude=bbox.lon_min,
            maximum_longitude=bbox.lon_max,
            minimum_latitude=bbox.lat_min,
            maximum_latitude=bbox.lat_max,
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat(),
            minimum_depth=0.0,
            maximum_depth=1.0,
        )
        ds.to_netcdf(out_path)

    def _download_era5(self, bbox: BBox, start: datetime, end: datetime, out_path: Path):
        import cdsapi
        logger.info(f"Downloading ERA5 for {bbox}")
        c = cdsapi.Client()
        
        # Area format: [North, West, South, East]
        area = [bbox.lat_max, bbox.lon_min, bbox.lat_min, bbox.lon_max]
        
        # Simplified time handling for ERA5
        c.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
                "year": [start.strftime("%Y")],
                "month": [start.strftime("%m")],
                "day": [start.strftime("%d")],
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": area,
                "format": "netcdf",
            },
            str(out_path)
        )

    def fetch_chlorophyll(self, bbox: BBox, start: datetime) -> xr.DataArray:
        """Fetch Chlorophyll-a (BIO) data separately as it's often daily/coarser."""
        import copernicusmarine
        out_path = self.env_dir / f"chl_{bbox.lon_min:.1f}_{bbox.lat_min:.1f}_{start.strftime('%Y%m%d')}.nc"
        
        if not out_path.exists():
            ds = copernicusmarine.open_dataset(
                dataset_id="cmems_mod_glo_bgc_anfc_0.25deg_P1D-m",
                variables=["chl"],
                minimum_longitude=bbox.lon_min,
                maximum_longitude=bbox.lon_max,
                minimum_latitude=bbox.lat_min,
                maximum_latitude=bbox.lat_max,
                start_datetime=start.isoformat(),
                end_datetime=(start + timedelta(days=1)).isoformat(),
            )
            ds.to_netcdf(out_path)
        
        chl_ds = xr.open_dataset(out_path)
        return chl_ds["chl"]

    def _get_synthetic_fallback(self) -> EnvStack:
        # Re-use existing synthetic builder logic from drift_engine or similar
        # For now, we'll let drift_engine handle the final fallback
        raise RuntimeError("Synthetic fallback requested from EnvService")
