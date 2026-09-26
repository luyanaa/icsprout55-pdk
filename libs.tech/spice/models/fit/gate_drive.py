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

"""Evaluate Liberty combinational arcs with flattened CDL and manual GDS RC.

This module deliberately handles combinational timing arcs only.  Sequential
DFF setup/hold/clock-to-Q arcs need a separate clocked testbench and are not
silently reduced to a combinational pulse.
"""
from __future__ import annotations

import functools
import itertools
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import cdl_parser as cp
import drive
import extract_data
import rc_extraction

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FLAVOR_SUFFIX = {"svt": "H7R", "lvt": "H7L", "hvt": "H7H"}
FLAVOR_TAG = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}


def _library(flavor: str) -> Path:
    tag = FLAVOR_TAG[flavor]
    return (ROOT / "libs.ref"
            / ("ics55_LLSC_%s" % tag) / "liberty"
            / ("ics55_LLSC_%s_typ_tt_1p2_25_nldm.lib" % tag))


def _cdl(flavor: str) -> Path:
    tag = FLAVOR_TAG[flavor]
    return (ROOT / "libs.ref"
            / ("ics55_LLSC_%s" % tag) / "cdl"
            / ("ics55_LLSC_%s.cdl" % tag))


def _cell_block(text: str, cell: str) -> str:
    match = re.search(
        r"^\s*cell\s*\(%s\)\s*\{(.*?)(?=^\s*cell\s*\([^)]*\)\s*\{|\Z)"
        % re.escape(cell), text, re.MULTILINE | re.DOTALL)
    if not match:
        raise KeyError("Liberty cell not found: %s" % cell)
    return match.group(1)


def _pin_block(block: str, pin: str) -> str:
    match = re.search(
        r"^\s{4}pin\s*\(%s\)\s*\{(.*?)(?=^\s{4}pin\s*\(|^\s{2}\}\s*$)"
        % re.escape(pin), block, re.MULTILINE | re.DOTALL)
    if not match:
        raise KeyError("Liberty pin not found: %s" % pin)
    return match.group(1)


def _table(block: str, name: str):
    match = re.search(
        r"%s\s*\([^)]*\)\s*\{(.*?)\n\s{8}\}" % name,
        block, re.DOTALL)
    if not match:
        raise KeyError("Liberty table not found: %s" % name)
    table = match.group(1)
    i1 = re.search(r"index_1\s*\(\s*\"([^\"]+)\"", table)
    i2 = re.search(r"index_2\s*\(\s*\"([^\"]+)\"", table)
    values = re.search(r"values\s*\(\s*\\?\s*(.*?)\n\s*\);",
                       table, re.DOTALL)
    if not (i1 and i2 and values):
        raise ValueError("incomplete Liberty table: %s" % name)
    index_1 = [float(x) for x in i1.group(1).split(",")]
    index_2 = [float(x) for x in i2.group(1).split(",")]
    rows = [[float(x) for x in row.split(",")]
            for row in re.findall(r'"([^\"]+)"', values.group(1))]
    if len(rows) != len(index_1) or any(len(row) != len(index_2)
                                          for row in rows):
        raise ValueError("Liberty table dimensions do not match: %s" % name)
    return index_1, index_2, rows


def _nearest(values: Sequence[float], target: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


def _timing_blocks(pin_block: str) -> Iterable[str]:
    return re.findall(
        r"^\s{6}timing\s*\(\)\s*\{(.*?)(?=^\s{6}timing\s*\(\)\s*\{|\Z)",
        pin_block, re.MULTILINE | re.DOTALL)


def _quoted(block: str, name: str) -> Optional[str]:
    match = re.search(r"\b%s\s*:\s*\"([^\"]*)\"" % name, block)
    return match.group(1) if match else None


def _boolean_value(expression: str, values: Mapping[str, int]) -> bool:
    """Evaluate the restricted Boolean syntax used by Liberty functions."""
    if not re.fullmatch(r"[A-Za-z0-9_!~*+() \t]+", expression):
        raise ValueError("unsupported Liberty Boolean expression: %s" % expression)
    translated = re.sub(r"[!~]\s*", " not ", expression)
    translated = translated.replace("*", " and ").replace("+", " or ")
    return bool(eval(translated, {"__builtins__": {}}, dict(values)))


def _condition_values(condition: Optional[str], related: str) -> Dict[str, int]:
    if not condition:
        return {}
    values: Dict[str, int] = {}
    for token in re.finditer(r"([!~]?)([A-Za-z_]\w*)", condition):
        name = token.group(2)
        if name == related:
            continue
        value = 0 if token.group(1) in ("!", "~") else 1
        previous = values.get(name)
        if previous is not None and previous != value:
            raise ValueError("contradictory Liberty timing condition: %s" % condition)
        values[name] = value
    return values


def _sensitized_values(function: str, related: str, inputs: Sequence[str],
                       sense: str) -> Dict[str, int]:
    others = [name for name in inputs if name != related]
    for bits in itertools.product((0, 1), repeat=len(others)):
        values = dict(zip(others, bits))
        values[related] = 0
        low = _boolean_value(function, values)
        values[related] = 1
        high = _boolean_value(function, values)
        if sense == "negative_unate" and low and not high:
            return dict(zip(others, bits))
        if sense == "positive_unate" and not low and high:
            return dict(zip(others, bits))
    raise ValueError("no sensitized state for %s on %s" % (related, function))


def _entry_from_sources(flavor: str, base_cell: str) -> Tuple[Dict[str, object], Path]:
    suffix = FLAVOR_SUFFIX[flavor]
    key = base_cell + suffix
    cdl = _cdl(flavor)
    lib = _library(flavor)
    parsed = cp.load(str(cdl), cell_filter={key})
    if key not in parsed:
        raise KeyError("CDL cell not found: %s" % key)
    liberty = extract_data.parse_liberty(str(lib))
    if key not in liberty:
        raise KeyError("Liberty cell not found: %s" % key)
    entry = dict(parsed[key])
    entry.update(liberty[key])
    entry["entry_key"] = key
    entry["base_cell"] = base_cell
    entry["flavor"] = flavor
    entry["netlist"] = entry["body"]
    return entry, lib


@functools.lru_cache(maxsize=64)
def load_entry(flavor: str, base_cell: str) -> Tuple[Dict[str, object], Path]:
    return _entry_from_sources(flavor, base_cell)


def timing_arcs(flavor: str, base_cell: str, *, output_pin: str = "Y",
                slew_ns: float = 0.0985337,
                load_pf: float = 0.00663118,
                one_arc_per_input: bool = True) -> List[Dict[str, object]]:
    """Return combinational output arcs with one Liberty target per input."""
    entry, lib_path = load_entry(flavor, base_cell)
    block = _cell_block(lib_path.read_text(), entry["entry_key"])
    output = _pin_block(block, output_pin)
    input_pins = [name for name in re.findall(
        r"^\s{4}pin\s*\((\w+)\)\s*\{(.*?)(?=^\s{4}pin\s*\(|^\s{2}\}\s*$)",
        block, re.MULTILINE | re.DOTALL)
                  if re.search(r"\bdirection\s*:\s*input", name[1])]
    inputs = [name for name, _ in input_pins]
    function_match = re.search(r"\bfunction\s*:\s*\"([^\"]+)\"", block)
    function = function_match.group(1) if function_match else None
    arcs = []
    for timing in _timing_blocks(output):
        related = _quoted(timing, "related_pin")
        sense = re.search(r"\btiming_sense\s*:\s*(\w+)", timing)
        timing_type = re.search(r"\btiming_type\s*:\s*(\w+)", timing)
        if not related or not sense or not timing_type:
            continue
        if timing_type.group(1) != "combinational":
            continue
        if sense.group(1) not in ("negative_unate", "positive_unate"):
            continue
        try:
            rise_i1, rise_i2, rise = _table(timing, "cell_rise")
            fall_i1, fall_i2, fall = _table(timing, "cell_fall")
        except (KeyError, ValueError):
            continue
        ri = (_nearest(rise_i1, slew_ns), _nearest(rise_i2, load_pf))
        fi = (_nearest(fall_i1, slew_ns), _nearest(fall_i2, load_pf))
        condition = _quoted(timing, "when")
        static = _condition_values(condition, related)
        if not static:
            if function is None:
                raise ValueError("no function for unconditioned arc %s" % related)
            static = _sensitized_values(function, related, inputs, sense.group(1))
        arcs.append({
            "input_pin": related,
            "output_pin": output_pin,
            "sense": sense.group(1),
            "static": static,
            "condition": condition,
            "slew_ns": rise_i1[ri[0]],
            "load_pf": rise_i2[ri[1]],
            "rise_ns": rise[ri[0]][ri[1]],
            "fall_ns": fall[fi[0]][fi[1]],
        })
    if one_arc_per_input:
        selected = []
        for input_pin in inputs:
            candidates = [arc for arc in arcs if arc["input_pin"] == input_pin]
            conditioned = [arc for arc in candidates if arc["condition"]]
            if conditioned:
                selected.append(conditioned[0])
            elif candidates:
                selected.append(candidates[0])
        arcs = selected
    if not arcs:
        raise ValueError("no combinational arcs found for %s" % base_cell)
    return arcs


@functools.lru_cache(maxsize=64)
def load_rc_model(flavor: str, base_cell: str,
                  signal_pins: Tuple[str, ...]):
    return rc_extraction.extract_flavor_cell(ROOT, flavor, base_cell, signal_pins)


def _mapped_node(node: str, primary: Mapping[str, str]) -> str:
    if node in primary:
        return primary[node]
    if node in ("VSS", "0"):
        return "0"
    if node == "VDD":
        return "vdd"
    return "x_%s" % node


def _deck(cards: str, entry: Mapping[str, object], arc: Mapping[str, object],
          vdd: float, temp: float, output_direction: str,
          rc_model=None) -> str:
    input_pin = str(arc["input_pin"])
    output_pin = str(arc["output_pin"])
    slew_ns = float(arc["slew_ns"])
    rise_fall = slew_ns * 1e-9
    input_direction = ("rise" if output_direction == "rise" else "fall")
    if arc["sense"] == "negative_unate":
        input_direction = "fall" if output_direction == "rise" else "rise"
    initial = vdd if input_direction == "fall" else 0.0
    final = 0.0 if input_direction == "fall" else vdd
    netlist, parasitics = (
        rc_model.spice_netlist(entry["netlist"])
        if rc_model is not None else (list(entry["netlist"]), []))
    output_node = "y"
    primary = {output_pin: output_node, "Y": output_node,
               "VDD": "vdd", "VSS": "0", "0": "0"}
    input_pins = list(entry["inputs"])
    for pin in input_pins:
        if pin != input_pin:
            primary[pin] = "s_%s" % pin
    primary[input_pin] = "in_%s" % input_pin
    lines = [
        "* ICS55 transient combinational timing check",
        ".options device temp=%g" % temp,
        cards.rstrip(),
        "VDD vdd 0 %g" % vdd,
        "VIN_%s %s 0 PULSE(%g %g 1n %g %g 1n 3n)" % (
            input_pin, primary[input_pin], initial, final, rise_fall, rise_fall),
        "CLOAD y 0 %.12gp" % float(arc["load_pf"]),
    ]
    static = dict(arc["static"])
    for pin in input_pins:
        if pin == input_pin:
            continue
        value = vdd if int(static.get(pin, 0)) else 0.0
        lines.append("VSTATIC_%s %s 0 %g" % (pin, primary[pin], value))
    for mline in netlist:
        parts = mline.split()
        if len(parts) < 7:
            raise ValueError("unexpected CDL MOS line: %s" % mline)
        dev = parts[0]
        nodes = parts[1:5]
        model = parts[5]
        attrs = " ".join(parts[6:])
        lines.append("M%s %s %s %s" % (
            dev, " ".join(_mapped_node(node, primary) for node in nodes),
            model, attrs))
    for element in parasitics:
        parts = element.split()
        if len(parts) != 4:
            raise ValueError("unexpected RC element: %s" % element)
        lines.append("%s %s %s %s" % (
            parts[0], _mapped_node(parts[1], primary),
            _mapped_node(parts[2], primary), parts[3]))
    lines.extend([
        ".tran 0.5p 3.5n",
        ".print tran v(%s) v(y)" % primary[input_pin],
        ".end",
    ])
    return "\n".join(lines) + "\n"


def delay_seconds(cards: str, entry: Mapping[str, object],
                  arc: Mapping[str, object], output_direction: str,
                  vdd: float = 1.2, temp: float = 25,
                  rc_model=None) -> float:
    deck = _deck(cards, entry, arc, vdd, temp, output_direction, rc_model)
    rows = drive._run(deck)
    input_direction = "rise" if output_direction == "rise" else "fall"
    if arc["sense"] == "negative_unate":
        input_direction = "fall" if output_direction == "rise" else "rise"
    input_cross = drive._crossing(rows, 1, 0.5 * vdd, input_direction)
    output_cross = drive._crossing(
        rows, 2, 0.5 * vdd, output_direction,
        start=input_cross or 0.0)
    if input_cross is None or output_cross is None:
        raise RuntimeError("could not find %s crossing for %s" %
                           (output_direction, arc["input_pin"]))
    return output_cross - input_cross


def evaluate(cards: str, flavor: str, base_cell: str,
             arcs: Sequence[Mapping[str, object]], *, vdd: float = 1.2,
             temp: float = 25, rc: bool = True,
             allow_unmapped_internal: bool = False) -> List[Dict[str, object]]:
    entry, _ = load_entry(flavor, base_cell)
    rc_model = None
    if rc:
        signal_pins = tuple(sorted(
            str(pin) for pin in entry["pins"]
            if str(pin) not in {"VDD", "VSS"}))
        rc_model = load_rc_model(flavor, base_cell, signal_pins)
        if rc_model.has_unmapped_interconnect and not allow_unmapped_internal:
            raise RuntimeError("manual RC extraction left unlabelled interconnect in %s: %s"
                               % (base_cell, rc_model.unmapped_interconnect))
    rows = []
    for arc in arcs:
        for direction in ("rise", "fall"):
            delay = delay_seconds(cards, entry, arc, direction,
                                  vdd=vdd, temp=temp, rc_model=rc_model)
            target = float(arc[direction + "_ns"])
            rows.append({
                "cell": base_cell,
                "input_pin": arc["input_pin"],
                "direction": direction,
                "condition": arc["condition"],
                "target_ns": target,
                "simulated_ns": delay * 1e9,
                "log10_ratio": math.log10(delay * 1e9 / target),
            })
    return rows


def evaluate_cells(cards: str, flavor: str, cells: Iterable[str], *,
                   rc: bool = True) -> List[Dict[str, object]]:
    rows = []
    for cell in cells:
        arcs = timing_arcs(flavor, cell)
        rows.extend(evaluate(cards, flavor, cell, arcs, rc=rc))
    return rows


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("flavor", choices=tuple(FLAVOR_TAG))
    parser.add_argument("cell")
    parser.add_argument("--no-rc", action="store_true")
    args = parser.parse_args()
    arcs = timing_arcs(args.flavor, args.cell)
    print(json.dumps({"arcs": arcs, "timing": evaluate(
        "", args.flavor, args.cell, arcs, rc=not args.no_rc)}, indent=2))
