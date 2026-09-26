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

"""Audit staged drive-fit candidates on fit and disjoint inverter cells."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import drive  # noqa: E402
import fit_drive as fd  # noqa: E402
import fit_expanded as fx  # noqa: E402
import simulate as sm  # noqa: E402

FLAVORS = ("svt", "lvt", "hvt")
CELL_SETS = {
    "fit": ("INVX1", "INVX3", "INVX4"),
    "train37": ("INVX1", "INVX3", "INVX4"),
    "holdout": ("INVX2", "INVX5"),
    "holdout2": ("INVX20",),
}


def _cards(flavor, values, start):
    n, p = fd.overrides(start, flavor, values)
    legacy = fx.legacy_values(start, flavor)
    return sm.make_model_cards(
        fx.PM, "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
        vth0n=legacy["vth0n"], vth0p=legacy["vth0p"],
        dibl_scale_n=legacy["dibl_n"], dibl_scale_p=legacy["dibl_p"],
        voff_scale_n=legacy["voff_n"], voff_scale_p=legacy["voff_p"],
        overrides_n=n, overrides_p=p,
    )

def _timing_rms(cards, flavor, data, cells, rc_enabled=False):
    points = drive.collect_points(fd._library(flavor), flavor, data, cells)
    rows = drive.evaluate(cards, data, points, rc=rc_enabled)
    errors = [row["log10_ratio"] for row in rows]
    return math.sqrt(sum(x * x for x in errors) / len(errors)), rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--datasets", default="fit,holdout,holdout2")
    parser.add_argument("--fitted", default=str(HERE.parent / "fitted" / "FIT_PARAMS.json"))
    parser.add_argument("--rc", action="store_true",
                        help="include manually assigned GDS M1 signal RC")
    args = parser.parse_args()
    results = json.loads(Path(args.results).expanduser().read_text())
    start = fx.load_fit_start(Path(args.fitted).expanduser())
    rc_enabled = args.rc or any(
        bool(row.get("rc_enabled")) for row in results.values()
    )
    baseline = {name: 1.0 for name in fd.DRIVE_SPECS}
    report = {"rc_enabled": rc_enabled}
    for flavor in FLAVORS:
        report[flavor] = {}
        candidate_cards = _cards(flavor, results[flavor]["values"], start)
        baseline_cards = _cards(flavor, baseline, start)
        for dataset in [x for x in args.datasets.split(",") if x]:
            data = drive.load_data(flavor, dataset)
            cells = CELL_SETS[dataset]
            candidate_drive, candidate_rows = _timing_rms(
                candidate_cards, flavor, data, cells, rc_enabled)
            baseline_drive, _ = _timing_rms(
                baseline_cards, flavor, data, cells, rc_enabled)
            candidate_leak = fx.leakage_rms(
                data, fx.leakage_rows(flavor, data, candidate_cards))
            baseline_leak = fx.leakage_rms(
                data, fx.leakage_rows(flavor, data, baseline_cards))
            report[flavor][dataset] = {
                "cells": list(cells),
                "baseline_drive_rms": baseline_drive,
                "candidate_drive_rms": candidate_drive,
                "baseline_leakage_rms": baseline_leak,
                "candidate_leakage_rms": candidate_leak,
                "candidate_timing": candidate_rows,
            }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
