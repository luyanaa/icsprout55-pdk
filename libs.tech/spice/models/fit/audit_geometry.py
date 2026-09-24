#!/usr/bin/env python3
"""Audit released CDL geometry against the rendered BSIM4 model cards.

This is a structural/evidence-bound audit.  It never adds instance geometry
parameters and it does not infer foundry junction geometry from layout.  The
checks answer whether the current flat CDL and Xyce model are internally
consistent before any C-V or multi-input timing fit:

* every released MOS has explicit drawn W/L and m=1;
* no released MOS relies on an unreviewed AS/AD/PS/PD/NF/SA/SB/SD/XL/LINT
  instance override;
* the rendered cards use the expected CAPMOD/GEOMOD/LINT and junction-sidewall
  fields; and
* all enabled LDE coefficients are reported explicitly.

The absence of AS/AD/PS/PD is intentional in the released CDL.  BSIM4/Xyce
therefore supplies its default geometry for the omitted fields; this tool
reports that boundary rather than manufacturing instance values.  A
representative INVX1 GDS check separately confirms nonzero diffusion
extensions, so a complete junction-area model still requires LVS/device
mapping that is not present in the release.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, Mapping

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CDL_ROOT = ROOT / "IP" / "STD_cell" / "ics55_LLSC_H7C_V1p10C100"
MODEL_PATH = HERE.parent / "fitted" / "ics55_mos_core.l"
FLAVORS = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}
FORBIDDEN_INSTANCE_FIELDS = {
    "as", "ad", "ps", "pd", "nf", "sa", "sb", "sd", "xl", "lint",
}
LDE_FIELDS = (
    "lpe0", "lpeb", "dmcg", "dmci", "dmdg", "dmcgt", "dwj", "xgw", "xgl",
)
NUMBER = re.compile(
    r"^[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?([munpfkMG]?)$",
    re.IGNORECASE,
)


def _number(value: str) -> float:
    """Parse the CDL suffixes used by the released netlists."""
    match = NUMBER.match(value.strip())
    if not match:
        raise ValueError("unsupported numeric literal: %s" % value)
    suffix = match.group(1).lower()
    scale = {
        "": 1.0,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "g": 1e9,
    }[suffix]
    return float(value[:-len(match.group(1))] if match.group(1) else value) * scale


def _parse_model_cards(text: str) -> Dict[str, Dict[str, float]]:
    """Return scalar model assignments keyed by model name."""
    result: Dict[str, Dict[str, float]] = {}
    block_pattern = re.compile(
        r"\.model\s+(\S+)\s+.*?level\s*=\s*54(.*?)(?=\.model\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    assignment = re.compile(
        r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*=\s*"
        r"([+\-]?\d*\.?\d+(?:[eE][+\-]?\d+)?)",
    )
    for match in block_pattern.finditer(text):
        result[match.group(1)] = {
            key.lower(): float(value)
            for key, value in assignment.findall(match.group(0))
        }
    if len(result) != 6:
        raise ValueError("expected six rendered level-54 cards, found %d" % len(result))
    return result


def _audit_cdl(path: Path) -> Dict[str, object]:
    # Keep the parser dependency local so the script remains runnable from the
    # fit directory and does not duplicate the released CDL in this report.
    import cdl_parser  # pylint: disable=import-outside-toplevel

    cells = cdl_parser.load(path)
    attrs: Dict[str, int] = {}
    lengths = []
    multipliers = []
    mos = 0
    for cell in cells.values():
        for line in cell["body"]:
            if not line.startswith("M"):
                continue
            mos += 1
            tokens = line.split()
            fields = {
                token.split("=", 1)[0].lower(): token.split("=", 1)[1]
                for token in tokens[6:]
                if "=" in token
            }
            for key in fields:
                attrs[key] = attrs.get(key, 0) + 1
            lengths.append(fields["l"])
            multipliers.append(fields["m"])
    unsupported = sorted(FORBIDDEN_INSTANCE_FIELDS & set(attrs))
    unique_lengths = sorted({round(_number(value), 15) for value in lengths})
    return {
        "path": str(path),
        "cells": len(cells),
        "mos": mos,
        "attribute_counts": attrs,
        "forbidden_instance_fields_present": unsupported,
        "m_values": sorted(set(multipliers)),
        "drawn_lengths_m": unique_lengths,
        "all_lengths_explicit": len(lengths) == mos,
        "all_multipliers_explicit": len(multipliers) == mos,
    }


def _audit_models(path: Path) -> Dict[str, object]:
    cards = _parse_model_cards(path.read_text())
    required = ("capmod", "geomod", "lint", "cgso", "cgdo", "cjs", "cjd",
                "cjsws", "cjswd", "cjswgs", "cjswgd")
    models = {}
    for name, values in cards.items():
        missing = [key for key in required if key not in values]
        models[name] = {
            "capmod": values.get("capmod"),
            "geomod": values.get("geomod"),
            "lint_m": values.get("lint"),
            "xl_model_present": "xl" in values,
            "cgso_f_per_m": values.get("cgso"),
            "cgdo_f_per_m": values.get("cgdo"),
            "junction": {key: values.get(key) for key in
                         ("cjs", "cjd", "cjsws", "cjswd", "cjswgs", "cjswgd")},
            "lde": {key: values.get(key) for key in LDE_FIELDS},
            "missing_required_fields": missing,
        }
    return models


def _bbox(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), max(xs), min(ys), max(ys)


def _horizontal_span(points, y):
    intersections = []
    for first, second in zip(points, points[1:]):
        x0, y0 = first
        x1, y1 = second
        if y0 == y1:
            if y == y0:
                intersections.extend((x0, x1))
            continue
        if min(y0, y1) <= y <= max(y0, y1):
            fraction = (y - y0) / (y1 - y0)
            intersections.append(x0 + fraction * (x1 - x0))
    if len(intersections) < 2:
        raise ValueError("cannot intersect POLY at y=%g" % y)
    return min(intersections), max(intersections)


def _polygon_area(points):
    return abs(sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )) / 2.0


def _audit_representative_gds() -> Dict[str, object]:
    """Show whether a released layout has nonzero diffusion extensions.

    This is evidence only: without LVS, the two sides cannot be assigned to
    CDL source/drain names for every device.  The check deliberately does not
    turn these areas into instance parameters.
    """
    import rc_extraction  # pylint: disable=import-outside-toplevel

    path = (CDL_ROOT / "ics55_LLSC_H7CR" / "gds" /
            "ics55_LLSC_H7CR.gds")
    gds_path = path
    cell = rc_extraction._read_gds(gds_path, ["INVX1H7R"])["INVX1H7R"]
    active = [poly for poly in cell.polygons if
              (poly.layer, poly.datatype) == (2, 1)]
    poly = [item for item in cell.polygons if
            (item.layer, item.datatype) == (41, 1)]
    if len(active) != 2 or len(poly) != 1:
        raise ValueError("unexpected INVX1H7R ACT/POLY topology")
    regions = []
    extension_area = 0.0
    for item in active:
        x0, x1, y0, y1 = _bbox(item.points)
        height = y1 - y0
        gate_x0, gate_x1 = _horizontal_span(
            poly[0].points, (y0 + y1) / 2.0
        )
        left = max(0.0, gate_x0 - x0) * height
        right = max(0.0, x1 - gate_x1) * height
        extension_area += left + right
        regions.append({
            "active_bbox_um": [x0, x1, y0, y1],
            "active_area_um2": _polygon_area(item.points),
            "left_extension_area_um2": left,
            "right_extension_area_um2": right,
        })
    return {
        "cell": "INVX1H7R",
        "act_polygon_count": len(active),
        "poly_polygon_count": len(poly),
        "gate_bbox_um": list(_bbox(poly[0].points)),
        "regions": regions,
        "nonzero_source_drain_extension_area_um2": extension_area,
        "source": str(gds_path),
    }


def audit() -> Dict[str, object]:
    models = _audit_models(MODEL_PATH)
    flavors = {}
    for flavor, tag in FLAVORS.items():
        cdl = CDL_ROOT / ("ics55_LLSC_%s" % tag) / "cdl" / ("ics55_LLSC_%s.cdl" % tag)
        flavors[flavor] = _audit_cdl(cdl)
    gds = _audit_representative_gds()
    return {
        "model_path": str(MODEL_PATH),
        "flavors": flavors,
        "models": models,
        "gds": gds,
        "checks": {
            "all_cdl_lengths_explicit": all(row["all_lengths_explicit"] for row in flavors.values()),
            "all_cdl_m_explicit": all(row["all_multipliers_explicit"] for row in flavors.values()),
            "no_explicit_geometry_or_finger_fields": all(
                not row["forbidden_instance_fields_present"] for row in flavors.values()
            ),
            "all_m_equal_one": all(row["m_values"] == ["1"] for row in flavors.values()),
            "required_model_fields_present": all(
                not row["missing_required_fields"] for row in models.values()
            ),
            "all_lint_zero": all(
                row["lint_m"] == 0.0 for row in models.values()
            ),
            "no_model_xl": all(not row["xl_model_present"] for row in models.values()),
            "capmod_two": all(row["capmod"] == 2.0 for row in models.values()),
            "geomod_one": all(row["geomod"] == 1.0 for row in models.values()),
            "lde_fields_zero": all(
                all(value == 0.0 for value in row["lde"].values())
                for row in models.values()
            ),
            "gds_has_diffusion_extension": (
                gds["nonzero_source_drain_extension_area_um2"] > 0.0
            ),
        },
    }


def _print_summary(report: Mapping[str, object]) -> None:
    checks = report["checks"]
    print("MOS geometry audit")
    for name, value in checks.items():
        print("  %-42s %s" % (name, "PASS" if value else "FAIL"))
    for flavor, row in report["flavors"].items():
        lengths = ", ".join("%.3gnm" % (value * 1e9) for value in row["drawn_lengths_m"])
        print("  %s: %d cells, %d MOS, Ldrawn={%s}, m=%s" %
              (flavor, row["cells"], row["mos"], lengths, ",".join(row["m_values"])))
    print("  INVX1H7R GDS source/drain extension area (unassigned): %.5g um^2" %
          report["gds"]["nonzero_source_drain_extension_area_um2"])
    print("  rendered cards: CAPMOD=2, GEOMOD=1, LINT=0, no model XL")
    print("  instance AS/AD/PS/PD/NF/SA/SB/SD/XL/LINT are absent; no values added")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit the complete JSON report")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_summary(report)
    if not all(report["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
