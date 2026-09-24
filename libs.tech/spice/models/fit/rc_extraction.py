#!/usr/bin/env python3
"""Manual, device-aware RC extraction for released ICS55 std-cell GDS.

The released library has no LVS/PEX netlist.  This module therefore uses a
strict ownership boundary rather than guessing electrical connectivity:

* ACT, POLY, implants, wells, and contacts are device-owned and never receive
  standalone interconnect R/C.
* M1..M5, vias, thick metal, and pad metal are interconnect-owned.
* Only interconnect polygons carrying a duplicated top-level GDS pin label are
  assigned to a CDL net.  Unlabelled interconnect is reported and omitted.

That last rule is deliberate.  It prevents double-counting device parasitics
and prevents an inferred internal-net assignment from silently changing a
MOS fit.  The released inverter layouts expose all signal M1 polygons through
labels, so INVX1/3/4 can be used by the timing fitter.  Other cells may report
unmapped internal metal until a manual topology map or LVS exists.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


EPS = 1.0e-9

# GDS layer/datatype ownership.  These names mirror libs.tech/klayout/tech/ics55.map.
DEVICE_LAYERS = frozenset(
    {
        (2, 1),   # ACT
        (9, 1),   # NW
        (17, 1), (18, 1), (21, 1), (22, 1),  # Vt implants
        (28, 1),  # IOWELL
        (41, 1), (41, 4),  # POLY/PPO
        (52, 1), (53, 1), (55, 1),  # implants/ESD
        (71, 1), (72, 1),  # IOACT/CT
        (261, 12),  # VPW marker
    }
)
INTERCONNECT_LAYERS = {
    (81, 1): "M1",
    (82, 1): "M2",
    (83, 1): "M3",
    (84, 1): "M4",
    (85, 1): "M5",
    (91, 1): "V1",
    (92, 1): "V2",
    (93, 1): "V3",
    (94, 1): "V4",
    (103, 1): "TM2",
    (113, 1): "TV2",
    (120, 1): "PADM",
    (121, 1): "ALPAD",
}

GDS_ELEMENT_TYPES = {0x08: "BOUNDARY", 0x09: "PATH", 0x0A: "SREF",
                     0x0B: "AREF", 0x0C: "TEXT", 0x2B: "BOX"}


class RCExtractionError(ValueError):
    """Raised when a layout or RC seed cannot be interpreted safely."""


@dataclass(frozen=True)
class _Polygon:
    layer: int
    datatype: int
    points: Tuple[Tuple[float, float], ...]


@dataclass(frozen=True)
class _Label:
    text: str
    x: float
    y: float


@dataclass
class _GDSCell:
    name: str
    polygons: List[_Polygon] = field(default_factory=list)
    labels: List[_Label] = field(default_factory=list)


@dataclass(frozen=True)
class MetalRC:
    layer: str
    sheet_resistance_ohm: float
    area_cap_pf_per_um2: float
    edge_cap_pf_per_um: float
    default_width_um: float


@dataclass
class PinRC:
    name: str
    resistance_ohm: float = 0.0
    capacitance_pf: float = 0.0
    polygon_count: int = 0
    contact_count: int = 0


@dataclass
class CellRC:
    """Extracted signal-net parasitics and audit metadata for one cell."""

    cell_name: str
    pins: Dict[str, PinRC]
    unmapped_interconnect: List[Tuple[int, int]]
    device_polygon_count: int
    interconnect_polygon_count: int
    warnings: List[str]
    mapping_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def has_unmapped_interconnect(self) -> bool:
        return bool(self.unmapped_interconnect)

    def summary(self) -> Dict[str, object]:
        return {
            "cell": self.cell_name,
            "pins": {
                name: {
                    "resistance_ohm": record.resistance_ohm,
                    "capacitance_pf": record.capacitance_pf,
                    "polygon_count": record.polygon_count,
                    "contact_count": record.contact_count,
                }
                for name, record in sorted(self.pins.items())
            },
            "device_polygon_count": self.device_polygon_count,
            "interconnect_polygon_count": self.interconnect_polygon_count,
            "interconnect_mapping": dict(self.mapping_counts),
            "unmapped_interconnect": [
                {"layer": layer, "datatype": datatype}
                for layer, datatype in self.unmapped_interconnect
            ],
            "warnings": list(self.warnings),
        }

    def spice_netlist(
        self,
        netlist: Sequence[str],
        *,
        include_resistance: bool = True,
        include_capacitance: bool = True,
    ) -> Tuple[List[str], List[str]]:
        """Return ``(rewritten_mos, parasitic_elements)`` for a flat CDL body.

        Each extracted signal net is split into an external pin node and a
        device-side node.  The metal capacitance remains on the external node;
        the equivalent contact-to-pin resistance is placed in series.  Power
        rails are intentionally absent from ``self.pins`` so leakage decks do
        not acquire unverified supply-network drops.
        """
        rewritten: List[str] = []
        elements: List[str] = []
        split_nodes: Dict[str, str] = {}
        for name, record in sorted(self.pins.items()):
            if include_resistance and record.resistance_ohm > 0.0:
                safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
                split_nodes[name] = "__rc_%s" % safe
                elements.append(
                    "RRC_%s %s %s %.12g" %
                    (safe, name, split_nodes[name], record.resistance_ohm)
                )
            if include_capacitance and record.capacitance_pf > 0.0:
                safe = re.sub(r"[^A-Za-z0-9_]", "_", name)
                elements.append(
                    "CRC_%s %s 0 %.12gp" %
                    (safe, name, record.capacitance_pf)
                )

        for line in netlist:
            parts = line.split()
            if len(parts) >= 6 and parts[0].startswith("M"):
                nodes = [split_nodes.get(node, node) for node in parts[1:5]]
                rewritten.append("%s %s %s" % (parts[0], " ".join(nodes), " ".join(parts[5:])))
            else:
                rewritten.append(line)
        return rewritten, elements


def _gds_real8(data: bytes) -> float:
    if data == b"\x00" * 8:
        return 0.0
    sign = -1.0 if data[0] & 0x80 else 1.0
    exponent = (data[0] & 0x7F) - 64
    mantissa = int.from_bytes(data[1:], "big") / float(1 << 56)
    return sign * mantissa * (16.0 ** exponent)


def _gds_ints(data: bytes, width: int) -> Tuple[int, ...]:
    if len(data) % width:
        raise RCExtractionError("malformed GDS integer record")
    code = "h" if width == 2 else "i"
    return struct.unpack(">%d%s" % (len(data) // width, code), data)


def _read_gds(path: Path, wanted: Iterable[str]) -> Dict[str, _GDSCell]:
    wanted_set = set(wanted)
    if not wanted_set:
        raise RCExtractionError("no GDS cell names requested")
    blob = path.read_bytes()
    position = 0
    dbu_um: Optional[float] = None
    current_name: Optional[str] = None
    current: Optional[_GDSCell] = None
    element: Optional[Dict[str, object]] = None
    cells: Dict[str, _GDSCell] = {}

    while position + 4 <= len(blob):
        length, record_type, data_type = struct.unpack_from(">HBB", blob, position)
        if length == 0 and blob[position:] == b"\x00" * (len(blob) - position):
            break
        if length < 4 or position + length > len(blob):
            raise RCExtractionError("malformed GDS record at byte %d" % position)
        data = blob[position + 4:position + length]
        position += length

        if record_type == 0x05:  # BGNSTR
            current_name = None
            current = None
            element = None
        elif record_type == 0x06:  # STRNAME
            current_name = data.rstrip(b"\x00").decode("ascii", "replace")
            if current_name in wanted_set:
                current = _GDSCell(current_name)
                cells[current_name] = current
        elif record_type == 0x03:  # UNITS: user unit and database unit in metres
            if len(data) != 16:
                raise RCExtractionError("malformed GDS UNITS record")
            dbu_um = _gds_real8(data[8:]) * 1.0e6
        elif record_type in GDS_ELEMENT_TYPES:
            element = {"type": GDS_ELEMENT_TYPES[record_type]}
        elif record_type == 0x11:  # ENDEL
            if element is not None and current is not None:
                kind = element.get("type")
                if kind == "BOUNDARY" and "layer" in element and "datatype" in element and "xy" in element:
                    xy = element["xy"]
                    if not isinstance(xy, tuple) or len(xy) < 8 or len(xy) % 2:
                        raise RCExtractionError("malformed boundary in %s" % current.name)
                    points = tuple(
                        (xy[index] * (dbu_um or 0.001), xy[index + 1] * (dbu_um or 0.001))
                        for index in range(0, len(xy), 2)
                    )
                    current.polygons.append(
                        _Polygon(int(element["layer"]), int(element["datatype"]), points)
                    )
                elif kind == "TEXT" and "layer" in element and "xy" in element and "string" in element:
                    xy = element["xy"]
                    if not isinstance(xy, tuple) or len(xy) < 2:
                        raise RCExtractionError("malformed text label in %s" % current.name)
                    current.labels.append(
                        _Label(str(element["string"]), xy[0] * (dbu_um or 0.001), xy[1] * (dbu_um or 0.001))
                    )
            element = None
        elif element is not None and current is not None and current_name in wanted_set:
            if record_type == 0x0D:  # LAYER
                element["layer"] = _gds_ints(data, 2)[0]
            elif record_type == 0x0E:  # DATATYPE
                element["datatype"] = _gds_ints(data, 2)[0]
            elif record_type == 0x10:  # XY
                element["xy"] = _gds_ints(data, 4)
            elif record_type == 0x19:  # STRING
                element["string"] = data.rstrip(b"\x00").decode("ascii", "replace")

    if dbu_um is None:
        raise RCExtractionError("GDS has no UNITS record")
    missing = wanted_set - cells.keys()
    if missing:
        raise RCExtractionError("GDS cells not found: %s" % ", ".join(sorted(missing)))
    return cells


def _point_on_segment(point: Tuple[float, float], left: Tuple[float, float], right: Tuple[float, float]) -> bool:
    cross = ((point[0] - left[0]) * (right[1] - left[1]) -
             (point[1] - left[1]) * (right[0] - left[0]))
    if abs(cross) > 1.0e-8:
        return False
    return (
        min(left[0], right[0]) - 1.0e-8 <= point[0] <= max(left[0], right[0]) + 1.0e-8
        and min(left[1], right[1]) - 1.0e-8 <= point[1] <= max(left[1], right[1]) + 1.0e-8
    )


def _point_in_polygon(point: Tuple[float, float], polygon: Sequence[Tuple[float, float]]) -> bool:
    if any(_point_on_segment(point, left, right) for left, right in zip(polygon, polygon[1:])):
        return True
    inside = False
    x, y = point
    for left, right in zip(polygon, polygon[1:]):
        if (left[1] > y) != (right[1] > y):
            x_cross = (right[0] - left[0]) * (y - left[1]) / (right[1] - left[1]) + left[0]
            if x < x_cross:
                inside = not inside
    return inside


def _polygon_area_perimeter(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    area = 0.0
    perimeter = 0.0
    for left, right in zip(points, points[1:]):
        area += left[0] * right[1] - right[0] * left[1]
        perimeter += ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
    return abs(area) / 2.0, perimeter


def _minimum_edge(points: Sequence[Tuple[float, float]]) -> float:
    lengths = [
        ((right[0] - left[0]) ** 2 + (right[1] - left[1]) ** 2) ** 0.5
        for left, right in zip(points, points[1:])
    ]
    positive = [length for length in lengths if length > EPS]
    return min(positive) if positive else 0.0


def _centroid(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _load_metal_rc(lef: Path, layer: str = "MET1") -> MetalRC:
    text = lef.read_text()
    match = re.search(r"(?ms)^LAYER\s+%s\s*\n(.*?)^END\s+%s\s*$" % (re.escape(layer), re.escape(layer)), text)
    if match is None:
        raise RCExtractionError("routing layer %s not found in %s" % (layer, lef))
    block = match.group(1)

    def number(pattern: str, field: str) -> float:
        found = re.search(pattern + r"\s+([+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?)\s*;", block)
        if found is None:
            raise RCExtractionError("%s missing for %s" % (field, layer))
        value = float(found.group(1))
        if value < 0.0:
            raise RCExtractionError("%s is negative for %s" % (field, layer))
        return value

    return MetalRC(
        layer=layer,
        sheet_resistance_ohm=number(r"RESISTANCE\s+RPERSQ", "sheet resistance"),
        area_cap_pf_per_um2=number(r"CAPACITANCE\s+CPERSQDIST", "area capacitance"),
        edge_cap_pf_per_um=number(r"EDGECAPACITANCE", "edge capacitance"),
        default_width_um=number(r"WIDTH", "default width"),
    )


def _unique_labels(cell: _GDSCell) -> Dict[str, Tuple[float, float]]:
    labels: Dict[str, Tuple[float, float]] = {}
    for label in cell.labels:
        if label.text in labels:
            continue
        labels[label.text] = (label.x, label.y)
    return labels


def extract_cell(
    gds: Path,
    lef: Path,
    cell_name: str,
    signal_pins: Iterable[str],
) -> CellRC:
    """Extract labeled M1 signal-net RC for one released std-cell."""
    requested = set(signal_pins)
    cells = _read_gds(gds, [cell_name])
    cell = cells[cell_name]
    metal = _load_metal_rc(lef)
    labels = _unique_labels(cell)
    pins = {name: PinRC(name) for name in sorted(requested) if name in labels}
    signal_labels = {name: point for name, point in labels.items() if name in pins}
    all_pin_labels = {
        name: point for name, point in labels.items()
        if name not in {"VPW", "VNW"}
    }
    contacts = []
    for polygon in cell.polygons:
        if (polygon.layer, polygon.datatype) == (72, 1):
            contacts.append(_centroid(polygon.points))

    device_count = 0
    interconnect_count = 0
    unmapped = set()
    mapping_counts = {
        "signal_labeled_polygon_count": 0,
        "power_or_non_signal_labeled_polygon_count": 0,
        "unlabeled_polygon_count": 0,
        "non_m1_interconnect_polygon_count": 0,
    }
    for polygon in cell.polygons:
        layer_key = (polygon.layer, polygon.datatype)
        if layer_key in DEVICE_LAYERS:
            device_count += 1
            continue
        if layer_key not in INTERCONNECT_LAYERS:
            continue
        interconnect_count += 1
        if layer_key != (81, 1):
            mapping_counts["non_m1_interconnect_polygon_count"] += 1
            unmapped.add(layer_key)
            continue
        matching = [
            name for name, point in all_pin_labels.items()
            if _point_in_polygon(point, polygon.points)
        ]
        if not matching:
            mapping_counts["unlabeled_polygon_count"] += 1
            unmapped.add(layer_key)
            continue
        matching_signals = [name for name in matching if name in pins]
        if not matching_signals:
            # VDD/VSS are intentionally recognized but not split or loaded.
            mapping_counts["power_or_non_signal_labeled_polygon_count"] += 1
            continue
        mapping_counts["signal_labeled_polygon_count"] += 1
        for name in matching_signals:
            record = pins[name]
            area, perimeter = _polygon_area_perimeter(polygon.points)
            record.capacitance_pf += (
                area * metal.area_cap_pf_per_um2 + perimeter * metal.edge_cap_pf_per_um
            )
            record.polygon_count += 1
            width = max(_minimum_edge(polygon.points), metal.default_width_um)
            point = signal_labels[name]
            branch_resistance = []
            for contact in contacts:
                if _point_in_polygon(contact, polygon.points):
                    distance = abs(point[0] - contact[0]) + abs(point[1] - contact[1])
                    branch_resistance.append(
                        metal.sheet_resistance_ohm * max(distance, width / 2.0) / width
                    )
            record.contact_count += len(branch_resistance)
            if branch_resistance:
                conductance = sum(1.0 / value for value in branch_resistance if value > 0.0)
                if conductance > 0.0:
                    record.resistance_ohm += 1.0 / conductance

    # These are electrical signal pins that have no labeled interconnect.  The
    # omission is explicit; adding guessed parasitics would be less safe.
    warnings = []
    missing_labels = sorted(requested - pins.keys())
    if missing_labels:
        warnings.append("signal pins without GDS labels: %s" % ", ".join(missing_labels))
    if unmapped:
        warnings.append(
            "unmapped interconnect layers: %s" %
            ", ".join("%d/%d" % pair for pair in sorted(unmapped))
        )
    if mapping_counts["unlabeled_polygon_count"]:
        warnings.append(
            "unlabeled M1 polygons omitted: %d" %
            mapping_counts["unlabeled_polygon_count"]
        )
    return CellRC(
        cell_name=cell_name,
        pins=pins,
        unmapped_interconnect=sorted(unmapped),
        device_polygon_count=device_count,
        interconnect_polygon_count=interconnect_count,
        warnings=warnings,
        mapping_counts=mapping_counts,
    )


def flavor_paths(root: Path, flavor: str) -> Tuple[Path, Path]:
    """Return released GDS and tech-LEF paths for ``svt/lvt/hvt``."""
    tags = {"svt": "H7CR", "lvt": "H7CL", "hvt": "H7CH"}
    try:
        tag = tags[flavor]
    except KeyError as exc:
        raise RCExtractionError("unknown flavor %s" % flavor) from exc
    base = root / "IP" / "STD_cell" / "ics55_LLSC_H7C_V1p10C100" / ("ics55_LLSC_%s" % tag)
    return (
        base / "gds" / ("ics55_LLSC_%s.gds" % tag),
        root / "prtech" / "techLEF" / "N551P6M_ecos.lef",
    )


def extract_flavor_cell(root: Path, flavor: str, base_cell: str, signal_pins: Iterable[str]) -> CellRC:
    gds, lef = flavor_paths(root, flavor)
    gds_tag = {"svt": "H7R", "lvt": "H7L", "hvt": "H7H"}[flavor]
    return extract_cell(gds, lef, base_cell + gds_tag, signal_pins)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--flavor", choices=("svt", "lvt", "hvt"), required=True)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--pins", required=True, help="comma-separated signal pins")
    args = parser.parse_args()
    result = extract_flavor_cell(args.root, args.flavor, args.cell, args.pins.split(","))
    print(json.dumps(result.summary(), indent=2, sort_keys=True))
