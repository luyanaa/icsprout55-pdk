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

Port de-embedding: pass the open fixture run (same pads/ports/PGS, no
winding; make_em_deck.py --open) with --open.  Its Y matrix is subtracted
from the DUT Y matrix, removing the pad, port-sheet and shield parasitics:

    Y_dev = Y_dut - Y_open

A short fixture may be supplied as well (Z_dev = Z_dut - Z_short, applied
after the open step).

Usage:
    python extract_lq.py [palace_model/<name>_data/output/<name>/port-S.csv]
                         [--z0 50] [--open <open-port-S.csv>]
                         [--short <short-port-S.csv>]
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


def s_to_y(S, z0):
    ident = np.eye(S.shape[0])
    return (ident - S) @ np.linalg.inv(ident + S) / z0


def y_to_s(Y, z0):
    ident = np.eye(Y.shape[0])
    return (ident - z0 * Y) @ np.linalg.inv(ident + z0 * Y)


def s_to_z(S, z0):
    ident = np.eye(S.shape[0])
    return z0 * (ident + S) @ np.linalg.inv(ident - S)


def z_to_s(Z, z0):
    ident = np.eye(Z.shape[0])
    return (Z - z0 * ident) @ np.linalg.inv(Z + z0 * ident)


def _interp_matrix(freq_ref, freq_src, mats):
    if len(freq_ref) == len(freq_src) and np.allclose(freq_ref, freq_src):
        return mats
    flat = np.array(mats)
    out = np.empty((len(freq_ref),) + flat.shape[1:], dtype=complex)
    for idx in np.ndindex(flat.shape[1:]):
        values = flat[(slice(None),) + idx]
        out[(slice(None),) + idx] = (np.interp(freq_ref, freq_src, values.real)
                                     + 1j * np.interp(freq_ref, freq_src,
                                                      values.imag))
    return list(out)


def deembed(freqs, smats, open_csv=None, short_csv=None, z0=50.0):
    """Remove fixture parasitics; returns (freqs, [S_device])."""
    if not (open_csv or short_csv):
        return freqs, [S for S, _ in smats]
    if not all(complete for _, complete in smats):
        raise SystemExit("de-embedding needs a complete 2-port S matrix")
    mats = [S for S, _ in smats]
    if open_csv:
        f_o, s_o = read_port_s(open_csv)
        if not all(complete for _, complete in s_o):
            raise SystemExit("open fixture needs a complete 2-port S matrix")
        opens = _interp_matrix(freqs, f_o, [S for S, _ in s_o])
        mats = [y_to_s(s_to_y(S, z0) - s_to_y(O, z0), z0)
                for S, O in zip(mats, opens)]
    if short_csv:
        f_s, s_s = read_port_s(short_csv)
        if not all(complete for _, complete in s_s):
            raise SystemExit("short fixture needs a complete 2-port S matrix")
        shorts = _interp_matrix(freqs, f_s, [S for S, _ in s_s])
        mats = [z_to_s(s_to_z(S, z0) - s_to_z(Z, z0), z0)
                for S, Z in zip(mats, shorts)]
    return freqs, mats


def series_lq(S, f_ghz, z0=50.0):
    """(Zs, Csh) from the pi-equivalent series branch at one frequency."""
    w = 2.0 * np.pi * f_ghz * 1e9
    Y = s_to_y(S, z0)
    return -1.0 / Y[1, 0], (Y[0, 0] + Y[0, 1]).imag / w


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(here, "palace_model", "ics55_ind_m2_data", "output",
                           "ics55_ind_m2", "port-S.csv")
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=default)
    ap.add_argument("--z0", type=float, default=50.0)
    ap.add_argument("--open", dest="open_csv",
                    help="open-fixture port-S.csv for Y de-embedding")
    ap.add_argument("--short", dest="short_csv",
                    help="short-fixture port-S.csv for Z de-embedding")
    args = ap.parse_args()

    freqs, smats = read_port_s(args.csv)
    if args.open_csv or args.short_csv:
        print("# de-embedded: open=%s short=%s"
              % (args.open_csv or "-", args.short_csv or "-"))
        freqs, mats = deembed(freqs, smats, args.open_csv, args.short_csv,
                              args.z0)
        complete_flags = [True] * len(freqs)
    else:
        mats = [S for S, _ in smats]
        complete_flags = [complete for _, complete in smats]
    print("%9s %12s %10s %8s %10s" % ("f (GHz)", "Re Zs (ohm)", "L (nH)", "Q", "Csh (fF)"))
    for f_ghz, S, complete in zip(freqs, mats, complete_flags):
        w = 2.0 * np.pi * f_ghz * 1e9
        if complete:
            zs, csh = series_lq(S, f_ghz, args.z0)
        else:
            # only S11/S21 available: series 2-port approximation
            zs = 2.0 * args.z0 * (1.0 - S[1, 0]) / S[1, 0]
            csh = float("nan")
        print("%9.4f %12.4f %10.4f %8.3f %10.3f"
              % (f_ghz, zs.real, zs.imag / w * 1e9, zs.imag / zs.real, csh * 1e15))


if __name__ == "__main__":
    sys.exit(main())
