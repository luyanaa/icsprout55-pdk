#!/usr/bin/env python3
"""Explore model-level junction and overlap capacitance changes.

This is an audit tool, not a promotion path.  It sweeps CJSWGS/CJSWGD and
CGSO/CGDO on temporary Xyce cards, reports AC input-capacitance ratios and
RC-aware inverter timing RMS, and never edits FIT_PARAMS.json or the rendered
core model.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
FITTED = HERE.parent / "fitted" / "FIT_PARAMS.json"
FLAVORS = ("svt", "lvt", "hvt")
DEFAULT_CELLS = ("INVX1", "INVX3", "INVX4")
DEFAULT_CJSW_SCALES = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0)
DEFAULT_CG_VALUES = (
    1.10e-10,
    1.25e-10,
    1.30e-10,
    1.35e-10,
    1.50e-10,
    1.80e-10,
)

import cap_compensation as cc  # noqa: E402
import cell_parasitics as cp  # noqa: E402
import drive  # noqa: E402
import audit_fit  # noqa: E402
import simulate as sm  # noqa: E402

import audit_geometry  # noqa: E402

NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"


def _parse_float_list(value: str) -> List[float]:
    return [float(token.strip()) for token in value.split(",") if token.strip()]


def _model_value(cards: str, model_name: str, parameter: str) -> float:
    match = re.search(
        r"\.model\s+%s\s+\w+.*?(?=\.model\s|\Z)" % re.escape(model_name),
        cards,
        re.DOTALL,
    )
    if not match:
        raise ValueError("model not found: %s" % model_name)
    value = re.search(
        r"(?<![A-Za-z0-9_])%s\s*=\s*(%s)" % (re.escape(parameter), NUMBER),
        match.group(0),
        re.IGNORECASE,
    )
    if not value:
        raise ValueError("parameter not found: %s" % parameter)
    return float(value.group(1))


def _timing_rms(cards: str, flavor: str, cells: Sequence[str]) -> float:
    data = drive.load_data(flavor, "fit")
    points = drive.collect_points(
        cp.default_library(flavor), flavor, data, cells,
    )
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



def _input_ratios(cards: str, flavor: str,
                  cells: Sequence[str]) -> Dict[str, float]:
    data = drive.load_data(flavor, "fit")
    result = {}
    for cell in cells:
        key = cell + cc.FLAVOR_SUFFIX[flavor]
        entry = data[key]
        pins = [str(pin) for pin in entry["inputs"]]
        if len(pins) != 1:
            raise ValueError("expected one input pin for %s" % key)
        model_pf = cc.ac_cap_pf(cards, entry, pins[0])
        liberty_pf = float(entry["caps"][pins[0]])
        result[cell] = model_pf / liberty_pf
    return result


def _sidewall_rows(flavor: str, cells: Sequence[str], scales: Iterable[float],
                   leakage_dataset: str | None):
    base_cards = cc.model_cards(flavor)
    cjswgs = _model_value(base_cards, "nm1p2_%s_lp" % flavor, "cjswgs")
    cjswgd = _model_value(base_cards, "nm1p2_%s_lp" % flavor, "cjswgd")
    rows = []
    for axis in ("both", "cjswgs", "cjswgd"):
        for scale in scales:
            overrides_n = {
                "cjswgs": cjswgs * (scale if axis in {"both", "cjswgs"} else 1.0),
                "cjswgd": cjswgd * (scale if axis in {"both", "cjswgd"} else 1.0),
            }
            cards = cc.model_cards(flavor, overrides_n, overrides_n)
            try:
                timing = _timing_rms(cards, flavor, cells)
                leakage = (
                    _leakage_rms(cards, flavor, leakage_dataset)
                    if leakage_dataset else None
                )
                status = "ok"
            except Exception as exc:  # record a failed candidate, do not hide it
                timing = None
                leakage = None
                status = "error: %s" % exc
            rows.append({
                "flavor": flavor,
                "axis": axis,
                "scale": scale,
                "cjswgs_f_per_m": overrides_n["cjswgs"],
                "cjswgd_f_per_m": overrides_n["cjswgd"],
                "timing_rms_log10": timing,
                "leakage_dataset": leakage_dataset,
                "leakage_rms_log10": leakage,
                "status": status,
            })
    return rows


def _overlap_rows(flavor: str, cells: Sequence[str], values: Iterable[float],
                  leakage_dataset: str | None):
    rows = []
    for value in values:
        overrides = {"cgso": value, "cgdo": value}
        cards = cc.model_cards(flavor, overrides, overrides)
        try:
            ratios = _input_ratios(cards, flavor, cells)
            timing = _timing_rms(cards, flavor, cells)
            leakage = (
                _leakage_rms(cards, flavor, leakage_dataset)
                if leakage_dataset else None
            )
            status = "ok"
        except Exception as exc:
            ratios = {}
            timing = None
            leakage = None
            status = "error: %s" % exc
        rows.append({
            "flavor": flavor,
            "cgso_f_per_m": value,
            "cgdo_f_per_m": value,
            "model_to_liberty_input_cap_ratio": ratios,
            "timing_rms_log10": timing,
            "leakage_dataset": leakage_dataset,
            "leakage_rms_log10": leakage,
            "status": status,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavors", nargs="+", choices=FLAVORS, default=list(FLAVORS))
    parser.add_argument("--cells", default=",".join(DEFAULT_CELLS))
    parser.add_argument("--cjsw-scales", default="")
    parser.add_argument("--cg-values", default="")
    parser.add_argument(
        "--leakage-dataset",
        choices=("train37", "holdout2"),
        help="also run the full Xyce leakage audit for every temporary candidate",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cells = tuple(cell.strip() for cell in args.cells.split(",") if cell.strip())
    if not cells:
        parser.error("--cells must contain at least one cell")
    scales = (
        _parse_float_list(args.cjsw_scales)
        if args.cjsw_scales
        else list(DEFAULT_CJSW_SCALES)
    )
    cg_values = (
        _parse_float_list(args.cg_values)
        if args.cg_values
        else list(DEFAULT_CG_VALUES)
    )
    gds = audit_geometry.audit()["gds"]
    report = {
        "schema_version": 1,
        "kind": "ics55_model_capacitance_sweep",
        "model_manifest": str(FITTED),
        "cells": list(cells),
        "leakage_dataset": args.leakage_dataset,
        "geometry_evidence": {
            "representative_cell": gds["cell"],
            "non_gate_diffusion_extension_area_um2": (
                gds["nonzero_source_drain_extension_area_um2"]
            ),
            "terminal_assignment": "unassigned_without_LVS",
        },
        "flavors": {},
    }
    for flavor in args.flavors:
        report["flavors"][flavor] = {
            "sidewall_sweep": _sidewall_rows(
                flavor, cells, scales, args.leakage_dataset,
            ),
            "overlap_sweep": _overlap_rows(
                flavor, cells, cg_values, args.leakage_dataset,
            ),
        }
    args.out.expanduser().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(args.out.expanduser())


if __name__ == "__main__":
    main()
