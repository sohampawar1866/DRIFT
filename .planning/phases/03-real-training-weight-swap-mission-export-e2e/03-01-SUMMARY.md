---
phase: 03-real-training-weight-swap-mission-export-e2e
plan: 01
subsystem: infra
tags: [environment, dependencies, basemap, gitignore]
requires: []
provides:
  - path: "backend/requirements.txt (reportlab>=4.2,<5.0)"
    for: "PDF briefing export (Plan 02)"
  - path: "data/basemap/ne_10m_coastline_indian_eez.shp"
    for: "Offline coastline for PDF map panel (D-11)"
  - path: "backend/ml/checkpoints/.gitkeep + hardened .gitignore"
    for: "User-supplied checkpoint handoff (Plan 03/04)"
  - path: "scripts/clip_basemap.py"
    for: "Reproducible clip from ne_10m_coastline source"
affects: []
tech_stack:
  added:
    - "reportlab 4.4.10 (>=4.2,<5.0 pin)"
  patterns:
    - "Natural Earth public-domain shapefile clipped + simplified with geopandas + shapely.box"
    - "gitignore whitelist via data/* + !data/basemap/* to keep env data ignored"
key_files:
  created:
    - "scripts/clip_basemap.py"
    - "data/basemap/README.md"
    - "data/basemap/ne_10m_coastline_indian_eez.{shp,shx,dbf,prj,cpg}"
    - "backend/ml/checkpoints/.gitkeep"
  modified:
    - "backend/requirements.txt"
    - ".gitignore"
decisions:
  - "Used naciscdn.org primary URL (plan listed it) — succeeded first try, no fallback needed."
  - "Simplify tol = 0.01 deg yields 199 features / 64 KB; well under 2 MB ceiling."
  - "Changed .gitignore 'data/' -> 'data/*' to enable directory whitelist — directory-form pattern blocks git from traversing into data/, which would defeat '!data/basemap/'."
metrics:
  duration_min: 3
  completed: "2026-04-17"
  tasks_total: 3
  tasks_done: 3
  commits: 3
---

# Phase 3 Plan 1: Environment Prerequisites Summary

Pinned reportlab 4.4.10, committed a 64 KB Natural Earth Indian-EEZ coastline subset for offline PDF mapping, and hardened `.gitignore` so `backend/ml/checkpoints/*.{pt,pth,pkl,ckpt}` cannot be accidentally committed while the directory stays tracked via `.gitkeep`.

## Objective Met

All three environment prerequisites in place: (a) `reportlab>=4.2,<5.0` importable in the active Python 3.11.3 venv; (b) offline coastline shapefile on disk at `data/basemap/ne_10m_coastline_indian_eez.shp` (199 features, 66,076 bytes, EPSG:4326); (c) checkpoint handoff path `backend/ml/checkpoints/` ignored for binary artefacts but tracked via `.gitkeep`.

## What Was Built

### Task 1 — reportlab pin (commit `6b8bc8c`)
- Appended `reportlab>=4.2,<5.0` to `backend/requirements.txt` under a new "Phase 3 — PDF briefing export" comment block.
- Installed 4.4.10 via `python -m pip install`. Import verified.
- No `torchmetrics`, `gpxpy`, `weasyprint`, or `cartopy` added (zero-sum scope rule honored).

### Task 2 — checkpoint gitignore hardening (commit `ce1eb3d`)
- Added explicit `backend/ml/checkpoints/*.{pt,pth,pkl,ckpt}` entries with `!backend/ml/checkpoints/.gitkeep` negation.
- Created `backend/ml/checkpoints/.gitkeep` so the dir tracks even when empty.
- Verified `git check-ignore` matches for `our_real.pt` (line 46), `foo.pth` (line 47), `bar.pkl` (line 48); `.gitkeep` correctly NOT ignored.

### Task 3 — basemap clip script + shapefile (commit `99404f2`)
- Wrote `scripts/clip_basemap.py` exactly per plan template (BBOX=(65.0, 3.0, 97.0, 27.0), simplify 0.01 deg).
- Downloaded `ne_10m_coastline.zip` from `https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip` (primary URL succeeded; fallback not needed).
- Ran clip: 199 features, 64 KB shp, total 4-file bundle 92,520 bytes.
- Wrote `data/basemap/README.md` with attribution and reproduction command.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rewrite `.gitignore` data rule to enable whitelist**
- **Found during:** Task 3 — staging basemap files
- **Issue:** Existing `data/` directory-form ignore rule blocks git from traversing into `data/basemap/`, so the plan-implied `!data/basemap/*` negation alone could not re-include the basemap files (`git add -n` returned "The following paths are ignored by one of your .gitignore files: data"). Plus `*.shp` was globally ignored.
- **Fix:** Changed `.gitignore` line from `data/` to `data/*` (per-entry form supports whitelisting), then added `!data/basemap/` + `!data/basemap/*` block. Verified `data/env/cmems.nc` still matches the ignore rule — no regression for env NetCDFs.
- **Files modified:** `.gitignore`
- **Commit:** `99404f2` (rolled into Task 3 commit)

No architectural deviations. No auth gates.

## Verification Results

| Check | Result |
| --- | --- |
| `python -c "import sys; assert (3,10)<=sys.version_info[:2]<(3,13)"` | OK — 3.11.3 |
| `python -c "import reportlab; print(reportlab.__version__)"` | `4.4.10` |
| `grep -E '^reportlab>=4\.2,<5\.0' backend/requirements.txt` | 1 line match |
| `grep -E 'torchmetrics\|gpxpy\|weasyprint\|cartopy' backend/requirements.txt` | no matches |
| `git check-ignore backend/ml/checkpoints/our_real.pt` | exit 0 (matched) |
| `git check-ignore backend/ml/checkpoints/foo.pth` | exit 0 (matched) |
| `git check-ignore backend/ml/checkpoints/bar.pkl` | exit 0 (matched) |
| `git check-ignore backend/ml/checkpoints/.gitkeep` | exit 1 (not ignored — correct) |
| `test -f backend/ml/checkpoints/.gitkeep` | present |
| `grep -n 'BBOX = (65.0, 3.0, 97.0, 27.0)' scripts/clip_basemap.py` | line 21 |
| `test -f data/basemap/ne_10m_coastline_indian_eez.{shp,shx,dbf,prj}` | all present |
| Shapefile size | 66,076 bytes (< 2 MB) |
| Total 4-file bundle size | 92,520 bytes |
| `gpd.read_file(...)` | 199 features, EPSG:4326 |
| README contains "Natural Earth" + "public domain" | both present |

All acceptance criteria for all three tasks passed.

## Commits

| Task | Commit | Message |
| --- | --- | --- |
| 1 | `6b8bc8c` | `chore(03-01): pin reportlab>=4.2,<5.0 for PDF briefing export` |
| 2 | `ce1eb3d` | `chore(03-01): harden .gitignore for user-supplied checkpoint handoff` |
| 3 | `99404f2` | `feat(03-01): add Indian EEZ coastline basemap + clip script (D-11)` |

## Downstream Unblocks

- **Plan 03-02 (mission export):** can now `import reportlab` and `geopandas.read_file("data/basemap/ne_10m_coastline_indian_eez.shp")` for the PDF map panel (D-09/D-10/D-11).
- **Plan 03-03 / 03-04 (weight-swap):** user can drop `our_real.pt`/`.pth`/`.pkl` into `backend/ml/checkpoints/` with zero risk of accidental commit.

## Self-Check: PASSED

- `scripts/clip_basemap.py` — FOUND
- `data/basemap/ne_10m_coastline_indian_eez.shp` — FOUND
- `data/basemap/ne_10m_coastline_indian_eez.shx` — FOUND
- `data/basemap/ne_10m_coastline_indian_eez.dbf` — FOUND
- `data/basemap/ne_10m_coastline_indian_eez.prj` — FOUND
- `data/basemap/README.md` — FOUND
- `backend/ml/checkpoints/.gitkeep` — FOUND
- Commit `6b8bc8c` — FOUND
- Commit `ce1eb3d` — FOUND
- Commit `99404f2` — FOUND
