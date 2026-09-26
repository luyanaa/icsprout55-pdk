#!/usr/bin/env python3
"""Analyze LVT timing residuals with finite-driver and Cwire variants.

The released timing evaluator is inverter-specific: the current RC-aware
calibration and its holdout2 timing point use INVX1/3/4 and INVX20. This tool
expands that same Xyce deck over every Liberty slew/load point for those
inverters, records manual-GDS output-net R/C features, and compares ideal-source
and finite-driver decks with and without a formal local Cwire wrapper. The
finite-driver path accepts one driver or a driver-strength sweep; fitted
splits are preferred and released CDL/Liberty source is used for a valid cell
that is absent from the generated splits. Finite-driver decks precondition the
driver/DUT operating point before measuring either pulse edge, and finite-driver
delay and transition targets are interpolated at the measured DUT-input slew
rather than the unbuffered source slew. Raw relative metrics are retained,
including direct RMS percentage errors; a delay-floor metric makes tiny targets
auditable without allowing them to dominate the aggregate.
Invalid Liberty targets, simulation failures, and unavailable wrappers remain
explicit.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FLAVOR = "lvt"
TRAIN_CELLS = ("INVX1", "INVX3", "INVX4")
HOLDOUT_CELLS = ("INVX20",)
DIRECTIONS = ("rise", "fall")
TIMING_VARIANTS = ("baseline", "cwire", "driver", "driver_cwire")
CNET_TARGET_BAND_PF = (0.00035, 0.00100)
SOURCE_TAG = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}

sys.path.insert(0, str(HERE))
import cap_compensation as cc  # noqa: E402
import drive  # noqa: E402
import fit_drive  # noqa: E402
import extract_data as source_extract  # noqa: E402


NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"


def _isclose(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def _y_pin_block(liberty_text: str, cell: str) -> str:
    block = drive._cell_block(liberty_text, cell)
    match = re.search(
        r"\n    pin\s*\(Y\)\s*\{(.*?)(?=\n    pin\s*\(|\n  \})",
        block,
        re.DOTALL,
    )
    if not match:
        raise KeyError("Liberty output pin Y not found: %s" % cell)
    return match.group(1)


def _timing_grid(liberty_text: str, cell: str) -> List[Dict[str, object]]:
    """Expand rise/fall delay and transition tables into simulation points."""
    y_block = _y_pin_block(liberty_text, cell)
    rise_i1, rise_i2, rise = drive._table(y_block, "cell_rise")
    fall_i1, fall_i2, fall = drive._table(y_block, "cell_fall")
    rise_t_i1, rise_t_i2, rise_transition = drive._table(
        y_block, "rise_transition",
    )
    fall_t_i1, fall_t_i2, fall_transition = drive._table(
        y_block, "fall_transition",
    )
    if (
        rise_i1 != fall_i1
        or rise_i2 != fall_i2
        or rise_i1 != rise_t_i1
        or rise_i2 != rise_t_i2
        or rise_i1 != fall_t_i1
        or rise_i2 != fall_t_i2
    ):
        raise ValueError("Liberty timing indexes differ: %s" % cell)
    rows = []
    for direction, values, transition_values in (
        ("rise", rise, rise_transition),
        ("fall", fall, fall_transition),
    ):
        for row_index, slew_ns in enumerate(rise_i1):
            for load_index, load_pf in enumerate(rise_i2):
                rows.append({
                    "direction": direction,
                    "input_slew_ns": slew_ns,
                    "c_load_pf": load_pf,
                    "target_ns": values[row_index][load_index],
                    "target_output_slew_ns":
                        transition_values[row_index][load_index],
                    "_slew_index": rise_i1,
                    "_load_index": rise_i2,
                    "_delay_table": values,
                    "_transition_table": transition_values,
                })
    return rows


def _interpolate_table(
    index_1: Sequence[float],
    index_2: Sequence[float],
    values: Sequence[Sequence[float]],
    x_value: float,
    y_value: float,
) -> Tuple[float, bool]:
    """Bilinearly interpolate a Liberty table, clamping outside its grid."""
    def bracket(index: Sequence[float], value: float):
        if value < index[0]:
            return 0, 0, True
        if value > index[-1]:
            last = len(index) - 1
            return last, last, True
        for position in range(len(index) - 1):
            left, right = index[position], index[position + 1]
            if left <= value <= right:
                return position, position + 1, False
        last = len(index) - 1
        return last, last, False

    x0, x1, x_clamped = bracket(index_1, x_value)
    y0, y1, y_clamped = bracket(index_2, y_value)
    x_fraction = 0.0 if x0 == x1 else (
        x_value - index_1[x0]
    ) / (index_1[x1] - index_1[x0])
    y_fraction = 0.0 if y0 == y1 else (
        y_value - index_2[y0]
    ) / (index_2[y1] - index_2[y0])
    lower = (
        values[x0][y0] * (1.0 - y_fraction)
        + values[x0][y1] * y_fraction
    )
    upper = (
        values[x1][y0] * (1.0 - y_fraction)
        + values[x1][y1] * y_fraction
    )
    return (
        lower * (1.0 - x_fraction) + upper * x_fraction,
        x_clamped or y_clamped,
    )


def _load_driver_entry(base_cell: str):
    """Load a driver from a fitted split or directly from released sources."""
    key = base_cell + cc.FLAVOR_SUFFIX[FLAVOR]
    for dataset in ("train37", "fit"):
        data = drive.load_data(FLAVOR, dataset)
        if key in data:
            return data[key], dataset
    source_tag = SOURCE_TAG[FLAVOR]
    source_base = (
        ROOT / "libs.ref" / ("ics55_LLSC_%s" % source_tag)
    )
    cdl = source_base / "cdl" / ("ics55_LLSC_%s.cdl" % source_tag)
    liberty = source_base / "liberty" / (
        "ics55_LLSC_%s_typ_tt_1p2_25_nldm.lib" % source_tag
    )
    source_data = source_extract.extract_records(
        FLAVOR, str(cdl), str(liberty), [key],
    )
    if key not in source_data:
        raise KeyError("driver cell is absent from released sources: %s" % base_cell)
    return source_data[key], "released_source"

def _load_cwire_profile(path: Path, flavor: str, bias_v: float,
                        cells: Sequence[str]) -> Dict[Tuple[str, str], Dict[str, object]]:
    raw = json.loads(path.expanduser().read_text())
    for flavor_report in raw.get("flavors", []):
        if flavor_report.get("flavor") != flavor:
            continue
        for profile in flavor_report.get("profiles", []):
            probe = profile.get("probe", {})
            if not _isclose(float(probe.get("bias_v")), bias_v):
                continue
            result = {}
            for row in profile.get("cells", []):
                if row.get("cell") in cells:
                    result[(str(row["entry_key"]), str(row["pin"]))] = row
            missing = [
                cell for cell in cells
                if (cell + cc.FLAVOR_SUFFIX[flavor], "A") not in result
            ]
            if missing:
                raise KeyError(
                    "Cwire profile %.6g V lacks input A for %s"
                    % (bias_v, ", ".join(missing))
                )
            return result
    raise KeyError("Cwire profile not found: flavor=%s bias=%.12g" % (flavor, bias_v))


def _rc_features(base_cell: str, entry: Mapping[str, object]):
    signal_pins = tuple(sorted(
        str(pin) for pin in entry["pins"] if str(pin) not in {"VDD", "VSS"}
    ))
    rc_model = drive.load_rc_model(FLAVOR, base_cell, signal_pins)
    if rc_model.has_unmapped_interconnect:
        raise RuntimeError(
            "RC extraction left unmapped interconnect in %s: %s"
            % (base_cell, rc_model.unmapped_interconnect)
        )
    output = rc_model.pins.get("Y")
    if output is None:
        raise KeyError("output pin Y has no RC record: %s" % base_cell)
    return rc_model, {
        "r_net_ohm": output.resistance_ohm,
        "c_net_pf": output.capacitance_pf,
        "r_input_ohm": rc_model.pins["A"].resistance_ohm,
        "c_input_pf": rc_model.pins["A"].capacitance_pf,
    }


def _quantiles(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        return {}
    ordered = sorted(float(value) for value in values)
    last = len(ordered) - 1
    return {
        str(level): ordered[int(round(level * last))]
        for level in (0.0, 0.25, 0.5, 0.75, 0.95, 1.0)
    }


def _rc_space(rows: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    return {
        "n": len(rows),
        "r_net_ohm": _quantiles([float(row["r_net_ohm"]) for row in rows]),
        "c_net_pf": _quantiles([float(row["c_net_pf"]) for row in rows]),
    }

def _cnet_band(rows: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    low_pf, high_pf = CNET_TARGET_BAND_PF
    selected = [
        row for row in rows
        if row["has_output_y"]
        and low_pf <= float(row["c_net_pf"]) <= high_pf
    ]
    safe = [row for row in selected if row["mapped_for_timing"]]
    return {
        "range_pf": [low_pf, high_pf],
        "range_ff": [1000.0 * low_pf, 1000.0 * high_pf],
        "n_output_y": len(selected),
        "n_timing_safe": len(safe),
        "output_y_cells": sorted(str(row["cell"]) for row in selected),
        "timing_safe_cells": sorted(str(row["cell"]) for row in safe),
    }


def _rc_coverage(dataset: str) -> Dict[str, object]:
    """Summarize output-Y RC features, including unmapped records."""
    data = drive.load_data(FLAVOR, dataset)
    suffix = cc.FLAVOR_SUFFIX[FLAVOR]
    rows = []
    for entry_key in sorted(data):
        if not entry_key.endswith(suffix):
            continue
        base_cell = entry_key[:-len(suffix)]
        entry = data[entry_key]
        signal_pins = tuple(sorted(
            str(pin) for pin in entry["pins"] if str(pin) not in {"VDD", "VSS"}
        ))
        rc_model = drive.load_rc_model(FLAVOR, base_cell, signal_pins)
        output = rc_model.pins.get("Y")
        record = {
            "cell": base_cell,
            "has_output_y": output is not None,
            "mapped_for_timing": (
                output is not None and not rc_model.has_unmapped_interconnect
            ),
            "interconnect_mapping": dict(rc_model.mapping_counts),
            "unmapped_interconnect": list(rc_model.unmapped_interconnect),
            "warnings": list(rc_model.warnings),
        }
        if output is not None:
            record.update({
                "r_net_ohm": output.resistance_ohm,
                "c_net_pf": output.capacitance_pf,
            })
        rows.append(record)
    output_rows = [row for row in rows if row["has_output_y"]]
    mapped_rows = [row for row in output_rows if row["mapped_for_timing"]]
    mapping_totals = defaultdict(int)
    for row in rows:
        for key, value in row["interconnect_mapping"].items():
            mapping_totals[key] += int(value)
    return {
        "dataset": dataset,
        "n_entries": len(rows),
        "n_output_y": len(output_rows),
        "n_missing_output_y": len(rows) - len(output_rows),
        "n_fully_mapped": len(mapped_rows),
        "n_with_unmapped_interconnect": sum(
            bool(row["unmapped_interconnect"]) for row in rows
        ),
        "interconnect_mapping_polygon_totals": dict(sorted(mapping_totals.items())),
        "cnet_target_band": _cnet_band(rows),
        "feature_space_all_output_y": _rc_space(output_rows),
        "timing_safe_space_mapped_output_y": _rc_space(mapped_rows),
        "unmapped_examples": [
            row for row in rows if row["unmapped_interconnect"]
        ][:10],
    }


def _residual(
    simulated_ns: float, target_ns: float, delay_floor_ps: float,
) -> Dict[str, float]:
    signed_ps = (simulated_ns - target_ns) * 1000.0
    relative = simulated_ns / target_ns - 1.0
    denominator_ps = max(abs(target_ns * 1000.0), delay_floor_ps)
    floor_relative = signed_ps / denominator_ps
    return {
        "simulated_ns": simulated_ns,
        "signed_error_ps": signed_ps,
        "absolute_error_ps": abs(signed_ps),
        "relative_error": relative,
        "signed_relative_error_pct": 100.0 * relative,
        "absolute_relative_error_pct": 100.0 * abs(relative),
        "floor_weighted_relative_error": floor_relative,
        "floor_weighted_relative_error_pct": 100.0 * floor_relative,
        "floor_weighted_absolute_relative_error_pct": 100.0 * abs(floor_relative),
        "log10_ratio": math.log10(simulated_ns / target_ns),
    }


def _attach_transition_metrics(
    result: Dict[str, object],
    target_output_slew_ns: float,
    c_load_pf: float,
    vdd: float,
) -> None:
    measured = result.get("measured_output_slew_ns")
    if (
        not math.isfinite(target_output_slew_ns)
        or target_output_slew_ns <= 0.0
        or not isinstance(measured, (float, int))
        or not math.isfinite(float(measured))
        or float(measured) <= 0.0
    ):
        result["slew_status"] = "failed"
        result["slew_error"] = "missing positive transition measurement"
        return
    measured = float(measured)
    slew_relative = measured / target_output_slew_ns - 1.0
    result.update({
        "target_output_slew_ns": target_output_slew_ns,
        "slew_status": "ok",
        "slew_signed_error_ps": (measured - target_output_slew_ns) * 1000.0,
        "slew_absolute_error_ps": abs(measured - target_output_slew_ns) * 1000.0,
        "slew_signed_relative_error_pct": 100.0 * slew_relative,
        "slew_absolute_relative_error_pct": 100.0 * abs(slew_relative),
        "slew_log10_ratio": math.log10(measured / target_output_slew_ns),
    })
    if c_load_pf > 0.0 and math.isfinite(c_load_pf):
        target_current_ma = vdd * c_load_pf / target_output_slew_ns
        measured_current_ma = vdd * c_load_pf / measured
        current_relative = measured_current_ma / target_current_ma - 1.0
        result.update({
            "i_eff_status": "ok",
            "i_eff_target_ma": target_current_ma,
            "i_eff_simulated_ma": measured_current_ma,
            "i_eff_signed_relative_error_pct": 100.0 * current_relative,
            "i_eff_absolute_relative_error_pct": 100.0 * abs(current_relative),
            "i_eff_log10_ratio": math.log10(
                measured_current_ma / target_current_ma,
            ),
        })
    else:
        result["i_eff_status"] = "unavailable"
        result["i_eff_error"] = "zero or invalid output load"


def _retarget_result(
    result: Mapping[str, object],
    target_ns: float,
    target_output_slew_ns: float,
    c_load_pf: float,
    vdd: float,
    delay_floor_ps: float,
) -> Dict[str, object]:
    """Recompute target-relative metrics without rerunning Xyce."""
    if result.get("status") != "ok":
        return dict(result)
    simulated_ns = float(result["simulated_ns"])
    rebased = {
        "status": "ok",
        "target_ns": target_ns,
        **_residual(simulated_ns, target_ns, delay_floor_ps),
    }
    for key in ("measured_input_slew_ns", "measured_output_slew_ns"):
        rebased[key] = result.get(key)
    _attach_transition_metrics(
        rebased, target_output_slew_ns, c_load_pf, vdd,
    )
    return rebased


def _delay_residual(
    cards: str,
    entry: Mapping[str, object],
    kwargs: Mapping[str, object],
    target_ns: float,
    delay_floor_ps: float,
    target_output_slew_ns: float | None = None,
    c_load_pf: float | None = None,
    vdd: float = 1.2,
) -> Dict[str, object]:
    if not math.isfinite(target_ns) or target_ns <= 0.0:
        return {
            "status": "failed",
            "error": "non-positive or non-finite Liberty target: %.12g ns"
                    % target_ns,
        }
    try:
        measurement = drive.delay_measurement(cards, entry, **kwargs)
        simulated_ns = measurement["delay_seconds"] * 1e9
    except RuntimeError as exc:
        return {
            "status": "failed",
            "error": str(exc),
        }
    if not math.isfinite(simulated_ns) or simulated_ns <= 0.0:
        return {
            "status": "failed",
            "error": "non-positive or non-finite simulated delay: %.12g ns"
                    % simulated_ns,
        }
    result = {
        "status": "ok",
        "target_ns": target_ns,
        **_residual(simulated_ns, target_ns, delay_floor_ps),
    }
    result["measured_input_slew_ns"] = measurement["input_slew_ns"]
    result["measured_output_slew_ns"] = measurement["output_slew_ns"]
    if target_output_slew_ns is not None and c_load_pf is not None:
        _attach_transition_metrics(
            result, target_output_slew_ns, c_load_pf, vdd,
        )
    return result

def _failure_rows(
    rows: Sequence[Mapping[str, object]],
    variants: Sequence[str] = TIMING_VARIANTS,
) -> List[Dict[str, object]]:
    failures = []
    for row in rows:
        for variant in variants:
            result = row[variant]
            if result.get("status") == "ok":
                continue
            failures.append({
                "dataset": row["dataset"],
                "cell": row["cell"],
                "entry_key": row["entry_key"],
                "direction": row["direction"],
                "input_slew_ns": row["input_slew_ns"],
                "c_load_pf": row["c_load_pf"],
                "target_ns": row["target_ns"],
                "r_net_ohm": row["r_net_ohm"],
                "c_net_pf": row["c_net_pf"],
                "variant": variant,
                "error": result["error"],
            })
    return failures


def _finite_driver_residual(
    cards: str,
    entry: Mapping[str, object],
    kwargs: Mapping[str, object],
    point: Mapping[str, object],
    delay_floor_ps: float,
) -> Dict[str, object]:
    """Compare a finite-driver result at its actual DUT input slew."""
    c_load_pf = float(point["c_load_pf"])
    result = _delay_residual(
        cards,
        entry,
        kwargs,
        float(point["target_ns"]),
        delay_floor_ps,
    )
    if result.get("status") != "ok":
        return result
    measured_input_slew = result.get("measured_input_slew_ns")
    if not isinstance(measured_input_slew, (float, int)):
        result["status"] = "failed"
        result["error"] = "finite driver produced no DUT-input slew"
        return result
    target_delay, delay_clamped = _interpolate_table(
        point["_slew_index"],
        point["_load_index"],
        point["_delay_table"],
        float(measured_input_slew),
        c_load_pf,
    )
    target_slew, slew_clamped = _interpolate_table(
        point["_slew_index"],
        point["_load_index"],
        point["_transition_table"],
        float(measured_input_slew),
        c_load_pf,
    )
    result = _retarget_result(
        result,
        target_delay,
        target_slew,
        c_load_pf,
        1.2,
        delay_floor_ps,
    )
    result.update({
        "requested_input_slew_ns": float(point["input_slew_ns"]),
        "liberty_input_slew_ns": float(measured_input_slew),
        "liberty_input_slew_clamped": bool(delay_clamped or slew_clamped),
        "requested_target_ns": float(point["target_ns"]),
        "requested_target_output_slew_ns":
            float(point["target_output_slew_ns"]),
    })
    return result


def _simulate_cell(
    cards: str,
    data: Mapping[str, object],
    liberty_text: str,
    base_cell: str,
    dataset: str,
    cwire: Mapping[Tuple[str, str], Mapping[str, object]],
    bias_v: float,
    driver_entry: Mapping[str, object] | None = None,
    driver_rc_model=None,
    delay_floor_ps: float = 5.0,
) -> List[Dict[str, object]]:
    entry_key = base_cell + cc.FLAVOR_SUFFIX[FLAVOR]
    entry = data[entry_key]
    if tuple(str(pin) for pin in entry["inputs"]) != ("A",):
        raise ValueError("timing analysis requires one-input inverter: %s" % entry_key)
    rc_model, rc = _rc_features(base_cell, entry)
    cwire_row = cwire[(entry_key, "A")]
    cwire_pf = float(cwire_row["cwire_pf"])
    cwire_alpha = float(cwire_row.get("alpha_per_v", 0.0))
    cwire_available = cwire_row["cwire_status"] in cc.WRAPPER_CWIRE_STATUSES
    rows = []
    for point in _timing_grid(liberty_text, entry_key):
        direction = str(point["direction"])
        target_ns = float(point["target_ns"])
        kwargs = {
            "vdd": 1.2,
            "temp": 25,
            "slew_ns": float(point["input_slew_ns"]),
            "load_pf": float(point["c_load_pf"]),
            "direction": direction,
            "rc_model": rc_model,
        }
        driver_kwargs = dict(kwargs)
        if driver_entry is not None:
            driver_kwargs["driver_entry"] = driver_entry
            driver_kwargs["driver_rc_model"] = driver_rc_model
        base_error = _delay_residual(
            cards,
            entry,
            kwargs,
            target_ns,
            delay_floor_ps,
            float(point["target_output_slew_ns"]),
            float(point["c_load_pf"]),
        )
        driver_error = _finite_driver_residual(
            cards,
            entry,
            driver_kwargs,
            point,
            delay_floor_ps,
        ) if driver_entry is not None else {
            "status": "unavailable",
            "error": "finite driver was not configured",
        }
        if cwire_available:
            wrapper_kwargs = dict(kwargs)
            wrapper_kwargs.update({
                "cwire_pf": cwire_pf,
                "cwire_alpha": cwire_alpha,
                "cwire_bias_v": bias_v,
                "cwire_wrapper_subckt": cwire_row.get("wrapper_subckt"),
            })
            wrapper_error = _delay_residual(
                cards,
                entry,
                wrapper_kwargs,
                target_ns,
                delay_floor_ps,
                float(point["target_output_slew_ns"]),
                float(point["c_load_pf"]),
            )
            driver_wrapper_kwargs = dict(driver_kwargs)
            driver_wrapper_kwargs.update({
                "cwire_pf": cwire_pf,
                "cwire_alpha": cwire_alpha,
                "cwire_bias_v": bias_v,
                "cwire_wrapper_subckt": cwire_row.get("wrapper_subckt"),
            })
            driver_wrapper_error = _finite_driver_residual(
                cards,
                entry,
                driver_wrapper_kwargs,
                point,
                delay_floor_ps,
            ) if driver_entry is not None else {
                "status": "unavailable",
                "error": "finite driver was not configured",
            }
        else:
            unavailable = {
                "status": "unavailable",
                "error": "Cwire wrapper unavailable: %s" %
                        cwire_row["cwire_status"],
            }
            wrapper_error = dict(unavailable)
            driver_wrapper_error = dict(unavailable)
        rows.append({
            "dataset": dataset,
            "cell": base_cell,
            "entry_key": entry_key,
            "direction": direction,
            "input_slew_ns": point["input_slew_ns"],
            "c_load_pf": point["c_load_pf"],
            "target_ns": target_ns,
            "target_output_slew_ns": point["target_output_slew_ns"],
            "r_net_ohm": rc["r_net_ohm"],
            "c_net_pf": rc["c_net_pf"],
            "r_input_ohm": rc["r_input_ohm"],
            "c_input_pf": rc["c_input_pf"],
            "cwire_pf": cwire_pf,
            "cwire_bias_v": bias_v,
            "cwire_wrapper_subckt": cwire_row.get("wrapper_subckt"),
            "baseline": base_error,
            "cwire": wrapper_error,
            "driver": driver_error,
            "driver_cwire": driver_wrapper_error,
        })
    return rows


def _flatten_variant(rows: Iterable[Mapping[str, object]], variant: str):
    for row in rows:
        value = row[variant]
        result = dict(row)
        for name in TIMING_VARIANTS:
            result.pop(name, None)
        result["variant"] = variant
        result.update(value)
        yield result


def _summary(rows: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    valid = [row for row in rows if "log10_ratio" in row]
    failed = len(rows) - len(valid)
    if not valid:
        return {"n": 0, "n_total": len(rows), "n_failed": failed}
    logs = [float(row["log10_ratio"]) for row in valid]
    relative_signed = [float(row["relative_error"]) for row in valid]
    absolute = [float(row["absolute_error_ps"]) for row in valid]
    relative = [float(row["absolute_relative_error_pct"]) for row in valid]
    floor_relative = [
        float(row["floor_weighted_relative_error_pct"]) for row in valid
    ]
    floor_absolute = [
        float(row["floor_weighted_absolute_relative_error_pct"]) for row in valid
    ]
    result = {
        "n": len(valid),
        "n_total": len(rows),
        "n_failed": failed,
        "timing_rms_log10": math.sqrt(sum(x * x for x in logs) / len(logs)),
        "rms_relative_error_pct": 100.0 * math.sqrt(
            sum(x * x for x in relative_signed) / len(relative_signed)
        ),
        "mean_absolute_error_ps": sum(absolute) / len(absolute),
        "median_absolute_error_ps": sorted(absolute)[len(absolute) // 2],
        "p95_absolute_relative_error_pct": sorted(relative)[
            int(0.95 * (len(relative) - 1))
        ],
        "mean_signed_relative_error_pct": sum(
            float(row["signed_relative_error_pct"]) for row in valid
        ) / len(valid),
        "floor_weighted_rms_relative_pct": math.sqrt(
            sum(x * x for x in floor_relative) / len(floor_relative)
        ),
        "floor_weighted_mean_absolute_relative_pct": (
            sum(floor_absolute) / len(floor_absolute)
        ),
    }
    slew_valid = [
        row for row in rows if "slew_log10_ratio" in row
    ]
    if slew_valid:
        slew_logs = [float(row["slew_log10_ratio"]) for row in slew_valid]
        slew_relative = [
            float(row["slew_signed_relative_error_pct"]) / 100.0
            for row in slew_valid
        ]
        result.update({
            "slew_n": len(slew_valid),
            "slew_rms_log10": math.sqrt(
                sum(x * x for x in slew_logs) / len(slew_logs)
            ),
            "slew_rms_relative_error_pct": 100.0 * math.sqrt(
                sum(x * x for x in slew_relative) / len(slew_relative)
            ),
            "slew_mean_absolute_error_ps": sum(
                float(row["slew_absolute_error_ps"]) for row in slew_valid
            ) / len(slew_valid),
            "slew_mean_signed_relative_error_pct": sum(
                float(row["slew_signed_relative_error_pct"])
                for row in slew_valid
            ) / len(slew_valid),
            "slew_p95_absolute_relative_error_pct": sorted(
                float(row["slew_absolute_relative_error_pct"])
                for row in slew_valid
            )[int(0.95 * (len(slew_valid) - 1))],
        })
    i_eff_valid = [
        row for row in rows if "i_eff_log10_ratio" in row
    ]
    if i_eff_valid:
        i_eff_logs = [float(row["i_eff_log10_ratio"]) for row in i_eff_valid]
        i_eff_relative = [
            float(row["i_eff_signed_relative_error_pct"]) / 100.0
            for row in i_eff_valid
        ]
        result.update({
            "i_eff_n": len(i_eff_valid),
            "i_eff_rms_log10": math.sqrt(
                sum(x * x for x in i_eff_logs) / len(i_eff_logs)
            ),
            "i_eff_rms_relative_error_pct": 100.0 * math.sqrt(
                sum(x * x for x in i_eff_relative) / len(i_eff_relative)
            ),
            "i_eff_mean_absolute_relative_error_pct": sum(
                float(row["i_eff_absolute_relative_error_pct"])
                for row in i_eff_valid
            ) / len(i_eff_valid),
            "i_eff_mean_signed_relative_error_pct": sum(
                float(row["i_eff_signed_relative_error_pct"])
                for row in i_eff_valid
            ) / len(i_eff_valid),
        })
    return result


def _group_summary(rows: Sequence[Mapping[str, object]], key: str):
    groups = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {name: _summary(group) for name, group in sorted(groups.items())}


def _outliers(rows: Sequence[Mapping[str, object]], limit: int = 10):
    valid = [row for row in rows if "absolute_relative_error_pct" in row]
    return [
        {
            key: row[key]
            for key in (
                "dataset", "cell", "direction", "input_slew_ns", "c_load_pf",
                "r_net_ohm", "c_net_pf", "target_ns",
                "target_output_slew_ns", "requested_target_ns",
                "liberty_input_slew_ns", "simulated_ns",
                "measured_output_slew_ns", "absolute_error_ps",
                "signed_relative_error_pct", "slew_absolute_relative_error_pct",
                "i_eff_absolute_relative_error_pct", "log10_ratio",
            )
            if key in row
        }
        for row in sorted(
            valid,
            key=lambda item: float(item["absolute_relative_error_pct"]),
            reverse=True,
        )[:limit]
    ]


def _plot_holdout(rows: Sequence[Mapping[str, object]], variant: str, path: Path) -> None:
    import matplotlib.pyplot as plt
    valid = [
        item for item in rows
        if all(key in item for key in (
            "c_load_pf", "input_slew_ns", "r_net_ohm",
            "absolute_error_ps", "signed_relative_error_pct",
        ))
    ]
    if not valid:
        fig, axis = plt.subplots(figsize=(8, 3.2), layout="constrained")
        axis.text(
            0.5,
            0.5,
            "No physically valid %s wrapper predictions" % variant,
            ha="center",
            va="center",
        )
        axis.set_axis_off()
        fig.savefig(path, dpi=180)
        plt.close(fig)
        return

    color = {"rise": "#0072B2", "fall": "#D55E00"}
    marker = {"rise": "o", "fall": "s"}
    axes_data = (
        ("c_load_pf", "C_load (pF)"),
        ("input_slew_ns", "Input slew (ns)"),
        ("r_net_ohm", "R_net (ohm)"),
    )
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.8), layout="constrained")
    for col, (xkey, xlabel) in enumerate(axes_data):
        for row_index, (ykey, ylabel) in enumerate((
            ("absolute_error_ps", "Absolute error (ps)"),
            ("signed_relative_error_pct", "Signed relative error (%)"),
        )):
            ax = axes[row_index, col]
            for direction in DIRECTIONS:
                subset = [
                    item for item in rows
                    if item["direction"] == direction
                    and xkey in item
                    and ykey in item
                ]
                ax.scatter(
                    [float(item[xkey]) for item in subset],
                    [float(item[ykey]) for item in subset],
                    s=20,
                    alpha=0.78,
                    color=color[direction],
                    marker=marker[direction],
                    label=direction,
                    edgecolors="none",
                )
            ax.set_xscale("log")
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.grid(True, which="both", alpha=0.22)
            if row_index == 1:
                ax.axhline(0.0, color="#555555", linewidth=0.8)
            if col == 0 and row_index == 0:
                ax.legend(frameon=False, title="Transition")
    fig.suptitle("LVT holdout2 residuals: %s timing deck" % variant)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_by_cell(rows: Sequence[Mapping[str, object]], path: Path) -> None:
    import matplotlib.pyplot as plt

    cells = sorted({str(row["cell"]) for row in rows})
    datasets = sorted({str(row["dataset"]) for row in rows})
    x_index = {cell: index for index, cell in enumerate(cells)}
    color = {"train37": "#009E73", "holdout2": "#CC79A7"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    for axis, variant in zip(axes, ("baseline", "cwire")):
        for dataset in datasets:
            for direction, offset in (("rise", -0.13), ("fall", 0.13)):
                subset = [
                    row for row in rows
                    if row["dataset"] == dataset
                    and row["direction"] == direction
                    and row[variant].get("status") == "ok"
                ]
                xs = [x_index[str(row["cell"])] + offset for row in subset]
                ys = [float(row[variant]["signed_relative_error_pct"]) for row in subset]
                axis.scatter(
                    xs,
                    ys,
                    s=13,
                    alpha=0.58,
                    color=color[dataset],
                    marker="o" if direction == "rise" else "s",
                    label="%s / %s" % (dataset, direction),
                    edgecolors="none",
                )
        axis.axhline(0.0, color="#555555", linewidth=0.8)
        axis.set_xticks(range(len(cells)))
        axis.set_xticklabels(cells, rotation=25)
        axis.set_ylabel("Signed relative error (%)")
        axis.set_title(variant)
        axis.grid(True, axis="y", alpha=0.22)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("LVT timing residuals by inverter size and split")
    fig.savefig(path, dpi=180)
    plt.close(fig)

def _plot_driver_sensitivity(
    holdout_by_driver: Mapping[str, Sequence[Mapping[str, object]]],
    path: Path,
) -> None:
    import matplotlib.pyplot as plt

    labels = []
    relative_data = []
    absolute_data = []
    delta_data = []
    for driver_cell in sorted(holdout_by_driver):
        rows = holdout_by_driver[driver_cell]
        driver_rows = [
            row for row in rows
            if row["variant"] == "driver" and "signed_relative_error_pct" in row
        ]
        cwire_rows = {
            (
                row["cell"],
                row["direction"],
                row["input_slew_ns"],
                row["c_load_pf"],
            ): row
            for row in rows
            if row["variant"] == "driver_cwire"
            and "simulated_ns" in row
        }
        deltas = []
        for row in driver_rows:
            key = (
                row["cell"],
                row["direction"],
                row["input_slew_ns"],
                row["c_load_pf"],
            )
            cwire_row = cwire_rows.get(key)
            if cwire_row is not None:
                deltas.append(
                    (float(cwire_row["simulated_ns"]) -
                     float(row["simulated_ns"])) * 1000.0
                )
        if not driver_rows:
            continue
        labels.append(driver_cell)
        relative_data.append([
            float(row["signed_relative_error_pct"]) for row in driver_rows
        ])
        absolute_data.append([
            float(row["absolute_error_ps"]) for row in driver_rows
        ])
        delta_data.append(deltas or [float("nan")])

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), layout="constrained")
    for axis, values, ylabel, title in (
        (
            axes[0],
            relative_data,
            "Signed relative error (%)",
            "Residual distribution",
        ),
        (
            axes[1],
            absolute_data,
            "Absolute error (ps)",
            "Absolute residual",
        ),
        (
            axes[2],
            delta_data,
            "Driver+Cwire − Driver (ps)",
            "Cwire sensitivity",
        ),
    ):
        axis.boxplot(values, tick_labels=labels, showfliers=True)
        axis.axhline(0.0, color="#555555", linewidth=0.8)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.grid(True, axis="y", alpha=0.22)
        axis.tick_params(axis="x", rotation=25)
    fig.suptitle("LVT holdout2 driver-strength sensitivity")
    fig.savefig(path, dpi=180)
    plt.close(fig)

def _run_outputs(rows: Sequence[Mapping[str, object]]) -> Dict[str, object]:
    flat = [
        item
        for variant in TIMING_VARIANTS
        for item in _flatten_variant(rows, variant)
    ]
    by_variant = {
        variant: [row for row in flat if row["variant"] == variant]
        for variant in TIMING_VARIANTS
    }
    holdout_by_variant = {
        variant: [
            row for row in by_variant[variant]
            if row["dataset"] == "holdout2"
        ]
        for variant in TIMING_VARIANTS
    }
    summary = {
        variant: _summary(holdout_by_variant[variant])
        for variant in TIMING_VARIANTS
    }
    for variant in TIMING_VARIANTS:
        summary["%s_by_cell" % variant] = _group_summary(
            by_variant[variant], "cell",
        )
        summary["%s_by_dataset" % variant] = _group_summary(
            by_variant[variant], "dataset",
        )
    return {
        "flat": flat,
        "by_variant": by_variant,
        "holdout_by_variant": holdout_by_variant,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwire-json", type=Path, required=True)
    parser.add_argument("--bias-v", type=float, default=0.6)
    parser.add_argument(
        "--driver-cell",
        default=None,
        help="one finite inverter driver; defaults to INVX4",
    )
    parser.add_argument(
        "--driver-cells",
        default=None,
        help="comma-separated finite inverter drivers for sensitivity sweep",
    )
    parser.add_argument(
        "--delay-floor-ps",
        type=float,
        default=5.0,
        help="minimum delay denominator for floor-weighted relative metrics",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.delay_floor_ps) or args.delay_floor_ps <= 0.0:
        parser.error("--delay-floor-ps must be finite and positive")
    if args.driver_cell is not None and args.driver_cells is not None:
        parser.error("use only one of --driver-cell and --driver-cells")
    driver_text = (
        args.driver_cells
        if args.driver_cells is not None
        else args.driver_cell
        if args.driver_cell is not None
        else "INVX4"
    )
    driver_cells = []
    for token in driver_text.split(","):
        cell = token.strip().upper()
        if not cell:
            parser.error("driver list contains an empty cell name")
        if cell not in driver_cells:
            driver_cells.append(cell)
    if "NONE" in driver_cells and len(driver_cells) != 1:
        parser.error("'none' cannot be combined with finite drivers")

    out_dir = args.out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    cwire = _load_cwire_profile(
        args.cwire_json,
        FLAVOR,
        args.bias_v,
        TRAIN_CELLS + HOLDOUT_CELLS,
    )
    cards = cc.model_cards(FLAVOR)
    liberty_path = fit_drive._library(FLAVOR)
    liberty_text = liberty_path.read_text()

    driver_specs = {}
    for driver_cell in driver_cells:
        if driver_cell == "NONE":
            driver_specs[driver_cell] = {
                "entry": None,
                "rc_model": None,
                "source": "ideal_source",
            }
            continue
        try:
            driver_entry, source = _load_driver_entry(driver_cell)
        except (KeyError, OSError, ValueError) as exc:
            parser.error(str(exc))
        if tuple(str(pin) for pin in driver_entry["inputs"]) != ("A",):
            parser.error(
                "driver cell must be a one-input inverter: %s" % driver_cell
            )
        driver_pins = tuple(sorted(
            str(pin) for pin in driver_entry["pins"]
            if str(pin) not in {"VDD", "VSS"}
        ))
        driver_rc_model = drive.load_rc_model(
            FLAVOR, driver_cell, driver_pins,
        )
        if driver_rc_model.has_unmapped_interconnect:
            parser.error(
                "driver RC extraction is unmapped: %s" %
                driver_rc_model.unmapped_interconnect
            )
        driver_specs[driver_cell] = {
            "entry": driver_entry,
            "rc_model": driver_rc_model,
            "source": source,
        }

    driver_runs = {}
    for driver_cell in driver_cells:
        spec = driver_specs[driver_cell]
        rows = []
        for dataset, cells in (("train37", TRAIN_CELLS), ("holdout2", HOLDOUT_CELLS)):
            data = drive.load_data(FLAVOR, dataset)
            for cell in cells:
                rows.extend(_simulate_cell(
                    cards,
                    data,
                    liberty_text,
                    cell,
                    dataset,
                    cwire,
                    args.bias_v,
                    driver_entry=spec["entry"],
                    driver_rc_model=spec["rc_model"],
                    delay_floor_ps=args.delay_floor_ps,
                ))
        outputs = _run_outputs(rows)
        reported_driver = None if driver_cell == "NONE" else driver_cell
        for row in outputs["flat"]:
            row["driver_cell"] = reported_driver
        driver_runs[driver_cell] = {
            "rows": rows,
            "outputs": outputs,
            "source": spec["source"],
            "reported_driver": reported_driver,
        }

    first_run = driver_runs[driver_cells[0]]
    first_outputs = first_run["outputs"]
    first_summary = first_outputs["summary"]
    driver_sweep = {}
    for driver_cell, run in driver_runs.items():
        driver_summary = {
            key: value
            for key, value in run["outputs"]["summary"].items()
            if key == "driver"
            or key == "driver_cwire"
            or key.startswith("driver_by_")
            or key.startswith("driver_cwire_by_")
        }
        holdout = run["outputs"]["holdout_by_variant"]
        driver_sweep[driver_cell] = {
            "reported_driver": run["reported_driver"],
            "source": run["source"],
            "summary": driver_summary,
            "holdout2_outliers": {
                variant: _outliers(holdout[variant])
                for variant in ("driver", "driver_cwire")
            },
            "n_holdout_rows": {
                variant: len(holdout[variant])
                for variant in ("driver", "driver_cwire")
            },
        }

    if len(driver_cells) == 1:
        flat = list(first_outputs["flat"])
        top_summary = dict(first_summary)
        holdout_by_variant = first_outputs["holdout_by_variant"]
        holdout_outliers = {
            variant: _outliers(holdout_by_variant[variant])
            for variant in TIMING_VARIANTS
        }
        failures = _failure_rows(first_run["rows"])
    else:
        flat = [
            row for row in first_outputs["flat"]
            if row["variant"] in ("baseline", "cwire")
        ]
        for run in driver_runs.values():
            flat.extend(
                row for row in run["outputs"]["flat"]
                if row["variant"] in ("driver", "driver_cwire")
            )
        top_summary = {
            key: value
            for key, value in first_summary.items()
            if key.startswith("baseline") or key.startswith("cwire")
        }
        top_summary["driver_sweep"] = driver_sweep
        holdout_by_variant = first_outputs["holdout_by_variant"]
        holdout_outliers = {
            "baseline": _outliers(holdout_by_variant["baseline"]),
            "cwire": _outliers(holdout_by_variant["cwire"]),
            "driver_sweep": {
                driver_cell: run["holdout2_outliers"]
                for driver_cell, run in driver_sweep.items()
            },
        }
        failures = _failure_rows(
            first_run["rows"], ("baseline", "cwire"),
        )
        for driver_cell, run in driver_runs.items():
            for failure in _failure_rows(
                run["rows"], ("driver", "driver_cwire"),
            ):
                failure["driver_cell"] = run["reported_driver"]
                failures.append(failure)
    if len(driver_cells) == 1:
        top_summary["driver_sweep"] = driver_sweep

    rc_coverage = {
        dataset: _rc_coverage(dataset)
        for dataset in ("train37", "holdout2")
    }
    reported_driver_cells = [
        None if cell == "NONE" else cell for cell in driver_cells
    ]
    summary = {
        "schema_version": 5,
        "kind": "lvt_timing_residual_analysis",
        "flavor": FLAVOR,
        "liberty": str(liberty_path),
        "cwire_json": str(args.cwire_json.expanduser()),
        "cwire_bias_v": args.bias_v,
        "driver_cell": (
            reported_driver_cells[0] if len(reported_driver_cells) == 1 else None
        ),
        "driver_cells": reported_driver_cells,
        "driver_sources": {
            cell: run["source"]
            for cell, run in driver_runs.items()
            if run["reported_driver"] is not None
        },
        "delay_floor_ps": args.delay_floor_ps,
        "definition": {
            "r_net": "manual-GDS output-pin Y resistance in ohms",
            "c_net": "manual-GDS output-pin Y shunt capacitance in pF",
            "absolute_error": "|simulated - Liberty| in ps",
            "relative_error": "(simulated / Liberty - 1) * 100",
            "timing_rms": "sqrt(mean(log10(simulated / Liberty)^2))",
            "rms_relative_error":
                "100 * sqrt(mean((simulated / Liberty - 1)^2))",
            "slew_rms": "sqrt(mean(log10(measured output slew / Liberty transition)^2))",
            "slew_rms_relative_error":
                "100 * sqrt(mean((measured output slew / Liberty transition - 1)^2))",
            "i_eff": "VDD * C_load / output slew, in mA; derived effective current",
            "i_eff_rms_relative_error":
                "100 * sqrt(mean((I_eff simulated / I_eff target - 1)^2))",
            "finite_driver_target":
                "finite-driver rows interpolate Liberty at measured DUT-input slew",
            "floor_weighted_relative_error":
                "delay error divided by max(|Liberty delay|, delay_floor_ps)",
            "plot_x_scales": "logarithmic for C_load, input slew, and R_net",
        },
        "coverage": {
            "train_cells": list(TRAIN_CELLS),
            "holdout2_cells": list(HOLDOUT_CELLS),
            "driver_cells": reported_driver_cells,
            "points_per_cell_direction": len(_timing_grid(
                liberty_text, "INVX1H7L",
            )) // len(DIRECTIONS),
        },
        "rc_coverage": rc_coverage,
        "summary": top_summary,
        "holdout2_outliers": holdout_outliers,
        "simulation_failures": failures,
        "rows": flat,
    }
    (out_dir / "lvt_timing_residuals.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )

    baseline_holdout = first_outputs["holdout_by_variant"]["baseline"]
    cwire_holdout = first_outputs["holdout_by_variant"]["cwire"]
    _plot_holdout(
        baseline_holdout,
        "baseline",
        out_dir / "lvt_holdout2_residuals_baseline.png",
    )
    _plot_holdout(
        cwire_holdout,
        "cwire",
        out_dir / "lvt_holdout2_residuals_cwire.png",
    )
    holdout_by_driver = {}
    for driver_cell, run in driver_runs.items():
        holdout = run["outputs"]["holdout_by_variant"]
        holdout_rows = holdout["driver"] + holdout["driver_cwire"]
        holdout_by_driver[driver_cell] = holdout_rows
        suffix = "" if len(driver_cells) == 1 else "_" + driver_cell.lower()
        for variant in ("driver", "driver_cwire"):
            _plot_holdout(
                holdout[variant],
                variant,
                out_dir / (
                    "lvt_holdout2_residuals_%s%s.png" % (variant, suffix)
                ),
            )
    _plot_by_cell(
        first_run["rows"], out_dir / "lvt_residuals_by_cell.png",
    )
    if len(driver_cells) > 1:
        _plot_driver_sensitivity(
            holdout_by_driver,
            out_dir / "lvt_driver_sensitivity.png",
        )
    print(out_dir / "lvt_timing_residuals.json")
    print(out_dir / "lvt_holdout2_residuals_baseline.png")
    print(out_dir / "lvt_holdout2_residuals_cwire.png")
    for driver_cell in driver_cells:
        suffix = "" if len(driver_cells) == 1 else "_" + driver_cell.lower()
        for variant in ("driver", "driver_cwire"):
            print(out_dir / (
                "lvt_holdout2_residuals_%s%s.png" % (variant, suffix)
            ))
    print(out_dir / "lvt_residuals_by_cell.png")
    if len(driver_cells) > 1:
        print(out_dir / "lvt_driver_sensitivity.png")


if __name__ == "__main__":
    main()
