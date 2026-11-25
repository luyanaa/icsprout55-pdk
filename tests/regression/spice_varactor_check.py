#!/usr/bin/env python3
"""Run the foundry MOS varactor through TT/SS/FF and check C(V) continuity.

The vendor varactor is a behavioural subcircuit whose capacitance is a
voltage-controlled expression, so the only portable way to observe C(V) is an
AC current measurement at a fixed frequency: |C| = imag(I(Vsrc)) / (2*pi*f)
for a 1 V AC stimulus.  Each corner/model runs one ngspice deck that steps the
DC bias with ``alter`` and repeats the AC analysis, which keeps the whole sweep
inside a single simulator invocation.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOUNDRY = ROOT / "libs.tech" / "spice" / "foundry" / "ngspice"
LIB_NAME = "ICsprout_55LLULP1225_V1p1_hsp.lib"
CORNERS = ("tt_var", "ss_var", "ff_var")
MODELS = (
    ("var1p2_npd_nw_lp", 1.2, 0.1),
    ("var2p5_npd_nw_lp", 2.5, 0.2),
)
FREQUENCY = 1.0e9
# Adjacent 0.1 V steps may move C by a fair amount around the threshold, but a
# smooth accumulation curve never doubles from one step to the next.
MAX_STEP_RATIO = 1.6

DECK = """\
* ICsprout55 varactor C(V) smoke - {model} {corner}
.lib '{lib}' {corner}
Vpos pos 0 dc {bias} ac 1
X1 pos 0 {model} lr=1u wr=1u nf=1 mr=1
.control
foreach vb {biases}
  alter Vpos dc = $vb
  ac lin 1 {frequency:g} {frequency:g}
  let cval = abs(imag(i(Vpos)))/(2*pi*{frequency:g})
  print cval
end
.endc
.end
"""


def c_values(
    model: str, corner: str, step: float, ngspice: str
) -> tuple[list[tuple[float, float]], str]:
    supply = next(supply for name, supply, _step in MODELS if name == model)
    biases = [round(-supply + index * step, 6)
              for index in range(int(round(2 * supply / step)) + 1)]
    deck = DECK.format(
        model=model, corner=corner, lib=FOUNDRY / LIB_NAME,
        bias=biases[0], biases=" ".join(f"{bias:g}" for bias in biases),
        frequency=FREQUENCY,
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "varactor.cir"
        path.write_text(deck)
        command = [ngspice, "-b", str(path)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if run.returncode != 0 and "GLIBCXX" in (run.stdout + run.stderr):
            # A caller-supplied LD_LIBRARY_PATH can shadow the system C++
            # runtime; retry with it removed rather than failing the sweep.
            env = {key: value for key, value in os.environ.items()
                   if key != "LD_LIBRARY_PATH"}
            run = subprocess.run(command, capture_output=True, text=True,
                                 timeout=300, env=env)
    output = (run.stdout + "\n" + run.stderr).strip()
    values = [float(match.group(1))
              for match in re.finditer(r"cval\s*=\s*([-+0-9.eE]+)", output)]
    if run.returncode != 0 or len(values) != len(biases):
        return [], output
    return list(zip(biases, values)), output


def check_case(model: str, corner: str, step: float, ngspice: str) -> dict:
    points, output = c_values(model, corner, step, ngspice)
    issues: list[str] = []
    if not points:
        return {
            "model": model, "corner": corner, "status": "FAIL",
            "issues": ["ngspice did not return one C value per bias point"],
            "output": output[-2000:],
        }
    for bias, value in points:
        if not math.isfinite(value) or value <= 0.0:
            issues.append(f"non-physical capacitance {value:g} F at {bias:g} V")
    for (bias_a, value_a), (bias_b, value_b) in zip(points, points[1:]):
        if value_a <= 0.0 or value_b <= 0.0:
            continue
        ratio = max(value_a, value_b) / min(value_a, value_b)
        if ratio > MAX_STEP_RATIO:
            issues.append(
                f"C(V) discontinuity between {bias_a:g} V ({value_a:.4g} F) and "
                f"{bias_b:g} V ({value_b:.4g} F), ratio {ratio:.2f}"
            )
    low, high = points[0][1], points[-1][1]
    if high <= low:
        issues.append(f"capacitance does not increase with bias ({low:.4g} -> {high:.4g} F)")
    return {
        "model": model, "corner": corner,
        "status": "FAIL" if issues else "PASS",
        "c_min": min(value for _bias, value in points),
        "c_max": max(value for _bias, value in points),
        "points": len(points),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default="ngspice")
    args = parser.parse_args()
    lib = FOUNDRY / LIB_NAME
    if not lib.is_file():
        print(f"FAIL: missing {lib}")
        return 1

    cases = []
    for model, _supply, step in MODELS:
        for corner in CORNERS:
            cases.append(check_case(model, corner, step, args.ngspice))
    failed = [case for case in cases if case["status"] != "PASS"]
    for case in cases:
        detail = ""
        if case["status"] == "PASS":
            detail = f" C={case['c_min']:.4g}..{case['c_max']:.4g} F over {case['points']} points"
        elif case["issues"]:
            detail = " " + "; ".join(case["issues"])
        print(f"{case['status']}: {case['model']} {case['corner']}{detail}")
    print(
        f"{'FAIL' if failed else 'PASS'}: varactor C(V) smoke "
        f"({len(cases) - len(failed)}/{len(cases)} corners)"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
