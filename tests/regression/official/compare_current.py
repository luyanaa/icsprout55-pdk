#!/usr/bin/env python3
"""Compare the shipped vendor DRC deck with the KLayout port and the crosswalk.

    python3 tests/regression/official/compare_current.py [--pdk-root DIR]

The vendor reference is the Calibre deck that ships in this repo,
`pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc`.  It uses two rule
syntaxes:

    RULECHECK NAME { ... }          (most rules)
    NAME { ... }                    (block style; all CT, implant, well rules)

The stored crosswalk (`drc_rule_comparison.json`) and the KLayout deck are
compared against it here.  This is a source-ID/value comparison, not a
Calibre differential: no Calibre run/report is available on this machine.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent.parent


def parse_vendor(path: Path) -> tuple[set[str], set[str]]:
    text = path.read_text(encoding="utf8", errors="replace")
    ruled = set(re.findall(r"RULECHECK\s+([A-Za-z0-9_.]+)\s*\{", text))
    blocks = set()
    for m in re.finditer(r"^([A-Z][A-Z0-9_]*(?:_[A-Za-z0-9]+)*)\s*\{\s*$",
                         text, re.M):
        blocks.add(m.group(1))
    return ruled, blocks - ruled


def parse_klayout(root: Path) -> dict[str, str]:
    """category -> source file for every emitted .output(...)."""
    out: dict[str, str] = {}
    for f in sorted((root / "libs.tech/drc").rglob("*.drc")):
        text = f.read_text(encoding="utf8", errors="replace")
        for m in re.finditer(r"\.output\(\s*'([^']+)'", text):
            out.setdefault(m.group(1), str(f.relative_to(root)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk-root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    root = Path(a.pdk_root)

    vendor_path = root / "pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc"
    ruled, blocks = parse_vendor(vendor_path)
    vendor = ruled | blocks
    cats = parse_klayout(root)
    cw = json.loads((root / "tests/regression/official/drc_rule_comparison.json")
                    .read_text())
    rules = cw["rules"]
    covered = [r for r in rules if r["status"] == "covered"]
    mapped_live = [r for r in covered if r.get("klayout") in cats]
    mapped_stale = [r for r in covered if r.get("klayout") not in cats]
    block_prefix = Counter(b.split("_")[0] for b in blocks)

    print(f"vendor deck      : {vendor_path.name}")
    print(f"  RULECHECK      : {len(ruled)}")
    print(f"  block style    : {len(blocks)}  ({', '.join(f'{k} {v}' for k, v in block_prefix.most_common(6))})")
    print(f"  unique rules   : {len(vendor)}")
    print(f"KLayout deck     : {len(cats)} emitted categories")
    print(f"crosswalk        : {len(rules)} ids, {len(covered)} covered, "
          f"{sum(1 for r in rules if r['status'] == 'missing')} missing")
    print(f"  covered and still emitted : {len(mapped_live)}")
    print(f"  covered but category gone : {len(mapped_stale)}")
    print(f"  vendor ids not in crosswalk: {len(vendor - {r['official'] for r in rules})}")

    print("\nfamily view (vendor rules / crosswalk covered / still emitted):")
    fam = Counter(r.split("_")[0] for r in vendor)
    cov = Counter(r["official"].split("_")[0] for r in covered)
    live = Counter(r["official"].split("_")[0] for r in mapped_live)
    for f, n in sorted(fam.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {f:10s} {n:3d} / {cov[f]:2d} / {live[f]:2d}")

    missing_families = sorted({b.split('_')[0] for b in blocks} -
                              {r['official'].split('_')[0] for r in rules})
    print(f"\nblock-style families absent from the crosswalk: "
          f"{', '.join(missing_families)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
