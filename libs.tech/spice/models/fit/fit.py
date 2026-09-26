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

"""Fit VTH0 (N and P) of a PTM BSIM4 candidate to the ICS55 digital-cell
leakage data.

Minimizes RMS of log10(simulated/measured) over all (cell, input-state)
leakages, by coordinate gradient descent on (vth0n, vth0p) using full-cell
Xyce simulations.
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simulate as sm


def parse_defaults(pm_path):
    text = open(pm_path).read()
    d = {}
    for part in re.split(r"(?=\.model)", text):
        m = re.match(r"\.model\s+\S+\s+(nmos|pmos)\s", part)
        if not m:
            continue
        v = re.search(r"vth0\s*=\s*([\d.eE+\-]+)", part)
        if v:
            d[m.group(1)] = float(v.group(1))
    return d


def rms_log(res, weights=None):
    errs = []
    for (_, _, _, meas, sim) in res:
        if sim is None or meas is None or meas <= 0:
            continue
        errs.append(math.log10(sim / meas))
    if not errs:
        return 1e9
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def fit(data, pm_path, n_name, p_name, iters=12, step=2e-4, verbose=True):
    defaults = parse_defaults(pm_path)
    vth0n = defaults["nmos"]
    vth0p = abs(defaults["pmos"])
    cards = sm.make_model_cards(pm_path, n_name, p_name, vth0n, vth0p)
    base = sm.sim_leakage(data, cards)
    base_err = rms_log(base)
    if verbose:
        print("start vth0n=%.4f vth0p=%.4f  RMS(log10)=%.4f" % (vth0n, vth0p, base_err))
    for it in range(iters):
        # finite-difference gradients
        cards_n = sm.make_model_cards(pm_path, n_name, p_name, vth0n + step, vth0p)
        rn = rms_log(sm.sim_leakage(data, cards_n))
        cards_p = sm.make_model_cards(pm_path, n_name, p_name, vth0n, vth0p + step)
        rp = rms_log(sm.sim_leakage(data, cards_p))
        if verbose:
            print("  it%d rms=%.4f dr/dvn=%.2f dr/dvp=%.2f" % (it, base_err,
                  (rn - base_err) / step, (rp - base_err) / step))
        gn = (rn - base_err) / step
        gp = (rp - base_err) / step
        # gradient descent on RMS (log scale); leak ~ exp(-vth/(n Vt)) so
        # rms ~ linear in vth for small deltas; step proportional
        eta = 0.010
        dvn = -eta * gn
        dvp = -eta * gp
        vth0n += dvn
        vth0p += dvp
        cards = sm.make_model_cards(pm_path, n_name, p_name, vth0n, vth0p)
        new_err = rms_log(sm.sim_leakage(data, cards))
        if new_err > base_err and it > 0:
            # overshoot: revert half step
            vth0n -= dvn / 2
            vth0p -= dvp / 2
            cards = sm.make_model_cards(pm_path, n_name, p_name, vth0n, vth0p)
            new_err = rms_log(sm.sim_leakage(data, cards))
        base_err = new_err
        if verbose:
            print("  -> vth0n=%.4f vth0p=%.4f rms=%.4f" % (vth0n, vth0p, base_err))
        if base_err < 1e-3:
            break
    return vth0n, vth0p, base_err


if __name__ == "__main__":
    data_path = sys.argv[1]
    pm = sys.argv[2]
    n_name = sys.argv[3] if len(sys.argv) > 3 else "nm1p2_svt_lp"
    p_name = sys.argv[4] if len(sys.argv) > 4 else "pm1p2_svt_lp"
    data = json.load(open(data_path))
    vn, vp, err = fit(data, pm, n_name, p_name)
    print("FITTED: vth0n=%.4f vth0p=%.4f RMS(log10)=%.4f" % (vn, vp, err))
