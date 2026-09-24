#!/usr/bin/env python3
"""Extract released LEF wire-RC seeds for the Layer-3 RCX handoff.

The extractor is intentionally fail-closed for coupling capacitance.  The
current LEF contains resistance, area capacitance, and edge capacitance seeds,
but no lateral/vertical coupling model.  The JSON therefore supports early
RC estimates and deck generation, not signoff parasitic extraction.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"


def _number(block: str, pattern: str) -> Optional[float]:
    match = re.search(pattern + r"\s+(" + NUMBER + r")\s*;", block)
    return float(match.group(1)) if match else None


def _scalar(block: str, name: str) -> Optional[str]:
    match = re.search(r"(?m)^\s*" + re.escape(name) + r"\s+([^;]+);", block)
    return match.group(1).strip() if match else None


def _layer_records(text: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    pattern = re.compile(
        r"(?ms)^LAYER\s+(\S+)\s*\n(.*?)^END\s+\1\s*$"
    )
    for match in pattern.finditer(text):
        name, block = match.group(1), match.group(2)
        if _scalar(block, "TYPE") != "ROUTING":
            continue
        records.append({
            "name": name,
            "direction": _scalar(block, "DIRECTION"),
            "width_um": _number(block, r"WIDTH"),
            "pitch_x_um": (
                float(re.search(NUMBER, _scalar(block, "PITCH") or "").group(0))
                if _scalar(block, "PITCH") and re.search(NUMBER, _scalar(block, "PITCH") or "")
                else None
            ),
            "resistance_ohm_per_square": _number(
                block, r"RESISTANCE\s+RPERSQ"
            ),
            "capacitance_pf_per_um2": _number(
                block, r"CAPACITANCE\s+CPERSQDIST"
            ),
            "edge_capacitance_pf_per_um": _number(
                block, r"EDGECAPACITANCE"
            ),
        })
    return records


def _via_records(text: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    pattern = re.compile(r"(?ms)^VIA\s+(\S+).*?^END\s+\1\s*$")
    for match in pattern.finditer(text):
        block = match.group(0)
        resistance = _number(block, r"RESISTANCE")
        if resistance is None:
            continue
        records.append({
            "name": match.group(1),
            "resistance_ohm": resistance,
        })
    return records


def extract(lef: Path) -> Dict[str, Any]:
    text = lef.read_text()
    layers = _layer_records(text)
    vias = _via_records(text)
    missing = []
    if not layers:
        missing.append("routing_layers")
    if any(layer["resistance_ohm_per_square"] is None for layer in layers):
        missing.append("routing_resistance")
    if any(layer["capacitance_pf_per_um2"] is None for layer in layers):
        missing.append("routing_area_capacitance")
    if any(layer["edge_capacitance_pf_per_um"] is None for layer in layers):
        missing.append("routing_edge_capacitance")
    missing.append("coupling_capacitance")
    return {
        "schema_version": 1,
        "kind": "ics55_layer3_lef_rc_seed",
        "source": str(lef),
        "units": {
            "length": "um",
            "resistance_per_square": "ohm/square",
            "resistance": "ohm",
            "area_capacitance": "pF/um^2",
            "edge_capacitance": "pF/um",
        },
        "routing_layers": layers,
        "vias": vias,
        "coupling_capacitance": None,
        "missing_inputs": sorted(set(missing)),
        "status": "seed_only" if "coupling_capacitance" in missing else "complete",
        "warnings": [
            "LEF provides no lateral/vertical coupling capacitance model.",
            "Do not use this seed as signoff RCX without a calibrated field-solver or foundry deck.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lef", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--require-coupling",
        action="store_true",
        help="fail unless the source supplies a coupling model",
    )
    args = parser.parse_args()
    lef = args.lef.expanduser()
    if not lef.is_file():
        parser.error("LEF file not found: %s" % lef)
    result = extract(lef)
    if args.require_coupling and result["coupling_capacitance"] is None:
        parser.error("source LEF has no coupling capacitance model")
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = args.out.expanduser()
        out.write_text(rendered)
        print(out)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
