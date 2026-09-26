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

"""Characterize standard-cell pin capacitance and effective drive resistance.

This is a Layer-2 evidence tool.  It reads released Liberty data and reports:

* input-pin capacitance at the cell boundary;
* local delay-versus-load slopes from Liberty timing tables;
* the corresponding first-order Thevenin resistance estimate;
* optional intrinsic-capacitance residuals supplied by a separate AC run.

The optional intrinsic JSON uses capacitance values in pF.  It may be either
``{"INVX1H7R": {"A": 0.0007}}`` or a list of records with ``cell``, ``pin``,
and ``c_intrinsic_pf`` fields.  The report deliberately does not invent
intrinsic capacitance.  A negative residual is reported as an inconsistency
instead of being clamped.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LIB_DIR = ROOT / "libs.ref"
FLAVOR_TAG = {"svt": "H7R", "lvt": "H7L", "hvt": "H7H"}
LIBRARY_TAG = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}
DEFAULT_CELLS = ("INVX1", "INVX3", "INVX4")
NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"


class LibertyError(ValueError):
    """Raised when the supported Liberty subset is malformed."""


def _balanced_end(text: str, opening: int) -> int:
    """Return the index just after the brace matching ``opening``."""
    if opening >= len(text) or text[opening] != "{":
        raise LibertyError("block does not start with '{'")
    depth = 0
    quoted = False
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise LibertyError("unterminated Liberty block")


def _named_blocks(text: str, keyword: str) -> Iterable[Tuple[str, str]]:
    pattern = re.compile(
        r"(?m)^\s*" + re.escape(keyword)
        + r"\s*\(\s*([^)]*?)\s*\)\s*\{"
    )
    for match in pattern.finditer(text):
        end = _balanced_end(text, match.end() - 1)
        yield match.group(1).strip(), text[match.end():end - 1]


def _anonymous_blocks(text: str, keyword: str) -> Iterable[str]:
    pattern = re.compile(
        r"(?m)^\s*" + re.escape(keyword)
        + r"\s*(?:\([^)]*\))?\s*\{"
    )
    for match in pattern.finditer(text):
        end = _balanced_end(text, match.end() - 1)
        yield text[match.end():end - 1]


def _scalar(block: str, name: str) -> Optional[str]:
    match = re.search(
        r"(?m)^\s*" + re.escape(name) + r"\s*:\s*([^;]+);", block
    )
    return match.group(1).strip() if match else None


def _number(block: str, name: str) -> Optional[float]:
    value = _scalar(block, name)
    if value is None:
        return None
    match = re.search(NUMBER, value)
    if not match:
        raise LibertyError("invalid numeric %s: %s" % (name, value))
    return float(match.group(0))


def _float_list(value: str) -> List[float]:
    value = value.replace("\\", " ")
    result = []
    for token in value.split(","):
        token = token.strip()
        if token:
            result.append(float(token))
    return result


def _table(block: str, name: str) -> Optional[Dict[str, Any]]:
    pattern = re.compile(
        r"(?m)^\s*" + re.escape(name)
        + r"\s*\([^)]*\)\s*\{"
    )
    match = pattern.search(block)
    if not match:
        return None
    end = _balanced_end(block, match.end() - 1)
    table = block[match.end():end - 1]
    index_1_match = re.search(r"\bindex_1\s*\(\s*\"([^\"]*)\"", table)
    index_2_match = re.search(r"\bindex_2\s*\(\s*\"([^\"]*)\"", table)
    values_match = re.search(r"\bvalues\s*\((.*?)\)\s*;", table, re.DOTALL)
    if not (index_1_match and index_2_match and values_match):
        raise LibertyError("incomplete Liberty table: %s" % name)
    index_1 = _float_list(index_1_match.group(1))
    index_2 = _float_list(index_2_match.group(1))
    rows = [_float_list(row) for row in re.findall(
        r'"([^\"]*)"', values_match.group(1)
    )]
    if len(rows) != len(index_1):
        raise LibertyError(
            "%s row count %d does not match index_1 count %d"
            % (name, len(rows), len(index_1))
        )
    if any(len(row) != len(index_2) for row in rows):
        raise LibertyError("%s column count does not match index_2" % name)
    return {"index_1": index_1, "index_2": index_2, "values": rows}


def _library_units(text: str) -> Dict[str, str]:
    time = re.search(r"(?m)^\s*time_unit\s*:\s*\"([^\"]+)\"", text)
    cap = re.search(
        r"(?m)^\s*capacitive_load_unit\s*\(\s*([^,]+),\s*([^)]*)\)",
        text,
    )
    return {
        "time": time.group(1).strip() if time else "unknown",
        "capacitance": (
            "%s %s" % (cap.group(1).strip(), cap.group(2).strip())
            if cap else "unknown"
        ),
    }


def _cell_block(text: str, cell: str) -> str:
    for name, block in _named_blocks(text, "cell"):
        if name == cell:
            return block
    raise LibertyError("Liberty cell not found: %s" % cell)


def _resolve_cell_name(base: str, flavor: str) -> str:
    tag = FLAVOR_TAG[flavor]
    return base if base.endswith(tag) else base + tag


def _intrinsic_map(path: Optional[Path]) -> Dict[Tuple[str, str], float]:
    if path is None:
        return {}
    raw = json.loads(path.read_text())
    result: Dict[Tuple[str, str], float] = {}
    if isinstance(raw, dict) and "records" in raw:
        raw = raw["records"]
    if isinstance(raw, dict):
        for cell, pins in raw.items():
            if not isinstance(pins, dict):
                continue
            for pin, value in pins.items():
                if isinstance(value, dict):
                    value = value.get("c_intrinsic_pf")
                if value is not None:
                    result[(str(cell), str(pin))] = float(value)
        return result
    if isinstance(raw, list):
        for record in raw:
            result[(str(record["cell"]), str(record["pin"]))] = float(
                record["c_intrinsic_pf"]
            )
        return result
    raise ValueError("intrinsic JSON must be an object or records list")


def _pin_record(cell: str, name: str, block: str,
                intrinsic: Mapping[Tuple[str, str], float]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "name": name,
        "direction": _scalar(block, "direction"),
    }
    for field in ("capacitance", "rise_capacitance", "fall_capacitance"):
        record[field + "_pf"] = _number(block, field)
    if record["direction"] == "input":
        intrinsic_value = intrinsic.get((cell, name))
        if intrinsic_value is None:
            record["intrinsic_capacitance_pf"] = None
            record["local_capacitance_pf"] = None
            record["residual_status"] = "intrinsic_input_missing"
        else:
            liberty_value = record["capacitance_pf"]
            record["intrinsic_capacitance_pf"] = intrinsic_value
            if liberty_value is None:
                record["local_capacitance_pf"] = None
                record["residual_status"] = "liberty_input_missing"
            else:
                residual = liberty_value - intrinsic_value
                record["local_capacitance_pf"] = residual
                record["residual_status"] = (
                    "ok" if residual >= 0.0 else "negative_residual"
                )
    return record


def _timing_record(block: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "related_pin": None,
        "sdf_cond": _scalar(block, "sdf_cond"),
        "cell_rise": _table(block, "cell_rise"),
        "cell_fall": _table(block, "cell_fall"),
        "rise_transition": _table(block, "rise_transition"),
        "fall_transition": _table(block, "fall_transition"),
    }
    related = _scalar(block, "related_pin")
    if related is not None:
        result["related_pin"] = related.strip('"')
    return result


def _slope_records(table: Mapping[str, Any], transition: str) -> List[Dict[str, Any]]:
    loads = list(table["index_2"])
    records: List[Dict[str, Any]] = []
    for row_index, (slew, row) in enumerate(zip(table["index_1"], table["values"])):
        for left in range(len(loads) - 1):
            c0, c1 = loads[left], loads[left + 1]
            if c1 == c0:
                continue
            slope = (row[left + 1] - row[left]) / (c1 - c0)
            records.append({
                "transition": transition,
                "row_index": row_index,
                "input_slew_ns": slew,
                "load_left_pf": c0,
                "load_right_pf": c1,
                "delay_slope_ns_per_pf": slope,
                "r_thevenin_kohm": slope / math.log(2.0),
            })
    return records


def characterize_cell(text: str, cell: str,
                      intrinsic: Mapping[Tuple[str, str], float]) -> Dict[str, Any]:
    block = _cell_block(text, cell)
    pins = list(_named_blocks(block, "pin"))
    input_records = []
    output_records = []
    for name, pin_block in pins:
        record = _pin_record(cell, name, pin_block, intrinsic)
        if record["direction"] == "input":
            input_records.append(record)
        elif record["direction"] == "output":
            timing_records = []
            for timing_block in _anonymous_blocks(pin_block, "timing"):
                timing = _timing_record(timing_block)
                slopes = []
                if timing["cell_rise"] is not None:
                    slopes.extend(_slope_records(timing["cell_rise"], "rise"))
                if timing["cell_fall"] is not None:
                    slopes.extend(_slope_records(timing["cell_fall"], "fall"))
                timing["driver_slope_records"] = slopes
                timing_records.append(timing)
            output_records.append({
                "name": name,
                "timing": timing_records,
            })
    return {
        "input_pins": input_records,
        "output_pins": output_records,
    }


def default_library(flavor: str) -> Path:
    tag = LIBRARY_TAG[flavor]
    return LIB_DIR / ("ics55_LLSC_%s" % tag) / "liberty" / (
        "ics55_LLSC_%s_typ_tt_1p2_25_nldm.lib" % tag
    )


def report(library: Path, cells: Iterable[str], flavor: str,
           intrinsic: Mapping[Tuple[str, str], float]) -> Dict[str, Any]:
    text = library.read_text()
    resolved = [_resolve_cell_name(cell, flavor) for cell in cells]
    return {
        "schema_version": 1,
        "kind": "ics55_layer2_liberty_characterization",
        "source": str(library),
        "flavor": flavor,
        "units": _library_units(text),
        "driver_resistance_definition": (
            "r_thevenin_kohm = (d_delay_ns / d_load_pf) / ln(2); "
            "local 50-percent first-order estimate"
        ),
        "cells": {
            cell: characterize_cell(text, cell, intrinsic)
            for cell in resolved
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavor", choices=sorted(FLAVOR_TAG), default="svt")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--cells", default=",".join(DEFAULT_CELLS))
    parser.add_argument("--intrinsic-json", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    library = args.library.expanduser() if args.library else default_library(args.flavor)
    if not library.is_file():
        parser.error("Liberty file not found: %s" % library)
    cells = [cell.strip() for cell in args.cells.split(",") if cell.strip()]
    if not cells:
        parser.error("--cells must contain at least one cell")
    intrinsic = _intrinsic_map(
        args.intrinsic_json.expanduser() if args.intrinsic_json else None
    )
    try:
        result = report(library, cells, args.flavor, intrinsic)
    except (LibertyError, OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().write_text(rendered)
        print(args.out.expanduser())
    else:
        print(rendered, end="")

if __name__ == "__main__":
    main()
