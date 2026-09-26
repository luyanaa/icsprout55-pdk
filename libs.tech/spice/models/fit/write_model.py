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

"""Render the shipped fitted BSIM4 cards from FIT_PARAMS.json."""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import simulate as sm  # noqa: E402

FLAVORS = ("svt", "lvt", "hvt")


def render(manifest):
    params = manifest.get("flavors", manifest)
    rows = []
    for flavor in FLAVORS:
        p = params[flavor]["params"]
        rows.extend([
            p["vth0n"], p["vth0p"], p["dibl_n"], p["dibl_p"],
            p["voff_n"], p["voff_p"], params[flavor]["rms"],
        ])
    header = """* ============================================================================
* ICsprout55 - FITTED core MOS BSIM4 models (provisional, pre-silicon)
* ============================================================================
* Base : PTM 45nm Low-Power BSIM4 (45nm_LP.pm), level 54, full card
* Fit  : vth0 + DIBL scale + voff scale for leakage; RC-aware u0/vsat/rdsw
*       for inverter drive, with labeled M1 signal RC added by fit/drive.py.
* Data : 37-cell leakage train split plus INVX1/3/4 Liberty TT timing points.
*       The 37-cell train split is data_fit + disjoint data_holdout.
* Tool : Optuna TPE + Xyce 7.10; deterministic in-process verification.
* Metric: RMS(log10(sim/meas)); 10^RMS is the multiplicative RMS factor,
*        not an arithmetic mean relative error.
*
* flavor  vth0n   vth0p   diblN  diblP  voffN  voffP    train RMS
* svt     %.6f %.6f %.6f %.6f %.6f %.6f   %.6f
* lvt     %.6f %.6f %.6f %.6f %.6f %.6f   %.6f
* hvt     %.6f %.6f %.6f %.6f %.6f %.6f   %.6f
*
* Simulator detail: Xyce device temperature is set with `.options device temp`.
* a SPICE `.temp` card is not sufficient for this Xyce build.
*
* Model modifications:
*   - vth0   : fitted per flavor/device
*   - pdiblc : scaled (DIBL reduction matches the LP off-current slope)
*   - voff   : scaled (subthreshold off-floor)
*   - u0/vsat/rdsw : provisional RC-aware timing calibration per flavor/device
*   - GIDL   : disabled (agidl/bgidl/cgidl/aigsd/bigsd/cigsd = 0); the PTM
*              GIDL floor is above the measured off-currents.
*   - other  : PTM 45nm_LP values (C-V, temp, noise, mismatch, aging)
*              remain uncalibrated.
*
* WARNING - read fitted/FIT_REPORT.md before use:
*   (1) This is a leakage-calibrated exploratory model, not foundry data.
*   (2) Independent 20-cell holdout remains materially worse than the train fit.
*   (3) Drive, C-V, noise, mismatch, aging, and non-TT corners are not signoff
*       validated; use the released Liberty timing/cap tables for digital work.
*   (4) DFFX1, MUX2X1, and DFFQX1 static states are excluded from the fit.
* ============================================================================
*
""" % tuple(rows)
    parts = [header]
    pm = os.path.expanduser(manifest.get(
        "base_model", "~/Downloads/45nm_LP.pm"))
    for flavor in FLAVORS:
        p = params[flavor]["params"]
        drive = params[flavor].get("drive", {})
        parts.append("* ------------------------------------------------------------\n")
        parts.append("* %s flavor\n" % flavor.upper())
        parts.append(sm.make_model_cards(
            pm, "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
            vth0n=p["vth0n"], vth0p=p["vth0p"],
            dibl_scale_n=p["dibl_n"], dibl_scale_p=p["dibl_p"],
            voff_scale_n=p["voff_n"], voff_scale_p=p["voff_p"],
            overrides_n=drive.get("overrides_n"),
            overrides_p=drive.get("overrides_p")))
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=os.path.join(
        HERE, "..", "fitted", "FIT_PARAMS.json"))
    ap.add_argument("--out", default=os.path.join(
        HERE, "..", "fitted", "ics55_mos_core.l"))
    args = ap.parse_args()
    manifest = json.load(open(os.path.abspath(args.params)))
    with open(os.path.abspath(args.out), "w") as stream:
        stream.write(render(manifest))
    print(os.path.abspath(args.out))


if __name__ == "__main__":
    main()
