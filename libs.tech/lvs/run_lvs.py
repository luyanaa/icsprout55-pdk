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

"""ICsprout55 LVS run wrapper (KLayout).

Usage:
  python3 run_lvs.py --layout <cell.gds> --top <CELL> \
      --netlist <cell.cdl> [--report <out.lvsdb>] \
      [--target-netlist <extracted.cir>] [--combine-devices] [--run-mode deep|flat]

Options:
  --layout PATH        input GDS (required)
  --netlist PATH       schematic netlist (CDL/SPICE); defaults to <top>.cdl
                       next to the layout
  --top CELL           top cell name (required)
  --report PATH        LVS report database (.lvsdb); default: <top>.lvsdb
  --target-netlist P   extracted layout netlist; default: <top>_extracted.cir
  --no-well-ties       do not tie p-substrate to VSS / n-well to VDD
  --combine-devices    combine parallel/series devices before comparison
  --purge              purge unused nets/devices before comparison
  --run-mode MODE      deep (default) | flat
  --klayout PATH       klayout executable; defaults to 'klayout' on PATH
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DECK = Path(__file__).resolve().parent / "ics55.lvs"


def main() -> int:
    ap = argparse.ArgumentParser(description="ICsprout55 LVS run wrapper")
    ap.add_argument("--layout", required=True)
    ap.add_argument("--top", required=True)
    ap.add_argument("--netlist")
    ap.add_argument("--report")
    ap.add_argument("--target-netlist")
    ap.add_argument("--no-well-ties", action="store_true")
    ap.add_argument("--combine-devices", action="store_true")
    ap.add_argument("--purge", action="store_true")
    ap.add_argument("--run-mode", default="deep", choices=["deep", "flat"])
    ap.add_argument("--klayout", default=None)
    args = ap.parse_args()

    klayout = args.klayout or shutil.which("klayout")
    if not klayout:
        print("error: klayout not found on PATH (use --klayout)", file=sys.stderr)
        return 2

    layout = Path(args.layout)
    if not layout.exists():
        print(f"error: layout not found: {layout}", file=sys.stderr)
        return 2

    netlist = Path(args.netlist) if args.netlist else layout.parent / f"{args.top}.cdl"
    report = Path(args.report) if args.report else Path(f"{args.top}.lvsdb")
    target = Path(args.target_netlist) if args.target_netlist else Path(f"{args.top}_extracted.cir")

    cmd = [
        klayout, "-b", "-r", str(DECK),
        "-rd", f"input={layout}",
        "-rd", f"top={args.top}",
        "-rd", f"schematic={netlist}",
        "-rd", f"report={report}",
        "-rd", f"target_netlist={target}",
        "-rd", f"run_mode={args.run_mode}",
    ]
    if args.no_well_ties:
        cmd += ["-rd", "no_well_ties=true"]
    if args.combine_devices:
        cmd += ["-rd", "combine_devices=true"]
    if args.purge:
        cmd += ["-rd", "purge=true"]
    cmd += ["-z"]

    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
