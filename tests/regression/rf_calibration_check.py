#!/usr/bin/env python3
"""RF passive calibration harness regression.

The calibration report must recover the analytic R/L/Q/SRF of a synthetic
two-port and must gate on an independent reference; the varactor sweep must
return a physical, monotonic C(V) with no numerical blow-up.  This validates
`libs.tech/pex/rf_calib.py` itself, not any absolute silicon accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "libs.tech" / "pex" / "rf_calib.py"

R_OHM = 2.0
L_H = 1.0e-9
C_F = 200e-15
FREQS = np.unique(np.concatenate([np.linspace(0.1, 20.0, 800), [0.5, 1.0]]))


def series_impedance(freqs_ghz: np.ndarray) -> np.ndarray:
    """R + jwL in parallel with 1/jwC (an inductor with its own capacitance)."""
    w = 2.0 * np.pi * freqs_ghz * 1e9
    return (R_OHM + 1j * w * L_H) / (1.0 - w**2 * L_H * C_F + 1j * w * R_OHM * C_F)


def expected_srf() -> float:
    # Im(Zs) = 0  ->  w^2 = 1/(LC) - (R/L)^2
    w = math.sqrt(1.0 / (L_H * C_F) - (R_OHM / L_H) ** 2)
    return w / (2.0 * math.pi) / 1e9


def write_palace_csv(path: Path, freqs_ghz: np.ndarray, zs: np.ndarray) -> None:
    y21 = -1.0 / zs
    Y = np.zeros((len(freqs_ghz), 2, 2), dtype=complex)
    Y[:, 0, 0] = -y21
    Y[:, 1, 1] = -y21
    Y[:, 0, 1] = y21
    Y[:, 1, 0] = y21
    ident = np.eye(2)
    z0 = 50.0
    header = ("        f (GHz),             |S[1][1]| (dB),"
              "        arg(S[1][1]) (deg.),             |S[2][1]| (dB),"
              "        arg(S[2][1]) (deg.),             |S[1][2]| (dB),"
              "        arg(S[1][2]) (deg.),             |S[2][2]| (dB),"
              "        arg(S[2][2]) (deg.)")
    lines = [header]
    for freq, y in zip(freqs_ghz, Y):
        S = (ident - z0 * y) @ np.linalg.inv(ident + z0 * y)
        fields = [f"{freq:.8e}"]
        for i, j in ((0, 0), (1, 0), (0, 1), (1, 1)):
            fields.append(f"{20 * math.log10(abs(S[i, j])):.12e}")
            fields.append(f"{math.degrees(np.angle(S[i, j])):.12e}")
        lines.append(",".join(fields))
    path.write_text("\n".join(lines) + "\n")


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, timeout=600)


def check_inductor(directory: Path) -> list[dict]:
    cases = []
    zs = series_impedance(FREQS)
    golden = directory / "golden.csv"
    write_palace_csv(golden, FREQS, zs)
    detuned = directory / "detuned.csv"
    write_palace_csv(detuned, FREQS, series_impedance(FREQS) * 1.2)

    report_path = directory / "inductor.json"
    run = run_tool("inductor", "--sparam", f"golden={golden}",
                   "--freq", "0.5", "--json", str(report_path))
    issues: list[str] = []
    report = {}
    if run.returncode != 0 or not report_path.is_file():
        issues.append(f"tool failed (exit {run.returncode}): "
                      f"{(run.stdout + run.stderr).strip()[-500:]}")
    else:
        report = json.loads(report_path.read_text())
        device = report["devices"]["golden"]
        row = min(device["points"], key=lambda item: abs(item["f_ghz"] - 0.5))
        w = 2.0 * math.pi * row["f_ghz"] * 1e9
        z_ref = series_impedance(np.array([row["f_ghz"]]))[0]
        for key, expected in (("r_ohm", z_ref.real),
                              ("l_nh", z_ref.imag / w * 1e9),
                              ("q", z_ref.imag / z_ref.real)):
            actual = row[key]
            if abs(actual - expected) > 1e-6 * max(1.0, abs(expected)):
                issues.append(f"{key}: {actual:.9g} vs analytic {expected:.9g}")
        srf = device["srf_ghz"]
        if srf is None or abs(srf - expected_srf()) > 0.01 * expected_srf():
            issues.append(f"SRF {srf} vs analytic {expected_srf():.4f} GHz")
        if report["calibration_status"] != "UNCALIBRATED":
            issues.append("status without a reference must stay UNCALIBRATED")
    cases.append({"case": "analytic FOM + SRF", "status": "PASS" if not issues else "FAIL",
                  "issues": issues})

    corner = directory / "corner_slow.csv"
    write_palace_csv(corner, FREQS, series_impedance(FREQS) * 1.05)
    pvt_path = directory / "pvt.json"
    run_tool("inductor", "--sparam", f"typ={golden}", "--sparam", f"slow={corner}",
             "--freq", "0.5", "--json", str(pvt_path))
    issues = []
    if not pvt_path.is_file():
        issues.append("no PVT report")
    else:
        pvt = json.loads(pvt_path.read_text())["pvt"]["relative_spread"]
        for key in ("r_ohm", "l_nh"):
            if abs(pvt[key] - 0.05) > 1e-6:
                issues.append(f"{key} spread {pvt[key]:.6f} != 0.05")
    cases.append({"case": "PVT spread", "status": "PASS" if not issues else "FAIL",
                  "issues": issues})

    for name, expected in (("self", "CALIBRATED"), ("detuned", "MISMATCH")):
        path = golden if name == "self" else detuned
        out = directory / f"reference_{name}.json"
        run = run_tool("inductor", "--sparam", f"golden={golden}",
                       "--reference", str(path), "--json", str(out))
        issues = []
        if not out.is_file():
            issues.append(f"no report (exit {run.returncode})")
        else:
            reference = json.loads(out.read_text())["reference"]
            if reference["status"] != expected:
                issues.append(f"status {reference['status']} != {expected}")
            if expected == "CALIBRATED" and reference["relative_error"]["L"] > 1e-9:
                issues.append("identical runs report a non-zero L error")
            if expected == "MISMATCH" and run.returncode == 0:
                issues.append("mismatch must exit nonzero")
        cases.append({"case": f"reference {name}", "status": "PASS" if not issues else "FAIL",
                      "issues": issues})
    return cases


def check_varactor(ngspice: str | None) -> dict:
    if not ngspice:
        return {"case": "varactor C(V,f)", "status": "SKIP",
                "issues": ["ngspice unavailable"]}
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "varactor.json"
        run = run_tool("varactor", "--corners", "tt_var", "ss_var", "ff_var",
                       "--freqs", "0.1", "10", "--bias-step", "0.8",
                       "--ngspice", ngspice, "--json", str(out))
        report = json.loads(out.read_text()) if out.is_file() else None
    issues = []
    if run.returncode != 0 or report is None:
        issues.append(f"tool failed (exit {run.returncode}): "
                      f"{(run.stdout + run.stderr).strip()[-500:]}")
    else:
        for corner, data in report["corners"].items():
            if data["status"] != "PASS":
                issues.append(f"{corner}: {'; '.join(data['issues'])}")
                continue
            values = [point["c_ff"] for point in data["points"]]
            if min(values) <= 0 or not all(math.isfinite(value) for value in values):
                issues.append(f"{corner}: non-physical capacitance")
            ratio = data["per_freq"]["0.1"]["tuning_ratio"]
            if not 1.5 <= ratio <= 20:
                issues.append(f"{corner}: implausible tuning ratio {ratio:.2f}")
            if report["calibration_status"] != "UNCALIBRATED":
                issues.append("C(V,f) without a measured reference must stay UNCALIBRATED")
    return {"case": "varactor C(V,f)", "status": "PASS" if not issues else "FAIL",
            "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default=shutil.which("ngspice"))
    args = parser.parse_args()
    if not TOOL.is_file():
        print(f"FAIL: missing {TOOL}")
        return 1

    with tempfile.TemporaryDirectory() as directory:
        cases = check_inductor(Path(directory))
    cases.append(check_varactor(args.ngspice))
    failed = [case for case in cases if case["status"] == "FAIL"]
    for case in cases:
        detail = "" if not case["issues"] else " " + "; ".join(case["issues"])
        print(f"{case['status']}: {case['case']}{detail}")
    print(f"{'FAIL' if failed else 'PASS'}: RF calibration harness "
          f"({len(cases) - len(failed)}/{len(cases)} checks)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
