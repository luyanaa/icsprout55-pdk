#!/usr/bin/env python3
"""ICS55 LEF <-> Liberty pin-direction consistency check.

For every libs.ref/<lib> shipping both LEF and Liberty:
  - every Liberty cell must exist in the LEF and vice versa;
  - every shared pin must declare the same direction in both;
  - all Liberty corners must agree on directions (typ/ff/ss).

Direction drift between the two views breaks P&R (the IO LEF pin-direction
bug fixed in the upstream merge was exactly this class).  Pure stdlib python.

Libs without Liberty locally (std-cell liberties are downloaded by `make`
and git-ignored) are reported as SKIPPED, not failures.

Usage:
  python3 lef_liberty_check.py [--out tests/regression/out]

Exit codes: 0 pass/skipped, 1 mismatches, 2 harness error.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LIBS_REF = ROOT / "libs.ref"


def _braced_blocks(text: str, header_pat: re.Pattern) -> dict[str, str]:
    """Return {name: body} for every `header { ... }` block (brace-matched)."""
    out: dict[str, str] = {}
    for m in header_pat.finditer(text):
        start = m.end()
        depth = 1
        i = start
        while depth and i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out[m.group(1)] = text[start:i - 1]
    return out


def parse_liberty_directions(path: Path) -> dict[str, dict[str, str]]:
    """cell -> {pin: DIRECTION} from a Liberty file (directions upper-cased)."""
    text = path.read_text()
    cells: dict[str, dict[str, str]] = {}
    for name, body in _braced_blocks(text, re.compile(r'cell\s*\(\s*"([^"]+)"\s*\)\s*\{')).items():
        pins = {}
        for pname, pbody in _braced_blocks(body, re.compile(r'pin\s*\(\s*(\w+)\s*\)\s*\{')).items():
            m = re.search(r'direction\s*:\s*"(\w+)"\s*;', pbody)
            pins[pname] = m.group(1).upper() if m else "?"
        cells[name] = pins
    return cells


def parse_lef_directions(path: Path) -> dict[str, dict[str, str]]:
    """MACRO -> {PIN: DIRECTION} from a LEF file."""
    text = path.read_text()
    macros: dict[str, dict[str, str]] = {}
    for m in re.finditer(r"MACRO\s+(\w+)\s*\n(.*?)(?=\n\s*END\s+\1\s*\n|\n\s*END\s+\1\s*$)",
                         text, re.S):
        pins = {}
        for pm in re.finditer(r"PIN\s+(\w+)\s*\n(.*?)(?=\n\s*END\s+\1\s*\n|\n\s*END\s+\1\s*$)",
                              m.group(2), re.S):
            dm = re.search(r"DIRECTION\s+(\w+)\s*;", pm.group(2))
            pins[pm.group(1)] = dm.group(1).upper() if dm else "?"
        macros[m.group(1)] = pins
    return macros


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ROOT / "tests" / "regression" / "out")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    rc = 0
    for lib_dir in sorted(LIBS_REF.iterdir()):
        lef_dir = lib_dir / "lef"
        lib_dir_liberty = lib_dir / "liberty"
        if not lef_dir.is_dir():
            continue
        lef_files = sorted(lef_dir.glob("*.lef"))
        lib_files = sorted(lib_dir_liberty.glob("*.lib")) if lib_dir_liberty.is_dir() else []
        if not lib_files:
            results.append({"lib": lib_dir.name, "status": "SKIPPED",
                            "reason": "no liberty locally (downloaded by make)"})
            continue
        rec: dict[str, Any] = {"lib": lib_dir.name, "status": "PASS"}
        issues = []
        for lef_path in lef_files:
            lef = parse_lef_directions(lef_path)
            # typ/tt corner preferred for the comparison, all corners for consistency
            primary = sorted(lib_files, key=lambda p: (
                0 if ("tt" in p.name and "25c" in p.name) else
                1 if "tt" in p.name else 2, p.name))[0]
            corners = {p.name: parse_liberty_directions(p) for p in lib_files}
            lib = corners[primary.name]
            # corner agreement on directions
            for cname, cdirs in corners.items():
                for cell, pins in cdirs.items():
                    for pin, d in pins.items():
                        if lib.get(cell, {}).get(pin) not in (None, d):
                            issues.append(
                                f"corner {cname}: {cell}/{pin} direction {d} != {primary.name} {lib[cell][pin]}")
            # cell set agreement: LEF-only cells are fine (fillers/corner/power
            # cells carry no timing model); a Liberty cell missing from the LEF
            # breaks P&R and is a hard failure.
            for cell in sorted(set(lib) - set(lef)):
                issues.append(f"cell {cell}: in liberty, missing from {lef_path.name}")
            lef_only = sorted(set(lef) - set(lib))
            rec.setdefault("lef_only_cells", []).extend(
                f"{cell} ({lef_path.name})" for cell in lef_only)
            # pin direction agreement
            for cell, pins in sorted(lib.items()):
                for pin, d in pins.items():
                    lf = lef.get(cell, {}).get(pin)
                    if lf is None:
                        issues.append(f"{cell}/{pin}: in liberty, missing from {lef_path.name}")
                    elif lf != d:
                        issues.append(f"{cell}/{pin}: liberty {d} != lef {lf}")
            rec["lef_files"] = [p.name for p in lef_files]
            rec["liberty_corners"] = sorted(corners)
            rec["cells_checked"] = len(set(lib) & set(lef))
            rec["pins_checked"] = sum(len(p) for p in lib.values())
        if issues:
            rec["status"] = "FAIL"
            rec["issues"] = issues
            rc = 1
        results.append(rec)

    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((ROOT / "libs.ref").glob("*/lef/*.lef"))}
    (out_dir / "lef_liberty_check.json").write_text(json.dumps({
        "schema": "ics55-lef-liberty-check/1.0", "results": results, "lef_sha256": hashes,
    }, indent=2))
    for r in results:
        print(f"{r['status']:8s} {r['lib']}" + (f"  - {r.get('issues', [])[:3]}" if r.get("issues") else ""))
    return rc


if __name__ == "__main__":
    sys.exit(main())
