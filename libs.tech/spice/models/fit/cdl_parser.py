#!/usr/bin/env python3
# Copyright 2026 Yan Lu with DeepSeek V4 Flash and GPT-5.6-Luna
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parse ICS55 std-cell CDL into flat per-cell SPICE netlists.

- Reads a CDL file (one Vt flavor), dedupes .SUBCKT blocks by name.
- Parameterized leaf cells (INV, TG, NAND2, NOR2, TSINV) are inlined into
  each cell with the instance parameters from the XI/XXI calls.
- Output: dict cell_name -> flat netlist text (M devices only), plus
  input-pin list (from *.PININFO) and total N/P widths.
"""
import re
import sys

LEAF_PARAMS = ("nw", "nl", "pw", "pl")


def parse_subckts(text):
    """name -> {'pins': [...], 'body': [lines], 'pininfo': {...}}"""
    subs = {}
    pininfo = {}
    for m in re.finditer(r"\.SUBCKT\s+(\S+)\s+([^\n]*)\n(.*?)\.ENDS", text, re.S):
        name = m.group(1)
        pins = m.group(2).split()
        raw = [l.strip() for l in m.group(3).splitlines() if l.strip() and not l.strip().startswith("*")]
        # join SPICE continuation lines ('+' prefix)
        body = []
        for l in raw:
            if l.startswith("+") and body:
                body[-1] += " " + l[1:].strip()
            else:
                body.append(l)
        # PININFO: *.PININFO A:I Y:O VDD:B VSS:B
        pi = {}
        pm = re.search(r"\*\.PININFO\s+(.*)", m.group(3))
        if pm:
            for tok in pm.group(1).split():
                if ":" in tok:
                    pn, pt = tok.split(":")
                    pi[pn] = pt
        subs[name] = {"pins": pins, "body": body, "pininfo": pi}
    return subs


def is_param_leaf(subs, name):
    """leaf if body references nw/nl/pw/pl parameters"""
    body = "\n".join(subs[name]["body"])
    return any(p in body for p in LEAF_PARAMS)


def inline_leaves(cell_name, subs, depth=0):
    """Return flat body (list of M lines) for cell, inlining parameterized
    leaf subcircuit calls. Calls: 'XI2 net90 VDD VSS S / INV pl=.. pw=..'"""
    if depth > 8:
        raise RuntimeError("recursion too deep in " + cell_name)
    sub = subs[cell_name]
    out = []
    for line in sub["body"]:
        if not re.match(r"^X", line):
            out.append(line)
            continue
        # X<inst> <nodes...> / <leaf> <params>
        m = re.match(r"^(X\S+)\s+(.*?)\s*/\s*(\S+)(.*)$", line)
        if not m:
            out.append(line)
            continue
        inst, nodes, leaf, params = m.groups()
        if leaf not in subs:
            out.append(line)
            continue
        if not is_param_leaf(subs, leaf):
            out.append(line)
            continue
        # build param dict from the call
        pvals = {}
        for pm in re.finditer(r"(\w+)\s*=\s*([\d.eE+\-]+[mun]?)", params):
            pvals[pm.group(1)] = pm.group(2)
        # inline leaf body with substituted params and prefixed internal nodes
        lsub = subs[leaf]
        node_list = nodes.split()
        # map leaf pins -> instance nodes
        pmap = dict(zip(lsub["pins"], node_list))
        for lline in lsub["body"]:
            if lline.startswith("M"):
                # MMN0 Y A VSS VSS nm1p2_svt_lp W=nw L=nl m=1
                parts = lline.split()
                dev = parts[0]
                nn = parts[1:5]
                model = parts[5]
                attr = " ".join(parts[6:])
                new_nodes = [pmap.get(n, n) for n in nn]
                new_dev = inst + "_" + dev
                # substitute leaf param names (nw/nl/pw/pl used as W/L values)
                attr2 = re.sub(r"\b(nw|nl|pw|pl)\b", lambda am: pvals[am.group(0)], attr)
                out.append("M%s %s %s %s" % (new_dev, " ".join(new_nodes), model, attr2))
            else:
                out.append("# " + lline)  # non-M lines inside leaves: skip as comment
    return out


def cell_netlist(cell, subs):
    """flat netlist text + pin info for a cell"""
    body = inline_leaves(cell, subs)
    sub = subs[cell]
    pins = sub["pins"]
    inputs = [p for p, t in sub["pininfo"].items() if t == "I"]
    # total widths
    wn = wp = 0.0
    mcount = 0
    for line in body:
        m = re.match(r"^M\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)\s+W=([\d.eE+\-]+[mun]?)\s+L=([\d.eE+\-]+[mun]?)\s+m=(\d+)", line)
        if m:
            model, w, l, mult = m.groups()
            w = float(w.rstrip("mun")) * {"": 1, "m": 1e-3, "u": 1e-6, "n": 1e-9}[w[-1] if w[-1] in "mun" else ""] * int(mult)
            if model.startswith("n"):
                wn += w
            else:
                wp += w
            mcount += 1
    return {
        "pins": pins,
        "inputs": inputs,
        "body": body,
        "wn": wn,
        "wp": wp,
        "mcount": mcount,
    }


def load(cdl_path, cell_filter=None):
    text = open(cdl_path).read()
    subs = parse_subckts(text)
    result = {}
    for name in subs:
        if name in ("INV", "TG", "NAND2", "NOR2", "TSINV"):
            continue
        if cell_filter and name not in cell_filter:
            continue
        try:
            result[name] = cell_netlist(name, subs)
        except Exception as e:
            sys.stderr.write("skip %s: %s\n" % (name, e))
    return result


if __name__ == "__main__":
    import json
    cdl = sys.argv[1]
    net = load(cdl)
    for c in ["INVX1H7R", "NAND2X1H7R", "ADDFX1H7R", "DFFX1H7R"]:
        if c in net:
            n = net[c]
            print("%s: pins=%s inputs=%s mos=%d Wn=%.3fu Wp=%.3fu" % (
                c, n["pins"], n["inputs"], n["mcount"], n["wn"], n["wp"]))
            print("  first lines:", n["body"][:3])
