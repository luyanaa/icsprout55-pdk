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

# ============================================================================
# config_gen.py - ICsprout55 extraction-config generator
# ============================================================================
# Single clean-room value source for the ICsprout55 parasitic-extraction
# configurations.  All RC values come from the released LEFs (N551P6M.lef /
# N551P6M_ecos.lef) plus the user-approved process estimates (metal thickness
# from bulk-Cu RPSQ inference, dielectric eps/thickness = typical 55nm-node,
# thermal conductivities = typical values).  The generator emits:
#
#   --palace        gds2palace stackup XML  (libs.tech/pex/palace/ics55_stackup.xml)
#   --magic-snippet magic .tech extract lines (resist/areacap/perimc values)
#   --openrcx       OpenRCX extraction rules (libs.tech/librelane/<scl>/rcx.rules)
#   --layers-rc     LibreLane LAYERS_RC/VIAS_R tcl fragment
#
# Values are centralized here so that a future silicon calibration only has to
# touch this file (then regenerate all configs).  Provenance: every value is
# LEF-seeded or an explicitly marked estimate; the decrypted ECOS/StarRC data
# from the upstream LibreLane repository is deliberately NOT used (see
# libs.tech/pex/README.md "RCX provenance limit").
#
# Usage:
#   python config_gen.py --palace --magic-snippet --openrcx --layers-rc [--scl ics55_LLSC_H7CR]
# ============================================================================

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# 1. Released LEF seeds (clean-room; the released tech LEFs)
# ---------------------------------------------------------------------------
# layer: (rpsq, area_cap_pf_um2, edge_cap_pf_um, width_um)
LEF_SEEDS = {
    "M1":  (0.1122, 0.0007630, 0.0000339, 0.09),
    "M2":  (0.0914, 0.0011069, 0.0000391, 0.10),
    "M3":  (0.0914, 0.0011069, 0.0000409, 0.10),
    "M4":  (0.0914, 0.0011069, 0.0000409, 0.10),
    "M5":  (0.0914, 0.0006259, 0.0000344, 0.10),
    "TM2": (0.0239, 0.0001299, 0.0000368, 0.40),
    "RDL": (0.0151, 0.0000574, 0.0000281, 3.00),
}
VIA_R_OHM = 2.5          # LEF VIA RESISTANCE (all via levels)
VIA_CUT_UM = {"V1": 0.09, "V2": 0.09, "V3": 0.09, "V4": 0.09, "TV2": 0.36}
VIA_HEIGHT_UM = 0.12     # vertical via height estimate (55nm-node typical)

# ---------------------------------------------------------------------------
# 2. Process estimates (user-approved 2026-09-25; single place to calibrate)
# ---------------------------------------------------------------------------
RHO_BULK = 1.72e-8       # ohm*m, bulk Cu (thickness inference)

EPS_IMD = 3.3            # low-k inter-metal dielectric
EPS_PMD = 3.9            # pre-metal dielectric
EPS_PASS = 4.0           # passivation
EPS_SUB = 11.9           # silicon

SPACING_PMD = 0.15       # um, PMD below M1
SPACING_IMD = 0.12       # um, IMD between metals
PASSIVATION_MARGIN = 0.5 # um, passivation above the top metal

SUBSTRATE_THICK_UM = 200.0
SUBSTRATE_SIGMA = 10.0   # S/m (~10 ohm*cm)

# thermal (W/m.K, kg/m3) - typical values
THERMAL = {
    "metal": (385.0, 8960.0), "imd": (0.6, 2200.0), "pmd": (1.4, 2200.0),
    "passivation": (1.5, 2500.0), "substrate": (150.0, 2329.0), "air": (0.026, 1.0),
}

# GDS layer numbers (official map, libs.tech/klayout/tech/ics55.map)
GDS_LAYER = {"M1": 81, "M2": 82, "M3": 83, "M4": 84, "M5": 85, "TM2": 103,
             "V1": 91, "V2": 92, "V3": 93, "V4": 94, "TV2": 113}

# ---------------------------------------------------------------------------
# 3. Derived process model
# ---------------------------------------------------------------------------
def metal_thickness_um(rpsq):
    return RHO_BULK / rpsq * 1e6


def sigma_s_m2(rpsq, thickness_um):
    return 1.0 / (rpsq * thickness_um * 1e-6)


def build_stack():
    """Return the metal/via z-ranges (um, z=0 at the substrate bottom)."""
    metals = []
    z = SUBSTRATE_THICK_UM + SPACING_PMD
    for name in ["M1", "M2", "M3", "M4", "M5", "TM2"]:
        rpsq, cap, edge, w = LEF_SEEDS[name]
        t = metal_thickness_um(rpsq)
        zmin = round(z, 4)
        zmax = round(z + t, 4)
        metals.append({"name": name, "rpsq": rpsq, "cap": cap, "edge": edge,
                       "width": w, "thickness": t, "zmin": zmin, "zmax": zmax,
                       "sigma": sigma_s_m2(rpsq, t),
                       "thermal": THERMAL["metal"][0], "density": THERMAL["metal"][1]})
        z = round(z + t + SPACING_IMD, 4)
    vias = []
    order = [("V1", "M1", "M2"), ("V2", "M2", "M3"), ("V3", "M3", "M4"),
             ("V4", "M4", "M5"), ("TV2", "M5", "TM2")]
    for via, low, high in order:
        zlo = next(m["zmax"] for m in metals if m["name"] == low)
        zhi = next(m["zmin"] for m in metals if m["name"] == high)
        w = VIA_CUT_UM[via]
        h = zhi - zlo
        sigma = h * 1e-6 / (VIA_R_OHM * (w * 1e-6) ** 2)   # from R = 2.5 ohm
        vias.append({"name": via, "zmin": zlo, "zmax": zhi, "cut": w,
                     "sigma": sigma, "lower": low, "upper": high})
    return {"metals": metals, "vias": vias}


# ---------------------------------------------------------------------------
# 4. Emitters
# ---------------------------------------------------------------------------
def emit_palace_stackup(stack, out):
    """gds2palace stackup XML (schemaVersion 2.0, legacy; top-first dielectrics)."""
    root = ET.Element("Stackup", {"schemaVersion": "2.0"})
    mats = ET.SubElement(root, "Materials")
    for m in stack["metals"]:
        ET.SubElement(mats, "Material", {
            "Name": "TopMetal" if m["name"] == "TM2" else "Metal" + m["name"][1:],
            "Type": "Conductor", "Conductivity": "%.1f" % m["sigma"],
            "ThermalConductivity": "%.1f" % m["thermal"], "Density": "%.1f" % m["density"],
            "Color": "ff8000" if m["name"] == "TM2" else "ccccd9"})
    for v in stack["vias"]:
        ET.SubElement(mats, "Material", {
            "Name": "TopVia" if v["name"] == "TV2" else "Via" + v["name"][1:],
            "Type": "Conductor", "Conductivity": "%.1f" % v["sigma"],
            "ThermalConductivity": "%.1f" % THERMAL["metal"][0],
            "Density": "%.1f" % THERMAL["metal"][1], "Color": "ffe6bf"})
    for nm, eps, k, rho, typ in [
            ("IMD", EPS_IMD, *THERMAL["imd"], "Dielectric"),
            ("PMD", EPS_PMD, *THERMAL["pmd"], "Dielectric"),
            ("Passivation", EPS_PASS, *THERMAL["passivation"], "Dielectric"),
            ("Substrate", EPS_SUB, *THERMAL["substrate"], "Semiconductor"),
            ("AIR", 1.0, *THERMAL["air"], "Dielectric")]:
        attrs = {"Name": nm, "Type": typ, "Permittivity": "%.1f" % eps,
                 "DielectricLossTangent": "0.01",
                 "ThermalConductivity": "%.3f" % k, "Density": "%.1f" % rho,
                 "Color": {"IMD": "fffcad", "PMD": "fffcad", "Passivation": "a0a0f0",
                           "Substrate": "01e0ff", "AIR": "d0d0d0"}[nm]}
        if nm == "Substrate":
            attrs["Conductivity"] = "%.1f" % SUBSTRATE_SIGMA
        else:
            attrs["Conductivity"] = "0"
        ET.SubElement(mats, "Material", attrs)

    el = ET.SubElement(root, "ELayers", {"LengthUnit": "um"})
    diels = ET.SubElement(el, "Dielectrics")
    metals = stack["metals"]
    # top-first dielectric thicknesses.  The reader stacks them bottom-up and
    # registers each metal by its zmin, so every dielectric range must span
    # metal-bottom to next-metal-bottom (the verified convention):
    #   IMD_k = zmin(metal k+1) - zmin(metal k); passivation covers the top metal.
    pass_th = metals[-1]["zmax"] + PASSIVATION_MARGIN - metals[-1]["zmin"]
    for name, th, mat in [
            ("Passivation", pass_th, "Passivation"),
            ("IMD5", metals[5]["zmin"] - metals[4]["zmin"], "IMD"),
            ("IMD4", metals[4]["zmin"] - metals[3]["zmin"], "IMD"),
            ("IMD3", metals[3]["zmin"] - metals[2]["zmin"], "IMD"),
            ("IMD2", metals[2]["zmin"] - metals[1]["zmin"], "IMD"),
            ("IMD1", metals[1]["zmin"] - metals[0]["zmin"], "IMD"),
            ("PMD", SPACING_PMD, "PMD"), ("Substrate", SUBSTRATE_THICK_UM, "Substrate")]:
        ET.SubElement(diels, "Dielectric", {
            "Name": name, "Material": mat, "Thickness": "%.4f" % th})
    layers = ET.SubElement(el, "Layers")
    for m in reversed(metals):
        ET.SubElement(layers, "Layer", {
            "Name": "TM2" if m["name"] == "TM2" else m["name"], "Type": "conductor",
            "Zmin": "%.4f" % m["zmin"], "Zmax": "%.4f" % m["zmax"],
            "Material": "TopMetal" if m["name"] == "TM2" else "Metal" + m["name"][1:],
            "Layer": str(GDS_LAYER[m["name"]])})
    for v in reversed(stack["vias"]):
        ET.SubElement(layers, "Layer", {
            "Name": "TV2" if v["name"] == "TV2" else v["name"], "Type": "via",
            "Zmin": "%.4f" % v["zmin"], "Zmax": "%.4f" % v["zmax"],
            "Material": "TopVia" if v["name"] == "TV2" else "Via" + v["name"][1:],
            "Layer": str(GDS_LAYER[v["name"]])})
    _indent(root)
    header = ("<?xml version='1.0' encoding='UTF-8'?>\n"
              "<!-- Generated by libs.tech/pex/config_gen.py - clean-room LEF seeds\n"
              "     + user-approved estimates.  Regenerate after any calibration. -->\n")
    out.write_text(header + ET.tostring(root, encoding="unicode") + "\n")


def emit_magic_snippet(stack):
    """Print the magic .tech extract values (resist/areacap/perimc)."""
    for m in stack["metals"]:
        print("\tresist\t%s\t%d" % (m["name"].lower(), round(m["rpsq"] * 1000)))
    for v in stack["vias"]:
        print("\tresist\t%s\t2500" % v["name"].lower())
    for m in stack["metals"]:
        print("\tareacap\t%s\t%d" % (m["name"].lower(), round(m["cap"] * 1e6)))
    for m in stack["metals"]:
        print("\tperimc\t%s\tspace\t%d" % (m["name"].lower(), round(m["edge"] * 1e6)))


def emit_openrcx_rules(stack, out):
    """OpenRCX extraction rules (LayerCount 7: M1-M5 + TM2 + RDL) with the
    upstream block pattern (RESOVER/OVER/UNDER/DIAGUNDER/OVERUNDER per metal,
    the full index matrix).  All coefficients are LEF-seeded estimates; the
    values are placeholders for field-solver/calibration data."""
    # 7-metal list: the 6 stack metals + the RDL (the rules' LayerCount 7)
    metals = list(stack["metals"]) + [{
        "name": "RDL", "rpsq": 0.0151, "cap": 0.0000574, "edge": 0.0000281,
        "width": 3.0}]
    nlayers = len(metals)
    # The pinned OpenROAD 2026-02-17 requires the legacy header
    # ("Extraction Rules for rcx" + Version + Corners); the newer
    # "Extraction Rules for OpenRCX" header segfaults its calcMinMaxRC.
    L = ["Extraction Rules for rcx", "",
         "Version 1.2", "",
         "DIAGMODEL ON", "",
         "LayerCount %d" % nlayers, "",
         "DensityRate 1  0", "",
         "Corners 1 :  TYP", "",
         "COMMENT : ICsprout55 clean-room estimates (LEF-seeded); calibration pending", "",
         "DensityModel 0", ""]

    pairs = [(0.0, 0.0), (0.0, 0.1), (0.0, 0.2), (0.1, 0.1), (0.1, 0.2),
             (0.2, 0.2)]
    for i, m in enumerate(metals):
        w = m["width"]
        c_lat = m["edge"] * 1e3          # fF/um lateral
        c_area = m["cap"] * 0.15         # adjacent-layer area cap (pF/um2)
        c_fringe = m["edge"] * 0.35
        c_other = m["cap"] * 30.0
        dists = [w, 1.5 * w, 2.0 * w, 3.0 * w, 5.0 * w]

        def width_and_dist():
            L.append("WIDTH Table 1 entries:  %g" % w)
            L.append("")

        def dist_block(rows):
            L.append("DIST count %d width %g" % (len(rows), w))
            for row in rows:
                L.append(" ".join("%g" % v for v in row))
            L.append("END DIST")
            L.append("")

        # RESOVER (same layer): triangular distance pairs
        L.append("Metal %d RESOVER" % (i + 1))
        width_and_dist()
        L.append("Metal %d RESOVER 0" % (i + 1))
        dist_block([(d1, d2, 0.0, c_lat * (1 - 0.4 * (d1 + d2) / 0.6))
                    for d1, d2 in pairs])
        for j in range(1, i + 1):
            L.append("Metal %d RESOVER %d" % (i + 1, j))
            dist_block([(d1, d2, 0.0, c_lat * (1 - 0.4 * (d1 + d2) / 0.6))
                        for d1, d2 in pairs])
        # OVER (coupling to the layers above)
        L.append("Metal %d OVER" % (i + 1))
        width_and_dist()
        for j in range(0, i + 1):
            L.append("Metal %d OVER %d" % (i + 1, j))
            dist_block([(d, c_area, c_fringe, c_other) for d in dists])
        # UNDER / DIAGUNDER (coupling to the layers below)
        if i + 1 < nlayers:
            L.append("Metal %d UNDER" % (i + 1))
            width_and_dist()
            for j in range(i + 2, nlayers + 1):
                L.append("Metal %d UNDER %d" % (i + 1, j))
                dist_block([(d, c_area, c_fringe, c_other) for d in dists])
            L.append("Metal %d DIAGUNDER" % (i + 1))
            width_and_dist()
            for j in range(i + 2, nlayers + 1):
                L.append("Metal %d DIAGUNDER %d" % (i + 1, j))
                dist_block([(d, c_area * 0.3, c_fringe, c_other * 0.5)
                            for d in dists])
        # OVERUNDER (the combined table, M2+)
        if i >= 1:
            L.append("Metal %d OVERUNDER" % (i + 1))
            width_and_dist()
            for j in range(1, i + 1):
                for _ in range(nlayers - i - 1):
                    L.append("Metal %d OVER %d" % (i + 1, j))
                    dist_block([(d, c_area, c_fringe, c_other) for d in dists])
    out.write_text("\n".join(L) + "\n")


# the released LEF layer/via names (the OpenROAD's set_layer_rc lookups)
LEF_LAYER_NAMES = {"M1": "MET1", "M2": "MET2", "M3": "MET3", "M4": "MET4",
                   "M5": "MET5", "TM2": "T4M2", "RDL": "RDL"}
LEF_VIA_NAMES = {"V1": "VIA1", "V2": "VIA2", "V3": "VIA3", "V4": "VIA4",
                 "TV2": "T4V2"}


def emit_layers_rc(stack, out, corner="nom_*"):
    """LibreLane LAYERS_RC / VIAS_R tcl fragment (LEF values), keyed by corner
    (the format librelane/steps/openroad.py consumes: {corner: {layer: {R, C}}}).
    Layer/via names are the released LEF names (MET1.., VIA1..) so the
    OpenROAD set_layer_rc lookups match the technology."""
    L = ["# LAYERS_RC / VIAS_R (generated by libs.tech/pex/config_gen.py; LEF values)",
         "set ::env(LAYERS_RC) [dict create \\",
         "  \"%s\" [dict create \\" % corner]
    for m in stack["metals"]:
        name = LEF_LAYER_NAMES.get(m["name"], m["name"])
        L.append("    %s [dict create R %.4f C %.7f] \\" % (name, m["rpsq"], m["cap"]))
    L.append("  ] \\")
    L.append("]")
    L.append("set ::env(VIAS_R) [dict create \\")
    L.append("  \"%s\" [dict create \\" % corner)
    for v in stack["vias"]:
        name = LEF_VIA_NAMES.get(v["name"], v["name"])
        L.append("    %s [dict create res %.1f] \\" % (name, VIA_R_OHM))
    L.append("  ] \\")
    L.append("]")
    out.write_text("\n".join(L) + "\n")


def _indent(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            _indent(e, level + 1)
            if not e.tail or not e.tail.strip():
                e.tail = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--palace", action="store_true")
    ap.add_argument("--magic-snippet", action="store_true")
    ap.add_argument("--openrcx", action="store_true")
    ap.add_argument("--layers-rc", action="store_true")
    ap.add_argument("--scl", default="ics55_LLSC_H7CR")
    ap.add_argument("--librelane", default=str(ROOT / "libs.tech/librelane"))
    args = ap.parse_args(argv)

    stack = build_stack()
    if args.palace:
        out = ROOT / "libs.tech/pex/palace/ics55_stackup.xml"
        emit_palace_stackup(stack, out)
        print("palace stackup ->", out)
    if args.magic_snippet:
        emit_magic_snippet(stack)
    if args.openrcx:
        out = Path(args.librelane) / args.scl / "rcx.rules"
        emit_openrcx_rules(stack, out)
        print("openrcx rules ->", out)
    if args.layers_rc:
        out = Path(args.librelane) / args.scl / "layers_rc.tcl"
        emit_layers_rc(stack, out, corner="nom_*")
        print("layers_rc ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
