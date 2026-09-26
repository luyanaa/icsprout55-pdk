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

"""Fit a small BSIM4 drive subset against released Liberty timing points.

The leakage fit and this transient timing fit are staged.  The timing objective
uses inverter rise/fall delays at a fixed Liberty slew/load point and reports
leakage again for an independent promotion decision; it is not a replacement
for measured Id-Vg/Id-Vd extraction.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, Mapping, Tuple

import optuna
from optuna.samplers import TPESampler

FITDIR = Path(__file__).resolve().parent
ROOT = FITDIR.parents[3]
sys.path.insert(0, str(FITDIR))
import drive  # noqa: E402
import fit_expanded as fx  # noqa: E402
import simulate as sm  # noqa: E402

FLAVORS = ("svt", "lvt", "hvt")
LIB_DIR = ROOT / "libs.ref"
FLAVOR_TAG = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}
DRIVE_CELLS = ("INVX1", "INVX3", "INVX4")
DRIVE_SPECS = {
    "u0_n": (0.50, 2.00, 0.20),
    "u0_p": (0.50, 2.00, 0.20),
    "vsat_n": (0.75, 1.35, 0.15),
    "vsat_p": (0.75, 1.35, 0.15),
    "rdsw_n": (0.50, 2.00, 0.25),
    "rdsw_p": (0.50, 2.00, 0.25),
}
DRIVE_PRIOR_PARAM = {
    "u0": "u0",
    "vsat": "vsat",
    "rdsw": "rdsw",
}


def _library(flavor: str) -> Path:
    tag = FLAVOR_TAG[flavor]
    return LIB_DIR / ("ics55_LLSC_%s" % tag) / "liberty" / (
        "ics55_LLSC_%s_typ_tt_1p2_25_nldm.lib" % tag)


def _start_device(start, flavor: str, typ: str):
    return dict(start["flavors"][flavor]["devices"][typ])


def overrides(start: Mapping[str, object], flavor: str,
              values: Mapping[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    n_base = _start_device(start, flavor, "nmos")
    p_base = _start_device(start, flavor, "pmos")
    n: Dict[str, float] = {}
    p: Dict[str, float] = {}
    for base, target, prefix in (
            (n_base, n, "n"), (p_base, p, "p")):
        for parameter in ("u0", "vsat", "rdsw"):
            scale = values["%s_%s" % (parameter, prefix)]
            if scale != 1.0:
                target[parameter] = base[parameter] * scale
    return n, p


def suggest(trial: optuna.Trial, active_names):
    values = {}
    for name, (lo, hi, _) in DRIVE_SPECS.items():
        values[name] = (trial.suggest_float(name, lo, hi)
                        if name in active_names else 1.0)
    return values


def _source_scale(initial, start, flavor: str, name: str) -> float:
    family, prefix = name.rsplit("_", 1)
    typ = "nmos" if prefix == "n" else "pmos"
    parameter = DRIVE_PRIOR_PARAM[family]
    source = initial["flavors"][flavor]["devices"][typ]["initial"][parameter]
    base = _start_device(start, flavor, typ)[parameter]
    if abs(source) < 1e-12 or abs(base) < 1e-12 or source * base <= 0:
        return 1.0
    return abs(source / base)


def prior_penalty(values, active_names, initial, start, flavor: str) -> float:
    terms = []
    for name in active_names:
        _, _, sigma = DRIVE_SPECS[name]
        center = _source_scale(initial, start, flavor, name)
        terms.append(math.log(values[name] / center) / sigma)
    return math.sqrt(sum(x * x for x in terms) / len(terms))

def fit_one(flavor: str, dataset: str, initial, start, trials: int,
            seed: int, active_names, leakage_weight: float,
            rc_enabled: bool):
    data = drive.load_data(flavor, dataset)
    leakage_data = drive.load_data(flavor, "train37")
    points = drive.collect_points(_library(flavor), flavor, data, DRIVE_CELLS)
    legacy = fx.legacy_values(start, flavor)
    study = optuna.create_study(direction="minimize",
                                sampler=TPESampler(seed=seed))
    study.enqueue_trial({name: 1.0 for name in DRIVE_SPECS})

    def objective(trial):
        values = suggest(trial, active_names)
        try:
            n, p = overrides(start, flavor, values)
            cards = sm.make_model_cards(
                fx.PM, "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
                vth0n=legacy["vth0n"], vth0p=legacy["vth0p"],
                dibl_scale_n=legacy["dibl_n"], dibl_scale_p=legacy["dibl_p"],
                voff_scale_n=legacy["voff_n"], voff_scale_p=legacy["voff_p"],
                overrides_n=n, overrides_p=p,
            )
            timing = drive.evaluate(cards, data, points, rc=rc_enabled)
            drive_errors = [row["log10_ratio"] for row in timing]
            drive_rms = math.sqrt(sum(x * x for x in drive_errors) /
                                  len(drive_errors))
            leakage_rows = fx.leakage_rows(flavor, leakage_data, cards)
            leakage_rms = fx.leakage_rms(leakage_data, leakage_rows)
        except (RuntimeError, ValueError, KeyError, OSError):
            return 1e6
        penalty = prior_penalty(values, active_names, initial, start, flavor)
        # Timing is the new signal.  Leakage is a guardrail, and the source
        # interpolation is a weaker prior than either observed objective.
        total = math.sqrt(
            drive_rms * drive_rms + leakage_weight * leakage_rms * leakage_rms
            + 0.002 * penalty * penalty)
        trial.set_user_attr("drive_rms", drive_rms)
        trial.set_user_attr("leakage_rms", leakage_rms)
        trial.set_user_attr("prior_penalty", penalty)
        return total

    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    best = dict(study.best_trial.params)
    best.update({name: best.get(name, 1.0) for name in DRIVE_SPECS})
    n, p = overrides(start, flavor, best)
    cards = sm.make_model_cards(
        fx.PM, "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
        vth0n=legacy["vth0n"], vth0p=legacy["vth0p"],
        dibl_scale_n=legacy["dibl_n"], dibl_scale_p=legacy["dibl_p"],
        voff_scale_n=legacy["voff_n"], voff_scale_p=legacy["voff_p"],
        overrides_n=n, overrides_p=p,
    )
    timing = drive.evaluate(cards, data, points, rc=rc_enabled)
    drive_errors = [row["log10_ratio"] for row in timing]
    drive_rms = math.sqrt(sum(x * x for x in drive_errors) / len(drive_errors))
    leakage_rms = fx.leakage_rms(leakage_data, fx.leakage_rows(
        flavor, leakage_data, cards))
    penalty = prior_penalty(best, active_names, initial, start, flavor)
    total = math.sqrt(drive_rms * drive_rms + leakage_weight * leakage_rms * leakage_rms
                      + 0.002 * penalty * penalty)
    return {
        "dataset": dataset,
        "leakage_dataset": "train37",
        "base_model": fx.PM,
        "rc_enabled": rc_enabled,
        "gmin_correct": fx.GMIN_CORRECT_BY_FLAVOR[flavor],
        "gmin_policy": (
            "subtract Xyce gmin floor"
            if fx.GMIN_CORRECT_BY_FLAVOR[flavor]
            else "retain raw Xyce current; correction produced negative HVT currents"
        ),
        "objective": "sqrt(drive_rms^2 + %.4g*leakage_rms^2 + 0.002*source_prior_penalty^2)" % leakage_weight,
        "leakage_weight": leakage_weight,
        "drive_cells": list(DRIVE_CELLS),
        "drive_points": points,
        "active_parameters": list(active_names),
        "values": best,
        "total": total,
        "drive_rms": drive_rms,
        "leakage_rms": leakage_rms,
        "prior_penalty": penalty,
        "timing": timing,
        "trials": trials,
        "seed": seed,
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("flavor", choices=FLAVORS, nargs="+")
    parser.add_argument("--dataset", default="fit")
    parser.add_argument("--initial", default=str(FITDIR / "INITIAL_VALUES.json"))
    parser.add_argument("--fitted", default=str(FITDIR.parent / "fitted" / "FIT_PARAMS.json"))
    parser.add_argument("--trials", type=int, default=24)
    parser.add_argument("--seed", type=int, default=311)
    parser.add_argument("--leakage-weight", type=float, default=0.25)
    parser.add_argument("--rc", action="store_true",
                        help="include manually assigned GDS M1 signal RC")
    parser.add_argument("--params", default=",")
    parser.add_argument("--out", default="drive_fit_results.json")
    args = parser.parse_args()
    initial = fx.load_initial(Path(args.initial).expanduser())
    start = fx.load_fit_start(Path(args.fitted).expanduser())
    active = list(DRIVE_SPECS) if args.params in ("", ",") else [
        x for x in args.params.split(",") if x]
    unknown = set(active) - set(DRIVE_SPECS)
    if unknown:
        raise SystemExit("unknown drive parameters: %s" % ", ".join(sorted(unknown)))
    result = {}
    for offset, flavor in enumerate(args.flavor):
        row = fit_one(
            flavor, args.dataset, initial, start, args.trials,
            args.seed + 2 * offset, active, args.leakage_weight,
            args.rc,
        )
        result[flavor] = row
        print(flavor, "total=%.6f drive=%.6f leakage=%.6f prior=%.6f" %
              (row["total"], row["drive_rms"], row["leakage_rms"],
               row["prior_penalty"]), flush=True)
        print("  ", {k: round(v, 6) for k, v in row["values"].items()})
    Path(args.out).expanduser().write_text(json.dumps(result, indent=2) + "\n")
    print(Path(args.out).expanduser())


if __name__ == "__main__":
    main()
