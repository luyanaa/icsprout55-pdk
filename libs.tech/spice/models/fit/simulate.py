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

"""BSIM4 leakage simulator for ICS55 std cells.

- Builds a Xyce deck: each (cell, state) becomes a flattened instance with
  its own VDD source and input biases; .op then reports per-instance
  leakage = -I(VDD instance source).
- Model cards are generated from a PTM .pm candidate (45nm_HP/LP, 65nm_bulk)
  with device names mapped to the ICS55 CDL names (nm1p2_svt_lp, ...) and
  VTH0 overridable per device for fitting.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NGSPICE = os.environ.get("NGSPICE", "ngspice")
XYCE = os.environ.get("XYCE", "/usr/local/XyceNF_OMPI_7.10/bin/Xyce")


def make_model_cards(pm_path, n_name, p_name, vth0n=None, vth0p=None, no_gidl=True,
                    dibl_scale_n=1.0, dibl_scale_p=1.0,
                    nf_scale_n=1.0, nf_scale_p=1.0,
                    voff_scale_n=1.0, voff_scale_p=1.0,
                    dvt_scale_n=1.0, dvt_scale_p=1.0,
                    kt1_scale_n=1.0, kt1_scale_p=1.0,
                    u0_scale_n=1.0, u0_scale_p=1.0,
                    overrides_n=None, overrides_p=None):
    """Extract the .model nmos/pmos blocks from a PTM .pm file, rename them
    and apply optional direct parameter overrides.  Full cards are kept: use
    Xyce as the simulator (ngspice cannot parse all BSIM4 parameters).

    no_gidl: zero the GIDL coefficients (agidl/bgidl/cgidl/aigsd/bigsd/cigsd).
    The PTM GIDL floor (~7 nA/um at Vds=1.2V, L=60nm) is ~20-50x above the
    measured ICS55 off-currents, so the foundry process is not GIDL-limited.

    The legacy *_scale arguments preserve the six-parameter fit API.  The
    overrides_n/overrides_p dictionaries are for staged fitting of parameters
    that have direct evidence; values are written exactly, including PMOS
    signs.
    """
    text = open(pm_path).read()
    blocks = {}
    for m in re.finditer(r"\.model\s+(\S+)\s+(nmos|pmos)\s+(level\s*=\s*54.*?)(?=\.model\s|\Z)", text, re.S):
        blocks[m.group(2)] = m.group(3)
    for k in blocks:
        b = blocks[k].strip()
        b = re.sub(r"^level\s*=\s*54\s*", "", b)          # body repeats header
        b = re.sub(r"\n\*.*$", "", b)                       # trailing next-model comment
        blocks[k] = b
    out = []
    for typ, name, vth in [("nmos", n_name, vth0n), ("pmos", p_name, vth0p)]:
        body = blocks[typ]
        if vth is not None:
            val = ("-%s" % abs(vth)) if typ == "pmos" else ("%s" % vth)
            body = re.sub(r"(vth0\s*=\s*)[\d.eE+\-]+", r"\g<1>%s" % val, body, count=1)
        if typ == "nmos":
            dscale, nfscale, voffscale, dvtscale = (dibl_scale_n, nf_scale_n,
                                                    voff_scale_n, dvt_scale_n)
            kt1scale, u0scale = kt1_scale_n, u0_scale_n
        else:
            dscale, nfscale, voffscale, dvtscale = (dibl_scale_p, nf_scale_p,
                                                    voff_scale_p, dvt_scale_p)
            kt1scale, u0scale = kt1_scale_p, u0_scale_p
        # *_scale multipliers: 1.0 leaves the PTM base card unchanged
        for p in ("pdiblc1", "pdiblc2", "pdiblcb"):
            m = re.search(r"%s\s*=\s*([\d.eE+\-]+)" % p, body)
            if m:
                body = re.sub(r"%s\s*=\s*[\d.eE+\-]+" % p,
                              "%s = %.6g" % (p, float(m.group(1)) * dscale),
                              body, count=1)
        m = re.search(r"nfactor\s*=\s*([\d.eE+\-]+)", body)
        if m:
            body = re.sub(r"nfactor\s*=\s*[\d.eE+\-]+",
                          "nfactor = %.6g" % (float(m.group(1)) * nfscale),
                          body, count=1)
        m = re.search(r"voff\s*=\s*([\d.eE+\-]+)", body)
        if m:
            body = re.sub(r"voff\s*=\s*[\d.eE+\-]+",
                          "voff = %.6g" % (float(m.group(1)) * voffscale),
                          body, count=1)
        for p in ("dvt0", "dvt1"):
            m = re.search(r"%s\s*=\s*([\d.eE+\-]+)" % p, body)
            if m:
                body = re.sub(r"%s\s*=\s*[\d.eE+\-]+" % p,
                              "%s = %.6g" % (p, float(m.group(1)) * dvtscale),
                              body, count=1)
        for p, scale in (("kt1", kt1scale), ("u0", u0scale)):
            m = re.search(r"%s\s*=\s*([\d.eE+\-]+)" % p, body)
            if m:
                body = re.sub(r"%s\s*=\s*[\d.eE+\-]+" % p,
                              "%s = %.6g" % (p, float(m.group(1)) * scale),
                              body, count=1)
        overrides = overrides_n if typ == "nmos" else overrides_p
        if overrides:
            for parameter, value in overrides.items():
                pattern = (r"(?<![A-Za-z0-9_])%s\s*=\s*"
                           r"[+\-]?(?:\d*\.?\d+)(?:[eE][+\-]?\d+)?"
                           % re.escape(parameter))
                body, count = re.subn(
                    pattern,
                    "%s = %.17g" % (parameter, float(value)),
                    body,
                    count=1,
                )
                if count == 0:
                    body += "\n+%s = %.17g" % (parameter, float(value))
                elif count != 1:
                    raise ValueError(
                        "parameter %s not found exactly once in %s card"
                        % (parameter, typ))
        out.append(".model %s %s level = 54\n%s" % (name, typ, body.rstrip()))
    if no_gidl:
        for i in range(len(out)):
            out[i] = re.sub(r"agidl\s*=\s*[\d.eE+\-]+", "agidl = 0", out[i])
            out[i] = re.sub(r"bgidl\s*=\s*[\d.eE+\-]+", "bgidl = 0", out[i])
            out[i] = re.sub(r"cgidl\s*=\s*[\d.eE+\-]+", "cgidl = 0", out[i])
            out[i] = re.sub(r"aigsd\s*=\s*[\d.eE+\-]+", "aigsd = 0", out[i])
            out[i] = re.sub(r"bigsd\s*=\s*[\d.eE+\-]+", "bigsd = 0", out[i])
            out[i] = re.sub(r"cigsd\s*=\s*[\d.eE+\-]+", "cigsd = 0", out[i])
    return "\n".join(out) + "\n"


def parse_when(when, inputs):
    """Parse a liberty when-clause into {input: 0/1} assignments.
    Handles '(...*...)', '&' and '!' forms. Unspecified inputs omitted."""
    if not when:
        return {}
    # normalize
    s = when.replace("&", " ").replace("*", " ").replace("(", " ").replace(")", " ")
    assign = {}
    for tok in s.split():
        neg = tok.startswith("!")
        name = tok[1:] if neg else tok
        if name in inputs:
            assign[name] = 0 if neg else 1
    return assign


def build_deck(data, model_cards, vdd=1.2, temp=25, flavor_tag="", sim="xyce"):
    """Return (deck_text, instances, all_nodes).

    Cells are flattened (no subckts) so every internal node is a printable
    top-level node -> the Xyce gmin floor (gmin*sum(V_i)) can be subtracted.
    instances = [(id, cell, state_idx, I_meas)]; all_nodes = list of node names.
    """
    # Xyce ignores the SPICE `.temp` card for device temperature; its
    # `.options device temp` setting is the effective operating temperature.
    # Keep temperature in Celsius, matching the released Liberty corner names.
    lines = ["* ICS55 leakage sim", ".options device temp = %g" % temp, ".op", model_cards]
    inst = []
    all_nodes = []
    idx = 0
    for cell, e in data.items():
        body = e["netlist"]
        pins = e["pins"]
        inputs = e["inputs"]
        states = [s for s in e["states"] if s[0]]
        for si, (when, meas_nw) in enumerate(states):
            assign = parse_when(when, inputs)
            sup = "vdd_%d" % idx
            lines.append("%s %s 0 %g" % (sup, sup, vdd))
            node_map = {}
            inodes = []
            for p in pins:
                if p == "VDD":
                    node_map[p] = sup
                elif p == "VSS":
                    node_map[p] = "0"
                elif p in inputs:
                    n = "%s_x%d" % (p, idx)
                    val = assign.get(p, 0)
                    lines.append("V%s %s 0 %g" %
                                 (n.replace("_", "x"), n, vdd if val else 0))
                    node_map[p] = n
                    inodes.append(p)
                else:
                    n = "out_x%d_%s" % (idx, p)
                    node_map[p] = n
                    all_nodes.append(n)
            # flatten body with per-instance node prefix
            pref = "x%d" % idx
            for mline in body:
                parts = mline.split()
                dev = parts[0]
                nodes = parts[1:5]
                model = parts[5]
                attr = " ".join(parts[6:])
                nn = []
                for nd in nodes:
                    if nd in node_map:
                        nn.append(node_map[nd])
                    elif nd == "0":
                        nn.append("0")
                    else:
                        n = "%s_%s" % (pref, nd)
                        nn.append(n)
                        all_nodes.append(n)
                lines.append("M%s_%s %s %s %s" % (pref, dev, " ".join(nn), model, attr))
            inst.append((idx, cell, si, meas_nw, assign, inodes))
            idx += 1
    # dedupe node list (vdd sources excluded)
    all_nodes = list(dict.fromkeys(n for n in all_nodes if not n.startswith("vdd_")))
    return "\n".join(lines) + "\n", inst, all_nodes


GMIN = 1e-12  # Xyce DC gmin floor (S, node-to-ground)


def run_xyce(deck, inst, all_nodes, timeout=900, gmin_correct=True):
    """Run deck with Xyce (full BSIM4); return per-instance |I(VDD)| in A
    with the gmin floor subtracted: I_true = |I(VDD)| - gmin*sum(V_internal)."""
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as f:
        f.write(deck)
        deck_path = f.name
    prints = ["i(vdd_%d)" % i[0] for i in inst]
    prints += ["v(%s)" % n for n in all_nodes]
    with open(deck_path, "a") as f:
        f.write(".print dc " + " ".join(prints) + "\n.end\n")
    env = dict(os.environ)
    env["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib"
    try:
        r = subprocess.run([XYCE, deck_path], capture_output=True, text=True,
                           timeout=timeout, env=env)
        out = r.stdout + r.stderr
        if r.returncode != 0:
            sys.stderr.write("xyce failed:\n" + out[-2000:] + "\n")
            return [None] * len(inst)
    finally:
        os.unlink(deck_path)
    prn = deck_path + ".prn"
    if not os.path.exists(prn):
        sys.stderr.write("xyce parse warning: no prn\n" + out[-1500:] + "\n")
        return [None] * len(inst)
    row = None
    for line in open(prn):
        line = line.strip()
        if not line or line.startswith(("Index", "End")):
            continue
        parts = line.split()
        try:
            int(parts[0])
            row = parts
        except ValueError:
            continue
    os.unlink(prn)
    if row is None or len(row) < 1 + len(prints):
        sys.stderr.write("xyce parse warning: row %s, need %d cols\n"
                         % (row, 1 + len(prints)))
        return [None] * len(inst)
    n_inst = len(inst)
    corr = {}
    if gmin_correct:
        # sum of internal node voltages per instance (node names carry xN_ prefix)
        for k, node in enumerate(all_nodes):
            try:
                v = float(row[1 + n_inst + k])
            except (ValueError, IndexError):
                continue
            if v <= 0:
                continue
            m = re.match(r"x(\d+)_", node)
            if m:
                iid = int(m.group(1))
                corr[iid] = corr.get(iid, 0.0) + v
    outv = []
    for k, i in enumerate(inst):
        try:
            iv = abs(float(row[1 + k]))
        except (ValueError, IndexError):
            outv.append(None)
            continue
        if gmin_correct:
            iv -= GMIN * corr.get(i[0], 0.0)
        outv.append(iv)
    return outv


def run_ngspice(deck, inst):
    """Run deck, return list of measured leakage currents (A) per instance."""
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as f:
        f.write(deck)
        deck_path = f.name
    ctrl = ".control\nop\n" + "".join("print -i(vdd_%d)\n" % i[0] for i in inst) + ".endc\n.end\n"
    with open(deck_path, "a") as f:
        f.write(ctrl)
    try:
        r = subprocess.run([NGSPICE, "-b", "-a", deck_path], capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
    finally:
        os.unlink(deck_path)
    vals = {}
    for m in re.finditer(r"vdd_(\d+)#branch\s*=\s*([\d.eE+\-]+)", out):
        vals[int(m.group(1))] = float(m.group(2))
    for m in re.finditer(r"[-]?i\((?:vdd_|VDD_)(\d+)\)\s*=\s*([\d.eE+\-]+)", out):
        vals[int(m.group(1))] = abs(float(m.group(2)))
    if len(vals) != len(inst):
        sys.stderr.write("ngspice parse warning: got %d/%d values\n" % (len(vals), len(inst)))
        sys.stderr.write(out[-1500:])
    return [vals.get(i[0]) for i in inst]


def sim_leakage(data, model_cards, vdd=1.2, temp=25, sim="xyce", gmin_correct=True):
    deck, inst, all_nodes = build_deck(data, model_cards, vdd, temp, sim=sim)
    if sim == "xyce":
        currents = run_xyce(deck, inst, all_nodes, gmin_correct=gmin_correct)
    else:
        currents = run_ngspice(deck, inst)
    # leakage in nW: I * VDD * 1e9
    return [(i[0], i[1], i[2], i[3], currents[k] * vdd * 1e9 if currents[k] is not None else None)
            for k, i in enumerate(inst)]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("pm")
    ap.add_argument("--vth0n", type=float, default=None)
    ap.add_argument("--vth0p", type=float, default=None)
    ap.add_argument("--nname", default="nm1p2_svt_lp")
    ap.add_argument("--pname", default="pm1p2_svt_lp")
    ap.add_argument("--sim", default="xyce", choices=["xyce", "ngspice"])
    a = ap.parse_args()
    data = json.load(open(a.data))
    cards = make_model_cards(a.pm, a.nname, a.pname, a.vth0n, a.vth0p)
    res = sim_leakage(data, cards, sim=a.sim)
    import math
    errs = []
    for (_, cell, si, meas, sim) in res:
        if sim is None:
            continue
        err = math.log10(sim / meas)
        errs.append(err)
        print("%s[%d] meas=%8.4f nW sim=%8.4f nW (log10 err %+.3f)" % (cell, si, meas, sim, err))
    if errs:
        rms = math.sqrt(sum(e * e for e in errs) / len(errs))
        print("RMS log10 error: %.4f" % rms)
