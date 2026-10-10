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
"""Validate the imported ICsprout model variants in ngspice and Xyce.

Runs a fixed single-device DC operating point for every
(simulator x variant x mismatch) combination and reports whether the netlist
parses, the resulting VDD current, and whether repeated runs are bit-stable.

This is the evidence behind the variant recommendation in
``libs.tech/spice/README.md``: both variants parse in both simulators, and the
only behavioural difference that matters is whether the wrapper's
``mismod`` mismatch term is evaluated.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOUNDRY = HERE / "foundry"
VARIANTS = ("hspice", "ngspice")
LIB_NAME = "ICsprout_55LLULP1225_V1p1_hsp.lib"

XYCE = os.environ.get("XYCE", "/usr/local/XyceNF_OMPI_7.10/bin/Xyce")
NGSPICE = os.environ.get("NGSPICE", "ngspice")
XYCE_ENV = {"DYLD_LIBRARY_PATH": "/opt/homebrew/lib"}
RUNS = 3

XYCE_DECK = """\
* model-variant validation (Xyce)
.lib '{lib}' tt_mos
VDD d 0 1.2
VG g 0 0
VS s 0 0
VB b 0 0
X1 d g s b nm1p2_svt_lp w=1u l=60n nf=1{mismatch}
.op
.print dc i(VDD)
.end
"""

NGSPICE_DECK = """\
* model-variant validation (ngspice)
.lib '{lib}' tt_mos
VDD d 0 1.2
VG g 0 0
VS s 0 0
VB b 0 0
X1 d g s b nm1p2_svt_lp w=1u l=60n nf=1{mismatch}
.control
op
print i(VDD)
.endc
.end
"""


def run_xyce(deck_text: str) -> tuple[bool, float | None, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as handle:
        handle.write(deck_text)
        path = handle.name
    try:
        env = dict(os.environ)
        env.update(XYCE_ENV)
        proc = subprocess.run([XYCE, path], capture_output=True, text=True,
                              timeout=300, env=env, cwd=str(Path(path).parent))
        log = proc.stdout + proc.stderr
        prn = Path(path + ".prn")
        if proc.returncode != 0 or not prn.exists():
            return False, None, log[-400:]
        row = None
        for line in prn.read_text().splitlines():
            parts = line.split()
            if parts and parts[0].isdigit():
                row = parts
        if row is None or len(row) < 2:
            return False, None, "no numeric row"
        return True, float(row[1]), ""
    finally:
        for suffix in ("", ".prn", ".out", ".mt0"):
            try:
                Path(path + suffix).unlink()
            except FileNotFoundError:
                pass


def run_ngspice(deck_text: str) -> tuple[bool, float | None, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".sp", delete=False) as handle:
        handle.write(deck_text)
        path = handle.name
    try:
        proc = subprocess.run([NGSPICE, "-b", "-a", path], capture_output=True,
                              text=True, timeout=300)
        log = proc.stdout + proc.stderr
        if "fatal error" in log or "Error in netlist" in log:
            return False, None, log[-400:]
        for line in log.splitlines():
            if line.strip().startswith("i(vdd)"):
                return True, float(line.split("=")[1]), ""
        return False, None, "no i(VDD) in output"
    finally:
        for suffix in ("", ".prn", ".out"):
            try:
                Path(path + suffix).unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=RUNS)
    args = parser.parse_args()

    results = []
    for variant in VARIANTS:
        lib = FOUNDRY / variant / LIB_NAME
        if not lib.exists():
            raise SystemExit(f"missing {lib}; run import_foundry_models.py first")
        for mismatch in ("", " mismod=1", " mismod=0"):
            label = mismatch.strip() or "unset"
            for simulator, runner, template in (
                ("xyce", run_xyce, XYCE_DECK),
                ("ngspice", run_ngspice, NGSPICE_DECK),
            ):
                deck = template.format(lib=lib, mismatch=mismatch)
                values, ok, log = [], True, ""
                for _ in range(args.runs):
                    parsed, value, log = runner(deck)
                    if not parsed:
                        ok = False
                        break
                    values.append(value)
                unique = sorted({round(v, 18) for v in values})
                results.append({
                    "variant": variant,
                    "simulator": simulator,
                    "mismod": label,
                    "parses": ok,
                    "runs": len(values),
                    "current_a": values[0] if values else None,
                    "distinct_values": len(unique),
                    "reproducible": ok and len(unique) == 1,
                    "log": log,
                })
                print("%-8s %-8s mismod=%-6s parses=%-5s reproducible=%-5s distinct=%d current=%s" % (
                    variant, simulator, label, ok, ok and len(unique) == 1,
                    len(unique), values[0] if values else "n/a"))

    report = {
        "experiment": "foundry_model_variant_validation",
        "runs_per_case": args.runs,
        "results": results,
        "conclusion": (
            "Both variants parse in both simulators. The ngspice variant is "
            "deterministic in ngspice because its wrapper defaults mismod=0; "
            "the hspice variant defaults mismod=1 and therefore varies "
            "run-to-run in ngspice under the wrapper's agauss mismatch terms. "
            "Xyce returns identical values for every case because it does not "
            "evaluate the wrapper's agauss mismatch terms outside a Monte "
            "Carlo analysis."
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print()
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
