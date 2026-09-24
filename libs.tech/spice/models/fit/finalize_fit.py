#!/usr/bin/env python3
"""Finalize and robustness-check a six-parameter leakage fit.

This legacy exploratory runner now uses data_fit_*.json by default, not the
historical split containing unstable sequential/pass-gate states.  Published
numbers should be regenerated with fit_clean.py and audit_fit.py.
"""
import concurrent.futures as cf
import json
import math
import os
import sys

import optuna
from optuna.samplers import TPESampler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_optuna as fo

PARAM6 = ["vth0n", "vth0p", "dibl_n", "dibl_p", "voff_n", "voff_p"]
PERT = 0.05


def main():
    flavor = sys.argv[1]
    data_path = os.path.join(fo.FITDIR, "data_fit_%s.json" % flavor)
    nname = "nm1p2_%s_lp" % flavor
    pname = "pm1p2_%s_lp" % flavor

    study = optuna.create_study(sampler=TPESampler(seed=42), direction="minimize")
    pool = cf.ProcessPoolExecutor(max_workers=6)
    pending = {}

    def launch():
        t = study.ask()
        p = fo.suggest_params(t, PARAM6)
        t.set_user_attr("params", p)
        pending[pool.submit(fo.eval_point, data_path, fo.PM, nname, pname, p)] = t

    def drain(block=True):
        while pending and (block or len(pending) >= 6):
            done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
            for f in done:
                t = pending.pop(f)
                try:
                    r = f.result()
                except Exception:
                    study.tell(t, state=optuna.trial.TrialState.FAIL)
                    continue
                if r is None:
                    study.tell(t, state=optuna.trial.TrialState.FAIL)
                else:
                    study.tell(t, r[0])

    n = 400
    while len(pending) < 6 and n > 0:
        launch(); n -= 1
    while pending:
        drain()
        while len(pending) < 6 and n > 0:
            launch(); n -= 1
    pool.shutdown()

    trials = sorted(study.trials, key=lambda t: t.value if t.value is not None else 1e9)
    top = [t for t in trials[:12] if t.value is not None]
    print("%s top-12 rms: %s" % (flavor, [round(t.value, 3) for t in top]))

    # robustness: worst rms under +/-5% per-param perturbations
    def eval_pert(p, idx=None):
        base = fo.eval_point(data_path, fo.PM, nname, pname, p)
        if base is None:
            return None
        worst = base[0]
        for k in PARAM6:
            for f in (1 - PERT, 1 + PERT):
                q = dict(p)
                q[k] = p[k] * f
                r = fo.eval_point(data_path, fo.PM, nname, pname, q)
                if r is not None:
                    worst = max(worst, r[0])
        return worst

    best_robust = None
    for t in top:
        p = t.user_attrs["params"]
        w = eval_pert(p)
        print("  trial %3d rms=%.4f  worst@5%%pert=%.4f  vn=%.4f vp=%.4f dn=%.3f dp=%.3f von=%.2f vop=%.2f"
              % (t.number, t.value, w, p["vth0n"], p["vth0p"], p["dibl_n"],
                 p["dibl_p"], p["voff_n"], p["voff_p"]))
        if best_robust is None or (w is not None and w < best_robust[0]):
            best_robust = (w, p)
    print("ROBUST BEST %s: worst@5%%=%.4f params=%s" % (flavor, best_robust[0],
          {k: round(v, 4) for k, v in best_robust[1].items()}))


if __name__ == "__main__":
    main()
