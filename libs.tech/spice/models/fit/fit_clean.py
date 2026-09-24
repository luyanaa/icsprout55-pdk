#!/usr/bin/env python3
"""Deterministic in-process leakage fit for the corrected Xyce deck.

The default split is data_fit_*.json: 17 stable combinational cells at
1.2 V/25 C.  Pass --dataset to fit another generated split.  The runner
keeps fitting and verification in one process, avoiding stale imports and
cross-process simulator state.
"""
import argparse
import json
import math
import os
import sys

import optuna
from optuna.samplers import TPESampler

FITDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FITDIR)
import simulate as sm  # noqa: E402

PM = os.path.expanduser("~/Downloads/45nm_LP.pm")
NAMES = ["vth0n", "vth0p", "dibl_n", "dibl_p", "voff_n", "voff_p"]


def suggest(trial):
    return {
        "vth0n": trial.suggest_float("vth0n", 0.55, 1.05),
        "vth0p": trial.suggest_float("vth0p", 0.25, 1.05),
        "dibl_n": trial.suggest_float("dibl_n", 0.02, 1.0),
        "dibl_p": trial.suggest_float("dibl_p", 0.02, 1.0),
        "voff_n": trial.suggest_float("voff_n", 0.05, 1.5),
        "voff_p": trial.suggest_float("voff_p", 0.05, 1.5),
    }


def score(data, flavor, params, vdd=1.2, temp=25):
    cards = sm.make_model_cards(
        PM, f"nm1p2_{flavor}_lp", f"pm1p2_{flavor}_lp",
        vth0n=params["vth0n"], vth0p=params["vth0p"],
        dibl_scale_n=params["dibl_n"], dibl_scale_p=params["dibl_p"],
        voff_scale_n=params["voff_n"], voff_scale_p=params["voff_p"],
    )
    result = sm.sim_leakage(data, cards, vdd=vdd, temp=temp)
    by_cell = {}
    for (_, cell, _, measured, simulated) in result:
        if simulated is None or measured <= 0:
            return 1e9
        by_cell.setdefault(cell, []).append((measured, max(simulated, 1e-15)))
    errors = []
    for rows in by_cell.values():
        measured = sum(x for x, _ in rows) / len(rows)
        simulated = sum(x for _, x in rows) / len(rows)
        errors.append(math.log10(simulated / measured))
    return math.sqrt(sum(x * x for x in errors) / len(errors))


def fit(flavor, trials, seed, dataset):
    path = os.path.join(FITDIR, f"data_{dataset}_{flavor}.json")
    data = json.load(open(path))
    study = optuna.create_study(direction="minimize", sampler=TPESampler(seed=seed))
    study.optimize(lambda trial: score(data, flavor, suggest(trial)),
                   n_trials=trials, show_progress_bar=False)
    params = dict(study.best_trial.params)
    verification = [score(data, flavor, params) for _ in range(3)]
    return params, verification


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("flavor", choices=["svt", "lvt", "hvt"], nargs="+")
    ap.add_argument("--dataset", default="fit",
                    help="data split name used in data_<dataset>_<flavor>.json")
    ap.add_argument("--trials", type=int, default=250)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--out", default="fit_clean_results.json")
    args = ap.parse_args()
    result = {}
    for offset, flavor in enumerate(args.flavor):
        params, verification = fit(flavor, args.trials, args.seed + 2 * offset,
                                   args.dataset)
        result[flavor] = {"dataset": args.dataset, "params": params,
                          "rms": verification[-1],
                          "verification": verification}
        print(flavor, "rms", [round(x, 6) for x in verification],
              "params", {k: round(v, 6) for k, v in params.items()}, flush=True)
    with open(args.out, "w") as stream:
        json.dump(result, stream, indent=2)


if __name__ == "__main__":
    main()

