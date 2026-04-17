"""Clip Natural Earth 10m coastline to a buffered Indian EEZ bbox (D-11).

Usage:
    python scripts/clip_basemap.py \
        --src path/to/ne_10m_coastline.shp \
        --out data/basemap/ne_10m_coastline_indian_eez.shp

The buffered bbox [65, 97, 3, 27] preserves Lakshadweep (~73 E, 10 N),
Maldives (~73 E, 4 N), Andaman & Nicobar (~93 E, 12 N) per RESEARCH
Pitfall 6. Source shapefile is public domain (Natural Earth).
If --src is omitted, defaults to downloading via `pyogrio`-compatible URL
(offline-first: fail if no cached source available).
"""
from __future__ import annotations
import argparse
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

BBOX = (65.0, 3.0, 97.0, 27.0)  # (minx, miny, maxx, maxy) in WGS84
SIMPLIFY_TOL_DEG = 0.01          # ~1.1 km at equator; keeps file < 2 MB


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True,
                    help="Path to ne_10m_coastline.shp (downloaded from naturalearthdata.com)")
    ap.add_argument("--out", type=Path,
                    default=Path("data/basemap/ne_10m_coastline_indian_eez.shp"))
    args = ap.parse_args()

    if not args.src.exists():
        raise FileNotFoundError(
            f"source shapefile not found: {args.src}. "
            "Download from https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-coastline/"
        )

    coast = gpd.read_file(args.src)
    if coast.crs is None or str(coast.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
        coast = coast.to_crs("EPSG:4326")
    clip_poly = box(*BBOX)
    clipped = gpd.clip(coast, clip_poly)
    clipped["geometry"] = clipped.geometry.simplify(SIMPLIFY_TOL_DEG, preserve_topology=True)
    clipped = clipped[~clipped.geometry.is_empty]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    clipped.to_file(args.out, driver="ESRI Shapefile")
    size_kb = args.out.stat().st_size // 1024
    print(f"wrote {args.out} ({size_kb} KB, {len(clipped)} features)")
    if size_kb >= 2048:
        print(f"WARN: shapefile exceeds 2 MB target (got {size_kb} KB); "
              "consider bumping SIMPLIFY_TOL_DEG.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
