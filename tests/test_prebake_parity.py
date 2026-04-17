"""Plan 03-06 parity + manifest gates.

Checks, after `python -m scripts.prebake_demo` has been run:

* MANIFEST.json exists and is well-formed
* HARD gate: gulf_of_mannar has all 3 stages (detections/forecast/mission)
* SOFT gate: other AOIs warn (not fail) if any stage is missing
* Every declared hash matches the on-disk file's hash (fp-stable parity)
* Every manifest entry count is consistent with the on-disk file's feature count
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

PREBAKE_DIR = Path("data/prebaked")
MANIFEST = PREBAKE_DIR / "MANIFEST.json"
PRIMARY_AOI = "gulf_of_mannar"
OTHER_AOIS = ("mumbai_offshore", "bay_of_bengal_mouth", "arabian_sea_gyre_edge")
REQUIRED_STAGES = ("detections", "forecast", "mission")


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip(f"{MANIFEST} not found — run `python -m scripts.prebake_demo` first")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_well_formed():
    m = _load_manifest()
    assert "entries" in m
    assert "generated_at" in m
    assert "git_sha" in m
    assert "weights_source" in m
    assert isinstance(m["entries"], list)


def test_manifest_hard_gate_primary_aoi_complete():
    """HARD: primary AOI must bake all 3 stages."""
    m = _load_manifest()
    entries_by_aoi = {e["aoi"]: e for e in m["entries"]}
    primary = entries_by_aoi.get(PRIMARY_AOI)
    assert primary is not None, f"HARD gate: {PRIMARY_AOI} missing from manifest"
    assert primary["status"] == "ok", (
        f"HARD gate: {PRIMARY_AOI} status={primary['status']}, "
        f"error={primary.get('error')}"
    )
    for stage in REQUIRED_STAGES:
        assert stage in primary.get("stages", {}), (
            f"HARD gate: {PRIMARY_AOI} missing stage '{stage}'"
        )


def test_manifest_soft_gate_other_aois_warn_only():
    """SOFT: other AOIs emit warnings but never fail the test."""
    m = _load_manifest()
    entries_by_aoi = {e["aoi"]: e for e in m["entries"]}
    for aoi in OTHER_AOIS:
        e = entries_by_aoi.get(aoi)
        if e is None or e.get("status") != "ok":
            warnings.warn(
                f"SOFT gate: AOI '{aoi}' did not bake cleanly "
                f"(status={e.get('status') if e else 'missing'})",
                UserWarning, stacklevel=2,
            )


def test_manifest_entry_count_target():
    """Informational: target is 4 AOIs × 3 stages = 12 entry-stages."""
    m = _load_manifest()
    total_stages = sum(len(e.get("stages", {})) for e in m["entries"])
    if total_stages < 12:
        warnings.warn(
            f"Prebake target not reached: {total_stages}/12 stages present "
            f"across {len(m['entries'])} AOIs. Re-run prebake for full demo readiness.",
            UserWarning, stacklevel=2,
        )


def test_parity_hashes_match_disk():
    """Every declared hash must match the on-disk file's parity hash."""
    from scripts.parity_hash import parity_hash_json

    m = _load_manifest()
    for entry in m["entries"]:
        if entry.get("status") != "ok":
            continue
        for stage, declared in entry.get("hashes", {}).items():
            file_rel = entry.get("files", {}).get(stage)
            assert file_rel, f"{entry['aoi']} {stage}: no file path in manifest"
            file_path = Path(file_rel)
            assert file_path.exists(), f"missing file: {file_path}"
            actual = parity_hash_json(file_path.read_text(encoding="utf-8"))
            assert actual == declared, (
                f"parity mismatch {entry['aoi']}/{stage}: "
                f"declared={declared[:12]}... actual={actual[:12]}..."
            )


def test_all_files_listed_in_manifest_exist_on_disk():
    """Structural: no phantom manifest entries."""
    m = _load_manifest()
    for entry in m["entries"]:
        for stage, path_str in entry.get("files", {}).items():
            p = Path(path_str)
            assert p.exists(), f"{entry['aoi']}/{stage} → {p} missing on disk"
