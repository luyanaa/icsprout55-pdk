#!/usr/bin/env python3
"""Canonical MOS-graph normalizer for ICS55 LVS verification.

Parses a flat extracted netlist (*.cir) or a CDL-derived flat netlist and
emits canonical MOS device records for comparison:

- model names case-folded (official deck uses lowercase, KLayout uppercase)
- named-net aliasing: VDD|VNW == VDD (standard-cell well-tie convention)
- numeric nets (fresh KLayout output uses 1..N plus mapping comments) resolved
  via the SUBCKT pin order + * pin comments
- W/L/m converted to micrometer / integer
- optional geometry (AS/AD/PS/PD) distinguished present-vs-absent (None),
  never collapsed to zero

Usage:
  normalize_lvs.py <flat.cir> [--json]    # print canonical records

Exit codes: 0 ok, 2 unparseable.
"""
import argparse
import json
import re
import sys

SUFFIX = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12}
MODEL_RE = re.compile(r"^(n|p)(m\d+p\d+)_([a-z]+)_lp$", re.I)


def _num(value):
    value = value.strip()
    m = re.match(r"^([-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?)([munpf]?)$", value)
    if not m:
        return None
    return float(m.group(1)) * SUFFIX[m.group(4)]


def _fold_model(name):
    return name.lower()


def parse_cir(path):
    """Return canonical records list for a flat extracted netlist."""
    text = open(path).read()
    lines = []
    for l in text.splitlines():
        s = l.strip()
        if not s:
            continue
        if s.startswith("+"):
            if lines:
                lines[-1] = lines[-1] + " " + s[1:].strip()
            continue
        lines.append(s)

    pin_comment = []   # ordered pin names from '* pin X' comments
    net_map = {}       # numeric net -> resolved name
    pin_names = []
    records = []

    for l in lines:
        if l.startswith("* pin "):
            pin_comment = l[6:].split()
            continue
        if l.startswith("* net "):
            parts = l[5:].split()
            if len(parts) >= 2:
                # '* net 1 VDD,VNW'
                net_map[parts[0]] = parts[1].split(",")[0].replace("VNW", "VDD")
            continue
        if l.startswith("*"):
            continue
        m = re.match(r"^\*?\s*\.SUBCKT\s+(\S+)\s+(.*)$", l)
        if m:
            pin_names = m.group(2).split()
            continue
        m = re.match(r"^M(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$", l)
        if m:
            inst, d, g, s, b, model, attr = m.groups()
            # numeric-net resolution: try direct then pin-position
            def resolve(net):
                if net in net_map:
                    return net_map[net]
                if net.isdigit() and pin_comment:
                    idx = int(net) - 1
                    if 0 <= idx < len(pin_comment):
                        return pin_comment[idx].replace("VNW", "VDD")
                if net.isdigit() and pin_names:
                    idx = int(net) - 1
                    if 0 <= idx < len(pin_names):
                        return pin_names[idx].replace("VNW", "VDD")
                return net.replace("VNW", "VDD")
            d, g, s, b = resolve(d), resolve(g), resolve(s), resolve(b)
            rec = {
                "inst": inst,
                "model": _fold_model(model),
                "terminals": {"D": d, "G": g, "S": s, "B": b},
            }
            for am in re.finditer(r"([A-Za-z_]+)\s*=\s*([^\s]+)", attr):
                k, v = am.group(1), am.group(2)
                if k in ("W", "L", "AS", "AD", "PS", "PD", "m", "nf"):
                    rec[k.lower()] = _num(v)
            records.append(rec)
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        records = parse_cir(args.cir)
    except Exception as e:
        print(f"normalize_lvs: unparseable {args.cir}: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        for r in records:
            t = r["terminals"]
            print(f"{r['model']} D={t['D']} G={t['G']} S={t['S']} B={t['B']} "
                  f"W={r.get('w')} L={r.get('l')} AS={r.get('as')} AD={r.get('ad')} "
                  f"PS={r.get('ps')} PD={r.get('pd')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
