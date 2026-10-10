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
#
# EXCEPTION: the StarRC ITF/CAPTAB values loaded from libs.tech/pex/starrc/
# are ICsprout vendor data, not Apache-2.0.  See that directory's ORIGIN.json
# and libs.tech/pex/README.md.

# ============================================================================
# config_gen.py - ICsprout55 extraction-config generator
# ============================================================================
# Emits the parasitic-extraction configurations from two value sources:
#
#   BASE  (LEF / ECOS): the released LEF seeds (RPERSQ / CPERSQDIST /
#         EDGECAPACITANCE / WIDTH) plus the user-approved process estimates
#         (metal thickness from bulk-Cu RPSQ inference, dielectric eps and
#         spacing = typical 55nm-node values, thermal constants).  These are
#         the clean-room values and are kept verbatim below.
#
#   OVERRIDE (StarRC vendor): the ICsprout StarRC ITF + CAPTAB files under
#         libs.tech/pex/starrc/ (vendor data, educational use only).  When
#         --source=starrc (the default) the ITF supplies the absolute
#         thickness / RPSQ / dielectric eps / via and contact resistance, and
#         the CAPTAB supplies the per-corner capacitance scaling.
#
# What is overridden, and why:
#
#   thickness         ITF CONDUCTOR THICKNESS replaces the bulk-Cu inference
#                     (which was 10-21% thin).  THIS IS THE BIG ONE: it also
#                     fixes sigma = 1/(RPSQ*t).
#   RPSQ              ITF RPSQ; identical to the LEF for the Typ corner, so
#                     this only changes the non-Typ corners.
#   dielectric eps    ITF per-layer ER, collapsed to one effective value per
#                     group using the series-capacitance rule
#                     eps_eff = sum(t) / sum(t/eps).
#   via / contact R   ITF RPV.  Adds the contact resistances (CT_*) that the
#                     LEF does not carry at all.
#   capacitance       CAPTAB corner-to-Typ ratio applied to the BASE value.
#                     DELIBERATELY RATIO-ONLY: the absolute column semantics
#                     of the CAPTAB are not documented in the released data.
#                     Fitting C/L = col2*W + col3 against a*W + b is linear
#                     (rms ~4%), but the resulting a is ~45x below the LEF
#                     CPERSQDIST for M1 and the "OVER SUBSTRATE" tables are
#                     environment-specific, so the absolute scale is not
#                     comparable.  The ratios are unit-independent and are
#                     what the corners actually encode.
#
# Corner model (see build_stack docstring): the vendor set decomposes into an
# R axis (thickness + RPSQ) and a C axis (dielectric stack + CAPTAB).
#
# Usage:
#   python config_gen.py --palace --magic-snippet --openrcx --layers-rc
#   python config_gen.py --layers-rc --all-corners
#   python config_gen.py --palace --corner rcworst
#   python config_gen.py --source lef --layers-rc      # clean-room baseline
# ============================================================================

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import starrc_calib as star  # noqa: E402  (shared ITF/CAPTAB parser)

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
# 3. StarRC vendor override (libs.tech/pex/starrc/)
# ---------------------------------------------------------------------------
# Vendor corner name -> (ITF file, CAPTAB file).  The vendor ships five
# corners; the dielectric-only cbest stack was published upstream under the
# symbol name kItfRcbest_21eac0.txt and is imported here as kItfCbest.txt
# (its own TECHNOLOGY header says Cbest).
STARRC_DIR = ROOT / "libs.tech/pex/starrc"
STARRC_FILES = {
    "typ":    ("kItfTyp.txt",     "kCaptabTyp.txt"),
    "rcbest": ("kItfRcbest.txt",  "kCaptabRcbest.txt"),
    "rcworst": ("kItfRcworst.txt", "kCaptabRcworst.txt"),
    "cbest":  ("kItfCbest.txt",   "kCaptabCbest.txt"),
    "cworst": ("kItfCworst.txt",  "kCaptabCworst.txt"),
}
STARRC_CORNERS = tuple(STARRC_FILES)

# Published Liberty corner -> (R axis, C axis).  The Liberty names encode the
# RC corner they were characterized at (see libs.tech/librelane/config.tcl).
LIBERTY_CORNER_MAP = {
    "nom_tt_025C_1v20": ("typ", "typ"),
    "nom_ss_125C_1v08": ("rcworst", "cworst"),
    "nom_ff_n40C_1v32": ("rcbest", "cbest"),
}

# StarRC ITF conductor name -> the name used in this generator.
ITF_CONDUCTOR_ALIAS = {"TM": "TM2"}

# ITF via name -> the name used in this generator.
ITF_VIA_ALIAS = {"TV": "TV2"}


class StarRcData:
    """Loaded ITF/CAPTAB pair for one vendor corner.

    Kept as a plain loader so the generator can also run with --source=lef
    (override disabled) and so the comparison tool can reuse it.
    """

    def __init__(self, corner: str):
        itf_name, captab_name = STARRC_FILES[corner]
        self.corner = corner
        self.itf = star.parse_itf(STARRC_DIR / itf_name)
        self.captab = star.parse_captab(STARRC_DIR / captab_name)
        self._conductors = {c["name"]: c for c in self.itf["conductors"]}
        self._vias = {v["name"]: v for v in self.itf["vias"]}

    # -- R axis ------------------------------------------------------------
    def thickness_um(self, layer: str) -> float | None:
        conductor = self._conductors.get(self._itf_name(layer))
        if conductor is None:
            return None
        value = conductor.get("THICKNESS")
        return float(value) if value is not None else None

    def rpsq(self, layer: str) -> float | None:
        conductor = self._conductors.get(self._itf_name(layer))
        if conductor is None:
            return None
        value = conductor.get("RPSQ")
        return float(value) if value is not None else None

    def via_r(self, via: str) -> float | None:
        entry = self._vias.get(self._itf_via_name(via))
        if entry is None:
            return None
        value = entry.get("RPV")
        return float(value) if value is not None else None

    def contact_r(self) -> dict:
        """CT_* contact resistances (absent from the released LEF)."""
        return {
            name: float(entry["RPV"])
            for name, entry in self._vias.items()
            if name.startswith("CT_") and "RPV" in entry
        }

    # -- C axis ------------------------------------------------------------
    def capacitance_ratio(self, layer: str, reference: "StarRcData") -> float:
        """Corner/typ self-capacitance ratio for one layer.

        Unit-independent: both numerator and denominator come from the same
        CAPTAB column of the same block, so the unknown absolute scale of the
        CAPTAB cancels.  Averaged over the 12 tabulated widths and over the
        self and coupling columns.
        """
        name = self._itf_name(layer)
        here = _substrate_block(self.captab, name)
        base = _substrate_block(reference.captab, name)
        if here is None or base is None:
            return 1.0
        index = {round(row[0], 9): row for row in base["rows"]}
        ratios = []
        for width, self_c, coup_c in here["rows"]:
            ref = index.get(round(width, 9))
            if ref is None:
                continue
            if ref[1]:
                ratios.append(self_c / ref[1])
            if ref[2]:
                ratios.append(coup_c / ref[2])
        return sum(ratios) / len(ratios) if ratios else 1.0

    def effective_eps(self, prefix: tuple[str, ...]) -> float | None:
        """Series-capacitance effective eps for a dielectric group.

        eps_eff = sum(t_i) / sum(t_i / eps_i) - the permittivity a single
        slab of the same total thickness would need to give the same
        capacitance.
        """
        layers = [
            d for d in self.itf["dielectrics"]
            if str(d.get("name", "")).startswith(prefix) and d.get("THICKNESS")
        ]
        if not layers:
            return None
        total = sum(float(d["THICKNESS"]) for d in layers)
        if total <= 0:
            return None
        series = sum(float(d["THICKNESS"]) / float(d["ER"]) for d in layers)
        return total / series if series > 0 else None

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _itf_name(layer: str) -> str:
        for itf_name, local in ITF_CONDUCTOR_ALIAS.items():
            if local == layer:
                return itf_name
        return layer

    @staticmethod
    def _itf_via_name(via: str) -> str:
        for itf_name, local in ITF_VIA_ALIAS.items():
            if local == via:
                return itf_name
        return via


def _substrate_block(captab: dict, conductor: str) -> dict | None:
    for block in captab["blocks"]:
        if (block["kind"] == "A" and block["conductor"] == conductor
                and block["over"] == "SUBSTRATE"):
            return block
    return None


# ---------------------------------------------------------------------------
# 4. Derived process model
# ---------------------------------------------------------------------------
def metal_thickness_um(rpsq):
    """BASE thickness: bulk-Cu inference from the sheet resistance."""
    return RHO_BULK / rpsq * 1e6


def sigma_s_m2(rpsq, thickness_um):
    return 1.0 / (rpsq * thickness_um * 1e-6)


def build_stack(corner: str = "typ", rc_corner: str | None = None,
                c_corner: str | None = None, source: str = "starrc"):
    """Return the metal/via z-ranges (um, z=0 at the substrate bottom).

    Corner model
    ------------
    The vendor corners act on two independent axes:

      R axis (rc_corner) - conductor THICKNESS and RPSQ.
        rcbest  : t x1.10, RPSQ x0.63-0.78, all dielectrics x1.10
        rcworst : t x0.90, RPSQ x1.26-1.36, all dielectrics x0.90
      C axis (c_corner) - the dielectric stack shape.
        cbest   : dielectrics x1.10/-0.25/+0.25, conductors as rcworst
        cworst  : dielectrics x0.90/+0.25/-0.25, conductors as rcbest

    The vendor pairs them fixed (rcbest<->cbest, rcworst<->cworst) because
    that is how the process varies.  They are still separable in this
    generator: pass --rc-corner/--c-corner to mix them (for example
    --rc-corner rcworst --c-corner cworst for the pessimistic RC product),
    because some flows want worst-R x worst-C independently.  Mixing is a
    deliberate, caller-visible choice; the default is the vendor pairing.

    ``corner`` selects a single vendor corner for both axes.
    """
    if corner not in STARRC_FILES:
        raise SystemExit("unknown corner %r (choose from %s)"
                         % (corner, ", ".join(STARRC_CORNERS)))
    rc_corner = rc_corner or corner
    c_corner = c_corner or corner
    for name in (rc_corner, c_corner):
        if name not in STARRC_FILES:
            raise SystemExit("unknown corner %r" % (name,))

    rc_data = StarRcData(rc_corner) if source == "starrc" else None
    c_data = StarRcData(c_corner) if source == "starrc" else None
    typ_data = StarRcData("typ") if source == "starrc" else None

    metals = []
    z = SUBSTRATE_THICK_UM + SPACING_PMD
    for name in ["M1", "M2", "M3", "M4", "M5", "TM2"]:
        rpsq_base, cap, edge, w = LEF_SEEDS[name]

        # --- R axis: sheet resistance and metal thickness ---------------
        rpsq = rpsq_base
        thickness = metal_thickness_um(rpsq_base)
        if rc_data is not None:
            itf_rpsq = rc_data.rpsq(name)
            itf_t = rc_data.thickness_um(name)
            if itf_rpsq is not None:
                rpsq = itf_rpsq
            if itf_t is not None:
                thickness = itf_t
            elif itf_rpsq is not None:
                thickness = metal_thickness_um(itf_rpsq)

        # --- C axis: capacitance corner ratio on top of the BASE value ---
        cap_eff, edge_eff = cap, edge
        if c_data is not None and typ_data is not None:
            ratio = c_data.capacitance_ratio(name, typ_data)
            cap_eff, edge_eff = cap * ratio, edge * ratio

        zmin = round(z, 4)
        zmax = round(z + thickness, 4)
        metals.append({"name": name, "rpsq": rpsq, "cap": cap_eff,
                       "edge": edge_eff, "width": w, "thickness": thickness,
                       "zmin": zmin, "zmax": zmax,
                       "sigma": sigma_s_m2(rpsq, thickness),
                       "thermal": THERMAL["metal"][0],
                       "density": THERMAL["metal"][1],
                       "cap_ratio": (cap_eff / cap) if cap else 1.0})
        z = round(z + thickness + SPACING_IMD, 4)

    vias = []
    order = [("V1", "M1", "M2"), ("V2", "M2", "M3"), ("V3", "M3", "M4"),
             ("V4", "M4", "M5"), ("TV2", "M5", "TM2")]
    for via, low, high in order:
        zlo = next(m["zmax"] for m in metals if m["name"] == low)
        zhi = next(m["zmin"] for m in metals if m["name"] == high)
        w = VIA_CUT_UM[via]
        h = zhi - zlo
        r = VIA_R_OHM
        if rc_data is not None:
            itf_r = rc_data.via_r(via)
            if itf_r is not None:
                r = itf_r
        sigma = h * 1e-6 / (r * (w * 1e-6) ** 2)   # from R = r ohm
        vias.append({"name": via, "zmin": zlo, "zmax": zhi, "cut": w,
                     "r": r, "sigma": sigma, "lower": low, "upper": high})

    # --- dielectrics --------------------------------------------------------
    eps_imd, eps_pmd, eps_pass = EPS_IMD, EPS_PMD, EPS_PASS
    if c_data is not None:
        eps_imd = c_data.effective_eps(("IMD",)) or eps_imd
        eps_pmd = c_data.effective_eps(("ILD", "FOX", "PO_SP")) or eps_pmd
        eps_pass = c_data.effective_eps(("PASS",)) or eps_pass

    # --- RDL (above the TM stack, carried separately by the OpenRCX rules) ---
    rdl_rpsq, rdl_cap, rdl_edge, rdl_width = LEF_SEEDS["RDL"]
    if rc_data is not None:
        rdl_rpsq = rc_data.rpsq("RDL") or rdl_rpsq
    if c_data is not None and typ_data is not None:
        ratio = c_data.capacitance_ratio("RDL", typ_data)
        rdl_cap, rdl_edge = rdl_cap * ratio, rdl_edge * ratio
    rdl = {"name": "RDL", "rpsq": rdl_rpsq, "cap": rdl_cap,
           "edge": rdl_edge, "width": rdl_width}

    return {
        "metals": metals,
        "vias": vias,
        "rdl": rdl,
        "eps": {"imd": eps_imd, "pmd": eps_pmd, "pass": eps_pass,
                "sub": EPS_SUB},
        "contacts": rc_data.contact_r() if rc_data is not None else {},
        "corner": corner,
        "rc_corner": rc_corner,
        "c_corner": c_corner,
        "source": source,
    }


# ---------------------------------------------------------------------------
# 5. Emitters
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
    eps = stack["eps"]
    for nm, epsv, k, rho, typ in [
            ("IMD", eps["imd"], *THERMAL["imd"], "Dielectric"),
            ("PMD", eps["pmd"], *THERMAL["pmd"], "Dielectric"),
            ("Passivation", eps["pass"], *THERMAL["passivation"], "Dielectric"),
            ("Substrate", eps["sub"], *THERMAL["substrate"], "Semiconductor"),
            ("AIR", 1.0, *THERMAL["air"], "Dielectric")]:
        attrs = {"Name": nm, "Type": typ, "Permittivity": _num(epsv),
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
    # The XML declaration must be the first thing in the document, so the
    # licence comment goes after it (a comment before it makes the file
    # unparseable: "XML or text declaration not at start of entity").
    header = ("<?xml version='1.0' encoding='UTF-8'?>\n"
              "<!--\n"
              "Copyright 2026 Yan Lu with DeepSeek V4 Flash and GPT-5.6-Luna\n"
              "\n"
              "Licensed under the Apache License, Version 2.0 (the \"License\");\n"
              "you may not use this file except in compliance with the License.\n"
              "You may obtain a copy of the License at\n"
              "\n"
              "    http://www.apache.org/licenses/LICENSE-2.0\n"
              "\n"
              "Unless required by applicable law or agreed to in writing, software\n"
              "distributed under the License is distributed on an \"AS IS\" BASIS,\n"
              "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
              "See the License for the specific language governing permissions and\n"
              "limitations under the License.\n"
              "-->\n"
              "<!-- Generated by libs.tech/pex/config_gen.py\n"
              "     source=%s corner=%s (R=%s C=%s)\n"
              "     BASE: released LEF seeds + user-approved estimates.\n"
              "     OVERRIDE: StarRC vendor ITF (thickness/RPSQ/eps/via R) and\n"
              "     CAPTAB corner capacitance ratio.  The StarRC inputs are\n"
              "     ICsprout vendor data (see libs.tech/pex/README.md).\n"
              "     Regenerate after any change. -->\n"
              % (stack["source"], stack["corner"], stack["rc_corner"],
                 stack["c_corner"]))
    out.write_text(header + ET.tostring(root, encoding="unicode") + "\n")


def emit_magic_snippet(stack):
    """Print the magic .tech extract values (resist/areacap/perimc)."""
    for m in stack["metals"]:
        print("\tresist\t%s\t%d" % (m["name"].lower(), round(m["rpsq"] * 1000)))
    for v in stack["vias"]:
        print("\tresist\t%s\t%d" % (v["name"].lower(), round(v["r"] * 1000)))
    for m in stack["metals"]:
        print("\tareacap\t%s\t%d" % (m["name"].lower(), round(m["cap"] * 1e6)))
    for m in stack["metals"]:
        print("\tperimc\t%s\tspace\t%d" % (m["name"].lower(), round(m["edge"] * 1e6)))
    if stack["contacts"]:
        print("\t* contact resistance (ohm), from the StarRC ITF:")
        for name, value in sorted(stack["contacts"].items()):
            print("\t*   %-8s %g" % (name, value))


def emit_openrcx_rules(stack, out):
    """OpenRCX extraction rules (LayerCount 7: M1-M5 + TM2 + RDL) with the
    upstream block pattern (RESOVER/OVER/UNDER/DIAGUNDER/OVERUNDER per metal,
    the full index matrix).  R comes from the active corner; the C
    coefficients are the BASE LEF-seeded estimates scaled by the CAPTAB
    corner ratio."""
    # 7-metal list: the 6 stack metals + the RDL (the rules' LayerCount 7)
    metals = list(stack["metals"]) + [stack["rdl"]]
    nlayers = len(metals)
    # The pinned OpenROAD 2026-02-17 requires the legacy header
    # ("Extraction Rules for rcx" + Version + Corners); the newer
    # "Extraction Rules for OpenRCX" header segfaults its calcMinMaxRC.
    if stack["source"] == "lef":
        comment = ("COMMENT : ICsprout55 clean-room estimates (LEF-seeded); "
                   "calibration pending")
    else:
        comment = ("COMMENT : source=starrc R=%s C=%s; BASE=LEF seeds, "
                   "OVERRIDE=StarRC vendor ITF/CAPTAB"
                   % (stack["rc_corner"], stack["c_corner"]))
    L = ["Extraction Rules for rcx", "",
         "Version 1.2", "",
         "DIAGMODEL ON", "",
         "LayerCount %d" % nlayers, "",
         "DensityRate 1  0", "",
         "Corners 1 :  TYP", "",
         comment, "",
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


def emit_layers_rc(stacks, out):
    """LibreLane LAYERS_RC / VIAS_R tcl fragment.

    The format is a corner-keyed dict ({corner: {layer: {R, C}}}), so one file
    carries every corner and the flow selects with its own corner name.  Layer
    and via names are the released LEF names (MET1.., VIA1..) so the OpenROAD
    set_layer_rc lookups match the technology.

    ``stacks`` maps an emission key (vendor corner name, or a flow/Liberty
    corner name) -> stack.  Every key gets its own dict entry so STA and
    extraction agree on the corner.
    """
    L = ["# LAYERS_RC / VIAS_R (generated by libs.tech/pex/config_gen.py)",
         "# BASE: released LEF seeds.  OVERRIDE: StarRC vendor ITF/CAPTAB.",
         "# Keys: vendor corner names plus the flow/Liberty corner names the",
         "# released libraries were characterized at (see the manifest).",
         "set ::env(LAYERS_RC) [dict create \\"]
    emitted = []
    for key, stack in stacks.items():
        L.append("  \"%s\" [dict create \\" % key)
        for m in stack["metals"]:
            name = LEF_LAYER_NAMES.get(m["name"], m["name"])
            L.append("    %s [dict create R %.5f C %.8f] \\"
                     % (name, m["rpsq"], m["cap"]))
        rdl = stack["rdl"]
        L.append("    RDL [dict create R %.5f C %.8f] \\"
                 % (rdl["rpsq"], rdl["cap"]))
        L.append("  ] \\")
        emitted.append(key)
    L.append("]")
    L.append("set ::env(VIAS_R) [dict create \\")
    for key, stack in stacks.items():
        L.append("  \"%s\" [dict create \\" % key)
        for v in stack["vias"]:
            name = LEF_VIA_NAMES.get(v["name"], v["name"])
            L.append("    %s [dict create res %.3f] \\" % (name, v["r"]))
        L.append("  ] \\")
    L.append("]")
    out.write_text("\n".join(L) + "\n")
    return emitted


def emit_corner_manifest(stacks, out):
    """Machine-readable corner manifest for the flow and for review."""
    payload = {
        "generator": "libs.tech/pex/config_gen.py",
        "base_source": "released LEF seeds + user-approved estimates",
        "override_source": (
            "StarRC vendor ITF/CAPTAB under libs.tech/pex/starrc "
            "(ICsprout vendor data, educational use only; not Apache-2.0)"
        ),
        "corner_model": {
            "R axis": "conductor THICKNESS + RPSQ (from ITF)",
            "C axis": "dielectric stack eps + CAPTAB corner ratio",
            "vendor pairing": {
                "typ": "typ x typ",
                "rcbest": "low R (t x1.1, RPSQ x0.63-0.78)",
                "rcworst": "high R (t x0.9, RPSQ x1.26-1.36)",
                "cbest": "low C (dielectrics x1.1 shaped), conductors as rcworst",
                "cworst": "high C (dielectrics x0.9 shaped), conductors as rcbest",
            },
            "mixing": "--rc-corner/--c-corner mix the axes independently",
        },
        "liberty_corner_map": {
            name: {"rc_corner": rc, "c_corner": c}
            for name, (rc, c) in LIBERTY_CORNER_MAP.items()
        },
        "corners": {},
    }
    for name, stack in stacks.items():
        payload["corners"][name] = {
            "rc_corner": stack["rc_corner"],
            "c_corner": stack["c_corner"],
            "eps": stack["eps"],
            "metals": [
                {"layer": m["name"], "rpsq": m["rpsq"],
                 "thickness_um": m["thickness"], "sigma_s_m": m["sigma"],
                 "cap_pf_um2": m["cap"], "edge_pf_um": m["edge"],
                 "cap_ratio_vs_typ": m["cap_ratio"]}
                for m in stack["metals"]
            ],
            "vias": [
                {"via": v["name"], "r_ohm": v["r"], "cut_um": v["cut"],
                 "sigma_s_m": v["sigma"]}
                for v in stack["vias"]
            ],
            "contacts_ohm": stack["contacts"],
        }
    out.write_text(json.dumps(payload, indent=2) + "\n")


def _num(value, digits: int = 3) -> str:
    """Format a float without trailing zeros, keeping one decimal.

    3.3 -> '3.3', 4.0 -> '4.0', 3.610070 -> '3.61'.
    """
    text = "%.*f" % (digits, value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text


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
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument("--source", choices=("starrc", "lef"), default="starrc",
                    help="starrc = vendor override (default); lef = BASE only")
    ap.add_argument("--corner", default="typ", choices=STARRC_CORNERS,
                    help="vendor corner for both axes")
    ap.add_argument("--rc-corner", default=None, choices=STARRC_CORNERS,
                    help="override the R axis independently")
    ap.add_argument("--c-corner", default=None, choices=STARRC_CORNERS,
                    help="override the C axis independently")
    ap.add_argument("--all-corners", action="store_true",
                    help="emit one artifact per vendor corner")
    ap.add_argument("--scl", default="ics55_LLSC_H7CR")
    ap.add_argument("--librelane", default=str(ROOT / "libs.tech/librelane"))
    args = ap.parse_args(argv)

    scl_dir = Path(args.librelane) / args.scl
    palace_dir = ROOT / "libs.tech/pex/palace"

    # Per-file artifacts (palace XML, OpenRCX rules) are single-corner: emit
    # the selected corner, or every vendor corner with --all-corners.
    corners = list(STARRC_CORNERS) if args.all_corners else [args.corner]
    stacks = {}
    for name in corners:
        if args.all_corners:
            stacks[name] = build_stack(name, source=args.source)
        else:
            stacks[name] = build_stack(name, rc_corner=args.rc_corner,
                                       c_corner=args.c_corner,
                                       source=args.source)

    # Corner-keyed artifacts (LAYERS_RC/VIAS_R is one dict, the manifest
    # describes the whole corner set) always carry every vendor corner plus an
    # entry per released-Liberty flow corner, so the flow can pick any of them
    # from a single generation run.
    if args.layers_rc or args.manifest or args.all_corners:
        all_stacks = {name: build_stack(name, source=args.source)
                      for name in STARRC_CORNERS}
        for flow_name, (rc, c) in LIBERTY_CORNER_MAP.items():
            # Emit under the flow name even when a vendor corner already has
            # the same pairing, so the flow can look up its own corner name.
            all_stacks[flow_name] = build_stack(
                rc, rc_corner=rc, c_corner=c, source=args.source)
    else:
        all_stacks = stacks

    # --all-corners emits a palace/rules file for every corner, including the
    # flow-corner pairings; otherwise only the selected corner is written.
    file_stacks = all_stacks if args.all_corners else stacks

    for name, stack in file_stacks.items():
        if args.palace:
            # Typ keeps the canonical filename so the existing flow is
            # unchanged; every corner also gets an explicit file.
            if name == "typ":
                out = palace_dir / "ics55_stackup.xml"
                emit_palace_stackup(stack, out)
                print("palace stackup ->", out)
            out = palace_dir / ("ics55_stackup_%s.xml" % name)
            emit_palace_stackup(stack, out)
            print("palace stackup ->", out)
        if args.openrcx:
            # Typ keeps the canonical rcx.rules name for the current
            # RCX_RULESETS entry; every corner gets its own file.
            out = scl_dir / ("rcx_%s.rules" % name)
            emit_openrcx_rules(stack, out)
            print("openrcx rules ->", out)
            if name == "typ":
                canonical = scl_dir / "rcx.rules"
                emit_openrcx_rules(stack, canonical)
                print("openrcx rules ->", canonical)

    if args.magic_snippet:
        for name, stack in stacks.items():
            print("* --- corner %s (R=%s C=%s) ---"
                  % (name, stack["rc_corner"], stack["c_corner"]))
            emit_magic_snippet(stack)

    if args.layers_rc:
        out = scl_dir / "layers_rc.tcl"
        keys = emit_layers_rc(all_stacks, out)
        print("layers_rc ->", out)
        print("  corners:", ", ".join(keys))

    if args.manifest:
        out = ROOT / "libs.tech/pex/RC_CORNER_MANIFEST.json"
        emit_corner_manifest(all_stacks, out)
        print("corner manifest ->", out)

    if not any((args.palace, args.magic_snippet, args.openrcx,
                args.layers_rc, args.manifest)):
        ap.error("nothing to do: pass at least one of --palace, "
                 "--magic-snippet, --openrcx, --layers-rc, --manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
