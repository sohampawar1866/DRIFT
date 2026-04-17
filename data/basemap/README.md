# Basemap — Indian EEZ Coastline

## Source

Natural Earth 10m Coastline (public domain, naturalearthdata.com), clipped to bbox `[65, 3, 97, 27]` via `scripts/clip_basemap.py`.

The buffered bbox preserves Lakshadweep (~73 E, 10 N), Maldives (~73 E, 4 N), and Andaman & Nicobar (~93 E, 12 N) per Phase 3 RESEARCH Pitfall 6.

## Files

- `ne_10m_coastline_indian_eez.shp` — geometry
- `ne_10m_coastline_indian_eez.shx` — shape index
- `ne_10m_coastline_indian_eez.dbf` — attribute table
- `ne_10m_coastline_indian_eez.prj` — CRS (EPSG:4326 / WGS84)

## Reproduce

```bash
# Download Natural Earth 10m coastline (public domain, no auth) from:
#   https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip
# (fallback: https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-coastline/)

python scripts/clip_basemap.py --src <local_ne_10m_coastline.shp>
```

## License

Public domain (Natural Earth license). No attribution required but credited in PDF briefing footer per D-09.
