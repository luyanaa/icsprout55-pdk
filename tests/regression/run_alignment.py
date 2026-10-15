#!/usr/bin/env python3
"""ICS55 PV alignment regression runner.

Invokes KLayout LVS and, optionally, DRC directly or through the LibreLane
nix-shell; hashes inputs/decks, normalizes extracted MOS graphs, and compares
against the frozen manifest. Emits one JSON record per fixture.

Fail-closed policy (see tests/regression/README.md):
- official_oracle is UNAVAILABLE (no local Calibre, no shipped reports);
- cross-tool equivalence is always BLOCKED;
- a KLayout self-consistency PASS is local evidence only, never Calibre parity.

Usage:
  python3 run_alignment.py [--cells INVX1H7H,INVX3H7H,INVX4H7H]
                           [--manifest tests/regression/klayout_alignment_manifest.json]
                           [--out tests/regression/out]
                           [--no-run] [--drc] [--klayout PATH]
                           [--librelane ~/Documents/librelane]

`--drc` runs the exact-category fixture suite and KLayout DRC on each selected
layout. It records KLayout findings; it does not imply Calibre equivalence.

Exit codes: 0 LVS checks and requested fixture assertions pass (same-GDS DRC executed); 1 regression failure, 2 blocked/harness error.
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
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
LVS_RUNNER = ROOT / "libs.tech" / "lvs" / "run_lvs.py"
NORMALIZER = Path(__file__).resolve().parent / "normalize_lvs.py"
DRC_DECK = ROOT / "libs.tech" / "drc" / "ics55_drc.drc"
DRC_FIXTURE_RUNNER = Path(__file__).resolve().parent / "drc_fixture_check.py"
DRC_FIXTURE_GENERATOR = Path(__file__).resolve().parent / "make_fixtures.rb"
CALIBRE_DRC_SOURCE = ROOT / "pv" / "DRC" / "ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc"
CALIBRE_ANT_SOURCE = ROOT / "pv" / "DRC" / "ICsprout_CalDRC_55LLULP1233_REV1_0_OS.ant"
DRC_RULES_JSON = ROOT / "libs.tech" / "drc" / "rule_decks" / "ics55_rules.json"
DRC_CROSSWALK = Path(__file__).resolve().parent / "official" / "drc_rule_comparison.json"
DRC_CROSSWALK_DOC = Path(__file__).resolve().parent / "official" / "drc_rule_comparison.md"
DRC_LAYER_MAPS = [
    ROOT / "techfile" / "icsprout55.layermap",
    ROOT / "libs.tech" / "klayout" / "tech" / "ics55.map",
]
DRC_MAIN_PROFILE = {
    "tables": "main",
    "no_feol": False,
    "no_beol": False,
    "check_grid": False,
    "advanced": False,
    "no_density": False,
    "no_mom": False,
    "cell_exclusion": False,
    "run_mode": "deep",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_drc_crosswalk():
    comparison = json.loads(DRC_CROSSWALK.read_text())
    current_rules = json.loads(DRC_RULES_JSON.read_text())["drc_rules"]
    rows = comparison["rules"]
    mapped = [row for row in rows if row.get("status") == "covered"]
    unmapped = [row for row in rows if row.get("status") == "missing"]
    stale_rows = [
        row for row in mapped
        if any(
            key in current_rules and current_rules[key] != value
            for key, value in (row.get("klayout_values") or {}).items()
        )
    ]
    issues = []
    rule_ids = [row.get("official") for row in rows]
    if any(not rule_id for rule_id in rule_ids) or len(set(rule_ids)) != len(rule_ids):
        issues.append("crosswalk contains duplicate or missing official rule IDs")
    if len(mapped) + len(unmapped) != len(rows):
        issues.append("crosswalk contains rows without covered/missing status")
    counts = {
        "total": len(rows),
        "threshold_or_name_mapped": len(mapped),
        "unmapped": len(unmapped),
        "stale_value_rows": len(stale_rows),
    }
    summary = comparison.get("summary", {})
    issues.extend(
        f"summary.{key}={summary.get(key)!r}, computed {value}"
        for key, value in counts.items()
        if summary.get(key) != value
    )
    if summary.get("semantically_equivalent") != 0:
        issues.append("static crosswalk must not claim semantic-equivalence passes")
    if not str(summary.get("differential_status", "")).startswith("BLOCKED"):
        issues.append("cross-tool differential must remain BLOCKED without Calibre results")
    return counts, issues


def run_in_librelane(librelane, cmd):
    full = ["nix-shell", str(librelane), "--run", " ".join(cmd)]
    return subprocess.run(full, capture_output=True, text=True)


def find_klayout(args) -> tuple[str, str] | None:
    if args.klayout:
        return ("bin", args.klayout) if shutil.which(args.klayout) else None
    if shutil.which("klayout"):
        return ("bin", "klayout")
    if args.librelane and Path(args.librelane).exists() and shutil.which("nix-shell"):
        return ("nix", str(args.librelane))
    return None


def run_drc(kind, exe, gds, top, report):
    drc_args = ["-b", "-r", str(DRC_DECK), "-rd", f"input={gds}", "-rd", f"top={top}",
                "-rd", f"report={report}"]
    for key, value in DRC_MAIN_PROFILE.items():
        drc_args.extend(["-rd", f"{key}={str(value).lower()}"])
    if kind == "nix":
        cmd = ["nix-shell", exe, "--run", shlex.join(["klayout"] + drc_args)]
    else:
        cmd = [exe] + drc_args
    return subprocess.run(cmd, capture_output=True, text=True)


def read_drc_categories(report):
    root = ET.parse(report).getroot()
    return sorted({
        category.strip("'").strip()
        for category in (item.findtext("category", "") for item in root.findall(".//item"))
        if category.strip("'").strip()
    })


def expected_from_manifest(manifest, cell):
    for ent in manifest.get("core_lvs_matrix", []):
        if cell in ent["cells"]:
            exp = dict(ent["expected"])
            exp["w_um_n_p"] = exp["w_um_n_p"][cell]
            return ent, exp
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default="INVX1H7H,INVX3H7H,INVX4H7H")
    ap.add_argument("--manifest", default=ROOT / "tests" / "regression" / "klayout_alignment_manifest.json")
    ap.add_argument("--out", default=ROOT / "tests" / "regression" / "out")
    ap.add_argument("--no-run", action="store_true", help="compare existing LVS outputs only")
    ap.add_argument("--update-hashes", action="store_true",
                    help="rewrite frozen_hashes in the manifest after the run")
    ap.add_argument("--drc", action="store_true",
                    help="run DRC fixtures and KLayout DRC on each selected layout")
    ap.add_argument("--klayout", default=None, help="KLayout executable for --drc")
    ap.add_argument("--librelane", default=Path.home() / "Documents" / "librelane")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    rc = 0
    crosswalk_counts, crosswalk_issues = audit_drc_crosswalk()
    results.append({
        "fixture": "drc_crosswalk_audit",
        "status": "FAIL" if crosswalk_issues else "PASS",
        "counts": crosswalk_counts,
        "issues": crosswalk_issues,
    })
    if crosswalk_issues:
        rc = 1
    # Freeze both the KLayout DRC implementation and the original Calibre
    # source/profile inputs. A drift invalidates the recorded comparison.
    rule_decks = [ROOT / "libs.tech" / "lvs" / "ics55.lvs"]
    rule_decks.extend(sorted((ROOT / "libs.tech" / "lvs" / "rule_decks").glob("*")))
    drc_rule_decks = [
        DRC_DECK,
        *sorted((ROOT / "libs.tech" / "drc" / "rule_decks").rglob("*.drc")),
        ROOT / "libs.tech" / "drc" / "rule_decks" / "ics55_rules.json",
    ]
    profile_sha256 = hashlib.sha256(
        json.dumps(DRC_MAIN_PROFILE, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    current_hashes = {
        "lvs_runner": sha256(LVS_RUNNER),
        "normalizer": sha256(NORMALIZER),
        "harness": sha256(Path(__file__).resolve()),
        "lvs_rule_decks": {p.name: sha256(p) for p in rule_decks},
        "official_drc_profile": manifest.get("official_drc_profile"),
        "drc_profile": DRC_MAIN_PROFILE,
        "drc_profile_sha256": profile_sha256,
        "drc_rule_decks": {p.relative_to(ROOT).as_posix(): sha256(p) for p in drc_rule_decks},
        "drc_layer_maps": {p.relative_to(ROOT).as_posix(): sha256(p) for p in DRC_LAYER_MAPS},
        "drc_harnesses": {
            DRC_FIXTURE_RUNNER.relative_to(ROOT).as_posix(): sha256(DRC_FIXTURE_RUNNER),
            DRC_FIXTURE_GENERATOR.relative_to(ROOT).as_posix(): sha256(DRC_FIXTURE_GENERATOR),
        },
        "calibre_drc_sources": {
            CALIBRE_DRC_SOURCE.name: sha256(CALIBRE_DRC_SOURCE),
            CALIBRE_ANT_SOURCE.name: sha256(CALIBRE_ANT_SOURCE),
        },
        "drc_crosswalk": {
            DRC_CROSSWALK.relative_to(ROOT).as_posix(): sha256(DRC_CROSSWALK),
            DRC_CROSSWALK_DOC.relative_to(ROOT).as_posix(): sha256(DRC_CROSSWALK_DOC),
        },
    }
    frozen = manifest.get("frozen_hashes")
    if frozen:
        def _short(value):
            return value[:12] if isinstance(value, str) else json.dumps(value, sort_keys=True)[:60]

        def _diff(frozen_part, current_part, prefix=""):
            out = {}
            if not isinstance(frozen_part, dict) or not isinstance(current_part, dict):
                if frozen_part != current_part:
                    out[prefix.rstrip(".")] = (_short(frozen_part), _short(current_part))
                return out
            for key, val in current_part.items():
                if key not in frozen_part:
                    out[f"{prefix}{key}"] = ("MISSING", _short(val))
                else:
                    fv = frozen_part[key]
                    if isinstance(val, dict) or isinstance(fv, dict):
                        out.update(_diff(fv, val, f"{prefix}{key}."))
                    elif fv != val:
                        out[f"{prefix}{key}"] = (_short(fv), _short(val))
            for key, val in frozen_part.items():
                if key not in current_part:
                    out[f"{prefix}{key}"] = (_short(val), "MISSING")
            return out

        drifted = _diff(frozen, current_hashes)
        if drifted and not args.update_hashes:
            results.append({"fixture": "frozen_hashes", "status": "FAIL",
                            "issues": [f"input drift from frozen manifest: {drifted}"]})
            rc = 1
        if args.update_hashes:
            manifest["frozen_hashes"] = current_hashes
            Path(args.manifest).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
            print("frozen_hashes updated in manifest")
    drc_klayout = find_klayout(args) if args.drc else None
    drc_klayout_info = None
    if args.drc:
        if drc_klayout is None:
            results.append({
                "fixture": "drc_fixture_suite",
                "status": "BLOCKED",
                "reason": "KLayout unavailable (provide --klayout or --librelane)",
            })
            rc = 2
        else:
            fixture_out = out_dir / "drc_fixtures"
            fixture_cmd = [
                sys.executable, str(DRC_FIXTURE_RUNNER), "--out", str(fixture_out),
            ]
            fixture_cmd += ["--klayout", args.klayout] if args.klayout else ["--librelane", str(args.librelane)]
            fixture_run = subprocess.run(fixture_cmd, capture_output=True, text=True)
            fixture_report = fixture_out / "drc_fixture_check.json"
            try:
                fixture_data = json.loads(fixture_report.read_text())
                fixture_status = fixture_data.get("status")
                drc_klayout_info = fixture_data.get("klayout")
            except Exception as e:
                fixture_data = {"reason": f"fixture report unavailable/invalid: {e}"}
                fixture_status = "BLOCKED"
            fixture_record = {
                "fixture": "drc_fixture_suite",
                "status": fixture_status,
                "runner_rc": fixture_run.returncode,
                "report": str(fixture_report),
                "report_sha256": sha256(fixture_report) if fixture_report.exists() else None,
                "result": fixture_data,
            }
            results.append(fixture_record)
            if fixture_run.returncode != 0 or fixture_status != "PASS":
                rc = max(rc, 1 if fixture_status == "FAIL" else 2)
    for cell in [c.strip() for c in args.cells.split(",") if c.strip()]:
        ent, exp = expected_from_manifest(manifest, cell)
        if not ent or exp is None:
            results.append({"fixture": cell, "status": "BLOCKED", "reason": "not in manifest"})
            rc = 2
            continue
        exp = cast(dict[str, Any], exp)
        lib = ROOT / ent["lib"]
        gds = lib / "gds" / f"{lib.name}.gds"
        cdl = lib / "cdl" / f"{lib.name}.cdl"
        out_cir = out_dir / f"{cell}_fresh.cir"
        out_db = out_dir / f"{cell}.lvsdb"
        rec: dict[str, Any] = {"fixture": f"{ent['flavor']}/{cell}", "status": "PASS"}
        if not args.no_run:
            r = run_in_librelane(args.librelane, [
                "set -e",
                f"python3 {LVS_RUNNER} --layout {gds} --top {cell} --netlist {cdl} "
                f"--target-netlist {out_cir} --report {out_db}",
            ])
            rec["runner_rc"] = r.returncode
            rec["runner_stderr_tail"] = r.stderr.strip().splitlines()[-3:]
        # provenance hashes
        try:
            rec["provenance"] = {
                "gds_sha256": sha256(gds),
                "cdl_sha256": sha256(cdl),
                "lvs_runner_sha256": sha256(LVS_RUNNER),
                "lvs_deck_sha256": sha256(LVS_RUNNER.parent / "ics55.lvs"),
                "manifest_sha256": sha256(args.manifest),
                "extracted_sha256": sha256(out_cir),
            }
        except FileNotFoundError as e:
            rec["status"] = "BLOCKED"
            rec["reason"] = f"missing provenance input: {e}"
            results.append(rec)
            rc = 2
            continue
        if args.drc:
            drc_report = out_dir / "drc_reports" / f"{cell}.lyrdb"
            drc_report.parent.mkdir(parents=True, exist_ok=True)
            drc_rec = {
                "status": "BLOCKED",
                "klayout": drc_klayout_info,
                "profile": DRC_MAIN_PROFILE,
                "profile_sha256": profile_sha256,
                "deck_sha256": sha256(DRC_DECK),
                "klayout_rule_inputs_sha256": {
                    path.relative_to(ROOT).as_posix(): sha256(path) for path in drc_rule_decks
                },
                "layer_maps_sha256": {
                    path.relative_to(ROOT).as_posix(): sha256(path) for path in DRC_LAYER_MAPS
                },
                "calibre_source_decks_sha256": {
                    CALIBRE_DRC_SOURCE.name: sha256(CALIBRE_DRC_SOURCE),
                    CALIBRE_ANT_SOURCE.name: sha256(CALIBRE_ANT_SOURCE),
                },
                "input_gds_sha256": rec["provenance"]["gds_sha256"],
                "report": str(drc_report),
            }
            if drc_klayout is None:
                drc_rec["reason"] = "KLayout unavailable"
                rc = 2
            else:
                kind, exe = drc_klayout
                dr = run_drc(kind, exe, gds, cell, drc_report)
                drc_rec["runner_rc"] = dr.returncode
                if dr.returncode != 0 or not drc_report.exists():
                    drc_rec["reason"] = (
                        f"KLayout DRC failed (rc={dr.returncode}): "
                        f"{dr.stderr.strip().splitlines()[-3:]}"
                    )
                    rc = 2
                else:
                    try:
                        drc_rec["categories"] = read_drc_categories(drc_report)
                        drc_rec["report_sha256"] = sha256(drc_report)
                        drc_rec["status"] = "EXECUTED"
                    except Exception as e:
                        drc_rec["reason"] = f"DRC report parse failed: {e}"
                        rc = 2
            drc_rec["cross_tool_equivalence"] = "BLOCKED (no Calibre run/report)"
            rec["klayout_drc"] = drc_rec
        # normalize + compare against manifest expectations
        try:
            nr = subprocess.run([sys.executable, str(NORMALIZER), "--json", str(out_cir)],
                                capture_output=True, text=True, check=True)
            devices = json.loads(nr.stdout)
        except Exception as e:
            rec["status"] = "BLOCKED"
            rec["reason"] = f"normalizer failed: {e}"
            results.append(rec)
            rc = 2
            continue
        rec["devices"] = devices
        issues = []
        if len(devices) != exp["per_cell_devices"]:
            issues.append(f"device count {len(devices)} != {exp['per_cell_devices']}")
        wn, wp = exp["w_um_n_p"]  # type: ignore[misc]
        for dev in devices:
            w = dev.get("w"); l = dev.get("l")
            if l is not None and abs(l - exp["L_um"]) > 1e-9:
                issues.append(f"L {l} != {exp['L_um']}")
            prefix_ok = any(dev["model"].startswith(p.lower()) for p in exp["model_prefix"])
            if not prefix_ok:
                issues.append(f"model {dev['model']} not in {exp['model_prefix']}")
            if dev["model"].startswith("n") and w is not None and abs(w - wn) > 0.005:
                issues.append(f"NMOS W {w} != {wn}")
            if dev["model"].startswith("p") and w is not None and abs(w - wp) > 0.005:
                issues.append(f"PMOS W {w} != {wp}")
            t = dev["terminals"]
            if dev["model"].startswith("n"):
                if [t["D"], t["G"], t["S"], t["B"]] != exp["terminals_nmos"]:
                    issues.append(f"NMOS terminals {[t['D'], t['G'], t['S'], t['B']]}")
            else:
                if [t["D"], t["G"], t["S"], t["B"]] != exp["terminals_pmos"]:
                    issues.append(f"PMOS terminals {[t['D'], t['G'], t['S'], t['B']]}")
        if issues:
            rec["status"] = "FAIL"
            rec["issues"] = issues
            rc = max(rc, 1)
        # fail-closed oracle policy
        rec["official_oracle"] = "UNAVAILABLE"
        rec["cross_tool_equivalence"] = "BLOCKED (no Calibre artifacts)"
        if args.drc:
            rec["drc_cross_tool_equivalence"] = "BLOCKED (no Calibre run/report)"
        results.append(rec)

    out = out_dir / "alignment_results.json"
    out.write_text(json.dumps({"schema": "ics55-alignment-result/1.1", "results": results}, indent=2))
    for r in results:
        print(f"{r['status']:9s} {r['fixture']}" + (f"  - {r.get('issues')}" if r.get("issues") else ""))
    return rc

if __name__ == "__main__":
    sys.exit(main())
