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

"""Series R/L/Q from a gds2palace / Palace 2-port S-parameter run.

The inductor EM deck (palace/run_model.py) uses two vertical via ports from
the PGS ground to TM2, so the device is the series branch of the pi
equivalent of the measured two-port:

    Y = (I - S) (I + S)^-1 / Z0
    Zs = -1 / Y21

    L = Im(Zs) / (2 pi f),   Q = Im(Zs) / Re(Zs)

The pad-to-shield shunt capacitance is reported as C = Im(Y11 + Y12)/(2 pi f).

Usage:
    python extract_lq.py [palace_model/<name>_data/output/<name>/port-S.csv]
                         [--z0 50]
"""

import argparse
import os
import sys

import numpy as np


def read_port_s(path):
    """Read Palace port-S.csv -> (freq GHz, list of (i, j, S complex) per row)."""
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    header = [h.replace(",", "").strip() for h in lines[0].split(",")]
    # header: f (GHz), |S[i][j]| (dB), arg(S[i][j]) (deg.), ...
    cols = []
    for k, h in enumerate(header):
        if "|S[" in h:
            ij = h.split("|S[")[1].split("]|")[0].split("][")
            cols.append((int(ij[0]), int(ij[1]), k, k + 1))
    if not cols:
        raise SystemExit("no |S| columns found in %s" % path)

    freqs, smats = [], []
    for ln in lines[1:]:
        items = [x.strip() for x in ln.replace(",", " ").split()]
        f = float(items[0])
        n = max(max(i, j) for i, j, _, _ in cols)
        S = np.zeros((n, n), dtype=complex)
        complete = True
        for i, j, kdb, karg in cols:
            if items[kdb].upper() == "NULL" or items[karg].upper() == "NULL":
                complete = False
                continue
            mag = 10.0 ** (float(items[kdb]) / 20.0)
            ang = np.deg2rad(float(items[karg]))
            S[i - 1, j - 1] = mag * np.exp(1j * ang)
        freqs.append(f)
        smats.append((S, complete))
    return freqs, smats


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(here, "palace_model", "ics55_ind_m2_data", "output",
                           "ics55_ind_m2", "port-S.csv")
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=default)
    ap.add_argument("--z0", type=float, default=50.0)
    args = ap.parse_args()

    freqs, smats = read_port_s(args.csv)
    ident = np.eye(smats[0][0].shape[0])
    print("%9s %12s %10s %8s %10s" % ("f (GHz)", "Re Zs (ohm)", "L (nH)", "Q", "Csh (fF)"))
    for f_ghz, (S, complete) in zip(freqs, smats):
        w = 2.0 * np.pi * f_ghz * 1e9
        if complete:
            Y = (ident - S) @ np.linalg.inv(ident + S) / args.z0
            zs = -1.0 / Y[1, 0]
            csh = (Y[0, 0] + Y[0, 1]).imag / w
        else:
            # only S11/S21 available: series 2-port approximation
            zs = 2.0 * args.z0 * (1.0 - S[1, 0]) / S[1, 0]
            csh = float("nan")
        print("%9.4f %12.4f %10.4f %8.3f %10.3f"
              % (f_ghz, zs.real, zs.imag / w * 1e9, zs.imag / zs.real, csh * 1e15))


if __name__ == "__main__":
    sys.exit(main())
