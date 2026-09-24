#!/usr/bin/env python3
"""Audit size- and bias-sensitive BSIM4 C-V parameter candidates.

The tool is intentionally an experiment manifest, not a model-promotion path.
It probes the flattened CDL cell network with Xyce AC analysis, compares the
intrinsic probe capacitance with the cell-boundary Liberty input capacitance,
and sweeps one CV parameter at a time.  Liberty supplies one pin-capacitance
number per input pin, not a bias-resolved C-V curve, so the bias grid is
reported as sensitivity evidence and is never silently treated as measured
C-V data.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

HERE = Path(__file__).resolve().parent
FITTED = HERE.parent / "fitted" / "FIT_PARAMS.json"
FLAVORS = ("svt", "lvt", "hvt")
DEFAULT_CELLS = ("INVX1", "INVX3", "INVX4")
DEFAULT_BIASES = (0.0, 0.3, 0.6, 0.9, 1.2)
FIT_BIASES = (0.0, 0.6)
NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"

sys.path.insert(0, str(HERE))
import audit_fit  # noqa: E402
import cap_compensation as cc  # noqa: E402
import cell_parasitics as cp  # noqa: E402
import drive  # noqa: E402
import simulate as sm  # noqa: E402


# Values are deliberately narrow exploratory grids, not process limits.
PARAM_SPECS = {
    "dlc": {"kind": "absolute", "values": (-20e-9, -10e-9, 0.0, 10e-9, 20e-9)},
    "dwc": {"kind": "absolute", "values": (-40e-9, -20e-9, 0.0, 20e-9, 40e-9)},
    "cgsl": {"kind": "scale", "values": (0.5, 1.0, 1.5, 2.0)},
    "cgdl": {"kind": "scale", "values": (0.5, 1.0, 1.5, 2.0)},
    "cf": {"kind": "absolute", "values": (0.0, 1e-11, 2e-11, 5e-11, 1e-10)},
    "cgbo": {"kind": "scale", "values": (0.5, 1.0, 2.0, 4.0)},
    "vfbcv": {"kind": "absolute", "values": (-0.2, 0.0, 0.2, 0.4)},
    "moin": {"kind": "absolute", "values": (10.0, 15.0, 20.0, 30.0)},
    "noff": {"kind": "absolute", "values": (0.5, 0.9, 1.3, 2.0)},
    "voffcv": {"kind": "absolute", "values": (0.0, 0.02, 0.05, 0.1)},
}


def _card_block(cards: str, model_name: str) -> str:
    match = re.search(
        r"\.model\s+%s\s+\w+.*?(?=\.model\s|\Z)"
        % re.escape(model_name),
        cards,
        re.DOTALL,
    )
    if not match:
        raise KeyError("model not found: %s" % model_name)
    return match.group(0)


def _card_value(cards: str, model_name: str, parameter: str):
    block = _card_block(cards, model_name)
    match = re.search(
        r"(?<![A-Za-z0-9_])%s\s*=\s*(%s)"
        % (re.escape(parameter), NUMBER),
        block,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _cards(flavor: str, overrides: Mapping[str, float] | None = None) -> str:
    return cc.model_cards(flavor, overrides, overrides)


def _probe_rows(flavor: str, cells: Sequence[str], biases: Sequence[float],
                overrides: Mapping[str, float] | None = None) -> List[Dict[str, object]]:
    data = drive.load_data(flavor, "fit")
    cards = _cards(flavor, overrides)
    rows = []
    for base_cell in cells:
        key = base_cell + cc.FLAVOR_SUFFIX[flavor]
        entry = data[key]
        inputs = [str(pin) for pin in entry["inputs"]]
        if len(inputs) != 1:
            raise ValueError("expected one input pin for %s" % key)
        pin = inputs[0]
        liberty_pf = float(entry["caps"][pin])
        for bias in biases:
            model_pf = cc.ac_cap_pf(cards, entry, pin, bias_v=bias)
            rows.append({
                "flavor": flavor,
                "cell": base_cell,
                "entry_key": key,
                "pin": pin,
                "bias_v": bias,
                "c_model_pf": model_pf,
                "c_liberty_pf": liberty_pf,
                "model_to_liberty_ratio": model_pf / liberty_pf,
                "log10_ratio": math.log10(model_pf / liberty_pf),
            })
    return rows


def _rms(rows: Iterable[Mapping[str, object]], bias: float | None = None) -> float:
    selected = [
        row for row in rows
        if bias is None or float(row["bias_v"]) == bias
    ]
    if not selected:
        return 1.0e6
    errors = [float(row["log10_ratio"]) for row in selected]
    return math.sqrt(sum(error * error for error in errors) / len(errors))


def _base_value(flavor: str, parameter: str):
    cards = _cards(flavor)
    return _card_value(cards, "nm1p2_%s_lp" % flavor, parameter)


def _candidate_value(flavor: str, parameter: str, value: float) -> float:
    spec = PARAM_SPECS[parameter]
    if spec["kind"] == "scale":
        base = _base_value(flavor, parameter)
        if base is None:
            raise ValueError("cannot scale omitted parameter %s" % parameter)
        return base * value
    return value


def _override(flavor: str, parameter: str, value: float) -> Dict[str, float]:
    return {parameter: _candidate_value(flavor, parameter, value)}


def _support_audit(flavor: str, cell: str) -> Dict[str, object]:
    cards = _cards(flavor)
    data = drive.load_data(flavor, "fit")
    entry = data[cell + cc.FLAVOR_SUFFIX[flavor]]
    safe_values = {
        "dlc": 0.0,
        "dwc": 0.0,
        "cgsl": _base_value(flavor, "cgsl") or 2.653e-10,
        "cgdl": _base_value(flavor, "cgdl") or 2.653e-10,
        "cf": 0.0,
        "cgbo": _base_value(flavor, "cgbo") or 2.56e-11,
        "vfbcv": 0.0,
        "moin": _base_value(flavor, "moin") or 15.0,
        "noff": _base_value(flavor, "noff") or 0.9,
        "voffcv": _base_value(flavor, "voffcv") or 0.02,
    }
    result = {}
    for parameter, value in safe_values.items():
        try:
            measured = cc.ac_cap_pf(
                _cards(flavor, {parameter: value}),
                entry,
                str(entry["inputs"][0]),
                bias_v=0.6,
            )
            result[parameter] = {
                "card_value": _base_value(flavor, parameter),
                "temporary_value": value,
                "xyce_ac_probe": "accepted",
                "probe_cap_pf": measured,
            }
        except Exception as exc:
            result[parameter] = {
                "card_value": _base_value(flavor, parameter),
                "temporary_value": value,
                "xyce_ac_probe": "failed: %s" % exc,
            }
    return result


def _timing_rms(cards: str, flavor: str, cells: Sequence[str]) -> float:
    data = drive.load_data(flavor, "fit")
    points = drive.collect_points(cp.default_library(flavor), flavor, data, cells)
    rows = drive.evaluate(cards, data, points, rc=True)
    if not rows:
        return 1.0e6
    errors = [float(row["log10_ratio"]) for row in rows]
    return math.sqrt(sum(error * error for error in errors) / len(errors))


def _leakage_rms(cards: str, flavor: str, dataset: str) -> float:
    data = drive.load_data(flavor, dataset)
    rows = sm.sim_leakage(
        data,
        cards,
        vdd=1.2,
        temp=25,
        gmin_correct=(flavor != "hvt"),
    )
    return float(audit_fit.metrics(data, rows)["rms_log10"])


def _sweep_parameter(flavor: str, parameter: str, cells: Sequence[str],
                     biases: Sequence[float], validate: bool) -> List[Dict[str, object]]:
    rows = []
    for grid_value in PARAM_SPECS[parameter]["values"]:
        overrides = _override(flavor, parameter, grid_value)
        try:
            probes = _probe_rows(flavor, cells, biases, overrides)
            row = {
                "flavor": flavor,
                "parameter": parameter,
                "grid_value": grid_value,
                "effective_value": overrides[parameter],
                "cv_rms_by_bias": {
                    "%.6g" % bias: _rms(probes, bias)
                    for bias in biases
                },
                "status": "ok",
            }
            if validate:
                cards = _cards(flavor, overrides)
                row["timing_rms_log10"] = _timing_rms(cards, flavor, cells)
                row["leakage_rms_log10"] = _leakage_rms(cards, flavor, "train37")
        except Exception as exc:
            row = {
                "flavor": flavor,
                "parameter": parameter,
                "grid_value": grid_value,
                "effective_value": overrides.get(parameter),
                "status": "error: %s" % exc,
            }
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavors", nargs="+", choices=FLAVORS, default=list(FLAVORS))
    parser.add_argument("--cells", default=",".join(DEFAULT_CELLS))
    parser.add_argument("--biases", default=",".join(str(x) for x in DEFAULT_BIASES))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="also run RC-aware timing and train37 leakage for every candidate",
    )
    args = parser.parse_args()
    cells = tuple(cell.strip() for cell in args.cells.split(",") if cell.strip())
    biases = tuple(float(value.strip()) for value in args.biases.split(",") if value.strip())
    if not cells or not biases:
        parser.error("--cells and --biases must not be empty")
    support = {
        flavor: _support_audit(flavor, cells[0])
        for flavor in args.flavors
    }
    grid = {
        flavor: _probe_rows(flavor, cells, biases)
        for flavor in args.flavors
    }
    sweeps = {
        flavor: {
            parameter: _sweep_parameter(
                flavor, parameter, cells, FIT_BIASES, args.validate,
            )
            for parameter in PARAM_SPECS
        }
        for flavor in args.flavors
    }
    report = {
        "schema_version": 1,
        "kind": "ics55_core_cv_parameter_sweep",
        "model_manifest": str(FITTED),
        "cells": list(cells),
        "biases_v": list(biases),
        "fit_biases_v": list(FIT_BIASES),
        "liberty_target_note": (
            "Liberty provides one cell-boundary input capacitance per pin; it "
            "does not provide a bias-resolved intrinsic C-V curve."
        ),
        "parameter_support": support,
        "baseline_probe_grid": grid,
        "one_at_a_time_sweeps": sweeps,
        "promotion": "none; experiment manifest only",
    }
    args.out.expanduser().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(args.out.expanduser())


if __name__ == "__main__":
    main()
