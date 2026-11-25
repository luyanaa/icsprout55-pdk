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

"""Compare EM-deck variants (no PGS / PGS / ideal ground) at one frequency.

Each --case is label=path to a Palace port-S.csv.  An optional --open fixture
run is de-embedded from every case (Y subtraction, see extract_lq.py) so the
shield/ground comparison is made on the inductor itself.

Usage:
    python compare_em.py --open open/port-S.csv --freq 1.0 \
        --case no_pgs=no_pgs/port-S.csv \
        --case pgs=pgs/port-S.csv \
        --case ideal=ideal/port-S.csv [--csv out.csv]
"""

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_lq import deembed, read_port_s, series_lq  # noqa: E402


def case_value(case, freq_ghz, open_csv, z0):
    label, path = case.split("=", 1)
    freqs, smats = read_port_s(path)
    freqs, mats = deembed(freqs, smats, open_csv=open_csv, z0=z0)
    idx = int(np.argmin(np.abs(np.asarray(freqs) - freq_ghz)))
    f = freqs[idx]
    zs, csh = series_lq(mats[idx], f, z0)
    w = 2.0 * np.pi * f * 1e9
    return {
        "case": label, "path": path, "f_ghz": f,
        "L_nH": zs.imag / w * 1e9, "R_ohm": zs.real,
        "Q": zs.imag / zs.real, "Csh_fF": csh * 1e15,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", required=True,
                    metavar="LABEL=CSV")
    ap.add_argument("--open", dest="open_csv", default=None,
                    help="open-fixture port-S.csv de-embedded from every case")
    ap.add_argument("--freq", type=float, default=1.0, help="GHz")
    ap.add_argument("--z0", type=float, default=50.0)
    ap.add_argument("--csv", dest="csv_out", default=None)
    args = ap.parse_args()

    rows = [case_value(c, args.freq, args.open_csv, args.z0)
            for c in args.case]
    print("%-12s %8s %10s %10s %8s %10s"
          % ("case", "f (GHz)", "L (nH)", "R (ohm)", "Q", "Csh (fF)"))
    for row in rows:
        print("%-12s %8.3f %10.4f %10.4f %8.3f %10.2f"
              % (row["case"], row["f_ghz"], row["L_nH"], row["R_ohm"],
                 row["Q"], row["Csh_fF"]))

    if args.csv_out:
        with open(args.csv_out, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print("wrote", args.csv_out)


if __name__ == "__main__":
    sys.exit(main())
