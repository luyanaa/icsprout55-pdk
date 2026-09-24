#!/usr/bin/env python3
"""Audit fitted leakage cards on a named extracted-data split.

The fit objective is RMS of log10(simulated/measured) after averaging states
within each cell.  This script also reports arithmetic relative error, which
must not be confused with the log-space RMS factor.
"""
import argparse
import json
import math
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import simulate as sm  # noqa: E402


def metrics(data, rows):
    by_cell = {}
    for _, cell, _, measured, simulated in rows:
        if simulated is None or measured <= 0:
            raise RuntimeError("missing or non-positive leakage for %s" % cell)
        by_cell.setdefault(cell, []).append((measured, simulated))
    ratios = []
    abs_relative = []
    for values in by_cell.values():
        measured = sum(x for x, _ in values) / len(values)
        simulated = sum(y for _, y in values) / len(values)
        ratios.append(simulated / measured)
        abs_relative.append(abs(simulated / measured - 1.0))
    log_errors = [math.log10(x) for x in ratios]
    rms = math.sqrt(sum(x * x for x in log_errors) / len(log_errors))
    ratios_sorted = sorted(ratios)
    abs_sorted = sorted(abs_relative)
    mid = len(ratios_sorted) // 2
    median_ratio = ratios_sorted[mid] if len(ratios_sorted) % 2 else (
        ratios_sorted[mid - 1] + ratios_sorted[mid]
    ) / 2
    median_abs = abs_sorted[mid] if len(abs_sorted) % 2 else (
        abs_sorted[mid - 1] + abs_sorted[mid]
    ) / 2
    return {
        "cells": len(ratios),
        "states": len(rows),
        "rms_log10": rms,
        "multiplicative_rms_factor": 10 ** rms,
        "geometric_mean_ratio": 10 ** (sum(log_errors) / len(log_errors)),
        "mean_ratio": sum(ratios) / len(ratios),
        "mean_abs_relative_error": sum(abs_relative) / len(abs_relative),
        "median_abs_relative_error": median_abs,
        "max_factor": max(max(ratios), 1 / min(ratios)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fit",
                    help="split name in data_<split>_<flavor>.json")
    ap.add_argument("--params", default=os.path.join(
        HERE, "..", "fitted", "FIT_PARAMS.json"))
    ap.add_argument("--vdd", type=float, default=1.2)
    ap.add_argument("--temp", type=float, default=25.0)
    args = ap.parse_args()
    params = json.load(open(os.path.abspath(args.params)))
    fit_params = params.get("flavors", params)
    report = {}
    for flavor in ("svt", "lvt", "hvt"):
        data = json.load(open(os.path.join(HERE,
                                           "data_%s_%s.json" %
                                           (args.dataset, flavor))))
        p = fit_params[flavor]["params"]
        cards = sm.make_model_cards(
            os.path.expanduser("~/Downloads/45nm_LP.pm"),
            "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
            vth0n=p["vth0n"], vth0p=p["vth0p"],
            dibl_scale_n=p["dibl_n"], dibl_scale_p=p["dibl_p"],
            voff_scale_n=p["voff_n"], voff_scale_p=p["voff_p"])
        rows = sm.sim_leakage(
            data, cards, vdd=args.vdd, temp=args.temp,
            gmin_correct=(flavor != "hvt"))
        report[flavor] = metrics(data, rows)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
