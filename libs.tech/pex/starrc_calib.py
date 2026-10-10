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
"""Calibrate the clean-room RC extraction stack against StarRC ITF/CAPTAB.

Reads the vendor StarRC technology files (ITF process + CAPTAB capacitance
tables) and compares them against:

  * the released LEF seeds (RPERSQ / CPERSQDIST / EDGECAPACITANCE), and
  * the clean-room assumed stack in ``config_gen.py`` (EPS_*/SPACING_*).

Emits a machine-readable calibration record and a human summary.

PROVENANCE: the ITF/CAPTAB inputs are derived from the upstream repository's
``hacking/decrypted_output/`` files, i.e. XOR-decrypted proprietary ECOS iRCX
blobs.  They are vendor data of unverified redistribution status and are used
here only as an offline comparison target.  The *result* recorded in the
emitted calibration JSON is what the clean-room generator can adopt.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# StarRC CAPTAB column convention: <width_um> <self_cap> <coupling_cap>.
# Absolute unit is taken as fF/um pending an independent structure check; all
# ratios reported here are unit-independent.
ITF_NUMBER = r"[+\-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+\-]?\d+)?"


def parse_itf(path: Path) -> dict:
    """Parse a StarRC ITF process file (TECHNOLOGY/DIELECTRIC/CONDUCTOR/VIA)."""
    dielectrics: list[dict] = []
    conductors: list[dict] = []
    vias: list[dict] = []
    header: dict[str, object] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if "=" in line and "{" not in line:
            key, _, value = line.partition("=")
            header[key.strip()] = value.strip()
            continue
        match = re.match(r"^([A-Z_]+)\s+(\S+)\s*\{(.*)\}\s*$", line)
        if not match:
            continue
        kind, name, body = match.group(1), match.group(2), match.group(3)
        fields: dict[str, float | str] = {}
        for key, value in re.findall(r"([A-Z_]+)\s*=\s*(\S+)", body):
            try:
                fields[key] = float(value)
            except ValueError:
                fields[key] = value
        if kind == "DIELECTRIC":
            dielectrics.append({"name": name, **fields})
        elif kind == "CONDUCTOR":
            conductors.append({"name": name, **fields})
        elif kind == "VIA":
            vias.append({"name": name, **fields})
    return {
        "source": str(path),
        "technology": header.get("TECHNOLOGY"),
        "global_temperature_c": _as_float(header.get("GLOBAL_TEMPERATURE")),
        "half_node_scale_factor": _as_float(header.get("HALF_NODE_SCALE_FACTOR")),
        "dielectrics": dielectrics,
        "conductors": conductors,
        "vias": vias,
    }


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_captab(path: Path) -> dict:
    """Parse a StarRC CAPTAB capacitance table into blocks of rows."""
    blocks: list[dict] = []
    current: dict | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        head = re.match(r"^([AB])\s+(\S+)\s+OVER\s+(\S+)(?:\s+UNDER\s+(\S+))?$", line)
        if head:
            if current:
                blocks.append(current)
            current = {
                "kind": head.group(1),
                "conductor": head.group(2),
                "over": head.group(3),
                "under": head.group(4),
                "rows": [],
            }
            continue
        parts = line.split()
        if current is not None and len(parts) == 3:
            try:
                current["rows"].append([float(x) for x in parts])
            except ValueError:
                continue
    if current:
        blocks.append(current)
    return {"source": str(path), "blocks": blocks}


def _at_width(block: dict, width: float) -> tuple[float, float] | None:
    for w, self_c, coup_c in block["rows"]:
        if abs(w - width) < 1e-9:
            return self_c, coup_c
    return None


def corner_ratios(reference: dict, other: dict) -> dict:
    """Per-block self/coupling ratios of `other` relative to `reference`."""
    ref_index = {
        (b["kind"], b["conductor"], b["over"], b["under"]): b
        for b in reference["blocks"]
    }
    ratios = []
    for block in other["blocks"]:
        key = (block["kind"], block["conductor"], block["over"], block["under"])
        ref = ref_index.get(key)
        if ref is None:
            continue
        self_ratios, coup_ratios = [], []
        for w, self_c, coup_c in block["rows"]:
            ref_row = _at_width(ref, w)
            if ref_row is None:
                continue
            if ref_row[0]:
                self_ratios.append(self_c / ref_row[0])
            if ref_row[1]:
                coup_ratios.append(coup_c / ref_row[1])
        if not self_ratios:
            continue
        ratios.append({
            "block": _block_name(block),
            "self_min": min(self_ratios),
            "self_max": max(self_ratios),
            "self_mean": sum(self_ratios) / len(self_ratios),
            "coupling_min": min(coup_ratios) if coup_ratios else None,
            "coupling_max": max(coup_ratios) if coup_ratios else None,
        })
    return {
        "source": other["source"],
        "blocks_compared": len(ratios),
        "self_mean_over_blocks": (
            sum(r["self_mean"] for r in ratios) / len(ratios) if ratios else None
        ),
        "self_min": min((r["self_min"] for r in ratios), default=None),
        "self_max": max((r["self_max"] for r in ratios), default=None),
        "per_block": ratios,
    }


def _block_name(block: dict) -> str:
    name = f"{block['kind']} {block['conductor']} OVER {block['over']}"
    if block["under"]:
        name += f" UNDER {block['under']}"
    return name


def lef_seeds(scl: str = "ics55_LLSC_H7CR") -> dict:
    """Read the released LEF RPERSQ/CPERSQDIST/EDGECAPACITANCE per layer."""
    lef = ROOT / "libs.tech/librelane/N551P6M_ecos.lef"
    text = lef.read_text()
    out: dict[str, dict] = {}
    for match in re.finditer(
        r"LAYER\s+(\S+)\s*\n(.*?)(?=\nLAYER\s|\Z)", text, re.S
    ):
        name, body = match.group(1), match.group(2)
        if "RPERSQ" not in body:
            continue
        def grab(prop: str) -> float | None:
            m = re.search(rf"{prop}\s+({ITF_NUMBER})", body)
            return float(m.group(1)) if m else None
        out[name] = {
            "rpersq_ohm_sq": grab("RPERSQ"),
            "cpersqdist_pf_um2": grab("CPERSQDIST"),
            "edgecapacitance_pf_um": grab("EDGECAPACITANCE"),
        }
    return out


# clean-room assumed stack in libs.tech/pex/config_gen.py
CONFIG_GEN_ESTIMATES = {
    "EPS_IMD": 3.3,
    "EPS_PMD": 3.9,
    "EPS_PASS": 4.0,
    "EPS_SUB": 11.9,
    "SPACING_PMD_um": 0.15,
    "SPACING_IMD_um": 0.12,
}
CONFIG_GEN_RHO_BULK = 1.72e-8  # ohm*m, the inference constant for thickness


def thickness_crosscheck(seeds: dict, conductors: list[dict]) -> list[dict]:
    """Compare config_gen's inferred metal thickness against the ITF truth.

    config_gen.py derives thickness from RPSQ with a bulk-Cu resistivity
    assumption; the ITF states the measured thickness directly.
    """
    rows = []
    for conductor in conductors:
        name = conductor["name"]
        seed = seeds.get(name)
        if seed is None or conductor.get("LAYER_TYPE"):
            continue
        rpsq = seed["rpersq_ohm_sq"]
        inferred = CONFIG_GEN_RHO_BULK / rpsq * 1e6 if rpsq else None
        actual = float(conductor.get("THICKNESS")) if conductor.get("THICKNESS") else None
        rows.append({
            "conductor": name,
            "itf_thickness_um": actual,
            "config_gen_inferred_um": inferred,
            "relative_delta": (
                (inferred - actual) / actual if actual and inferred else None
            ),
        })
    return rows


def capacitance_crosscheck(seeds: dict, captab: dict) -> list[dict]:
    """Compare the LEF area+edge capacitance model against CAPTAB.

    The LEF carries only one area and one edge density per layer, so the
    per-length capacitance it predicts is width-dependent:
        C_lep(W) = CPERSQDIST * W + EDGECAPACITANCE   [pF/um]
    CAPTAB gives the width-resolved self capacitance directly and therefore
    exposes the lateral/over-layer dependence the LEF cannot express.
    CAPTAB self values are read as fF/um pending a structure check; the ratio
    is the quantity that matters here.
    """
    rows = []
    for block in captab["blocks"]:
        if block["kind"] != "A" or block["over"] != "SUBSTRATE":
            continue
        seed = seeds.get(block["conductor"])
        if seed is None:
            continue
        area = seed["cpersqdist_pf_um2"]
        edge = seed["edgecapacitance_pf_um"]
        per_width = []
        for width, self_c, _ in block["rows"]:
            lef_pf_um = area * width + edge
            per_width.append({
                "width_um": width,
                "lef_area_plus_edge_fF_um": lef_pf_um * 1000.0,
                "captab_self_fF_um": self_c,
                "ratio_captab_over_lef": self_c / (lef_pf_um * 1000.0),
            })
        rows.append({
            "conductor": block["conductor"],
            "lef_cpersqdist_pf_um2": area,
            "lef_edgecapacitance_pf_um": edge,
            "rows": per_width,
        })
    return rows


def build_report(itf_paths: dict[str, Path], captab_paths: dict[str, Path],
                 lef_layer_map: dict[str, str]) -> dict:
    itfs = {corner: parse_itf(path) for corner, path in itf_paths.items()}
    captabs = {corner: parse_captab(path) for corner, path in captab_paths.items()}

    reference_itf = itfs["Typ"]
    itf_conductors = {c["name"]: c for c in reference_itf["conductors"]}
    seeds = lef_seeds()

    # --- Resistance: ITF RPSQ vs released LEF RPERSQ -------------------------
    resistance = []
    for itf_name, lef_name in lef_layer_map.items():
        conductor = itf_conductors.get(itf_name)
        seed = seeds.get(lef_name)
        if conductor is None or seed is None:
            continue
        itf_rpsq = float(conductor.get("RPSQ"))
        lef_rpsq = seed["rpersq_ohm_sq"]
        resistance.append({
            "itf_conductor": itf_name,
            "lef_layer": lef_name,
            "itf_rpsq_ohm_sq": itf_rpsq,
            "lef_rpersq_ohm_sq": lef_rpsq,
            "relative_delta": (
                (itf_rpsq - lef_rpsq) / lef_rpsq if lef_rpsq else None
            ),
        })

    # --- R: ITF truth vs config_gen's bulk-Cu thickness inference ------------
    itf_seeds = {
        itf_name: seeds[lef_name]
        for itf_name, lef_name in lef_layer_map.items()
        if lef_name in seeds
    }
    thickness = thickness_crosscheck(itf_seeds, reference_itf["conductors"])

    # --- C: released-LEF area+edge model vs CAPTAB width resolution ----------
    capacitance = capacitance_crosscheck(itf_seeds, captabs["Typ"])

    # --- Geometry: ITF thickness/WMIN/SMIN (absent from the LEF) -------------
    geometry = [
        {
            "conductor": c["name"],
            "thickness_um": c.get("THICKNESS"),
            "wmin_um": c.get("WMIN"),
            "smin_um": c.get("SMIN"),
            "layer_type": c.get("LAYER_TYPE", "METAL"),
        }
        for c in reference_itf["conductors"]
    ]

    # --- Dielectrics: ITF ER/THICKNESS vs config_gen guesses -----------------
    itf_imd_ers = sorted({
        float(d["ER"]) for d in reference_itf["dielectrics"]
        if "ER" in d and str(d["name"]).startswith(("IMD", "ILD"))
    })
    itf_pass_ers = sorted({
        float(d["ER"]) for d in reference_itf["dielectrics"]
        if "ER" in d and str(d["name"]).startswith("PASS")
    })
    dielectrics = {
        "itf_imd_er_values": itf_imd_ers,
        "itf_passivation_er_values": itf_pass_ers,
        "config_gen_estimates": CONFIG_GEN_ESTIMATES,
        "config_gen_eps_imd_in_itf_range": (
            CONFIG_GEN_ESTIMATES["EPS_IMD"] in itf_imd_ers
        ),
    }

    # --- Vias: ITF RPV vs released LEF VIA RESISTANCE ------------------------
    via_crosscheck = []
    for via in reference_itf["vias"]:
        via_crosscheck.append({
            "via": via["name"],
            "from": via.get("FROM"),
            "to": via.get("TO"),
            "itf_rpv_ohm": via.get("RPV"),
            "itf_area_um2": via.get("AREA"),
        })

    # --- Corner scaling from CAPTAB -----------------------------------------
    corners = {
        corner: corner_ratios(captabs["Typ"], captabs[corner])
        for corner in captabs
        if corner != "Typ"
    }

    # --- ITF corner deltas (RPSQ/THICKNESS) ---------------------------------
    itf_corner_deltas = {}
    for corner, data in itfs.items():
        if corner == "Typ":
            continue
        rows = []
        other = {c["name"]: c for c in data["conductors"]}
        for name, conductor in itf_conductors.items():
            peer = other.get(name)
            if peer is None:
                continue
            row = {"conductor": name}
            for field in ("RPSQ", "THICKNESS"):
                a = conductor.get(field)
                b = peer.get(field)
                row[f"{field.lower()}_typ"] = a
                row[f"{field.lower()}_corner"] = b
                if a:
                    row[f"{field.lower()}_ratio"] = b / a
            rows.append(row)
        itf_corner_deltas[corner] = rows

    return {
        "sources": {
            "itf": {c: str(p) for c, p in itf_paths.items()},
            "captab": {c: str(p) for c, p in captab_paths.items()},
        },
        "provenance_warning": (
            "ITF/CAPTAB are StarRC vendor data decrypted from the proprietary "
            "ECOS iRCX library (upstream hacking/decrypted_output). Redistribution "
            "status is unverified; use only as an offline comparison target."
        ),
        "itf_header": {
            "technology": reference_itf["technology"],
            "global_temperature_c": reference_itf["global_temperature_c"],
            "half_node_scale_factor": reference_itf["half_node_scale_factor"],
        },
        "resistance_crosscheck": resistance,
        "thickness_crosscheck": thickness,
        "capacitance_crosscheck": capacitance,
        "geometry_truth": geometry,
        "dielectric_crosscheck": dielectrics,
        "via_crosscheck": via_crosscheck,
        "captab_corner_scaling": corners,
        "captab_reference_shape": {
            _block_name(b): b["rows"]
            for b in captabs["Typ"]["blocks"]
            if b["kind"] == "A" and b["conductor"] in ("M1", "M2")
        },
        "itf_corner_deltas": itf_corner_deltas,
    }


def summarize(report: dict) -> None:
    print("ITF header:", report["itf_header"])
    print()
    print("Resistance cross-check (ITF RPSQ vs released LEF RPERSQ):")
    exact = 0
    for row in report["resistance_crosscheck"]:
        delta = row["relative_delta"]
        flag = "EXACT" if delta is not None and abs(delta) < 1e-12 else "DIFF"
        if flag == "EXACT":
            exact += 1
        print("  %-8s %-6s itf=%-8g lef=%-8g delta=%s  %s" % (
            row["itf_conductor"], row["lef_layer"], row["itf_rpsq_ohm_sq"],
            row["lef_rpersq_ohm_sq"],
            "%.3g" % delta if delta is not None else "n/a", flag))
    print("  -> %d/%d layers identical" % (exact, len(report["resistance_crosscheck"])))
    print()
    print("Thickness cross-check (ITF truth vs config_gen bulk-Cu inference):")
    for row in report["thickness_crosscheck"]:
        print("  %-6s itf=%-7s inferred=%-8s delta=%s" % (
            row["conductor"], row["itf_thickness_um"],
            "%.5f" % row["config_gen_inferred_um"],
            "%.1f%%" % (row["relative_delta"] * 100) if row["relative_delta"] is not None else "n/a"))
    print()
    print("Capacitance cross-check (released LEF area+edge vs CAPTAB self):")
    for row in report["capacitance_crosscheck"]:
        ratios = [r["ratio_captab_over_lef"] for r in row["rows"]]
        print("  %-6s area=%-9g edge=%-9g ratio=[%.2f..%.2f] mean=%.2f" % (
            row["conductor"], row["lef_cpersqdist_pf_um2"],
            row["lef_edgecapacitance_pf_um"], min(ratios), max(ratios),
            sum(ratios) / len(ratios)))
    print()
    print("Geometry truth absent from the LEF (ITF THICKNESS/WMIN/SMIN, um):")
    for row in report["geometry_truth"]:
        print("  %-8s t=%-7s wmin=%-7s smin=%-7s %s" % (
            row["conductor"], row["thickness_um"], row["wmin_um"],
            row["smin_um"], row["layer_type"]))
    print()
    print("Via resistance cross-check:")
    for row in report["via_crosscheck"]:
        print("  %-9s %-7s -> %-7s rpv=%-8s area=%s" % (
            row["via"], row["from"], row["to"], row["itf_rpv_ohm"],
            row["itf_area_um2"]))
    print()
    print("Dielectric cross-check:", json.dumps(
        report["dielectric_crosscheck"], indent=2))
    print()
    print("CAPTAB corner scaling (self-cap ratio vs Typ, unit-independent):")
    for corner, data in report["captab_corner_scaling"].items():
        print("  %-9s blocks=%3d self=[%.4f..%.4f] mean=%.4f" % (
            corner, data["blocks_compared"], data["self_min"], data["self_max"],
            data["self_mean_over_blocks"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--decrypted", type=Path,
        default=Path("/tmp/up/hacking/decrypted_output"),
        help="directory holding kItf*/kCaptab* files",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base = args.decrypted
    itf_paths = {
        corner: base / name for corner, name in {
            "Typ": "kItfTyp.txt",
            "Rcbest": "kItfRcbest.txt",
            "Rcworst": "kItfRcworst.txt",
            "Cworst": "kItfCworst.txt",
        }.items()
    }
    captab_paths = {
        corner: base / name for corner, name in {
            "Typ": "kCaptabTyp.txt",
            "Rcbest": "kCaptabRcbest.txt",
            "Rcworst": "kCaptabRcworst.txt",
            "Cbest": "kCaptabCbest.txt",
            "Cworst": "kCaptabCworst.txt",
        }.items()
    }
    missing = [str(p) for p in list(itf_paths.values()) + list(captab_paths.values())
               if not p.exists()]
    if missing:
        raise SystemExit("missing StarRC inputs: %s" % ", ".join(missing))

    lef_layer_map = {
        "M1": "MET1", "M2": "MET2", "M3": "MET3", "M4": "MET4",
        "M5": "MET5", "TM": "T4M2", "RDL": "RDL",
    }
    report = build_report(itf_paths, captab_paths, lef_layer_map)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    summarize(report)
    print()
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
