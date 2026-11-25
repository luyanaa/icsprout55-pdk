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

"""RF passive calibration figures of merit.

Two measurement modes, both writing one JSON report:

inductor
    R(f), L(f), Q(f), Csh(f) and the self-resonant frequency (SRF) from
    2-port S-parameters.  Palace ``port-S.csv`` and Touchstone ``.s2p`` are
    accepted, so the same command compares the Palace FEM and openEMS FDTD
    decks.  Repeat ``--sparam name=path`` for PVT corners; the report carries
    the per-corner spread.

varactor
    C(V, f) from an ngspice AC sweep of the released varactor models, one
    block per corner section (``tt_var``, ``ss_var``, ``ff_var``).  The
    capacitance is ``|Im(I)| / (2*pi*f)`` for a 1 V AC stimulus.

Calibration status is fail-closed: without an independently measured
reference it stays ``UNCALIBRATED``.  ``--reference <s2p|csv>`` supplies the
golden inductor S-parameters and turns the status into ``CALIBRATED`` or
``MISMATCH`` against ``--tolerance``.  No measured silicon data ships with
this PDK, so the current RF models are expected to report ``UNCALIBRATED``.

Usage:
    python3 rf_calib.py inductor --sparam typ=libs.tech/pex/palace/.../port-S.csv
    python3 rf_calib.py inductor --sparam palace=... --sparam openems=...
    python3 rf_calib.py inductor --sparam typ=... --reference golden.s2p
    python3 rf_calib.py varactor --model var1p2_npd_nw_lp \
        --corners tt_var ss_var ff_var --freqs 0.1 1 10 --bias-step 0.2
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PALACE = Path(__file__).resolve().parent / "palace"
FOUNDRY = ROOT / "libs.tech" / "spice" / "foundry" / "ngspice"
LIB_NAME = "ICsprout_55LLULP1225_V1p1_hsp.lib"

sys.path.insert(0, str(PALACE))
import extract_lq  # noqa: E402  (reuse the Palace S-parameter reader/math)

VARACTOR_SUPPLY = {
    "var1p2_npd_nw_lp": 1.2, "var1p2_npd_nw_dnw_lp": 1.2,
    "var2p5_npd_nw_lp": 2.5, "var2p5_npd_nw_dnw_lp": 2.5,
}

VARACTOR_DECK = """\
* ICsprout55 varactor C(V,f) - {model} {corner}
.lib '{lib}' {corner}
Vpos pos 0 dc {bias} ac 1
X1 pos 0 {model} lr=1u wr=1u nf=1 mr=1
.control
{loops}
.endc
.end
"""


def read_touchstone(path: Path) -> tuple[list[float], list[np.ndarray]]:
    """Minimal 2-port Touchstone reader (S, MA/DB/RI, Hz/kHz/MHz/GHz)."""
    freqs: list[float] = []
    mats: list[np.ndarray] = []
    unit = 1e-9
    fmt = "MA"
    z0 = 50.0
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.split("!")[0].strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("#"):
            fields = line[1:].upper().split()
            for field in fields:
                if field in ("HZ", "KHZ", "MHZ", "GHZ"):
                    unit = {"HZ": 1e-9, "KHZ": 1e-6, "MHZ": 1e-3, "GHZ": 1.0}[field]
                elif field in ("MA", "DB", "RI"):
                    fmt = field
                elif field == "R":
                    z0 = float(fields[fields.index(field) + 1])
            continue
        values = [float(x) for x in line.replace(",", " ").split()]
        if len(values) < 9:
            continue
        freq = values[0] * unit
        pairs = values[1:9]
        S = np.zeros((2, 2), dtype=complex)
        for idx, (i, j) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            a, b = pairs[2 * idx], pairs[2 * idx + 1]
            if fmt == "RI":
                S[i, j] = complex(a, b)
            elif fmt == "DB":
                S[i, j] = 10 ** (a / 20.0) * np.exp(1j * np.deg2rad(b))
            else:
                S[i, j] = a * np.exp(1j * np.deg2rad(b))
        freqs.append(freq)
        mats.append(S)
    return freqs, mats


def read_sparams(path: Path) -> tuple[list[float], list[np.ndarray]]:
    """Palace port-S.csv (GHz, dB/deg) or Touchstone .s2p."""
    text = path.read_text(errors="replace")
    if "|S[" in text:
        freqs, smats = extract_lq.read_port_s(str(path))
        return freqs, [S for S, complete in smats]
    return read_touchstone(path)


def fom_rows(
    freqs: list[float], mats: list[np.ndarray], z0: float
) -> list[dict[str, float]]:
    rows = []
    for f_ghz, S in zip(freqs, mats):
        if f_ghz <= 0:
            continue
        w = 2.0 * math.pi * f_ghz * 1e9
        zs, csh = extract_lq.series_lq(S, f_ghz, z0)
        rows.append({
            "f_ghz": f_ghz,
            "r_ohm": float(zs.real),
            "l_nh": float(zs.imag / w * 1e9),
            "q": float(zs.imag / zs.real) if zs.real else float("nan"),
            "csh_ff": float(csh * 1e15),
            "im_zs": float(zs.imag),
        })
    return rows


def self_resonance(rows: list[dict[str, float]]) -> float | None:
    """First frequency where Im(Zs) crosses + -> - (series SRF), interpolated."""
    for previous, current in zip(rows, rows[1:]):
        if previous["im_zs"] > 0.0 >= current["im_zs"]:
            span = previous["im_zs"] - current["im_zs"]
            if span <= 0.0:
                continue
            weight = previous["im_zs"] / span
            return previous["f_ghz"] + weight * (current["f_ghz"] - previous["f_ghz"])
    return None


def q_peak(rows: list[dict[str, float]]) -> tuple[float, float] | None:
    if not rows:
        return None
    best = max(rows, key=lambda row: row["q"] if math.isfinite(row["q"]) else -math.inf)
    if not math.isfinite(best["q"]):
        return None
    return best["f_ghz"], best["q"]


def device_summary(rows: list[dict[str, float]]) -> dict:
    srf = self_resonance(rows)
    peak = q_peak(rows)
    return {
        "points": rows,
        "srf_ghz": srf,
        "q_max": peak[1] if peak else None,
        "f_qmax_ghz": peak[0] if peak else None,
    }


def _nearest(rows: list[dict[str, float]], freq: float) -> dict[str, float] | None:
    if not rows:
        return None
    row = min(rows, key=lambda item: abs(item["f_ghz"] - freq))
    return row if abs(row["f_ghz"] - freq) <= max(1e-9, 0.01 * freq) else None


def compare(
    measured: dict, reference: dict, freq: float, tolerance: float
) -> dict:
    """Relative R/L/Q and SRF deviation against a golden S-parameter run."""
    here = _nearest(measured["points"], freq)
    there = _nearest(reference["points"], freq)
    issues: list[str] = []
    errors: dict[str, float] = {}
    if not here or not there:
        issues.append(f"no common point near {freq:g} GHz")
    else:
        for key, label in (("r_ohm", "R"), ("l_nh", "L"), ("q", "Q")):
            if there[key]:
                error = abs(here[key] - there[key]) / abs(there[key])
                errors[label] = error
                if error > tolerance:
                    issues.append(
                        f"{label} {here[key]:.4g} vs reference {there[key]:.4g} "
                        f"({error * 100:.1f}% > {tolerance * 100:.1f}%)"
                    )
    if measured["srf_ghz"] and reference["srf_ghz"]:
        error = abs(measured["srf_ghz"] - reference["srf_ghz"]) / reference["srf_ghz"]
        errors["SRF"] = error
        if error > tolerance:
            issues.append(
                f"SRF {measured['srf_ghz']:.4g} vs reference "
                f"{reference['srf_ghz']:.4g} GHz ({error * 100:.1f}% > "
                f"{tolerance * 100:.1f}%)"
            )
    return {
        "frequency_ghz": freq,
        "tolerance": tolerance,
        "relative_error": errors,
        "status": "MISMATCH" if issues else "CALIBRATED",
        "issues": issues,
    }


def spread(devices: dict[str, dict], freq: float) -> dict:
    """PVT spread of R/L/Q at one frequency across the supplied corners."""
    points = {}
    for name, summary in devices.items():
        row = _nearest(summary["points"], freq)
        if row:
            points[name] = {key: row[key] for key in ("r_ohm", "l_nh", "q")}
    if len(points) < 2:
        return {}
    result = {"frequency_ghz": freq, "corners": points, "relative_spread": {}}
    for key in ("r_ohm", "l_nh", "q"):
        values = [abs(point[key]) for point in points.values() if point[key]]
        if values:
            result["relative_spread"][key] = max(values) / min(values) - 1.0
    return result


def run_inductor(args: argparse.Namespace) -> int:
    devices: dict[str, dict] = {}
    for spec in args.sparam:
        name, _, path = spec.partition("=")
        if not path:
            name, path = Path(spec).stem, spec
        freqs, mats = read_sparams(Path(path))
        devices[name] = device_summary(fom_rows(freqs, mats, args.z0))
        devices[name]["source"] = str(path)

    report: dict = {
        "tool": "rf_calib", "mode": "inductor", "z0": args.z0,
        "calibration_status": "UNCALIBRATED",
        "notes": ["no measured reference supplied; absolute accuracy is unknown"],
        "devices": devices,
        "pvt": spread(devices, args.freq),
    }
    if args.reference:
        reference_freqs, reference_mats = read_sparams(Path(args.reference))
        reference = device_summary(fom_rows(reference_freqs, reference_mats, args.z0))
        comparison = compare(devices[next(iter(devices))], reference,
                             args.freq, args.tolerance)
        report["reference"] = {"source": str(args.reference), **comparison}
        report["calibration_status"] = comparison["status"]
        report["notes"] = comparison["issues"] or [
            "all compared figures of merit are within tolerance"
        ]

    for name, summary in devices.items():
        print(f"# {name}: {summary['source']}")
        print("%9s %12s %10s %8s %10s" % ("f (GHz)", "R (ohm)", "L (nH)", "Q", "Csh (fF)"))
        for row in summary["points"]:
            print("%9.4f %12.4f %10.4f %8.3f %10.3f"
                  % (row["f_ghz"], row["r_ohm"], row["l_nh"], row["q"], row["csh_ff"]))
        srf = summary["srf_ghz"]
        line = f"# SRF: {'%.4f GHz' % srf if srf else 'not reached in sweep'}"
        if summary["q_max"] is not None:
            line += (f"; Qmax {summary['q_max']:.3f} at "
                     f"{summary['f_qmax_ghz']:.4f} GHz")
        print(line)
    if report["pvt"]:
        print(f"# PVT spread at {args.freq:g} GHz: "
              + ", ".join(f"{key} {value * 100:.1f}%"
                          for key, value in report["pvt"]["relative_spread"].items()))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"# report: {args.json}")
    print(f"{report['calibration_status']}: inductor R(f)/L(f)/Q(f)/SRF")
    return 0 if report["calibration_status"] != "MISMATCH" else 1


def varactor_points(
    model: str, corner: str, biases: list[float], freqs: list[float], ngspice: str
) -> tuple[list[dict[str, float]], str]:
    loops = []
    for bias in biases:
        for freq in freqs:
            loops.append(
                f"  alter Vpos dc = {bias:g}\n"
                f"  ac lin 1 {freq:g} {freq:g}\n"
                f"  let cval = abs(imag(i(Vpos)))/(2*pi*{freq:g})\n"
                f"  print cval"
            )
    deck = VARACTOR_DECK.format(
        model=model, corner=corner, lib=FOUNDRY / LIB_NAME,
        bias=biases[0], loops="\n".join(loops),
    )
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "varactor.cir"
        path.write_text(deck)
        command = [ngspice, "-b", str(path)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if run.returncode != 0 and "GLIBCXX" in (run.stdout + run.stderr):
            # A caller-supplied LD_LIBRARY_PATH can shadow the system C++
            # runtime; retry with it removed rather than failing the sweep.
            env = {key: value for key, value in os.environ.items()
                   if key != "LD_LIBRARY_PATH"}
            run = subprocess.run(command, capture_output=True, text=True,
                                 timeout=600, env=env)
    output = (run.stdout + "\n" + run.stderr).strip()
    values = [float(match.group(1))
              for match in re.finditer(r"cval\s*=\s*([-+0-9.eE]+)", output)]
    if run.returncode != 0 or len(values) != len(biases) * len(freqs):
        return [], output
    points = []
    index = 0
    for bias in biases:
        for freq in freqs:
            points.append({"bias_v": bias, "f_ghz": freq, "c_ff": values[index] * 1e15})
            index += 1
    return points, output


def run_varactor(args: argparse.Namespace) -> int:
    supply = VARACTOR_SUPPLY.get(args.model, 1.2)
    step = args.bias_step
    count = int(round(2 * supply / step))
    biases = [round(-supply + index * (2 * supply / count), 6) for index in range(count + 1)]
    report: dict = {
        "tool": "rf_calib", "mode": "varactor",
        "model": args.model, "freqs_ghz": args.freqs,
        "calibration_status": "UNCALIBRATED",
        "notes": ["no measured C(V,f) reference; vendor model is uncalibrated"],
        "corners": {},
    }
    failed = False
    for corner in args.corners:
        points, output = varactor_points(
            args.model, corner, biases, args.freqs, args.ngspice
        )
        if not points:
            report["corners"][corner] = {
                "status": "FAIL", "issues": ["ngspice did not return one C per point"],
                "output": output[-2000:],
            }
            failed = True
            continue
        issues = [f"non-physical C {point['c_ff']:g} fF at {point['bias_v']:g} V "
                  f"{point['f_ghz']:g} GHz"
                  for point in points
                  if not math.isfinite(point["c_ff"]) or point["c_ff"] <= 0.0]
        per_freq = {}
        for freq in args.freqs:
            curve = [point for point in points if point["f_ghz"] == freq]
            values = [point["c_ff"] for point in curve]
            if not values:
                continue
            per_freq[f"{freq:g}"] = {
                "c_min_ff": min(values), "c_max_ff": max(values),
                "tuning_ratio": max(values) / min(values) if min(values) > 0 else None,
            }
            if max(values) <= min(values):
                issues.append(f"C(V) does not increase with bias at {freq:g} GHz")
        dispersion = {}
        for bias in biases:
            curve = [point["c_ff"] for point in points if point["bias_v"] == bias]
            if len(curve) == len(args.freqs) and min(curve) > 0:
                dispersion[f"{bias:g}"] = max(curve) / min(curve)
        report["corners"][corner] = {
            "status": "FAIL" if issues else "PASS", "issues": issues,
            "points": points, "per_freq": per_freq,
            "max_freq_dispersion": max(dispersion.values()) if dispersion else None,
        }
        failed = failed or bool(issues)
        print(f"{'FAIL' if issues else 'PASS'}: {args.model} {corner} "
              f"C(V,f) {len(points)} points, "
              f"tuning {', '.join('%s GHz %.2fx' % (key, value['tuning_ratio'])
                                  for key, value in per_freq.items())}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"# report: {args.json}")
    print(f"{'FAIL' if failed else 'PASS'}: varactor C(V,f) "
          f"({len(args.corners)} corners)")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    ind = sub.add_parser("inductor", help="R/L/Q/SRF from 2-port S-parameters")
    ind.add_argument("--sparam", action="append", default=[],
                     help="2-port S-parameter file, optionally name=path (repeat for PVT)")
    ind.add_argument("--reference", help="golden S-parameter file for calibration")
    ind.add_argument("--tolerance", type=float, default=0.1,
                     help="relative tolerance for the reference comparison (default 0.1)")
    ind.add_argument("--freq", type=float, default=1.0,
                     help="frequency in GHz for the PVT/reference table (default 1.0)")
    ind.add_argument("--z0", type=float, default=50.0)
    ind.add_argument("--json", help="write the JSON report here")

    var = sub.add_parser("varactor", help="C(V,f) from the released varactor models")
    var.add_argument("--model", default="var1p2_npd_nw_lp")
    var.add_argument("--corners", nargs="+", default=["tt_var", "ss_var", "ff_var"])
    var.add_argument("--freqs", nargs="+", type=float, default=[0.1, 1.0, 10.0])
    var.add_argument("--bias-step", type=float, default=0.2)
    var.add_argument("--ngspice", default="ngspice")
    var.add_argument("--json", help="write the JSON report here")
    args = parser.parse_args()

    if args.mode == "inductor":
        if not args.sparam:
            parser.error("inductor mode needs at least one --sparam")
        return run_inductor(args)
    return run_varactor(args)


if __name__ == "__main__":
    sys.exit(main())
