#!/usr/bin/env python3
"""Evaluate BSIM4 inverter delay against released Liberty timing tables.

This is deliberately separate from the leakage fitter.  Liberty timing is a
cell-level observable, not a transistor Id-Vg/Id-Vd measurement, so the result
is a constrained drive calibration experiment rather than a foundry card.
"""
from __future__ import annotations

import functools
import json
import math
import os
import re
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
XYCE = os.environ.get("XYCE", "/usr/local/XyceNF_OMPI_7.10/bin/Xyce")
FLAVOR_SUFFIX = {"svt": "H7R", "lvt": "H7L", "hvt": "H7H"}
NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"

sys.path.insert(0, str(HERE))
import rc_extraction  # noqa: E402


def _cell_block(text: str, cell: str) -> str:
    match = re.search(
        r"cell\s*\(%s\)\s*\{(.*?)(?=\n  cell\s*\(|\Z)"
        % re.escape(cell), text, re.DOTALL)
    if not match:
        raise KeyError("Liberty cell not found: %s" % cell)
    return match.group(1)


def _table(block: str, name: str):
    match = re.search(
        r"%s\s*\([^)]*\)\s*\{(.*?)\n        \}" % name,
        block, re.DOTALL)
    if not match:
        raise KeyError("Liberty table not found: %s" % name)
    table = match.group(1)
    i1 = re.search(r"index_1\s*\(\s*\"([^\"]+)\"", table)
    i2 = re.search(r"index_2\s*\(\s*\"([^\"]+)\"", table)
    values = re.search(r"values\s*\(\s*\\?\s*(.*?)\n\s*\);", table,
                       re.DOTALL)
    if not (i1 and i2 and values):
        raise ValueError("incomplete Liberty table: %s" % name)
    index_1 = [float(x) for x in i1.group(1).split(",")]
    index_2 = [float(x) for x in i2.group(1).split(",")]
    rows = []
    for row in re.findall(r'"([^\"]+)"', values.group(1)):
        rows.append([float(x) for x in row.split(",")])
    if len(rows) != len(index_1) or any(len(row) != len(index_2) for row in rows):
        raise ValueError("Liberty table dimensions do not match: %s" % name)
    return index_1, index_2, rows


def _nearest(values: Sequence[float], target: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


def liberty_point(lib_path: Path, cell: str, slew_ns: float,
                  load_pf: float) -> Dict[str, float]:
    """Read one rise/fall delay point from a Liberty inverter cell."""
    block = _cell_block(lib_path.read_text(), cell)
    ypin = re.search(r"\n    pin\s*\(Y\)\s*\{(.*?)(?=\n    pin\s*\(|\n  \})",
                     block, re.DOTALL)
    if not ypin:
        raise KeyError("output pin Y not found: %s" % cell)
    yblock = ypin.group(1)
    rise_i1, rise_i2, rise = _table(yblock, "cell_rise")
    fall_i1, fall_i2, fall = _table(yblock, "cell_fall")
    r = (_nearest(rise_i1, slew_ns), _nearest(rise_i2, load_pf))
    f = (_nearest(fall_i1, slew_ns), _nearest(fall_i2, load_pf))
    return {
        "cell": cell,
        "slew_ns": rise_i1[r[0]],
        "load_pf": rise_i2[r[1]],
        "rise_ns": rise[r[0]][r[1]],
        "fall_ns": fall[f[0]][f[1]],
    }


def collect_points(lib_path: Path, flavor: str, data: Mapping[str, object],
                   base_cells: Iterable[str], slew_ns: float = 0.0985337,
                   load_pf: float = 0.00663118):
    """Collect matched Liberty points and extracted CDL entries."""
    suffix = FLAVOR_SUFFIX[flavor]
    points = []
    for base in base_cells:
        key = base + suffix
        if key not in data:
            raise KeyError("extracted cell not found: %s" % key)
        target = liberty_point(lib_path, key, slew_ns, load_pf)
        target.update({"base_cell": base, "entry_key": key, "flavor": flavor})
        points.append(target)
    return points

@functools.lru_cache(maxsize=64)
def load_rc_model(flavor: str, base_cell: str, signal_pins: tuple[str, ...]):
    """Return the cached manual GDS RC model for one timing cell."""
    return rc_extraction.extract_flavor_cell(ROOT, flavor, base_cell, signal_pins)


def _deck(cards: str, entry: Mapping[str, object], vdd: float,
          temp: float, slew_ns: float, load_pf: float,
          stop_ns: float, rc_model=None, cwire_pf: float = 0.0,
          cwire_alpha: float = 0.0, cwire_bias_v: float = 0.0,
          cwire_wrapper_subckt: str = "CWIRE_WRAPPER",
          driver_entry: Mapping[str, object] | None = None,
          driver_rc_model=None) -> str:
    rise_fall = slew_ns * 1e-9

    def netlist_and_parasitics(
        local_entry: Mapping[str, object], local_rc_model,
    ):
        return (
            local_rc_model.spice_netlist(local_entry["netlist"])
            if local_rc_model is not None
            else (list(local_entry["netlist"]), [])
        )

    dut_netlist, dut_parasitics = netlist_and_parasitics(entry, rc_model)
    driver_netlist = driver_parasitics = None
    if driver_entry is not None:
        driver_netlist, driver_parasitics = netlist_and_parasitics(
            driver_entry, driver_rc_model,
        )
    load = load_pf * 1e-12

    def mapped_node(node: str, vss_node: str) -> str:
        return {
            "Y": "y",
            "A": "a",
            "VDD": "vdd",
            "VSS": vss_node,
            "0": vss_node,
        }.get(node, "x_%s" % node)

    def element_lines(
        netlist: Sequence[str], parasitics: Sequence[str], vss_node: str,
    ):
        result = []
        for mline in netlist:
            parts = mline.split()
            if len(parts) < 7:
                raise ValueError("unexpected CDL MOS line: %s" % mline)
            dev = parts[0]
            nodes = parts[1:5]
            model = parts[5]
            attrs = " ".join(parts[6:])
            result.append("M%s %s %s %s" %
                          (dev, " ".join(
                              mapped_node(node, vss_node) for node in nodes
                          ), model, attrs))
        for element in parasitics:
            parts = element.split()
            if len(parts) != 4:
                raise ValueError("unexpected RC element: %s" % element)
            result.append("%s %s %s %s" %
                          (parts[0],
                           mapped_node(parts[1], vss_node),
                           mapped_node(parts[2], vss_node),
                           parts[3]))
        return result

    lines = [
        "* ICS55 transient inverter drive check",
        ".options device temp=%g" % temp,
        cards.rstrip(),
        "VDD vdd 0 %g" % vdd,
    ]
    if driver_entry is None:
        lines.append(
            "VIN a 0 PULSE(0 %g 0 %g %g 1n 2n)" %
            (vdd, rise_fall, rise_fall)
        )
    else:
        lines.append(
            "VIN drv_in 0 PULSE(0 %g 1n %g %g 1n 3n)" %
            (vdd, rise_fall, rise_fall)
        )
    lines.append("CLOAD y 0 %.12g" % load)
    if cwire_pf < 0.0:
        raise ValueError("cwire_pf must be non-negative")

    if driver_entry is not None:
        lines.extend([
            ".SUBCKT DRIVER_CORE a vdd vss y",
            *element_lines(driver_netlist, driver_parasitics, "vss"),
            ".ENDS DRIVER_CORE",
            "XDRIVER drv_in vdd 0 a DRIVER_CORE",
        ])

    if cwire_pf:
        # Instantiate the same input-pin wrapper topology emitted by
        # cap_compensation.py.  The core subcircuit is local to this deck so
        # the generated wrapper name remains a traceable timing artifact.
        expression = "%.17g*(1+%.17g*(V(a)-%.17g))" % (
            cwire_pf * 1.0e-12,
            cwire_alpha,
            cwire_bias_v,
        )
        wrapper = cwire_wrapper_subckt or "CWIRE_WRAPPER"
        core = wrapper + "_CORE"
        lines.extend([
            ".SUBCKT %s a vdd vss y" % core,
            *element_lines(dut_netlist, dut_parasitics, "vss"),
            ".ENDS %s" % core,
            ".SUBCKT %s a vdd vss y" % wrapper,
            "XCORE a vdd vss y %s" % core,
            "CWRAP a vss C={%s}" % expression,
            ".ENDS %s" % wrapper,
            "XDUT a vdd 0 y %s" % wrapper,
        ])
    elif driver_entry is not None:
        lines.extend([
            ".SUBCKT DUT_CORE a vdd vss y",
            *element_lines(dut_netlist, dut_parasitics, "vss"),
            ".ENDS DUT_CORE",
            "XDUT a vdd 0 y DUT_CORE",
        ])
    else:
        lines.extend(element_lines(dut_netlist, dut_parasitics, "0"))
    lines.extend([
        ".tran 0.5p %.12gn" % stop_ns,
        ".print tran v(a) v(y)",
        ".end",
    ])
    return "\n".join(lines) + "\n"


def _run(deck: str, timeout: int = 180):
    fd, path = tempfile.mkstemp(suffix=".cir")
    os.close(fd)
    Path(path).write_text(deck)
    env = dict(os.environ)
    env["DYLD_LIBRARY_PATH"] = "/opt/homebrew/lib"
    prn = path + ".prn"
    try:
        result = subprocess.run([XYCE, path], capture_output=True, text=True,
                                timeout=timeout, env=env)
        if result.returncode:
            raise RuntimeError("Xyce transient failed:\n%s" %
                               (result.stdout + result.stderr)[-2000:])
        rows = []
        for line in Path(prn).read_text().splitlines():
            fields = line.split()
            if len(fields) < 4:
                continue
            try:
                int(fields[0])
                rows.append((float(fields[1]), float(fields[2]),
                             float(fields[3])))
            except ValueError:
                continue
        if len(rows) < 3:
            raise RuntimeError("Xyce transient output has too few samples")
        return rows
    finally:
        for name in (path, prn):
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass


def _crossing(rows, column: int, threshold: float, direction: str,
              start: float = 0.0):
    for before, after in zip(rows, rows[1:]):
        t0, y0 = before[0], before[column]
        t1, y1 = after[0], after[column]
        if t1 < start:
            continue
        if direction == "rise":
            crossed = y0 < threshold <= y1
        elif direction == "fall":
            crossed = y0 > threshold >= y1
        else:
            raise ValueError("direction must be rise or fall")
        if not crossed or y1 == y0:
            continue
        fraction = (threshold - y0) / (y1 - y0)
        return t0 + fraction * (t1 - t0)
    return None

def _transition_slew_ns(rows, column: int, vdd: float, direction: str):
    """Return 20–80% transition time in ns, or None if incomplete."""
    if direction == "rise":
        first = _crossing(rows, column, 0.2 * vdd, direction)
        second = _crossing(rows, column, 0.8 * vdd, direction,
                           start=first or 0.0)
    elif direction == "fall":
        first = _crossing(rows, column, 0.8 * vdd, direction)
        second = _crossing(rows, column, 0.2 * vdd, direction,
                           start=first or 0.0)
    else:
        raise ValueError("direction must be rise or fall")
    if first is None or second is None:
        return None
    return abs(second - first) * 1.0e9


def delay_measurement(
    cards: str, entry: Mapping[str, object], vdd: float = 1.2,
    temp: float = 25, slew_ns: float = 0.0985337,
    load_pf: float = 0.00663118, direction: str = "fall",
    rc_model=None, cwire_pf: float = 0.0,
    cwire_alpha: float = 0.0, cwire_bias_v: float = 0.0,
    cwire_wrapper_subckt: str = "CWIRE_WRAPPER",
    driver_entry: Mapping[str, object] | None = None,
    driver_rc_model=None,
):
    """Return delay and measured DUT-input transition details."""
    # Negative-unate inverter: input rise drives output fall, input fall
    # drives output rise.  A finite driver uses the delayed source fall at
    # 2 ns for the DUT falling transition, so its stop time must include the
    # second edge and the requested slow-slew settling tail.
    if driver_entry is None:
        stop_ns = max(3.0, 4.0 * slew_ns)
    else:
        stop_ns = max(4.5, 2.0 + 4.0 * slew_ns)
    rows = _run(_deck(
        cards, entry, vdd, temp, slew_ns, load_pf, stop_ns,
        rc_model=rc_model,
        cwire_pf=cwire_pf,
        cwire_alpha=cwire_alpha,
        cwire_bias_v=cwire_bias_v,
        cwire_wrapper_subckt=cwire_wrapper_subckt,
        driver_entry=driver_entry,
        driver_rc_model=driver_rc_model,
    ))
    input_direction = "rise" if direction == "fall" else "fall"
    input_cross = _crossing(rows, 1, 0.5 * vdd, input_direction)
    input_slew_ns = _transition_slew_ns(
        rows, 1, vdd, input_direction,
    )
    output_start = input_cross or 0.0
    if driver_entry is not None and input_cross is not None:
        # Capacitive feedthrough can put the DUT-output 50% crossing a few
        # picoseconds before the finite-driver input 50% crossing.  Associate
        # the nearest same-edge output event instead of skipping to the next
        # source period.
        margin_seconds = max(
            5.0e-12,
            0.5 * (input_slew_ns or 0.0) * 1.0e-9,
        )
        output_start = max(0.0, input_cross - margin_seconds)
    output_cross = _crossing(
        rows, 2, 0.5 * vdd, direction, start=output_start,
    )
    if input_cross is None or output_cross is None:
        raise RuntimeError("could not find %s 50%% crossing" % direction)
    delay_seconds = output_cross - input_cross
    if driver_entry is not None and abs(delay_seconds) > 1.5e-9:
        raise RuntimeError(
            "finite-driver output crossing is not associated with input edge"
        )
    return {
        "delay_seconds": delay_seconds,
        "input_cross_seconds": input_cross,
        "output_cross_seconds": output_cross,
        "input_slew_ns": input_slew_ns,
        "output_slew_ns": _transition_slew_ns(
            rows, 2, vdd, direction,
        ),
    }


def delay_seconds(
    cards: str, entry: Mapping[str, object], vdd: float = 1.2,
    temp: float = 25, slew_ns: float = 0.0985337,
    load_pf: float = 0.00663118, direction: str = "fall",
    rc_model=None, cwire_pf: float = 0.0,
    cwire_alpha: float = 0.0, cwire_bias_v: float = 0.0,
    cwire_wrapper_subckt: str = "CWIRE_WRAPPER",
    driver_entry: Mapping[str, object] | None = None,
    driver_rc_model=None,
):
    """Return 50%-to-50% propagation delay in seconds."""
    return delay_measurement(
        cards, entry, vdd=vdd, temp=temp, slew_ns=slew_ns,
        load_pf=load_pf, direction=direction, rc_model=rc_model,
        cwire_pf=cwire_pf, cwire_alpha=cwire_alpha,
        cwire_bias_v=cwire_bias_v,
        cwire_wrapper_subckt=cwire_wrapper_subckt,
        driver_entry=driver_entry, driver_rc_model=driver_rc_model,
    )["delay_seconds"]


def evaluate(cards: str, data: Mapping[str, object], points,
             vdd: float = 1.2, temp: float = 25, rc: bool = False):
    """Evaluate all selected rise/fall points, optionally with manual GDS RC."""
    result = []
    for point in points:
        entry = data[point["entry_key"]]
        rc_model = None
        if rc:
            signal_pins = tuple(sorted(
                str(pin) for pin in entry["pins"]
                if str(pin) not in {"VDD", "VSS"}
            ))
            rc_model = load_rc_model(
                str(point["flavor"]), str(point["base_cell"]), signal_pins
            )
            if rc_model.has_unmapped_interconnect:
                raise RuntimeError(
                    "manual RC extraction left unlabelled interconnect in %s: %s"
                    % (point["entry_key"], rc_model.unmapped_interconnect)
                )
        for direction in ("rise", "fall"):
            delay = delay_seconds(
                cards, entry, vdd=vdd, temp=temp,
                slew_ns=point["slew_ns"], load_pf=point["load_pf"],
                direction=direction, rc_model=rc_model)
            result.append({
                "cell": point["base_cell"],
                "entry_key": point["entry_key"],
                "direction": direction,
                "target_ns": point[direction + "_ns"],
                "simulated_ns": delay * 1e9,
                "log10_ratio": math.log10(delay * 1e9 / point[direction + "_ns"]),
            })
    return result


def load_data(flavor: str, split: str = "fit"):
    return json.loads((HERE / ("data_%s_%s.json" % (split, flavor))).read_text())
