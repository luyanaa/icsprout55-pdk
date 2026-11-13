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
import itertools
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent.parent


RESERVED_BLOCKS = {"if", "else", "elseif", "while", "foreach", "for", "proc",
                   "switch", "namespace", "VERBATIM", "skew_edge_check"}


def expand_loops(text: str) -> str:
    """Expand ${metal_layer}/${via_layer} inside foreach blocks.

    The vendor deck generates the metal, via, dummy and density rule names
    from Tcl loops.  Track the most recent list definition and foreach
    variable so each template is expanded with the list that is in scope,
    matching how the source deck is actually unrolled by Calibre.
    """
    lists: dict[str, list[str]] = {}
    scope: dict[str, list[str]] = {}
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*set\s+(\w+)\s+\{([^}]*)\}", line)
        if m:
            lists[m.group(1)] = m.group(2).split()
        m = re.search(r"\bforeach\s+(\w+)\s+\$(\w+)", line)
        if m:
            scope[m.group(1)] = lists.get(m.group(2), [])

        def repl(mm: re.Match[str]) -> str:
            values = scope.get(mm.group(1))
            return mm.group(0) if not values else "{" + " ".join(values) + "}"

        if "RULECHECK" in line and "${" in line:
            var_names = re.findall(r"\$\{(\w+)\}", line)
            if all(scope.get(v) for v in var_names):
                for combo in itertools.product(*(scope[v] for v in var_names)):
                    rendered = line
                    for var, value in zip(var_names, combo):
                        rendered = rendered.replace("${" + var + "}", value)
                    out.append(rendered)
                continue
        out.append(re.sub(r"\$\{(\w+)\}", repl, line))
    return "\n".join(out)


def parse_vendor(path: Path) -> tuple[set[str], set[str]]:
    text = expand_loops(path.read_text(encoding="utf8", errors="replace"))
    # Anchor at the line start so disabled "#RULECHECK ..." stubs are excluded.
    ruled = set(re.findall(r"^[ \t]*RULECHECK\s+([A-Za-z0-9_.]+)\s*\{", text,
                           re.M))
    blocks = set()
    for m in re.finditer(r"^([A-Za-z][A-Za-z0-9_]*(?:_[A-Za-z0-9]+)*)\s*\{\s*$",
                         text, re.M):
        name = m.group(1)
        if name not in RESERVED_BLOCKS:
            blocks.add(name)
    return ruled, blocks - ruled


def strip_ruby_comments(text: str) -> str:
    """Drop Ruby comments but keep ``#`` inside string literals.

    Rule IDs mentioned only in comments must not count as emitted categories;
    ``#{}`` interpolation inside strings is preserved because quote state is
    tracked per line.
    """
    out = []
    for line in text.splitlines():
        quote = None
        escaped = False
        cut = len(line)
        for i, ch in enumerate(line):
            if quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
            elif ch in "'\"":
                quote = ch
            elif ch == "#":
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def parse_klayout(root: Path) -> tuple[dict[str, str], set[str], list[re.Pattern[str]]]:
    """Collect emitted categories and mapping literals from the KLayout deck.

    Returns ``(output_categories, literals, templates)``.  ``output_categories``
    counts literal ``.output('name', ...)`` calls.  ``literals``/``templates``
    include names passed indirectly (``output(rule_id)`` with the literal at a
    helper call site) and Ruby-interpolated names (``"metal.#{key}.area"``),
    which are matched as full-name regex templates.  Ruby comments are ignored
    so a rule ID that survives only as documentation does not count.
    """
    out: dict[str, str] = {}
    literals: set[str] = set()
    patterns: list[re.Pattern[str]] = []
    for f in sorted((root / "libs.tech/drc").rglob("*.drc")):
        if f.name.startswith("."):
            continue
        text = strip_ruby_comments(f.read_text(encoding="utf8", errors="replace"))
        for m in re.finditer(r"\.output\(\s*(['\"])(.+?)\1", text):
            if "#{" not in m.group(2):
                out.setdefault(m.group(2), str(f.relative_to(root)))
        for m in re.finditer(r"(['\"])(.+?)\1", text):
            name = m.group(2)
            if "#{" in name:
                parts = re.split(r"#\{[^}]+\}", name)
                patterns.append(re.compile(".+".join(map(re.escape, parts))))
            else:
                literals.add(name)
    return out, literals, patterns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk-root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    root = Path(a.pdk_root)

    vendor_path = root / "pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc"
    ruled, blocks = parse_vendor(vendor_path)
    vendor = ruled | blocks
    cats, literals, templates = parse_klayout(root)

    def emitted(name: str) -> bool:
        return name in literals or any(p.fullmatch(name) for p in templates)

    cw = json.loads((root / "tests/regression/official/drc_rule_comparison.json")
                    .read_text())
    rules = cw["rules"]
    covered = [r for r in rules if r["status"] == "covered"]
    mapped_live = [r for r in covered if emitted(r.get("klayout") or "")]
    mapped_stale = [r for r in covered if not emitted(r.get("klayout") or "")]
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
