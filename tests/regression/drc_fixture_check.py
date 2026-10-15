#!/usr/bin/env python3
"""ICS55 DRC fixture regression (KLayout self-consistency).

Generates FEOL/BEOL core-rule layouts and asserts exact category sets, including
threshold boundaries, marker waivers, and rotated via enclosure. Fixtures are
written by KLayout itself (`tests/regression/make_fixtures.rb`); they do not
reimplement GDS encoding. This verifies only the KLayout port, never Calibre
parity.

KLayout is selected from PATH / `--klayout`, or from the LibreLane nix shell
(`--librelane`). Missing tools or failed runs are BLOCKED, not PASS.

Usage:
  python3 drc_fixture_check.py [--librelane ~/Documents/librelane]
                               [--klayout PATH] [--out tests/regression/out]

Exit codes: 0 exact fixture match, 1 category mismatch, 2 blocked/harness error.
"""
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DRC_DECK = ROOT / "libs.tech" / "drc" / "ics55_drc.drc"
MAKE_FIXTURES = Path(__file__).resolve().parent / "make_fixtures.rb"

# KLayout self-consistency profiles. Main covers FEOL/BEOL/dummy/special;
# density and MOM run separately so each fixture exercises the selected family.
# These are source-behavior fixtures, not a Calibre differential.
DRC_PROFILES = {
    "main": {
        "tables": "main", "no_feol": False, "no_beol": False,
        "check_grid": False, "advanced": False, "no_density": True,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
    },
    "density": {
        "tables": "density", "no_feol": False, "no_beol": False,
        "check_grid": False, "advanced": False, "no_density": False,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
    },
    "mom": {
        "tables": "mom", "no_feol": False, "no_beol": False,
        "check_grid": False, "advanced": False, "no_density": True,
        "no_mom": False, "cell_exclusion": False, "run_mode": "deep",
    },
}

# fixture name -> exact expected rule-category set; profile-specific families
# are mapped separately below.
FIXTURES: dict[str, frozenset[str]] = {
    "clean": frozenset(),
    "act_area": frozenset({"active.act.area"}),
    "act_area_at_limit": frozenset(),
    "act_area_nodrc_waived": frozenset(),
    "poly_area": frozenset({"poly.poly.area"}),
    "poly_area_at_limit": frozenset(),
    "poly_area_nodrc_waived": frozenset(),
    "poly_area_partial_marker": frozenset({"poly.poly.area"}),
    "poly_hole": frozenset({"poly.poly.enclosed_area"}),
    "poly_hole_at_limit": frozenset(),
    "np_area": frozenset({"implant.np.area"}),
    "np_area_at_limit": frozenset(),
    "pp_area": frozenset({"implant.pp.area"}),
    "pp_area_at_limit": frozenset(),
    "ct_outside_required_layers": frozenset({"cont.ct.inside"}),
    "m1_area": frozenset({"metal.m1.area"}),
    "m1_area_at_limit": frozenset(),
    "m1_area_nodrc_waived": frozenset(),
    "m1_hole": frozenset({"metal.m1.min_hole"}),
    "m1_hole_at_limit": frozenset(),
    "t4m2_area": frozenset({"metal.tm2.area"}),
    "t4m2_area_at_limit": frozenset(),
    "t4m2_hole": frozenset({"metal.tm2.min_hole"}),
    "t4m2_hole_at_limit": frozenset(),
    "v1_wrong_square": frozenset({"via.v1.width"}),
    "v1_square_at_limit": frozenset(),
    "v1_bar_not_used_by_w1": frozenset(),
    "v1_uncovered_lower_metal": frozenset({"via.v1.cover.lower"}),
    "v1_uncovered_nodrc_waived": frozenset(),
    "v1_diagonal_edges": frozenset({"via.v1.width", "via.v1.rotated"}),
    "v1_diagonal_sringblk_waived": frozenset(),
    "v1_grid_exclusion": frozenset(),
    "rv_wrong_rectangle": frozenset({"pad.rv.width"}),
    "rv_grid_exclusion": frozenset(),
    "rv_exact_rectangle": frozenset(),
    "rv_outside_rdl": frozenset({"pad.rv.cover.rdl"}),
    "cover_outside_alpa": frozenset({"pad.cover.alpa_full"}),
    "cb_outside_alpad": frozenset({"pad.cb.alpad_full"}),
    "act_dummy_valid": frozenset(),
    "act_dummy_invalid": frozenset({"AADUM_W_1"}),
    "act_dummy_ct_overlap": frozenset({"AADUM_R_1"}),
    "poly_dummy_valid": frozenset(),
    "poly_dummy_invalid": frozenset({"PODUM_W_1"}),
    "m1_dummy_invalid": frozenset({"M1DUM_W_1"}),
    "t4m2_dummy_valid_rotated": frozenset(),
    "slot_cb_overlap": frozenset({"SL_R_1"}),
    "efu_fuse_without_efuse": frozenset({"EFU_1b_G"}),
    "efu_efuse_uncovered_by_fuse": frozenset({"EFU_1c_G", "EFU_2b_G"}),
    "efu_po_block_uncovered": frozenset({"EFU_2c_G"}),
    "efu_nodrc_waived": frozenset(),
    "deupad_r2": frozenset({"DEUPAD_R_2"}),
    "deupad_r2_nodrc_waived": frozenset(),
    "deupad_r5": frozenset({"DEUPAD_R_5"}),
    "deupad_r6_v4bar": frozenset({"DEUPAD_R_6"}),
    "esd_area": frozenset({"ESD_A_1"}),
    "esd_area_at_limit": frozenset(),
    "esd_area_nodrc_waived": frozenset(),
    "esd_hole": frozenset({"ESD_A_2"}),
    "esd_hole_at_limit": frozenset(),
    "density_act_low": frozenset({"ACT_D_1_min", "ACT_D_4_min"}),
    "density_act_small_low": frozenset({"ACT_D_1_min", "ACT_D_4_min"}),
    "density_act_exact_min": frozenset({"ACT_D_4_min"}),
    "density_act_exact_max": frozenset({"ACT_D_4_max"}),
    "density_act_near_min": frozenset({"ACT_D_1_min", "ACT_D_4_min"}),
    "density_act_near_max": frozenset({"ACT_D_1_max", "ACT_D_4_max"}),
    "density_backup_min": frozenset({"ACT_D_1_min"}),
    "density_nodrc_waived": frozenset(),
    "density_act_dummy_low": frozenset({"ACT_D_1_min", "ACT_D_2", "ACT_D_4_min"}),
    "density_m1_dummy_low": frozenset({"MET1_D_1_min", "MET1_D_2"}),
    "density_t4m2_dummy_low": frozenset({"T4M2_D_1_min", "T4M2_D_2"}),
    "mom_v1_m1mom": frozenset({"mom.MOM_R_1.V1.MET1MOM"}),
    "mom_v1bar_m1mom": frozenset({"mom.MOM_R_1.V1.MET1MOM"}),
    "mom_v1_nodrc_waived": frozenset(),
    "mom_forbidden_m1_cap23": frozenset({"mom.MOM_R_2.forbidden_stack.MET1MOM.23"}),
    "mom_cap12_missing_label": frozenset({"mom.MOM_R_2.label_stack.12"}),
    "mom_cap12_valid_label": frozenset(),
}
FIXTURE_PROFILES = {
    name: ("density" if name.startswith("density_") else "mom")
    for name in FIXTURES
    if name.startswith(("density_", "mom_"))
}

RULE_INPUTS = [
    DRC_DECK,
    *sorted((ROOT / "libs.tech" / "drc" / "rule_decks").rglob("*.drc")),
    ROOT / "libs.tech" / "drc" / "rule_decks" / "ics55_rules.json",
    ROOT / "techfile" / "icsprout55.layermap",
    ROOT / "libs.tech" / "klayout" / "tech" / "ics55.map",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_klayout(args) -> tuple[str, str] | None:
    """Return (kind, executable) with kind 'bin' (direct) or 'nix' (nix shell)."""
    if args.klayout:
        return ("bin", args.klayout) if shutil.which(args.klayout) else None
    if shutil.which("klayout"):
        return ("bin", "klayout")
    if args.librelane and Path(args.librelane).exists() and shutil.which("nix-shell"):
        return ("nix", str(args.librelane))
    return None

def get_klayout_version(kind: str, exe: str) -> str | None:
    if kind == "nix":
        cmd = ["nix-shell", exe, "--run", shlex.join(["klayout", "-v"])]
    else:
        cmd = [exe, "-v"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return None
    if run.returncode != 0:
        return None
    return next(
        (line.strip() for line in (run.stdout + "\n" + run.stderr).splitlines()
         if line.strip().startswith("KLayout ")),
        None,
    )


def run_klayout(kind: str, exe: str, script: Path, extra: list[str]) -> subprocess.CompletedProcess:
    base = ["-b", "-r", str(script)] + extra
    if kind == "nix":
        cmd = ["nix-shell", exe, "--run", shlex.join(["klayout"] + base)]
    else:
        cmd = [exe] + base
    return subprocess.run(cmd, capture_output=True, text=True)


def run_drc(kind: str, exe: str, gds: Path, report: Path, profile: dict[str, Any]) -> subprocess.CompletedProcess:
    switches = ["-rd", f"tables={profile['tables']}"]
    switches.extend(
        argument
        for key, value in profile.items()
        if key != "tables"
        for argument in ("-rd", f"{key}={str(value).lower()}")
    )
    extra = ["-rd", f"input={gds}", "-rd", "top=TOP", "-rd", f"report={report}"] + switches
    base = ["-b", "-r", str(DRC_DECK)] + extra
    if kind == "nix":
        cmd = ["nix-shell", exe, "--run", shlex.join(["klayout"] + base)]
    else:
        cmd = [exe] + base
    return subprocess.run(cmd, capture_output=True, text=True)


def read_violation_categories(report: Path) -> list[str]:
    """Item categories from a KLayout .lyrdb (XML)."""
    root = ET.parse(report).getroot()
    cats = []
    for item in root.findall(".//item"):
        cat = item.findtext("category", "")
        cats.append(cat.strip("'").strip())
    return sorted(set(c for c in cats if c))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--librelane", default=Path.home() / "Documents" / "librelane")
    ap.add_argument("--klayout", default=None)
    ap.add_argument("--out", default=ROOT / "tests" / "regression" / "out")
    args = ap.parse_args()

    klayout = find_klayout(args)
    out_dir = Path(args.out)
    fx_dir = out_dir / "fixtures"
    fx_dir.mkdir(parents=True, exist_ok=True)

    if not klayout:
        (out_dir / "drc_fixture_check.json").write_text(json.dumps({
            "schema": "ics55-drc-fixture-check/1.3",
            "status": "BLOCKED",
            "reason": "KLayout not found (PATH, --klayout, or --librelane nix shell)",
        }, indent=2))
        print("BLOCKED (KLayout not found)")
        return 2

    kind, exe = klayout
    version = get_klayout_version(kind, exe)
    if version is None:
        (out_dir / "drc_fixture_check.json").write_text(json.dumps({
            "schema": "ics55-drc-fixture-check/1.3",
            "status": "BLOCKED",
            "klayout": {"kind": kind, "executable": exe},
            "reason": "KLayout version could not be recorded",
        }, indent=2))
        print("BLOCKED (KLayout version unavailable)")
        return 2

    # generate fixtures with klayout itself (no hand-rolled GDS writer)
    gen = run_klayout(kind, exe, MAKE_FIXTURES, ["-rd", f"out={fx_dir}"])
    if gen.returncode != 0:
        (out_dir / "drc_fixture_check.json").write_text(json.dumps({
            "schema": "ics55-drc-fixture-check/1.3",
            "status": "BLOCKED",
            "reason": f"fixture generation failed: {gen.stderr.strip().splitlines()[-3:]}",
        }, indent=2))
        print("BLOCKED (fixture generation failed)")
        return 2

    results = []
    rc = 0
    for name, expected in FIXTURES.items():
        profile_name = FIXTURE_PROFILES.get(name, "main")
        profile = DRC_PROFILES[profile_name]
        gds = fx_dir / f"{name}.gds"
        report = fx_dir / f"{name}.lyrdb"
        r = run_drc(kind, exe, gds, report, profile)
        rec: dict[str, Any] = {
            "fixture": name,
            "profile": profile_name,
            "expected_categories": sorted(expected),
        }
        if gds.exists():
            rec["gds_sha256"] = sha256(gds)
        if r.returncode != 0 or not report.exists():
            rec["status"] = "BLOCKED"
            detail = r.stderr.strip().splitlines()[-3:] or ["no stderr"]
            rec["reason"] = f"DRC run failed (rc={r.returncode}): {' | '.join(detail)}"
            results.append(rec)
            rc = 2
            continue
        try:
            cats = read_violation_categories(report)
        except Exception as e:
            rec["status"] = "BLOCKED"
            rec["reason"] = f"lyrdb parse failed: {e}"
            results.append(rec)
            rc = 2
            continue
        rec["categories"] = cats
        expected_categories = set(expected or ())
        actual_categories = set(cats)
        missing = sorted(expected_categories - actual_categories)
        unexpected = sorted(actual_categories - expected_categories)
        rec["status"] = "PASS" if not missing and not unexpected else "FAIL"
        if missing or unexpected:
            rec["issues"] = []
            if missing:
                rec["issues"].append(f"expected categories absent: {missing}")
            if unexpected:
                rec["issues"].append(f"unexpected categories present: {unexpected}")
            rc = 1
        results.append(rec)

    profile_sha256 = hashlib.sha256(
        json.dumps(DRC_PROFILES, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (out_dir / "drc_fixture_check.json").write_text(json.dumps({
        "schema": "ics55-drc-fixture-check/1.3",
        "status": "PASS" if rc == 0 else ("FAIL" if rc == 1 else "BLOCKED"),
        "profiles": DRC_PROFILES,
        "klayout": {"kind": kind, "executable": exe, "version": version},
        "profile_sha256": profile_sha256,
        "rule_inputs_sha256": {
            str(path.relative_to(ROOT)): sha256(path) for path in RULE_INPUTS
        },
        "results": results,
        "deck_sha256": sha256(DRC_DECK),
        "fixture_generator_sha256": sha256(MAKE_FIXTURES),
        "fixture_runner_sha256": sha256(Path(__file__).resolve()),
    }, indent=2))
    for r in results:
        print(f"{r['status']:9s} {r['fixture']}" + (f"  - {r.get('issues')}" if r.get("issues") else ""))
    return rc


if __name__ == "__main__":
    sys.exit(main())
