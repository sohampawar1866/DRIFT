"""Mission export artifacts: GPX 1.1, GeoJSON, and one-page PDF briefing.

Three pure functions (D-06). All consume the FROZEN MissionPlan; PDF
optionally accepts a ForecastEnvelope for the +72h density overlay AND a
per-waypoint currents summary table (D-09).

Imports order matters: matplotlib.use("Agg") MUST run before pyplot import
(RESEARCH Pitfall 2 + Anti-Pattern list). Coastline is cached at module
scope (Anti-Pattern: re-reading per call).

D-09 currents table note: the ForecastFrame schema carries particle_positions
only -- no explicit u/v or wind fields. We therefore derive a per-waypoint
CURRENTS magnitude + direction from the displacement of the nearest particle
between hour=0 and hour=72 (divided by elapsed seconds -> m/s). Wind columns
are intentionally dropped -- they are not present in the schema and fabricating
them would violate D-09's honesty principle. The PDF caption records this.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Optional

# CRITICAL: Agg backend before any pyplot import. Headless-safe.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Warm matplotlib so first export_pdf call doesn't blow the 3 s budget.
_warm = plt.figure(figsize=(1, 1))
plt.close(_warm)

import geopandas as gpd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from backend.core.schemas import MissionPlan, ForecastEnvelope  # noqa: E402

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOC = ("http://www.topografix.com/GPX/1/1 "
              "http://www.topografix.com/GPX/1/1/gpx.xsd")
COASTLINE_PATH = Path("data/basemap/ne_10m_coastline_indian_eez.shp")
FUEL_L_PER_KM = 2.5  # D-09

ET.register_namespace("", GPX_NS)
ET.register_namespace("xsi", XSI_NS)

_COASTLINE: Optional[gpd.GeoDataFrame] = None


def _get_coastline() -> Optional[gpd.GeoDataFrame]:
    global _COASTLINE
    if _COASTLINE is None and COASTLINE_PATH.exists():
        # Prefer pyogrio (modern default, no fiona.path dep). Fall back to
        # whatever default geopandas picks if pyogrio isn't importable.
        try:
            _COASTLINE = gpd.read_file(COASTLINE_PATH, engine="pyogrio")
        except Exception:
            _COASTLINE = gpd.read_file(COASTLINE_PATH)
    return _COASTLINE


# ---------- GPX ----------
def export_gpx(mission: MissionPlan, path: Path) -> Path:
    """Write a GPX 1.1 file with one <trk> (route) and one <wpt> per waypoint."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gpx = ET.Element(f"{{{GPX_NS}}}gpx", {
        "version": "1.1",
        "creator": "DRIFT PlastiTrack v1",
        f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOC,
    })
    for wp in mission.waypoints:
        wpt = ET.SubElement(gpx, f"{{{GPX_NS}}}wpt", {
            "lat": f"{wp.lat:.6f}", "lon": f"{wp.lon:.6f}",
        })
        ET.SubElement(wpt, f"{{{GPX_NS}}}name").text = f"WP{wp.order:02d}"
        ET.SubElement(wpt, f"{{{GPX_NS}}}desc").text = (
            f"priority={wp.priority_score:.3f} eta_h={wp.arrival_hour:.1f}"
        )
    trk = ET.SubElement(gpx, f"{{{GPX_NS}}}trk")
    ET.SubElement(trk, f"{{{GPX_NS}}}name").text = "DRIFT vessel route"
    trkseg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
    for coord in mission.route.geometry.coordinates:
        lon, lat = float(coord[0]), float(coord[1])
        ET.SubElement(trkseg, f"{{{GPX_NS}}}trkpt", {
            "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
        })
    ET.ElementTree(gpx).write(path, encoding="utf-8", xml_declaration=True)
    return path


# ---------- GeoJSON ----------
def export_geojson(mission: MissionPlan, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mission.model_dump_json(indent=2), encoding="utf-8")
    return path


# ---------- PDF helpers ----------
_DEG_PER_M_LAT = 1.0 / 111_000.0  # rough conversion for m/s derivation


def _nearest_particle_displacement(
    lon: float, lat: float, forecast: ForecastEnvelope
) -> tuple[float, float]:
    """Return (u_ms, v_ms) m/s between frame[0] and frame[-1] at the
    nearest-particle-index to (lon, lat). Falls back to (0.0, 0.0) if
    forecast is empty or single-frame.
    """
    if not forecast.frames or len(forecast.frames) < 2:
        return (0.0, 0.0)
    frame0 = forecast.frames[0]
    framef = forecast.frames[-1]
    if not frame0.particle_positions or not framef.particle_positions:
        return (0.0, 0.0)

    def _d2(p):
        return (p[0] - lon) ** 2 + (p[1] - lat) ** 2
    idx = min(range(len(frame0.particle_positions)),
              key=lambda i: _d2(frame0.particle_positions[i]))
    if idx >= len(framef.particle_positions):
        idx = len(framef.particle_positions) - 1
    p0 = frame0.particle_positions[idx]
    pf = framef.particle_positions[idx]
    dt_s = max(1.0, (framef.hour - frame0.hour) * 3600.0)
    mean_lat = math.radians((p0[1] + pf[1]) / 2.0)
    dlon_m = (pf[0] - p0[0]) * 111_000.0 * math.cos(mean_lat)
    dlat_m = (pf[1] - p0[1]) * 111_000.0
    return (dlon_m / dt_s, dlat_m / dt_s)


def _build_currents_table_rows(
    mission: MissionPlan, forecast: ForecastEnvelope
) -> list[list[str]]:
    """Compose the D-09 currents summary. Header + one row per waypoint.

    Wind columns are deliberately omitted -- ForecastFrame carries no wind
    field (see schema). If a future phase adds u10/v10 to ForecastFrame,
    extend this function; the PDF caption documents the current limitation.
    """
    rows: list[list[str]] = [["#", "|v_current| (m/s)", "v_current dir (deg)"]]
    for wp in mission.waypoints:
        u, v = _nearest_particle_displacement(wp.lon, wp.lat, forecast)
        mag = math.hypot(u, v)
        # Oceanographic convention: direction TOWARD which current flows, 0=N, 90=E
        dir_deg = (math.degrees(math.atan2(u, v)) + 360.0) % 360.0
        rows.append([f"{wp.order:02d}", f"{mag:.3f}", f"{dir_deg:.1f}"])
    return rows


def _render_map_png(mission: MissionPlan,
                    forecast: Optional[ForecastEnvelope],
                    *, dpi: int = 150) -> BytesIO:
    fig, ax = plt.subplots(figsize=(6, 5), dpi=dpi)
    coast = _get_coastline()
    if coast is not None:
        coast.plot(ax=ax, color="#777777", linewidth=0.5)
    if forecast is not None and forecast.frames:
        last = forecast.frames[-1]
        if last.hour == 72 and last.density_polygons.features:
            gdf_dens = gpd.GeoDataFrame.from_features(
                [f.model_dump() for f in last.density_polygons.features],
                crs="EPSG:4326",
            )
            gdf_dens.plot(ax=ax, alpha=0.3, color="#00A0B0")
    route_coords = mission.route.geometry.coordinates
    if route_coords:
        xs = [float(c[0]) for c in route_coords]
        ys = [float(c[1]) for c in route_coords]
        ax.plot(xs, ys, color="#C8102E", linewidth=1.5)
    for wp in mission.waypoints:
        ax.scatter([wp.lon], [wp.lat], s=30, color="#FFB300",
                   edgecolors="#333", zorder=5)
        ax.annotate(f"WP{wp.order:02d}", (wp.lon, wp.lat),
                    fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.scatter([mission.origin[0]], [mission.origin[1]],
               s=80, marker="*", color="#1A237E", zorder=6)
    all_lons = [mission.origin[0]] + [wp.lon for wp in mission.waypoints]
    all_lats = [mission.origin[1]] + [wp.lat for wp in mission.waypoints]
    if all_lons:
        pad = 0.3
        ax.set_xlim(min(all_lons) - pad, max(all_lons) + pad)
        ax.set_ylim(min(all_lats) - pad, max(all_lats) + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.3, linestyle=":")
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def export_pdf(mission: MissionPlan,
               forecast: Optional[ForecastEnvelope],
               path: Path) -> Path:
    """One-page A4 portrait briefing per D-09."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("<b>DRIFT Cleanup Mission Briefing</b>", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))
    map_buf = _render_map_png(mission, forecast, dpi=150)
    story.append(Image(map_buf, width=11 * cm, height=9 * cm))
    story.append(Spacer(1, 0.3 * cm))
    rows = [["#", "Lon", "Lat", "ETA (h)", "Priority"]]
    for wp in mission.waypoints:
        rows.append([
            str(wp.order), f"{wp.lon:.4f}", f"{wp.lat:.4f}",
            f"{wp.arrival_hour:.1f}", f"{wp.priority_score:.3f}",
        ])
    if len(rows) == 1:
        rows.append(["-", "-", "-", "-", "-"])
    table = Table(rows, colWidths=[1 * cm, 2.5 * cm, 2.5 * cm, 2 * cm, 2.5 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A237E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.whitesmoke, colors.HexColor("#F0F0F0")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))

    # M5: D-09 Currents summary table from the +72h frame.
    if forecast is not None and forecast.frames and mission.waypoints:
        story.append(Paragraph(
            "<b>Currents Summary (+72 h frame, nearest-particle derived)</b>",
            styles["Heading4"],
        ))
        curr_rows = _build_currents_table_rows(mission, forecast)
        curr_table = Table(
            curr_rows, colWidths=[1.5 * cm, 3.5 * cm, 3.5 * cm],
        )
        curr_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00695C")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.whitesmoke, colors.HexColor("#F0F0F0")]),
        ]))
        story.append(curr_table)
        story.append(Paragraph(
            "<font size=6 color='#666'>Wind columns omitted -- ForecastEnvelope "
            "does not carry explicit u10/v10 fields in this schema; currents "
            "derived from +0h -> +72h particle displacement at the nearest "
            "particle to each waypoint. Direction is oceanographic convention "
            "(bearing toward which current flows).</font>",
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.3 * cm))

    est_fuel = mission.total_distance_km * FUEL_L_PER_KM
    story.append(Paragraph(
        f"<b>Summary:</b> distance {mission.total_distance_km:.1f} km "
        f"&middot; duration {mission.total_hours:.1f} h "
        f"&middot; est. fuel {est_fuel:.0f} L "
        f"(at {FUEL_L_PER_KM} L/km)",
        styles["Normal"],
    ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "<font size=7 color='#666'>DRIFT / PlastiTrack -- "
        "Sankalp Bharat SKB_P5</font>",
        styles["Normal"],
    ))
    doc.build(story)
    return path


# ---------- CLI ----------
def _cli() -> int:
    import argparse
    from backend.core.schemas import MissionPlan, ForecastEnvelope

    ap = argparse.ArgumentParser(
        prog="python -m backend.mission.export",
        description="Export a MissionPlan as GPX, GeoJSON, or PDF.",
    )
    ap.add_argument("--mission", type=Path, required=True,
                    help="Path to a JSON file containing a pydantic-serialized MissionPlan")
    ap.add_argument("--forecast", type=Path, default=None,
                    help="Optional ForecastEnvelope JSON (PDF uses +72h density overlay + currents table)")
    ap.add_argument("--format", choices=("gpx", "geojson", "pdf"), required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    mission = MissionPlan.model_validate_json(args.mission.read_text(encoding="utf-8"))
    forecast = None
    if args.forecast is not None:
        forecast = ForecastEnvelope.model_validate_json(
            args.forecast.read_text(encoding="utf-8"))

    if args.format == "gpx":
        export_gpx(mission, args.out)
    elif args.format == "geojson":
        export_geojson(mission, args.out)
    else:
        export_pdf(mission, forecast, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
