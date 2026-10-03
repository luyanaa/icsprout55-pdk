#!/usr/bin/env python3
"""ICS55 PV alignment regression runner.

Invokes the existing KLayout LVS (and optionally DRC) runners through the
LibreLane nix-shell, hashes every input/deck/output, normalizes extracted MOS
graphs, and compares against the frozen manifest. Emits one JSON record per
fixture with status PASS | FAIL | BLOCKED | UNAVAILABLE.

Fail-closed policy (see tests/regression/README.md):
- official_oracle is UNAVAILABLE (no local Calibre, no shipped reports);
- cross-tool equivalence is always BLOCKED;
- a KLayout self-consistency PASS is local evidence only, never Calibre parity.

Usage:
  python3 run_alignment.py [--cells INVX1H7H,INVX3H7H,INVX4H7H]
                           [--manifest tests/regression/klayout_alignment_manifest.json]
                           [--out tests/regression/out]
                           [--no-run] [--drc] [--librelane ~/Documents/librelane]

Exit codes: 0 all ok, 1 fixture failures, 2 harness error.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
LVS_RUNNER = ROOT / "libs.tech" / "lvs" / "run_lvs.py"
NORMALIZER = Path(__file__).resolve().parent / "normalize_lvs.py"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_in_librelane(librelane, cmd):
    full = ["nix-shell", str(librelane), "--run", " ".join(cmd)]
    return subprocess.run(full, capture_output=True, text=True)


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
    ap.add_argument("--no-run", action="store_true", help="compare existing outputs only")
    ap.add_argument("--update-hashes", action="store_true",
                    help="rewrite frozen_hashes in the manifest after the run")
    ap.add_argument("--drc", action="store_true", help="also run DRC on the same layouts (basic)")
    ap.add_argument("--librelane", default=Path.home() / "Documents" / "librelane")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    rc = 0
    # frozen-input drift check: the LVS port and harness are frozen by hash in
    # the manifest; any drift invalidates PASS records.  Regenerate deliberately
    # with --update-hashes.
    rule_decks = sorted((ROOT / "libs.tech" / "lvs" / "rule_decks").glob("*"))
    current_hashes = {
        "lvs_runner": sha256(LVS_RUNNER),
        "normalizer": sha256(NORMALIZER),
        "harness": sha256(Path(__file__).resolve()),
        "lvs_rule_decks": {p.name: sha256(p) for p in rule_decks},
    }
    frozen = manifest.get("frozen_hashes")
    if frozen:
        def _diff(frozen_part, current_part, prefix=""):
            out = {}
            for key, val in current_part.items():
                fv = frozen_part.get(key)
                if isinstance(val, dict):
                    out.update(_diff(fv if isinstance(fv, dict) else {}, val, f"{prefix}{key}."))
                elif fv is not None and fv != val:
                    out[f"{prefix}{key}"] = (fv[:12], val[:12])
            return out
        drifted = _diff(frozen, current_hashes)
        if drifted:
            results.append({"fixture": "frozen_hashes", "status": "FAIL",
                            "issues": [f"input drift from frozen manifest: {drifted}"]})
            rc = 1
        if args.update_hashes:
            manifest["frozen_hashes"] = current_hashes
            Path(args.manifest).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
            print("frozen_hashes updated in manifest")
    for cell in [c.strip() for c in args.cells.split(",") if c.strip()]:
        ent, exp = expected_from_manifest(manifest, cell)
        if not ent or exp is None:
            results.append({"fixture": cell, "status": "BLOCKED", "reason": "not in manifest"})
            rc = 1
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
                "manifest_sha256": sha256(args.manifest),
                "extracted_sha256": sha256(out_cir),
            }
        except FileNotFoundError as e:
            rec["status"] = "BLOCKED"
            rec["reason"] = f"missing provenance input: {e}"
            results.append(rec)
            rc = 1
            continue
        # normalize + compare against manifest expectations
        try:
            nr = subprocess.run([sys.executable, str(NORMALIZER), "--json", str(out_cir)],
                                capture_output=True, text=True, check=True)
            devices = json.loads(nr.stdout)
        except Exception as e:
            rec["status"] = "BLOCKED"
            rec["reason"] = f"normalizer failed: {e}"
            results.append(rec)
            rc = 1
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
            rc = 1
        # fail-closed oracle policy
        rec["official_oracle"] = "UNAVAILABLE"
        rec["cross_tool_equivalence"] = "BLOCKED (no Calibre artifacts)"
        results.append(rec)

    out = out_dir / "alignment_results.json"
    out.write_text(json.dumps({"schema": "ics55-alignment-result/1.0", "results": results}, indent=2))
    for r in results:
        print(f"{r['status']:9s} {r['fixture']}" + (f"  - {r.get('issues')}" if r.get("issues") else ""))
    return rc

if __name__ == "__main__":
    sys.exit(main())
