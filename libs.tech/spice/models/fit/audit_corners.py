#!/usr/bin/env python3
"""Audit TT-fitted cards against released non-TT Liberty corners."""
import argparse
import copy
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract_data  # noqa: E402
import simulate as sm  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "../../../.."))
BASE = os.path.join(ROOT, "IP", "STD_cell", "ics55_LLSC_H7C_V1p10C100")
TAGS = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}
CORNERS = {
    "ss_1p2_m40": (1.20, -40, "ss_rcworst_1p2_m40"),
    "ss_1p08_m40": (1.08, -40, "ss_cworst_1p08_m40"),
    "ss_1p08_125": (1.08, 125, "ss_rcworst_1p08_125"),
    "ff_1p32_m40": (1.32, -40, "ff_rcbest_1p32_m40"),
    "ff_1p08_125": (1.08, 125, "ff_rcbest_1p08_125"),
    "ff_1p32_125": (1.32, 125, "ff_cbest_1p32_125"),
}


def corner_data(flavor, stem):
    tag = TAGS[flavor]
    base_data = json.load(open(os.path.join(HERE, "data_fit_%s.json" % flavor)))
    lib_path = os.path.join(
        BASE, "ics55_LLSC_%s" % tag, "liberty",
        "ics55_LLSC_%s_%s_nldm.lib" % (tag, stem))
    liberty = extract_data.parse_liberty(lib_path)
    result = {}
    for name, entry in base_data.items():
        if name not in liberty:
            continue
        out = copy.deepcopy(entry)
        out.update({key: liberty[name][key]
                    for key in ("inputs", "caps", "states", "cell_leak")})
        result[name] = out
    return result


def score(data, rows):
    by_cell = {}
    for _, cell, _, measured, simulated in rows:
        if simulated is None or measured <= 0:
            raise RuntimeError("missing or non-positive leakage for %s" % cell)
        by_cell.setdefault(cell, []).append((measured, simulated))
    errors = []
    for values in by_cell.values():
        measured = sum(x for x, _ in values) / len(values)
        simulated = sum(y for _, y in values) / len(values)
        errors.append(math.log10(simulated / measured))
    return math.sqrt(sum(x * x for x in errors) / len(errors))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=os.path.join(
        HERE, "..", "fitted", "FIT_PARAMS.json"))
    args = ap.parse_args()
    manifest = json.load(open(os.path.abspath(args.params)))
    params = manifest.get("flavors", manifest)
    report = {}
    for flavor in ("svt", "lvt", "hvt"):
        p = params[flavor]["params"]
        cards = sm.make_model_cards(
            os.path.expanduser("~/Downloads/45nm_LP.pm"),
            "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
            vth0n=p["vth0n"], vth0p=p["vth0p"],
            dibl_scale_n=p["dibl_n"], dibl_scale_p=p["dibl_p"],
            voff_scale_n=p["voff_n"], voff_scale_p=p["voff_p"])
        report[flavor] = {}
        for name, (vdd, temp, stem) in CORNERS.items():
            data = corner_data(flavor, stem)
            rows = sm.sim_leakage(
                data, cards, vdd=vdd, temp=temp,
                gmin_correct=(flavor != "hvt"))
            report[flavor][name] = {
                "cells": len(data), "vdd": vdd, "temp_c": temp,
                "rms_log10": score(data, rows),
            }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
