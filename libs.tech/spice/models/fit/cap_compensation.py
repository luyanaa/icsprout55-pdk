#!/usr/bin/env python3
"""Measure Liberty pin-capacitance gaps and emit bias/flavor Cwire wrappers.

The BSIM4 core remains a single baseline card per VT flavor. This tool does
not customize or split the core ``DLC``, ``DWC``, ``CF``, or ``VFBCV`` fields.
Instead it probes the immutable core at explicit static working biases and
emits separate per-flavor/per-bias Cwire wrapper subcircuits. The default
``bound`` policy records any raw Cmodel excess over Liberty Cpin and emits a
zero-Cwire wrapper for export feasibility; it does not claim a physical C-V
repair. ``raw`` preserves the negative residual and ``reject`` omits it.
The wrapper profile is a packaging choice: it adds the cell-boundary Liberty
residual without changing DC leakage or the core model.

For one Liberty pin-capacitance number, only the small-signal residual at the
selected bias is identified. A nonzero ``--alpha`` remains an explicit
behavioral extrapolation around that profile, not a foundry extraction.
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
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FITTED = HERE.parent / "fitted" / "FIT_PARAMS.json"
PM = Path(os.path.expanduser("~/Downloads/45nm_LP.pm"))
XYCE = os.environ.get("XYCE", "/usr/local/XyceNF_OMPI_7.10/bin/Xyce")
FLAVORS = ("svt", "lvt", "hvt")
FLAVOR_SUFFIX = {"svt": "H7R", "lvt": "H7L", "hvt": "H7H"}
DEFAULT_CELLS = ("INVX1", "INVX3", "INVX4")
VDD = 1.2
TEMP_C = 25.0
FREQ_HZ = 1.0e6
BIAS_V = 0.0
DEFAULT_BIASES = (BIAS_V, VDD / 2.0)
CMODEL_POLICIES = ("raw", "bound", "reject")
WRAPPER_CWIRE_STATUSES = frozenset(("ok", "bounded"))
FROZEN_CORE_CV_PARAMETERS = (
    "capmod", "cgso", "cgdo", "cgbo", "cgsl", "cgdl",
    "ckappas", "ckappad", "moin", "noff", "voffcv",
    "dlc", "dwc", "cf", "vfbcv",
)

sys.path.insert(0, str(HERE))
import drive  # noqa: E402
import fit_expanded as fx  # noqa: E402
import simulate as sm  # noqa: E402


class ProbeError(RuntimeError):
    """Raised when Xyce cannot produce a valid AC probe result."""


def _load_fitted() -> Mapping[str, object]:
    raw = json.loads(FITTED.read_text())
    return raw.get("flavors", raw)


def _load_start() -> Mapping[str, object]:
    return fx.load_fit_start(FITTED)


def _assert_core_cv_policy(
    flavor: str,
    drive_row: Mapping[str, object],
) -> None:
    """Reject shipped-manifest overrides that split the frozen CV core."""
    violations = []
    for device in ("overrides_n", "overrides_p"):
        values = drive_row.get(device, {})
        if not isinstance(values, Mapping):
            continue
        for parameter in values:
            if str(parameter).lower() in FROZEN_CORE_CV_PARAMETERS:
                violations.append("%s.%s" % (device, parameter))
    if violations:
        raise ValueError(
            "flavor %s violates the baseline core CV freeze: %s"
            % (flavor, ", ".join(sorted(violations)))
        )

def model_cards(flavor: str, n_overrides: Mapping[str, float] | None = None,
                p_overrides: Mapping[str, float] | None = None) -> str:
    """Render one baseline flavor card plus explicit temporary overrides.

    The checked-in flavor manifest may not override any frozen core C-V
    parameter.  ``n_overrides``/``p_overrides`` remain available to diagnostic
    scripts such as ``cv_core_sweep.py``; they are never used by wrapper
    generation.
    """
    fitted = _load_fitted()
    start = _load_start()
    legacy = fx.legacy_values(start, flavor)
    row = fitted[flavor]
    drive_row = row.get("drive", {})
    _assert_core_cv_policy(flavor, drive_row)
    n = dict(drive_row.get("overrides_n", {}))
    p = dict(drive_row.get("overrides_p", {}))
    n.update(n_overrides or {})
    p.update(p_overrides or {})
    return sm.make_model_cards(
        PM,
        "nm1p2_%s_lp" % flavor,
        "pm1p2_%s_lp" % flavor,
        vth0n=legacy["vth0n"],
        vth0p=legacy["vth0p"],
        dibl_scale_n=legacy["dibl_n"],
        dibl_scale_p=legacy["dibl_p"],
        voff_scale_n=legacy["voff_n"],
        voff_scale_p=legacy["voff_p"],
        overrides_n=n,
        overrides_p=p,
    )


def _node_map(entry: Mapping[str, object]) -> Dict[str, str]:
    result = {"VDD": "vdd", "VSS": "0", "0": "0"}
    for pin in entry["pins"]:
        if pin not in result:
            result[str(pin)] = "x_%s" % pin
    return result


def _ac_deck(cards: str, entry: Mapping[str, object], input_pin: str,
             rail: str, cwire_f: float = 0.0, alpha: float = 0.0,
             bias_v: float = BIAS_V, freq_hz: float = FREQ_HZ) -> str:
    pin_nodes = _node_map(entry)
    if input_pin not in pin_nodes:
        raise ProbeError("input pin %s not found in %s" % (input_pin, entry["pins"]))
    input_node = pin_nodes[input_pin]
    lines = [
        "* ICS55 AC input-capacitance probe",
        ".options device temp=%g" % TEMP_C,
        cards.rstrip(),
        "VDD vdd 0 %.12g" % VDD,
    ]
    # Bias every input low and clamp every output high.  For the default INV
    # set this is the stable output-high state used by the existing probe.
    for pin in entry["inputs"]:
        node = pin_nodes[str(pin)]
        if str(pin) == input_pin:
            lines.append("VIN %s 0 DC %.12g AC 1" % (node, bias_v))
        else:
            lines.append("VBIAS_%s %s 0 DC %.12g" % (pin, node, bias_v))
    input_names = {str(pin) for pin in entry["inputs"]}
    for pin in entry["pins"]:
        pin = str(pin)
        if pin in input_names or pin in {"VDD", "VSS"}:
            continue
        lines.append("VCLAMP_%s %s 0 DC %.12g" % (pin, pin_nodes[pin], VDD))
    if cwire_f:
        if rail not in {"VSS", "VDD"}:
            raise ValueError("rail must be VSS or VDD")
        rail_node = "0" if rail == "VSS" else "vdd"
        # C0 is exact at the probe bias.  Alpha has units 1/V and is optional.
        # Keeping the bias offset explicit prevents a nonzero alpha from
        # changing the fitted small-signal value at the calibration point.
        expression = "%.17g*(1+%.17g*(V(%s)-%.17g))" % (
            cwire_f, alpha, input_node, bias_v)
        lines.append("Cwire %s %s C={%s}" % (input_node, rail_node, expression))
    for mline in entry["netlist"]:
        parts = mline.split()
        if len(parts) < 7:
            raise ProbeError("unexpected CDL MOS line: %s" % mline)
        dev = parts[0]
        nodes = parts[1:5]
        model = parts[5]
        attrs = " ".join(parts[6:])
        lines.append(
            "M%s %s %s %s" % (
                dev,
                " ".join(pin_nodes.get(node, "x_%s" % node) for node in nodes),
                model,
                attrs,
            )
        )
    lines.extend([
        ".ac lin 1 %.12g %.12g" % (freq_hz, freq_hz),
        ".print ac I(VIN)",
        ".end",
    ])
    return "\n".join(lines) + "\n"


def _run_ac(deck: str) -> float:
    fd, path = tempfile.mkstemp(suffix=".cir")
    os.close(fd)
    deck_path = Path(path)
    deck_path.write_text(deck)
    env = dict(os.environ)
    env["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib"
    try:
        result = subprocess.run(
            [XYCE, str(deck_path)],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        output = result.stdout + result.stderr
        if result.returncode:
            raise ProbeError("Xyce AC failed:\n%s" % output[-2000:])
        reports = sorted(deck_path.parent.glob(deck_path.name + ".*.prn"))
        if not reports:
            raise ProbeError("Xyce AC produced no .FD.prn output")
        row = None
        for line in reports[0].read_text().splitlines():
            fields = line.split()
            if fields and fields[0].isdigit():
                row = fields
        if row is None or len(row) < 4:
            raise ProbeError("Xyce AC output contains no data row")
        # Index, frequency, Re(I(VIN)), Im(I(VIN)).
        return float(row[3])
    finally:
        for candidate in [deck_path, *deck_path.parent.glob(deck_path.name + ".*.prn")]:
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass


def ac_cap_pf(cards: str, entry: Mapping[str, object], input_pin: str,
              rail: str = "VSS", cwire_f: float = 0.0,
              alpha: float = 0.0, bias_v: float = BIAS_V,
              freq_hz: float = FREQ_HZ) -> float:
    """Return small-signal input capacitance in pF at one DC bias/frequency."""
    imag_current = _run_ac(
        _ac_deck(
            cards,
            entry,
            input_pin,
            rail,
            cwire_f,
            alpha,
            bias_v=bias_v,
            freq_hz=freq_hz,
        )
    )
    return abs(imag_current) / (2.0 * math.pi * freq_hz) * 1.0e12


def _linear_fit(rows: Sequence[Mapping[str, object]]) -> Tuple[float, float]:
    pairs = [
        (float(row["width_um"]), float(row["cwire_pf"]))
        for row in rows
    ]
    if len(pairs) < 2:
        return pairs[0][1], 0.0
    xbar = sum(x for x, _ in pairs) / len(pairs)
    ybar = sum(y for _, y in pairs) / len(pairs)
    denom = sum((x - xbar) ** 2 for x, _ in pairs)
    slope = (
        sum((x - xbar) * (y - ybar) for x, y in pairs) / denom
        if denom else 0.0
    )
    return ybar - slope * xbar, slope


def measure(flavor: str, cells: Iterable[str], rail: str,
            alpha: float = 0.0, bias_v: float = BIAS_V,
            datasets: Sequence[str] = ("fit",),
            cmodel_policy: str = "bound") -> Dict[str, object]:
    """Measure one flavor at one static working bias."""
    if cmodel_policy not in CMODEL_POLICIES:
        raise ValueError(
            "cmodel_policy must be one of %s" % ", ".join(CMODEL_POLICIES)
        )
    data = {}
    for dataset in datasets:
        data.update(drive.load_data(flavor, dataset))
    cards = model_cards(flavor)
    rows: List[Dict[str, object]] = []
    for base_cell in cells:
        key = base_cell + FLAVOR_SUFFIX[flavor]
        if key not in data:
            raise KeyError("extracted cell not found: %s" % key)
        entry = data[key]
        for pin_value in entry["inputs"]:
            pin = str(pin_value)
            c_model_raw_pf = ac_cap_pf(
                cards, entry, pin, rail=rail, bias_v=bias_v,
            )
            c_lib_pf = float(entry["caps"][pin])
            cmodel_bound_applied = c_model_raw_pf > c_lib_pf
            if cmodel_bound_applied and cmodel_policy == "reject":
                c_model_effective_pf = c_model_raw_pf
                cwire_pf = c_lib_pf - c_model_raw_pf
                cwire_status = "negative_residual"
            elif cmodel_bound_applied and cmodel_policy == "bound":
                c_model_effective_pf = c_lib_pf
                cwire_pf = 0.0
                cwire_status = "bounded"
            else:
                c_model_effective_pf = c_model_raw_pf
                cwire_pf = c_lib_pf - c_model_raw_pf
                cwire_status = "ok" if cwire_pf >= 0.0 else "negative_residual"
            row = {
                "flavor": flavor,
                "cell": base_cell,
                "entry_key": key,
                "pin": pin,
                "pins": [str(value) for value in entry["pins"]],
                "width_um": (float(entry["wn"]) + float(entry["wp"])) * 1e6,
                "c_liberty_pf": c_lib_pf,
                "c_model_ac_probe_pf": c_model_raw_pf,
                "c_model_effective_pf": c_model_effective_pf,
                "c_model_excess_pf": max(c_model_raw_pf - c_lib_pf, 0.0),
                "cmodel_policy": cmodel_policy,
                "cmodel_bound_applied": cmodel_bound_applied,
                "cwire_pf": cwire_pf,
                "cwire_status": cwire_status,
                "compensated_ratio": None,
                "probe_bias_v": bias_v,
                "probe_frequency_hz": FREQ_HZ,
                "rail": rail,
                "alpha_per_v": alpha,
            }
            if cwire_status in WRAPPER_CWIRE_STATUSES:
                c_comp_pf = ac_cap_pf(
                    cards,
                    entry,
                    pin,
                    rail=rail,
                    cwire_f=cwire_pf * 1e-12,
                    alpha=alpha,
                    bias_v=bias_v,
                )
                row["compensated_model_pf"] = c_comp_pf
                row["compensated_ratio"] = c_comp_pf / c_lib_pf
            else:
                row["compensated_model_pf"] = None
            rows.append(row)
    intercept, slope = _linear_fit(rows)
    for row in rows:
        row["linear_cwire_pf"] = intercept + slope * float(row["width_um"])
        row["linear_residual_pf"] = (
            float(row["linear_cwire_pf"]) - float(row["cwire_pf"])
        )
    return {
        "schema_version": 2,
        "kind": "ics55_cwire_capacitance_compensation",
        "flavor": flavor,
        "datasets": list(datasets),
        "cmodel_policy": cmodel_policy,
        "model_manifest": str(FITTED),
        "probe": {
            "simulator": "Xyce 7.10",
            "frequency_hz": FREQ_HZ,
            "bias_v": bias_v,
            "vdd": VDD,
            "temperature_c": TEMP_C,
            "rail": rail,
            "alpha_per_v": alpha,
            "nonlinearity_note": (
                "Only the small-signal value at the probe bias is identified "
                "from one Liberty capacitance number; nonzero alpha is an "
                "explicit behavioral extrapolation."
            ),
        },
        "cells": rows,
        "linear_width_fit": {
            "cwire_pf = intercept_pf + slope_pf_per_um * width_um": True,
            "intercept_pf": intercept,
            "slope_pf_per_um": slope,
        },
    }


def _spice_value(value: float) -> str:
    return "%.17g" % float(value * 1e-12)


def _bias_token(value: float) -> str:
    """Return a SPICE-safe, stable token for a working-bias value."""
    magnitude = ("%.6f" % abs(float(value))).rstrip("0").rstrip(".")
    magnitude = magnitude.replace(".", "P") or "0"
    return "BM%s" % magnitude if value < 0.0 else "BP%s" % magnitude


def wrapper_subckt_name(row: Mapping[str, object]) -> str:
    """Return a unique wrapper name for one flavor/bias/cell/pin profile."""
    flavor = str(row.get("flavor", "")).upper()
    key = str(row["entry_key"])
    bias = _bias_token(float(row["probe_bias_v"]))
    pin = re.sub(r"[^A-Za-z0-9_]", "_", str(row["pin"]))
    profile = "_".join(value for value in (flavor, bias) if value)
    return "%s_CWIRE_%s_%s" % (key, profile, pin)


def emit_wrappers(report: Mapping[str, object], out_path: Path) -> None:
    """Emit all selected flavor/bias wrapper subcircuits."""
    rows = report.get("cells", report.get("rows", []))
    lines = [
        "* ICS55 generated Cwire wrappers; released CDL and BSIM4 core are unchanged.",
        "* Include after the original CDL and instantiate the selected profile.",
        "* Names encode VT flavor and static working bias.",
        "* Cwire is calibrated at that profile bias; alpha is behavioral.",
        "",
    ]
    for row in rows:
        if row["cwire_status"] not in WRAPPER_CWIRE_STATUSES:
            continue
        cwire_pf = float(row["cwire_pf"])
        if not math.isfinite(cwire_pf) or cwire_pf < 0.0:
            raise ValueError(
                "wrapper Cwire must be finite and non-negative: %s" %
                row["entry_key"]
            )
        key = str(row["entry_key"])
        pin = str(row["pin"])
        cell_name = str(row.get("wrapper_subckt") or wrapper_subckt_name(row))
        pins = [str(value) for value in row["pins"]]
        core = "XCORE %s %s" % (" ".join(pins), key)
        rail = str(row["rail"])
        expression = "%s*(1+%s*(V(%s)-%.17g))" % (
            _spice_value(cwire_pf),
            float(row["alpha_per_v"]),
            pin,
            float(row["probe_bias_v"]),
        )
        lines.extend([
            ".SUBCKT %s %s" % (cell_name, " ".join(pins)),
            core,
            "CWI_%s_%s_%s %s %s C={%s}" % (
                key,
                _bias_token(float(row["probe_bias_v"])),
                pin,
                pin,
                rail,
                expression,
            ),
            ".ENDS %s" % cell_name,
            "",
        ])
    out_path.write_text("\n".join(lines))


def _parse_biases(text: str) -> Tuple[float, ...]:
    values = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("working bias must be finite: %s" % token)
        if not any(math.isclose(value, old, rel_tol=1e-12, abs_tol=1e-12)
                   for old in values):
            values.append(value)
    if not values:
        raise ValueError("at least one working bias is required")
    return tuple(values)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavors", nargs="+", choices=FLAVORS, default=list(FLAVORS))
    parser.add_argument("--cells", default=",".join(DEFAULT_CELLS))
    parser.add_argument(
        "--datasets",
        default="fit",
        help="comma-separated extracted-data splits used to find requested cells",
    )
    parser.add_argument("--rail", choices=("VSS", "VDD"), default="VSS")
    parser.add_argument(
        "--biases",
        default=",".join("%.12g" % value for value in DEFAULT_BIASES),
        help="comma-separated static working-bias profiles in volts "
             "(default: 0,VDD/2 = 0.6)",
    )
    parser.add_argument(
        "--records-bias",
        type=float,
        help="bias used for flat cell_parasitics records; defaults to the first profile",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.0,
        help="optional Cwire voltage coefficient in 1/V; default is static per-profile Cwire",
    )
    parser.add_argument(
        "--cmodel-policy",
        choices=CMODEL_POLICIES,
        default="bound",
        help="raw, reject, or bound Cmodel to Liberty before wrapper export",
    )
    parser.add_argument("--out", type=Path, required=True,
                        help="JSON capacitance-gap report")
    parser.add_argument("--spice-out", type=Path,
                        help="optional multi-profile Cwire wrapper subcircuit file")
    args = parser.parse_args()
    cells = tuple(cell.strip() for cell in args.cells.split(",") if cell.strip())
    if not cells:
        parser.error("--cells must contain at least one cell")
    datasets = tuple(dataset.strip() for dataset in args.datasets.split(",") if dataset.strip())
    if not datasets:
        parser.error("--datasets must contain at least one split")
    try:
        biases = _parse_biases(args.biases)
    except ValueError as exc:
        parser.error(str(exc))
    record_bias = biases[0] if args.records_bias is None else args.records_bias
    if not any(math.isclose(record_bias, bias, rel_tol=1e-12, abs_tol=1e-12)
               for bias in biases):
        parser.error("--records-bias must match one of --biases")

    flavor_reports = []
    profiles = []
    for flavor in args.flavors:
        bias_reports = [
            measure(
                flavor,
                cells,
                args.rail,
                alpha=args.alpha,
                bias_v=bias,
                datasets=datasets,
                cmodel_policy=args.cmodel_policy,
            )
            for bias in biases
        ]
        flavor_reports.append({
            "flavor": flavor,
            "profiles": bias_reports,
        })
        profiles.extend(bias_reports)
    rows = [
        row for profile in profiles
        for row in profile["cells"]
    ]
    for row in rows:
        row["wrapper_subckt"] = wrapper_subckt_name(row)
    selected_rows = [
        row for row in rows
        if math.isclose(
            float(row["probe_bias_v"]),
            record_bias,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    ]
    report = {
        "schema_version": 2,
        "kind": "ics55_cwire_capacitance_compensation_batch",
        "core_cv_policy": {
            "mode": "single baseline BSIM4 card per VT flavor",
            "frozen_parameters": list(FROZEN_CORE_CV_PARAMETERS),
            "customized_core_parameters": [],
            "wrapper_owns": ["cell_boundary_residual", "working_bias", "vt_flavor"],
        },
        "working_biases_v": list(biases),
        "datasets": list(datasets),
        "cmodel_policy": args.cmodel_policy,
        "flavors": flavor_reports,
        "wrapper_profiles": [
            {
                "flavor": flavor,
                "bias_v": bias,
                "subcircuits": [
                    row["wrapper_subckt"]
                    for row in rows
                    if row["flavor"] == flavor
                    and math.isclose(
                        float(row["probe_bias_v"]),
                        bias,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    )
                ],
            }
            for flavor in args.flavors
            for bias in biases
        ],
        "records_profile": {
            "bias_v": record_bias,
            "flavors": list(args.flavors),
        },
        # This flat form is accepted directly by cell_parasitics.py. It
        # selects one explicit working-bias profile to avoid duplicate keys.
        "records": [
            {
                "cell": row["entry_key"],
                "pin": row["pin"],
                "c_intrinsic_pf": row["c_model_ac_probe_pf"],
                "flavor": row["flavor"],
                "probe_bias_v": row["probe_bias_v"],
            }
            for row in selected_rows
        ],
    }
    args.out.expanduser().write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(args.out.expanduser())
    if args.spice_out:
        emit_wrappers({"cells": rows}, args.spice_out.expanduser())
        print(args.spice_out.expanduser())


if __name__ == "__main__":
    main()
