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

"""Optuna exploratory fit for the ICS55 Xyce leakage deck.

Searches per-device VTH0, DIBL, subthreshold swing, off-floor, and
short-channel parameters.  The default split is data_fit_*.json; pass
--dataset to use any generated data_<split>_<flavor>.json file.  Published
parameters should be rechecked with fit_clean.py in one process.
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import sys

import optuna
from optuna.samplers import TPESampler, RandomSampler, CmaEsSampler, NSGAIISampler

FITDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FITDIR)
import simulate as sm  # noqa: E402

PM = os.path.expanduser("~/Downloads/45nm_LP.pm")

PARAM_SPEC = [
    ("vth0n", 0.55, 1.05),
    ("vth0p", 0.25, 1.05),
    ("dibl_n", 0.02, 1.0),
    ("dibl_p", 0.02, 1.0),
    ("nf_n", 0.5, 1.5),
    ("nf_p", 0.5, 1.5),
    ("voff_n", 0.05, 1.5),
    ("voff_p", 0.05, 1.5),
    ("dvt_n", 0.2, 1.0),
    ("dvt_p", 0.2, 1.0),
]

# Focused subsets (override with --params "vth0n,vth0p,voff_n,voff_p")
PARAM_SETS = {
    "2": ["vth0n", "vth0p"],
    "4": ["vth0n", "vth0p", "nf_n", "nf_p"],
    "4v": ["vth0n", "vth0p", "voff_n", "voff_p"],
    "4d": ["vth0n", "vth0p", "dibl_n", "dibl_p"],
    "6": ["vth0n", "vth0p", "dibl_n", "dibl_p", "voff_n", "voff_p"],
}


def eval_point(data_path, pm, nname, pname, params):
    cards = sm.make_model_cards(
        pm, nname, pname,
        vth0n=params["vth0n"], vth0p=params["vth0p"],
        dibl_scale_n=params["dibl_n"], dibl_scale_p=params["dibl_p"],
        nf_scale_n=params["nf_n"], nf_scale_p=params["nf_p"],
        voff_scale_n=params["voff_n"], voff_scale_p=params["voff_p"],
        dvt_scale_n=params["dvt_n"], dvt_scale_p=params["dvt_p"])
    data = json.load(open(data_path))
    res = sm.sim_leakage(data, cards)
    bycell = {}
    for (_, cell, si, meas, sim) in res:
        if sim is None:
            return None
        bycell.setdefault(cell, []).append((meas, sim))
    errs = []
    for cell in bycell:
        rows = bycell[cell]
        m = sum(r[0] for r in rows) / len(rows)
        s = sum(max(r[1], 1e-9) for r in rows) / len(rows)
        errs.append(math.log10(s / m))
    rms = math.sqrt(sum(e * e for e in errs) / len(errs))
    return rms, max(abs(e) for e in errs)


def make_study(sampler_name, seed):
    if sampler_name == "nsgaii":
        return optuna.create_study(
            directions=["minimize", "minimize"],
            sampler=NSGAIISampler(seed=seed, population_size=24))
    if sampler_name == "tpe":
        sampler = TPESampler(seed=seed)
    elif sampler_name == "random":
        sampler = RandomSampler(seed=seed)
    elif sampler_name == "cmaes":
        sampler = CmaEsSampler(seed=seed)
    else:
        raise ValueError(sampler_name)
    return optuna.create_study(sampler=sampler, direction="minimize")


def suggest_params(trial, names=None):
    p = {}
    spec = {n: (lo, hi) for n, lo, hi in PARAM_SPEC}
    for name, (lo, hi) in spec.items():
        if names is not None and name not in names:
            p[name] = 1.0   # identity: PTM base card unchanged
            continue
        p[name] = trial.suggest_float(name, lo, hi)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("flavor", choices=["svt", "lvt", "hvt"])
    ap.add_argument("--sampler", default="tpe",
                    choices=["tpe", "random", "cmaes", "nsgaii"])
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--params", default=None,
                    help="comma list of params to search (e.g. 2,4,6 or names)")
    ap.add_argument("--dataset", default="fit",
                    help="split name used in data_<split>_<flavor>.json")
    a = ap.parse_args()
    names = None
    if a.params:
        if a.params in PARAM_SETS:
            names = PARAM_SETS[a.params]
        else:
            names = [x.strip() for x in a.params.split(",")]

    data_path = os.path.join(FITDIR, "data_%s_%s.json" % (a.dataset, a.flavor))
    nname = "nm1p2_%s_lp" % a.flavor
    pname = "pm1p2_%s_lp" % a.flavor
    study = make_study(a.sampler, a.seed)
    multi = a.sampler == "nsgaii"

    pool = cf.ProcessPoolExecutor(max_workers=a.workers)
    pending = {}

    def launch():
        trial = study.ask()
        p = suggest_params(trial, names)
        trial.set_user_attr("params", p)
        fut = pool.submit(eval_point, data_path, PM, nname, pname, p)
        pending[fut] = (trial, p)
        return trial

    def collect():
        done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
        for fut in done:
            trial, p = pending.pop(fut)
            try:
                r = fut.result()
            except Exception as e:
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                print("trial failed:", e)
                continue
            if r is None:
                study.tell(trial, state=optuna.trial.TrialState.FAIL)
                continue
            rms, maxerr = r
            study.tell(trial, [rms, maxerr] if multi else rms)
            print("%-6s trial %4d vn=%.3f vp=%.3f dn=%.2f dp=%.2f "
                  "nfN=%.2f rms=%.4f maxerr=%.4f"
                  % (a.flavor, trial.number, p["vth0n"], p["vth0p"],
                     p["dibl_n"], p["dibl_p"], p["nf_n"], rms, maxerr),
                  flush=True)

    n = a.trials
    try:
        while len(pending) < a.workers and n > 0:
            launch()
            n -= 1
        while pending:
            collect()
            while len(pending) < a.workers and n > 0:
                launch()
                n -= 1
    finally:
        pool.shutdown(wait=False)

    if multi:
        trials = sorted(study.best_trials, key=lambda t: t.values[0])
        best = trials[0]
        vals = best.values
    else:
        best = study.best_trial
        vals = [best.value]
    p = best.user_attrs.get("params") or best.params
    print("BEST(%s,%s) vth0n=%.4f vth0p=%.4f dibl_n=%.3f dibl_p=%.3f "
          "nf_n=%.3f nf_p=%.3f voff_n=%.2f voff_p=%.2f dvt_n=%.2f dvt_p=%.2f "
          "rms=%.4f maxerr=%.4f"
          % (a.flavor, a.sampler, p["vth0n"], p["vth0p"], p["dibl_n"],
             p["dibl_p"], p["nf_n"], p["nf_p"], p["voff_n"], p["voff_p"],
             p["dvt_n"], p["dvt_p"], vals[0],
             vals[1] if len(vals) > 1 else float("nan")))


if __name__ == "__main__":
    main()
