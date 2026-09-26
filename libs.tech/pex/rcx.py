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

"""Clean-room, seed-based RCX extraction for the ICsprout55 PDK.

The input is a normalized routed-layout JSON document.  It deliberately does
not parse DEF/IDB: callers must provide the routed geometry explicitly, which
keeps this module independent of a particular place-and-route database.

Input contract (all lengths in um, capacitances in pF, resistances in ohm)::

    {
      "design": "demo",
      "nets": [{
        "name": "N1",
        "special": false,
        "ports": [{"name": "A", "direction": "input",
                   "layer": "MET1", "x": 0, "y": 0}],
        "segments": [{"id": "s0", "layer": "MET1",
                       "x1": 0, "y1": 0, "x2": 10, "y2": 0,
                       "width": 0.09}],
        "vias": [{"id": "v0", "name": "VIA1", "x": 10, "y": 0,
                  "lower_layer": "MET1", "upper_layer": "MET2"}]
      }]
    }

A process JSON may contain either one default model or named corners::

    {
      "corners": {
        "TYP": {
          "temperature_c": 25,
          "layers": {
            "MET1": {
              "thickness_um": 0.20,
              "resistance_ohm_per_square": 0.1122,
              "ground_capacitance_pf_per_um2": 0.000763,
              "edge_capacitance_pf_per_um": 0.0000339,
              "coupling": {
                "same_layer_pf_per_um": 0.00001,
                "cross_layer_pf_per_um2": 0.00002
              }
            }
          },
          "vias": {"VIA1": {"resistance_ohm": 2.5}}
        }
      }
    }

To opt into the recovered scalar/table subset of the ICS55 algorithm, add an
explicit `ics55_static` object to a corner (or at process-JSON top level)::

    {
      "ics55_static": {
        "enabled": true,
        "model": "TYP",
        "present_keys": ["TYP|M1|RPSQ"],
        "apply_fields": [
          "thickness_um",
          "resistance_ohm_per_square",
          "resistance_by_width"
        ]
      }
    }

`present_keys` must be exact keys read from a real process source.  An absent
scalar key selects the recovered binary fallback multiplier; a present scalar
key selects the recovered FNV-1a variation branch.  `THICKNESS` maps to
`thickness_um`, `RPSQ` maps to `resistance_ohm_per_square`, and
`RPSQ_VS_WIDTH` maps to `resistance_by_width` using the recovered indexed
`q_11*0.006 + q_29*0.002` branch.  `ETCH`, `CRT1`, `CRT2`, RHO/RPV/AREA, and
the remaining table families are reported but not applied because their
numeric source and field mapping remain unrecovered.

With only released LEF data, the extractor produces a seed-only SPEF with
coupling disabled.  It never invents coupling values.  Explicit coupling
models in process JSON enable same-layer parallel coupling and cross-layer
projected-area coupling.  The output follows the generic iRCX topology,
resistance, capacitance, and SPEF stages, but is intentionally independent of
the ICS55 binary SDK.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

EPS = 1.0e-9
NUMBER = r"[+\-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+\-]?\d+)?"


class RCXError(ValueError):
    """Raised when the normalized geometry or process model is invalid."""


def _float(value: Any, field_name: str, *, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise RCXError("%s must be numeric" % field_name) from exc
    if not math.isfinite(result):
        raise RCXError("%s must be finite" % field_name)
    return result


def _positive(value: Any, field_name: str, *, default: Optional[float] = None) -> Optional[float]:
    result = _float(value, field_name, default=default)
    if result is not None and result < 0.0:
        raise RCXError("%s must be non-negative" % field_name)
    return result


def _first(mapping: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def _table_pairs(table: Any, field_name: str) -> List[Tuple[float, float]]:
    if isinstance(table, Mapping):
        xs = _first(table, "x", "spacing_um", "area_um2", "width_um", "index")
        ys = _first(table, "values", "values_pf_per_um", "values_pf_per_um2", "values_ohm", "value")
        if xs is None or ys is None:
            raise RCXError("%s requires x/index and values" % field_name)
        if (
            not isinstance(xs, Sequence)
            or isinstance(xs, (str, bytes))
            or not isinstance(ys, Sequence)
            or isinstance(ys, (str, bytes))
        ):
            raise RCXError("%s has inconsistent axes" % field_name)
        if len(xs) != len(ys):
            raise RCXError("%s has inconsistent axes" % field_name)
        raw_pairs = list(zip(xs, ys))
    elif isinstance(table, Sequence) and not isinstance(table, (str, bytes)):
        raw_pairs = []
        for item in table:
            if isinstance(item, Mapping):
                px = _first(item, "x", "spacing_um", "area_um2", "width_um")
                py = _first(item, "value", "values", "capacitance", "resistance")
                if px is None or py is None:
                    raise RCXError("invalid %s record" % field_name)
                raw_pairs.append((px, py))
            elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) == 2:
                raw_pairs.append((item[0], item[1]))
            else:
                raise RCXError("invalid %s record" % field_name)
    else:
        raise RCXError("%s must be a one-dimensional table" % field_name)
    try:
        points = sorted((float(px), float(py)) for px, py in raw_pairs)
    except (TypeError, ValueError) as exc:
        raise RCXError("%s contains non-numeric values" % field_name) from exc
    if any(not math.isfinite(px) or not math.isfinite(py) for px, py in points):
        raise RCXError("%s contains non-finite values" % field_name)
    return points


def _lookup_1d(table: Any, x: float, field_name: str) -> Optional[float]:
    """Linearly interpolate a table, clamping to its endpoint values."""
    if table is None:
        return None
    if isinstance(table, Mapping):
        xs = _first(table, "x", "spacing_um", "area_um2", "width_um", "index")
        ys = _first(table, "values", "values_pf_per_um", "values_pf_per_um2", "values_ohm", "value")
        if xs is None or ys is None:
            raise RCXError("%s requires x/index and values" % field_name)
    elif isinstance(table, Sequence) and not isinstance(table, (str, bytes)):
        pairs = []
        for item in table:
            if isinstance(item, Mapping):
                px = _first(item, "x", "spacing_um", "area_um2", "width_um")
                py = _first(item, "value", "values", "capacitance", "resistance")
                if px is None or py is None:
                    raise RCXError("invalid %s record" % field_name)
                pairs.append((float(px), float(py)))
            elif isinstance(item, Sequence) and len(item) == 2:
                pairs.append((float(item[0]), float(item[1])))
            else:
                raise RCXError("invalid %s record" % field_name)
        pairs.sort()
        if not pairs:
            return None
        xs = [pair[0] for pair in pairs]
        ys = [pair[1] for pair in pairs]
    else:
        return _float(table, field_name)

    if not isinstance(xs, Sequence) or not isinstance(ys, Sequence) or len(xs) != len(ys) or not xs:
        raise RCXError("%s has inconsistent axes" % field_name)
    points = sorted((float(px), float(py)) for px, py in zip(xs, ys))
    if any(not math.isfinite(px) or not math.isfinite(py) for px, py in points):
        raise RCXError("%s contains non-finite values" % field_name)
    if len(points) == 1 or x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            if abs(x1 - x0) <= EPS:
                return y1
            fraction = (x - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)
    return points[-1][1]


def _temperature_factor(temperature_c: float, nominal_c: float, c1: float, c2: float) -> float:
    delta = temperature_c - nominal_c
    factor = 1.0 + c1 * delta + c2 * delta * delta
    if factor < 0.0:
        raise RCXError("temperature model produced a negative resistance factor")
    return factor


@dataclass
class LayerModel:
    name: str
    order: int
    width_um: Optional[float] = None
    resistance_ohm_per_square: Optional[float] = None
    resistance_by_width: Any = None
    resistivity_ohm_um: Optional[float] = None
    thickness_um: Optional[float] = None
    ground_capacitance_pf_per_um2: Optional[float] = None
    ground_capacitance_pf_per_um: Optional[float] = None
    edge_capacitance_pf_per_um: Optional[float] = None
    edge_factor: float = 1.0
    etch_um: float = 0.0
    temperature_nominal_c: Optional[float] = None
    temperature_c1: Optional[float] = None
    temperature_c2: Optional[float] = None
    coupling_same_layer_pf_per_um: Optional[float] = None
    coupling_same_layer_by_spacing: Any = None
    coupling_cross_layer_pf_per_um2: Optional[float] = None
    ics55_static_name: Optional[str] = None

    @classmethod
    def from_mappings(
        cls,
        name: str,
        order: int,
        seed: Optional[Mapping[str, Any]],
        override: Optional[Mapping[str, Any]],
    ) -> "LayerModel":
        merged: Dict[str, Any] = dict(seed or {})
        merged.update(dict(override or {}))
        coupling = merged.get("coupling")
        coupling = coupling if isinstance(coupling, Mapping) else {}
        temperature = merged.get("temperature")
        temperature = temperature if isinstance(temperature, Mapping) else {}
        return cls(
            name=name,
            order=order,
            width_um=_positive(_first(merged, "width_um", "width"), "%s.width_um" % name),
            resistance_ohm_per_square=_positive(
                _first(merged, "resistance_ohm_per_square", "sheet_resistance_ohm_per_square", "rpsq"),
                "%s.resistance_ohm_per_square" % name,
            ),
            resistance_by_width=_first(
                merged,
                "resistance_by_width",
                "rpsq_by_width",
                "rpsq_vs_width",
            ),
            resistivity_ohm_um=_positive(
                _first(merged, "resistivity_ohm_um", "rho_ohm_um", "rho"),
                "%s.resistivity_ohm_um" % name,
            ),
            thickness_um=_positive(
                _first(merged, "thickness_um", "thickness"), "%s.thickness_um" % name
            ),
            ground_capacitance_pf_per_um2=_positive(
                _first(
                    merged,
                    "ground_capacitance_pf_per_um2",
                    "capacitance_pf_per_um2",
                    "area_capacitance_pf_per_um2",
                ),
                "%s.ground_capacitance_pf_per_um2" % name,
            ),
            ground_capacitance_pf_per_um=_positive(
                _first(merged, "ground_capacitance_pf_per_um", "ground_cap_pf_per_um"),
                "%s.ground_capacitance_pf_per_um" % name,
            ),
            edge_capacitance_pf_per_um=_positive(
                _first(merged, "edge_capacitance_pf_per_um", "edge_cap_pf_per_um"),
                "%s.edge_capacitance_pf_per_um" % name,
            ),
            edge_factor=_positive(
                _first(merged, "edge_factor", default=1.0), "%s.edge_factor" % name, default=1.0
            ) or 1.0,
            etch_um=_positive(_first(merged, "etch_um", "etch", default=0.0), "%s.etch_um" % name, default=0.0)
            or 0.0,
            temperature_nominal_c=_float(
                _first(merged, "temperature_nominal_c", "nominal_temperature_c", default=temperature.get("nominal_c")),
                "%s.temperature_nominal_c" % name,
            ),
            temperature_c1=_float(
                _first(merged, "temperature_c1", "tmpr_coefficient1", default=temperature.get("c1")),
                "%s.temperature_c1" % name,
            ),
            temperature_c2=_float(
                _first(merged, "temperature_c2", "tmpr_coefficient2", default=temperature.get("c2")),
                "%s.temperature_c2" % name,
            ),
            coupling_same_layer_pf_per_um=_positive(
                _first(
                    merged,
                    "coupling_same_layer_pf_per_um",
                    "coupling_capacitance_pf_per_um",
                    default=coupling.get("same_layer_pf_per_um"),
                ),
                "%s.coupling_same_layer_pf_per_um" % name,
            ),
            coupling_same_layer_by_spacing=_first(
                merged,
                "coupling_same_layer_by_spacing",
                "coupling_by_spacing",
                default=coupling.get("same_layer_by_spacing"),
            ),
            coupling_cross_layer_pf_per_um2=_positive(
                _first(
                    merged,
                    "coupling_cross_layer_pf_per_um2",
                    "cross_layer_coupling_pf_per_um2",
                    default=coupling.get("cross_layer_pf_per_um2"),
                ),
                "%s.coupling_cross_layer_pf_per_um2" % name,
            ),
            ics55_static_name=(
                str(_first(merged, "ics55_layer_name", "ics55_model_name"))
                if _first(merged, "ics55_layer_name", "ics55_model_name") is not None
                else None
            ),
        )

    def effective_width(self, drawn_width_um: float) -> float:
        width = drawn_width_um - 2.0 * self.etch_um
        if width <= 0.0:
            raise RCXError("etch correction removes layer %s width" % self.name)
        return width

    def same_layer_coupling(self, spacing_um: float) -> Optional[float]:
        value = _lookup_1d(
            self.coupling_same_layer_by_spacing, spacing_um, "%s coupling_by_spacing" % self.name
        )
        if value is not None:
            return max(0.0, value)
        return self.coupling_same_layer_pf_per_um


@dataclass
class ViaModel:
    name: str
    resistance_ohm: Optional[float] = None
    resistance_by_area: Any = None
    etch_length_um: float = 0.0
    etch_width_um: float = 0.0
    temperature_nominal_c: Optional[float] = None
    temperature_c1: float = 0.0
    temperature_c2: float = 0.0

    @classmethod
    def from_mapping(cls, name: str, data: Any) -> "ViaModel":
        if not isinstance(data, Mapping):
            data = {"resistance_ohm": data}
        temperature = data.get("temperature")
        temperature = temperature if isinstance(temperature, Mapping) else {}
        etch = data.get("etch")
        etch = etch if isinstance(etch, Mapping) else {}
        return cls(
            name=name,
            resistance_ohm=_positive(
                _first(data, "resistance_ohm", "resistance"), "%s.resistance_ohm" % name
            ),
            resistance_by_area=_first(data, "resistance_by_area", "resistance_by_area_um2"),
            etch_length_um=_positive(
                _first(data, "etch_length_um", default=etch.get("length_um", 0.0)),
                "%s.etch_length_um" % name,
                default=0.0,
            )
            or 0.0,
            etch_width_um=_positive(
                _first(data, "etch_width_um", default=etch.get("width_um", 0.0)),
                "%s.etch_width_um" % name,
                default=0.0,
            )
            or 0.0,
            temperature_nominal_c=_float(
                _first(data, "temperature_nominal_c", "nominal_temperature_c", default=temperature.get("nominal_c")),
                "%s.temperature_nominal_c" % name,
            ),
            temperature_c1=_float(
                _first(data, "temperature_c1", "tmpr_coefficient1", default=temperature.get("c1")),
                "%s.temperature_c1" % name,
                default=0.0,
            )
            or 0.0,
            temperature_c2=_float(
                _first(data, "temperature_c2", "tmpr_coefficient2", default=temperature.get("c2")),
                "%s.temperature_c2" % name,
                default=0.0,
            )
            or 0.0,
        )


@dataclass
class CornerModel:
    name: str
    temperature_c: float
    nominal_temperature_c: float
    temperature_c1: float
    temperature_c2: float
    max_cross_layer: int
    layers: Dict[str, LayerModel]
    vias: Dict[str, ViaModel]
    ics55_static_enabled: bool = False
    ics55_static_model_name: Optional[str] = None
    ics55_static_report: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Port:
    name: str
    direction: str
    layer: str
    x: float
    y: float


@dataclass
class RawSegment:
    net: str
    source_id: str
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float
    width_um: Optional[float]

    @property
    def horizontal(self) -> bool:
        return abs(self.y1 - self.y2) <= EPS

    @property
    def vertical(self) -> bool:
        return abs(self.x1 - self.x2) <= EPS

    @property
    def length_um(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class Node:
    net: str
    index: int
    layer: str
    x: float
    y: float
    ports: List[Port] = field(default_factory=list)

    @property
    def key(self) -> Tuple[str, float, float]:
        return (self.layer, round(self.x, 9), round(self.y, 9))


@dataclass
class Edge:
    net: str
    index: int
    kind: str
    layer: str
    start: Node
    end: Node
    width_um: float = 0.0
    source_id: str = ""
    direct_resistance_ohm: Optional[float] = None
    via_model_name: Optional[str] = None
    via_area_um2: Optional[float] = None

    @property
    def edge_id(self) -> str:
        return "%s:e%d" % (self.net, self.index)

    @property
    def length_um(self) -> float:
        return math.hypot(self.end.x - self.start.x, self.end.y - self.start.y)

    @property
    def horizontal(self) -> bool:
        return abs(self.start.y - self.end.y) <= EPS

    @property
    def vertical(self) -> bool:
        return abs(self.start.x - self.end.x) <= EPS


@dataclass
class NetGraph:
    name: str
    special: bool
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    ports: List[Port] = field(default_factory=list)
    _nodes_by_key: Dict[Tuple[str, float, float], Node] = field(default_factory=dict, repr=False)

    def node(self, layer: str, x: float, y: float) -> Node:
        key = (layer, round(x, 9), round(y, 9))
        existing = self._nodes_by_key.get(key)
        if existing is not None:
            return existing
        result = Node(self.name, len(self.nodes), layer, float(x), float(y))
        self._nodes_by_key[key] = result
        self.nodes.append(result)
        return result

    def add_port(self, port: Port) -> None:
        if any(existing.name == port.name for existing in self.ports):
            raise RCXError("duplicate port %s in net %s" % (port.name, self.name))
        self.ports.append(port)
        self.node(port.layer, port.x, port.y).ports.append(port)


def _coordinate(value: Any, name: str) -> float:
    result = _float(value, name)
    if result is None:
        raise RCXError("missing %s" % name)
    return result


def _direction(value: Any) -> str:
    text = str(value or "inout").strip().lower()
    if text in {"i", "input", "in"}:
        return "I"
    if text in {"o", "output", "out"}:
        return "O"
    return "B"


def _parse_ports(net_data: Mapping[str, Any], net_name: str) -> List[Port]:
    records = net_data.get("ports", [])
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise RCXError("ports for net %s must be a list" % net_name)
    result = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise RCXError("port %s in net %s must be an object" % (index, net_name))
        name = str(record.get("name", "")).strip()
        layer = str(record.get("layer", "")).strip()
        if not name or not layer:
            raise RCXError("port %s in net %s needs name and layer" % (index, net_name))
        result.append(
            Port(
                name=name,
                direction=_direction(record.get("direction")),
                layer=layer,
                x=_coordinate(record.get("x"), "%s.ports[%d].x" % (net_name, index)),
                y=_coordinate(record.get("y"), "%s.ports[%d].y" % (net_name, index)),
            )
        )
    return result


def _parse_segments(net_data: Mapping[str, Any], net_name: str) -> List[RawSegment]:
    records = net_data.get("segments", [])
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise RCXError("segments for net %s must be a list" % net_name)
    result = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise RCXError("segment %s in net %s must be an object" % (index, net_name))
        layer = str(record.get("layer", "")).strip()
        if not layer:
            raise RCXError("segment %s in net %s needs a layer" % (index, net_name))
        segment = RawSegment(
            net=net_name,
            source_id=str(record.get("id", "s%d" % index)),
            layer=layer,
            x1=_coordinate(record.get("x1"), "%s.segments[%d].x1" % (net_name, index)),
            y1=_coordinate(record.get("y1"), "%s.segments[%d].y1" % (net_name, index)),
            x2=_coordinate(record.get("x2"), "%s.segments[%d].x2" % (net_name, index)),
            y2=_coordinate(record.get("y2"), "%s.segments[%d].y2" % (net_name, index)),
            width_um=_positive(record.get("width"), "%s.segments[%d].width" % (net_name, index)),
        )
        if segment.length_um <= EPS:
            raise RCXError("segment %s in net %s has zero length" % (segment.source_id, net_name))
        if not (segment.horizontal or segment.vertical):
            raise RCXError("segment %s in net %s is not Manhattan" % (segment.source_id, net_name))
        result.append(segment)
    return result


def _point_on_segment(segment: RawSegment, layer: str, x: float, y: float) -> bool:
    if layer != segment.layer:
        return False
    if segment.horizontal:
        return abs(y - segment.y1) <= EPS and min(segment.x1, segment.x2) - EPS <= x <= max(segment.x1, segment.x2) + EPS
    return abs(x - segment.x1) <= EPS and min(segment.y1, segment.y2) - EPS <= y <= max(segment.y1, segment.y2) + EPS


def _add_break(breaks: Dict[int, set], index: int, coordinate: float) -> None:
    breaks[index].add(round(coordinate, 9))


def _split_segments(segments: Sequence[RawSegment], ports: Sequence[Port]) -> List[RawSegment]:
    breaks: Dict[int, set] = {index: set() for index in range(len(segments))}
    for index, segment in enumerate(segments):
        _add_break(breaks, index, segment.x1 if segment.horizontal else segment.y1)
        _add_break(breaks, index, segment.x2 if segment.horizontal else segment.y2)
        for port in ports:
            if _point_on_segment(segment, port.layer, port.x, port.y):
                _add_break(breaks, index, port.x if segment.horizontal else port.y)

    for left_index, left in enumerate(segments):
        for right_index in range(left_index + 1, len(segments)):
            right = segments[right_index]
            if left.layer != right.layer:
                continue
            if left.horizontal and right.horizontal and abs(left.y1 - right.y1) <= EPS:
                low = max(min(left.x1, left.x2), min(right.x1, right.x2))
                high = min(max(left.x1, left.x2), max(right.x1, right.x2))
                if high - low > EPS:
                    _add_break(breaks, left_index, low)
                    _add_break(breaks, left_index, high)
                    _add_break(breaks, right_index, low)
                    _add_break(breaks, right_index, high)
            elif left.vertical and right.vertical and abs(left.x1 - right.x1) <= EPS:
                low = max(min(left.y1, left.y2), min(right.y1, right.y2))
                high = min(max(left.y1, left.y2), max(right.y1, right.y2))
                if high - low > EPS:
                    _add_break(breaks, left_index, low)
                    _add_break(breaks, left_index, high)
                    _add_break(breaks, right_index, low)
                    _add_break(breaks, right_index, high)
            elif left.horizontal and right.vertical:
                if min(left.x1, left.x2) - EPS <= right.x1 <= max(left.x1, left.x2) + EPS and min(right.y1, right.y2) - EPS <= left.y1 <= max(right.y1, right.y2) + EPS:
                    _add_break(breaks, left_index, right.x1)
                    _add_break(breaks, right_index, left.y1)
            elif left.vertical and right.horizontal:
                if min(right.x1, right.x2) - EPS <= left.x1 <= max(right.x1, right.x2) + EPS and min(left.y1, left.y2) - EPS <= right.y1 <= max(left.y1, left.y2) + EPS:
                    _add_break(breaks, left_index, right.y1)
                    _add_break(breaks, right_index, left.x1)

    result: List[RawSegment] = []
    for index, segment in enumerate(segments):
        coordinates = sorted(breaks[index])
        for piece_index, (start, end) in enumerate(zip(coordinates, coordinates[1:])):
            if end - start <= EPS:
                continue
            if segment.horizontal:
                x1, y1, x2, y2 = start, segment.y1, end, segment.y1
            else:
                x1, y1, x2, y2 = segment.x1, start, segment.x1, end
            result.append(
                RawSegment(
                    net=segment.net,
                    source_id="%s.%d" % (segment.source_id, piece_index),
                    layer=segment.layer,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    width_um=segment.width_um,
                )
            )
    return result


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RCXError("cannot read JSON %s: %s" % (path, exc)) from exc
    if not isinstance(raw, dict):
        raise RCXError("JSON root must be an object: %s" % path)
    return raw


def _load_lef_seed(path: Path) -> Dict[str, Any]:
    module_path = Path(__file__).with_name("rc_seed.py")
    spec = importlib.util.spec_from_file_location("ics55_rc_seed", module_path)
    if spec is None or spec.loader is None:
        raise RCXError("cannot load LEF adapter %s" % module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.extract(path)
    except (OSError, ValueError, TypeError) as exc:
        raise RCXError("cannot extract LEF seed %s: %s" % (path, exc)) from exc


def _load_ics55_static():
    module_path = Path(__file__).with_name("ics55_static.py")
    spec = importlib.util.spec_from_file_location("ics55_static_recovered", module_path)
    if spec is None or spec.loader is None:
        raise RCXError("cannot load recovered ICS55 static model %s" % module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_ics55_static_config(raw: Any, corner_name: str) -> Optional[Dict[str, Any]]:
    if raw is None or raw is False:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, Mapping):
        raise RCXError("%s.ics55_static must be an object" % corner_name)
    if not bool(raw.get("enabled", True)):
        return None
    model_name = str(
        _first(raw, "model", "model_name", "corner_model", default=corner_name)
    ).strip()
    if not model_name:
        raise RCXError("%s.ics55_static.model must not be empty" % corner_name)
    present_keys = _first(raw, "present_keys", "available_keys", "keys", default=[])
    if isinstance(present_keys, Mapping):
        present_keys = [str(key) for key, enabled in present_keys.items() if bool(enabled)]
    elif isinstance(present_keys, Sequence) and not isinstance(present_keys, (str, bytes)):
        present_keys = [str(key) for key in present_keys]
    else:
        raise RCXError("%s.ics55_static.present_keys must be a list or object" % corner_name)
    apply_fields = _first(
        raw,
        "apply_fields",
        "apply",
        default=["thickness_um", "resistance_ohm_per_square", "resistance_by_width"],
    )
    if apply_fields is False or apply_fields is None:
        apply_fields = []
    if not isinstance(apply_fields, Sequence) or isinstance(apply_fields, (str, bytes)):
        raise RCXError("%s.ics55_static.apply_fields must be a list" % corner_name)
    static = _load_ics55_static()
    allowed_fields = set(static.RECOVERED_FIELD_MAP.values()) | set(
        static.RECOVERED_TABLE_FIELD_MAP.values()
    )
    apply_fields = [str(value) for value in apply_fields]
    unknown_fields = sorted(set(apply_fields) - allowed_fields)
    if unknown_fields:
        raise RCXError(
            "%s.ics55_static.apply_fields contains unrecovered mappings: %s"
            % (corner_name, ", ".join(unknown_fields))
        )
    return {
        "model_name": model_name,
        "present_keys": present_keys,
        "apply_fields": apply_fields,
    }


def _apply_ics55_static(layer: LayerModel, config: Mapping[str, Any]) -> Dict[str, Any]:
    static = _load_ics55_static()
    layer_name = layer.ics55_static_name or layer.name
    factors = static.scalar_factors(
        str(config["model_name"]),
        layer_name,
        config.get("present_keys", []),
    )
    applied: Dict[str, Any] = {}
    for parameter, field_name in static.RECOVERED_FIELD_MAP.items():
        if field_name not in config.get("apply_fields", []):
            continue
        before = getattr(layer, field_name)
        if before is None:
            continue
        factor = float(factors[parameter]["factor"])
        after = before * factor
        setattr(layer, field_name, after)
        applied[field_name] = {
            "parameter": parameter,
            "before": before,
            "factor": factor,
            "after": after,
            "key": factors[parameter]["key"],
            "source": factors[parameter]["source"],
        }
    if "resistance_by_width" in config.get("apply_fields", []) and layer.resistance_by_width is not None:
        before_table = _table_pairs(layer.resistance_by_width, "%s.resistance_by_width" % layer.name)
        thickness_factor = float(factors["THICKNESS"]["factor"])
        rpsq_factor = float(factors["RPSQ"]["factor"])
        scaled_table = []
        table_entries = []
        for index, (width, value) in enumerate(before_table):
            key = static.indexed_key(str(config["model_name"]), layer_name, "RPSQ_VS_WIDTH", index)
            entry = static.width_table_factor(key, rpsq_factor)
            scaled_table.append([width * thickness_factor, value * entry["factor"]])
            table_entries.append(
                {
                    "index": index,
                    "key": key,
                    "before": [width, value],
                    "after": scaled_table[-1],
                    "factor": entry["factor"],
                    "variation_factor": entry["variation_factor"],
                }
            )
        layer.resistance_by_width = scaled_table
        applied["resistance_by_width"] = {
            "parameter": "RPSQ_VS_WIDTH",
            "source": "fnv1a_q11_q29",
            "entries": table_entries,
        }
    unapplied_tables = list(static.TABLE_FAMILIES)
    if "resistance_by_width" in applied:
        unapplied_tables.remove("RPSQ_VS_WIDTH")
    return {
        "layer_name": layer_name,
        "layer_class": static.layer_class(layer_name),
        "applied_fields": applied,
        "scalars": factors,
        "unapplied_scalar_parameters": list(static.UNMAPPED_SCALAR_PARAMETERS),
        "applied_table_families": (
            ["RPSQ_VS_WIDTH"] if "resistance_by_width" in applied else []
        ),
        "unapplied_table_families": unapplied_tables,
    }


def _ics55_static_report(config: Mapping[str, Any], layer_reports: Mapping[str, Any]) -> Dict[str, Any]:
    static = _load_ics55_static()
    return {
        "enabled": True,
        "model_name": config["model_name"],
        "corner_class": static.corner_class(str(config["model_name"])),
        "present_keys": list(config.get("present_keys", [])),
        "apply_fields": list(config.get("apply_fields", [])),
        "layers": dict(layer_reports),
        "unapplied_scalar_parameters": list(static.UNMAPPED_SCALAR_PARAMETERS),
        "unapplied_table_families": list(static.TABLE_FAMILIES),
        "note": "Only recovered THICKNESS, RPSQ, and RPSQ_VS_WIDTH mappings are applied; ITF/CAPTAB numeric values and proprietary table interpolation are not synthesized.",
    }




def build_corners(lef: Optional[Path], process_json: Optional[Path]) -> Dict[str, CornerModel]:
    lef_seed: Dict[str, Any] = {}
    if lef is not None:
        lef_seed = _load_lef_seed(lef)

    process: Dict[str, Any] = _load_json(process_json) if process_json else {}
    seed_layers = {
        str(record["name"]): dict(record)
        for record in lef_seed.get("routing_layers", [])
        if isinstance(record, Mapping) and record.get("name")
    }
    seed_vias = {
        str(record["name"]): dict(record)
        for record in lef_seed.get("vias", [])
        if isinstance(record, Mapping) and record.get("name")
    }

    raw_corners = process.get("corners")
    if not seed_layers:
        raw_layers = process.get("layers")
        if isinstance(raw_layers, Mapping):
            seed_layers = {str(name): dict(value) for name, value in raw_layers.items() if isinstance(value, Mapping)}
        elif isinstance(process.get("routing_layers"), Sequence):
            seed_layers = {
                str(record["name"]): dict(record)
                for record in process["routing_layers"]
                if isinstance(record, Mapping) and record.get("name")
            }
    if not seed_layers and isinstance(raw_corners, Mapping):
        for corner_value in raw_corners.values():
            if not isinstance(corner_value, Mapping) or not isinstance(corner_value.get("layers"), Mapping):
                continue
            seed_layers = {
                str(name): dict(value)
                for name, value in corner_value["layers"].items()
                if isinstance(value, Mapping)
            }
            if seed_layers:
                break
    if not seed_layers:
        raise RCXError("provide --lef or process JSON with routing layer models")

    if isinstance(raw_corners, Mapping) and raw_corners:
        corner_items = [(str(name), value) for name, value in raw_corners.items()]
    else:
        corner_items = [("TYP", process)]

    result: Dict[str, CornerModel] = {}
    for corner_name, corner_value in corner_items:
        data = corner_value if isinstance(corner_value, Mapping) else {}
        static_config = _parse_ics55_static_config(
            data.get("ics55_static", process.get("ics55_static")),
            corner_name,
        )
        layer_overrides = data.get("layers") if isinstance(data.get("layers"), Mapping) else {}
        ordered_names = list(seed_layers)
        for name in layer_overrides:
            if str(name) not in ordered_names:
                ordered_names.append(str(name))
        layers: Dict[str, LayerModel] = {}
        layer_reports: Dict[str, Any] = {}
        for order, name in enumerate(ordered_names):
            layer = LayerModel.from_mappings(
                name,
                order,
                seed_layers.get(name),
                layer_overrides.get(name) if isinstance(layer_overrides, Mapping) else None,
            )
            if static_config is not None:
                layer_reports[name] = _apply_ics55_static(layer, static_config)
            layers[name] = layer
        raw_vias = dict(seed_vias)
        if isinstance(data.get("vias"), Mapping):
            raw_vias.update({str(name): value for name, value in data["vias"].items()})
        vias = {name: ViaModel.from_mapping(name, value) for name, value in raw_vias.items()}
        temperature = _float(
            _first(data, "temperature_c", default=25.0),
            "%s.temperature_c" % corner_name,
            default=25.0,
        )
        nominal = _float(
            _first(data, "nominal_temperature_c", default=25.0),
            "%s.nominal_temperature_c" % corner_name,
            default=25.0,
        )
        corner_c1 = _float(data.get("temperature_c1"), "%s.temperature_c1" % corner_name, default=0.0)
        corner_c2 = _float(data.get("temperature_c2"), "%s.temperature_c2" % corner_name, default=0.0)
        max_cross_layer = _positive(
            data.get("max_cross_layer", 3), "%s.max_cross_layer" % corner_name, default=3
        )
        static_report = (
            _ics55_static_report(static_config, layer_reports)
            if static_config is not None
            else {}
        )
        result[corner_name] = CornerModel(
            name=corner_name,
            temperature_c=temperature if temperature is not None else 25.0,
            nominal_temperature_c=nominal if nominal is not None else 25.0,
            temperature_c1=corner_c1 if corner_c1 is not None else 0.0,
            temperature_c2=corner_c2 if corner_c2 is not None else 0.0,
            max_cross_layer=int(max_cross_layer if max_cross_layer is not None else 3),
            layers=layers,
            vias=vias,
            ics55_static_enabled=static_config is not None,
            ics55_static_model_name=(
                str(static_config["model_name"]) if static_config is not None else None
            ),
            ics55_static_report=static_report,
        )
    return result


def _via_layers(name: str, record: Mapping[str, Any], corner: CornerModel) -> Tuple[str, str]:
    lower = str(_first(record, "lower_layer", "below_layer", default="")).strip()
    upper = str(_first(record, "upper_layer", "above_layer", default="")).strip()
    if lower and upper:
        return lower, upper
    hits = [layer for layer in corner.layers if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(layer), name)]
    if len(hits) < 2:
        raise RCXError("via %s needs lower_layer and upper_layer" % name)
    hits.sort(key=lambda layer: corner.layers[layer].order)
    return hits[-2], hits[-1]


def _via_model_name(record: Mapping[str, Any], corner: CornerModel) -> Optional[str]:
    candidates = [str(value) for value in (_first(record, "model", "name", "layer", default=""),) if value]
    for candidate in candidates:
        if candidate in corner.vias:
            return candidate
    return candidates[0] if candidates else None


def _build_graphs(data: Mapping[str, Any], corner: CornerModel) -> List[NetGraph]:
    raw_nets = data.get("nets")
    if not isinstance(raw_nets, Sequence) or isinstance(raw_nets, (str, bytes)):
        raise RCXError("input must contain a nets list")
    graphs: List[NetGraph] = []
    seen_names = set()
    for net_index, net_data in enumerate(raw_nets):
        if not isinstance(net_data, Mapping):
            raise RCXError("net %d must be an object" % net_index)
        net_name = str(net_data.get("name", "")).strip()
        if not net_name:
            raise RCXError("net %d has no name" % net_index)
        if net_name in seen_names:
            raise RCXError("duplicate net %s" % net_name)
        seen_names.add(net_name)
        graph = NetGraph(net_name, bool(net_data.get("special", False)))
        ports = _parse_ports(net_data, net_name)
        for port in ports:
            if port.layer not in corner.layers:
                raise RCXError("port %s references unknown layer %s" % (port.name, port.layer))
            graph.add_port(port)
        raw_segments = _parse_segments(net_data, net_name)
        for segment in raw_segments:
            if segment.layer not in corner.layers:
                raise RCXError("segment %s references unknown layer %s" % (segment.source_id, segment.layer))
        for segment in _split_segments(raw_segments, ports):
            layer = corner.layers[segment.layer]
            width = segment.width_um if segment.width_um is not None else layer.width_um
            if width is None or width <= 0.0:
                raise RCXError("segment %s has no positive width" % segment.source_id)
            start = graph.node(segment.layer, segment.x1, segment.y1)
            end = graph.node(segment.layer, segment.x2, segment.y2)
            graph.edges.append(
                Edge(
                    net=net_name,
                    index=len(graph.edges),
                    kind="wire",
                    layer=segment.layer,
                    start=start,
                    end=end,
                    width_um=width,
                    source_id=segment.source_id,
                )
            )
        raw_vias = net_data.get("vias", [])
        if not isinstance(raw_vias, Sequence) or isinstance(raw_vias, (str, bytes)):
            raise RCXError("vias for net %s must be a list" % net_name)
        for via_index, record in enumerate(raw_vias):
            if not isinstance(record, Mapping):
                raise RCXError("via %d in net %s must be an object" % (via_index, net_name))
            via_name = str(_first(record, "name", "layer", default="VIA%d" % via_index))
            lower, upper = _via_layers(via_name, record, corner)
            if lower not in corner.layers or upper not in corner.layers:
                raise RCXError("via %s references unknown routing layers" % via_name)
            x = _coordinate(record.get("x"), "%s.vias[%d].x" % (net_name, via_index))
            y = _coordinate(record.get("y"), "%s.vias[%d].y" % (net_name, via_index))
            start = graph.node(lower, x, y)
            end = graph.node(upper, x, y)
            area = _positive(record.get("area_um2"), "%s.vias[%d].area_um2" % (net_name, via_index))
            graph.edges.append(
                Edge(
                    net=net_name,
                    index=len(graph.edges),
                    kind="via",
                    layer=via_name,
                    start=start,
                    end=end,
                    source_id=str(record.get("id", "v%d" % via_index)),
                    direct_resistance_ohm=_positive(record.get("resistance_ohm"), "%s.vias[%d].resistance_ohm" % (net_name, via_index)),
                    via_model_name=_via_model_name(record, corner) or via_name,
                    via_area_um2=area,
                )
            )
        graphs.append(graph)
    if not graphs:
        raise RCXError("input contains no nets")
    return graphs


def _wire_resistance(edge: Edge, layer: LayerModel, corner: CornerModel) -> float:
    width = layer.effective_width(edge.width_um)
    length = edge.length_um
    base = 0.0
    if layer.resistivity_ohm_um is not None:
        if layer.thickness_um is None or layer.thickness_um <= 0.0:
            raise RCXError("layer %s has resistivity but no positive thickness" % layer.name)
        base += layer.resistivity_ohm_um * length / (width * layer.thickness_um)
    rpsq = _lookup_1d(
        layer.resistance_by_width,
        width,
        "%s.resistance_by_width" % layer.name,
    )
    if rpsq is None:
        rpsq = layer.resistance_ohm_per_square
    if rpsq is not None:
        base += rpsq * length / width
    if base <= 0.0:
        raise RCXError("layer %s has no resistance model" % layer.name)
    nominal = layer.temperature_nominal_c if layer.temperature_nominal_c is not None else corner.nominal_temperature_c
    c1 = layer.temperature_c1 if layer.temperature_c1 is not None else corner.temperature_c1
    c2 = layer.temperature_c2 if layer.temperature_c2 is not None else corner.temperature_c2
    return base * _temperature_factor(corner.temperature_c, nominal, c1 or 0.0, c2 or 0.0)


def _via_resistance(edge: Edge, corner: CornerModel) -> float:
    if edge.direct_resistance_ohm is not None:
        base = edge.direct_resistance_ohm
        model = corner.vias.get(edge.via_model_name or "")
    else:
        model = corner.vias.get(edge.via_model_name or "")
        if model is None:
            raise RCXError("via %s has no resistance model" % edge.source_id)
        base = model.resistance_ohm
        if base is None and model.resistance_by_area is not None:
            if edge.via_area_um2 is None:
                raise RCXError("via %s needs area_um2 for its resistance table" % edge.source_id)
            base = _lookup_1d(model.resistance_by_area, edge.via_area_um2, "%s resistance_by_area" % model.name)
        if base is None:
            raise RCXError("via %s has no resistance model" % edge.source_id)
    if model is None:
        return base
    nominal = model.temperature_nominal_c if model.temperature_nominal_c is not None else corner.nominal_temperature_c
    return base * _temperature_factor(corner.temperature_c, nominal, model.temperature_c1, model.temperature_c2)


def _wire_ground_capacitance(edge: Edge, layer: LayerModel) -> float:
    width = layer.effective_width(edge.width_um)
    length = edge.length_um
    result = 0.0
    if layer.ground_capacitance_pf_per_um2 is not None:
        result += layer.ground_capacitance_pf_per_um2 * width * length
    if layer.ground_capacitance_pf_per_um is not None:
        result += layer.ground_capacitance_pf_per_um * length
    if layer.edge_capacitance_pf_per_um is not None:
        result += layer.edge_capacitance_pf_per_um * layer.edge_factor * length
    return result


def _same_layer_overlap(left: Edge, right: Edge) -> Tuple[float, float]:
    if left.layer != right.layer or left.kind != "wire" or right.kind != "wire":
        return 0.0, 0.0
    if left.horizontal and right.horizontal:
        overlap = min(max(left.start.x, left.end.x), max(right.start.x, right.end.x)) - max(
            min(left.start.x, left.end.x), min(right.start.x, right.end.x)
        )
        center_spacing = abs(left.start.y - right.start.y)
        spacing = max(0.0, center_spacing - 0.5 * (left.width_um + right.width_um))
        return max(0.0, overlap), spacing
    if left.vertical and right.vertical:
        overlap = min(max(left.start.y, left.end.y), max(right.start.y, right.end.y)) - max(
            min(left.start.y, left.end.y), min(right.start.y, right.end.y)
        )
        center_spacing = abs(left.start.x - right.start.x)
        spacing = max(0.0, center_spacing - 0.5 * (left.width_um + right.width_um))
        return max(0.0, overlap), spacing
    return 0.0, 0.0


def _cross_layer_overlap_area(left: Edge, right: Edge, corner: CornerModel) -> float:
    if left.kind != "wire" or right.kind != "wire" or left.layer == right.layer:
        return 0.0
    left_order = corner.layers[left.layer].order
    right_order = corner.layers[right.layer].order
    if abs(left_order - right_order) > corner.max_cross_layer:
        return 0.0
    left_x0, left_x1 = sorted((left.start.x, left.end.x))
    left_y0, left_y1 = sorted((left.start.y, left.end.y))
    right_x0, right_x1 = sorted((right.start.x, right.end.x))
    right_y0, right_y1 = sorted((right.start.y, right.end.y))
    left_width = left.width_um / 2.0
    right_width = right.width_um / 2.0
    x_overlap = min(left_x1 + left_width, right_x1 + right_width) - max(left_x0 - left_width, right_x0 - right_width)
    y_overlap = min(left_y1 + left_width, right_y1 + right_width) - max(left_y0 - left_width, right_y0 - right_width)
    return max(0.0, x_overlap) * max(0.0, y_overlap)


def _nearest_nodes(left: Edge, right: Edge) -> Tuple[Node, Node]:
    candidates = [
        (abs(a.x - b.x) + abs(a.y - b.y), a, b)
        for a in (left.start, left.end)
        for b in (right.start, right.end)
    ]
    _, left_node, right_node = min(candidates, key=lambda item: item[0])
    return left_node, right_node


@dataclass
class ExtractedCorner:
    design: str
    corner: CornerModel
    graphs: List[NetGraph]
    resistance_ohm: Dict[str, float]
    ground_capacitance_pf: Dict[str, float]
    coupling_pf: Dict[Tuple[str, str], float]
    edge_by_id: Dict[str, Edge]
    warnings: List[str]

    @property
    def has_explicit_coupling(self) -> bool:
        return bool(self.coupling_pf)

    def summary(self) -> Dict[str, Any]:
        nets = {}
        for graph in self.graphs:
            net_edges = [edge for edge in graph.edges if edge.net == graph.name]
            net_ground = sum(self.ground_capacitance_pf.get(edge.edge_id, 0.0) for edge in net_edges)
            net_coupling = sum(
                value
                for (left_id, right_id), value in self.coupling_pf.items()
                if self.edge_by_id[left_id].net == graph.name or self.edge_by_id[right_id].net == graph.name
            )
            nets[graph.name] = {
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "ground_capacitance_pf": net_ground,
                "coupling_capacitance_pf": net_coupling,
                "resistance_ohm": sum(self.resistance_ohm[edge.edge_id] for edge in net_edges),
            }
        summary = {
            "schema_version": 1,
            "kind": "ics55_clean_room_rcx",
            "design": self.design,
            "corner": self.corner.name,
            "temperature_c": self.corner.temperature_c,
            "status": "explicit_coupling" if self.has_explicit_coupling else "seed_only",
            "coupling_enabled": self.has_explicit_coupling,
            "nets": nets,
            "warnings": list(self.warnings),
        }
        if self.corner.ics55_static_enabled:
            summary["ics55_static"] = self.corner.ics55_static_report
        return summary


def extract_corner(data: Mapping[str, Any], corner: CornerModel) -> ExtractedCorner:
    design = str(data.get("design", "design"))
    graphs = _build_graphs(data, corner)
    edge_by_id = {edge.edge_id: edge for graph in graphs for edge in graph.edges}
    resistance: Dict[str, float] = {}
    ground: Dict[str, float] = {}
    warnings: List[str] = []
    if corner.ics55_static_enabled:
        warnings.append(
            "ICS55 static alignment applied recovered THICKNESS/RPSQ scalar factors only; "
            "ITF/CAPTAB numeric values and proprietary table interpolation are not synthesized"
        )
    warned_layers = set()
    for graph in graphs:
        for edge in graph.edges:
            if edge.kind == "wire":
                layer = corner.layers[edge.layer]
                resistance[edge.edge_id] = _wire_resistance(edge, layer, corner)
                ground[edge.edge_id] = _wire_ground_capacitance(edge, layer)
                if layer.same_layer_coupling(0.0) is None and layer.coupling_cross_layer_pf_per_um2 is None and layer.name not in warned_layers:
                    warnings.append("no coupling model for layer %s; coupling is omitted" % layer.name)
                    warned_layers.add(layer.name)
            else:
                resistance[edge.edge_id] = _via_resistance(edge, corner)
                ground[edge.edge_id] = 0.0

    coupling: Dict[Tuple[str, str], float] = defaultdict(float)
    wire_edges = [edge for edge in edge_by_id.values() if edge.kind == "wire"]
    for left_index, left in enumerate(wire_edges):
        for right in wire_edges[left_index + 1 :]:
            same_layer_length, spacing = _same_layer_overlap(left, right)
            cap = 0.0
            if same_layer_length > EPS:
                cap_per_um = corner.layers[left.layer].same_layer_coupling(spacing)
                if cap_per_um is not None:
                    cap = cap_per_um * same_layer_length
            else:
                overlap_area = _cross_layer_overlap_area(left, right, corner)
                if overlap_area > EPS:
                    left_layer = corner.layers[left.layer]
                    right_layer = corner.layers[right.layer]
                    lower = left_layer if left_layer.order < right_layer.order else right_layer
                    if lower.coupling_cross_layer_pf_per_um2 is not None:
                        cap = lower.coupling_cross_layer_pf_per_um2 * overlap_area
            if cap <= 0.0:
                continue
            left_graph = next(graph for graph in graphs if graph.name == left.net)
            right_graph = next(graph for graph in graphs if graph.name == right.net)
            if left.net == right.net:
                ground[left.edge_id] += cap / 2.0
                ground[right.edge_id] += cap / 2.0
            elif left_graph.special or right_graph.special:
                non_special = right if left_graph.special else left
                ground[non_special.edge_id] += cap
            else:
                key = tuple(sorted((left.edge_id, right.edge_id)))
                coupling[key] += cap

    if not coupling:
        warnings.append("coupling capacitance is absent; this SPEF is not signoff RCX")
    return ExtractedCorner(design, corner, graphs, resistance, dict(ground), dict(coupling), edge_by_id, warnings)


class _NameMap:
    def __init__(self) -> None:
        self._values: Dict[str, int] = {}
        self._ordered: List[str] = []

    def ref(self, value: str) -> str:
        if value not in self._values:
            self._values[value] = len(self._ordered) + 1
            self._ordered.append(value)
        return "*%d" % self._values[value]

    @property
    def items(self) -> Iterable[Tuple[int, str]]:
        return enumerate(self._ordered, 1)


def _node_raw_name(node: Node) -> str:
    if node.ports:
        return sorted(port.name for port in node.ports)[0]
    return "%s:n%d" % (node.net, node.index)


def _write_number(value: float) -> str:
    if abs(value) < 0.0000000005:
        value = 0.0
    return "%.9f" % value


def write_spef(extracted: ExtractedCorner, path: Path) -> None:
    name_map = _NameMap()
    node_names: Dict[Tuple[str, int], str] = {}
    for graph in sorted(extracted.graphs, key=lambda item: item.name):
        name_map.ref(graph.name)
        for port in sorted(graph.ports, key=lambda item: item.name):
            name_map.ref(port.name)
        for node in sorted(graph.nodes, key=lambda item: item.index):
            raw = _node_raw_name(node)
            node_names[(graph.name, node.index)] = raw
            name_map.ref(raw)
    coupling_by_net: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
    for (left_id, right_id), value in sorted(extracted.coupling_pf.items()):
        left, right = extracted.edge_by_id[left_id], extracted.edge_by_id[right_id]
        left_node, right_node = _nearest_nodes(left, right)
        left_raw = node_names[(left.net, left_node.index)]
        right_raw = node_names[(right.net, right_node.index)]
        coupling_by_net[left.net].append((left_raw, right_raw, value))
        coupling_by_net[right.net].append((right_raw, left_raw, value))
        name_map.ref(left_raw)
        name_map.ref(right_raw)

    port_records = []
    for graph in sorted(extracted.graphs, key=lambda item: item.name):
        for port in sorted(graph.ports, key=lambda item: item.name):
            port_records.append(port)
    if len({port.name for port in port_records}) != len(port_records):
        raise RCXError("top-level port names must be globally unique for SPEF output")

    lines = [
        '*SPEF "IEEE 1481-1998"',
        '*DESIGN "%s"' % extracted.design,
        '*DATE "generated by ics55 clean-room rcx"',
        '*VENDOR "ICsprout55 clean-room RCX"',
        '*PROGRAM "ics55-rcx"',
        '*VERSION "1.0"',
        '*DESIGN_FLOW "PIN_CAP NONE"',
        "*DIVIDER /",
        "*DELIMITER :",
        "*BUS_DELIMITER []",
        "*T_UNIT 1.0 NS",
        "*C_UNIT 1.0 FF",
        "*R_UNIT 1.0 OHM",
        "*L_UNIT 1.0 HENRY",
        "",
        "*NAME_MAP",
    ]
    lines.extend("%s %s" % (name_map.ref(raw), raw) for _, raw in name_map.items)
    lines.extend(["", "*PORTS", ""])
    for port in port_records:
        lines.append("%s %s" % (name_map.ref(port.name), port.direction))

    for graph in sorted(extracted.graphs, key=lambda item: item.name):
        ground_by_node: Dict[str, float] = defaultdict(float)
        for edge in graph.edges:
            value = extracted.ground_capacitance_pf.get(edge.edge_id, 0.0)
            if value <= 0.0:
                continue
            start_raw = node_names[(graph.name, edge.start.index)]
            end_raw = node_names[(graph.name, edge.end.index)]
            if start_raw == end_raw:
                ground_by_node[start_raw] += value
            else:
                ground_by_node[start_raw] += value / 2.0
                ground_by_node[end_raw] += value / 2.0
        local_coupling = coupling_by_net.get(graph.name, [])
        total_pf = sum(ground_by_node.values()) + sum(value for _, _, value in local_coupling)
        lines.extend(["", "*D_NET %s %s" % (name_map.ref(graph.name), _write_number(total_pf * 1000.0)), "", "*CONN"])
        for port in sorted(graph.ports, key=lambda item: item.name):
            lines.append("*P %s %s" % (name_map.ref(port.name), port.direction))
        for node in sorted(graph.nodes, key=lambda item: item.index):
            if node.ports:
                continue
            lines.append("*N %s *C %s %s" % (name_map.ref(node_names[(graph.name, node.index)]), _write_number(node.x), _write_number(node.y)))
        lines.extend(["", "*CAP"])
        cap_index = 1
        for local_raw, peer_raw, value in sorted(local_coupling):
            lines.append("%d %s %s %s" % (cap_index, name_map.ref(local_raw), name_map.ref(peer_raw), _write_number(value * 1000.0)))
            cap_index += 1
        for node_raw, value in sorted(ground_by_node.items()):
            if value <= 0.0:
                continue
            lines.append("%d %s %s" % (cap_index, name_map.ref(node_raw), _write_number(value * 1000.0)))
            cap_index += 1
        lines.extend(["", "*RES"])
        resistance_index = 1
        for edge in graph.edges:
            start_raw = node_names[(graph.name, edge.start.index)]
            end_raw = node_names[(graph.name, edge.end.index)]
            lines.append("%d %s %s %s" % (resistance_index, name_map.ref(start_raw), name_map.ref(end_raw), _write_number(extracted.resistance_ohm[edge.edge_id])))
            resistance_index += 1
        lines.append("*END")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _safe_filename(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return result or "design"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="normalized routed-layout JSON")
    parser.add_argument("--lef", type=Path, help="released technology LEF used for seed models")
    parser.add_argument("--process-json", type=Path, help="corner/process overrides and optional coupling tables")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--corner", action="append", help="corner to emit; defaults to all corners")
    parser.add_argument("--summary", type=Path, help="write combined JSON summary")
    parser.add_argument("--require-coupling", action="store_true", help="fail when no explicit coupling is available")
    args = parser.parse_args(argv)
    try:
        data = _load_json(args.input.expanduser())
        corners = build_corners(
            args.lef.expanduser() if args.lef else None,
            args.process_json.expanduser() if args.process_json else None,
        )
        selected = args.corner or list(corners)
        unknown = [name for name in selected if name not in corners]
        if unknown:
            raise RCXError("unknown corner(s): %s" % ", ".join(unknown))
        summaries = []
        for corner_name in selected:
            extracted = extract_corner(data, corners[corner_name])
            if args.require_coupling and not extracted.has_explicit_coupling:
                raise RCXError("corner %s has no explicit coupling model" % corner_name)
            output = args.out_dir.expanduser() / (
                "%s_%s.spef" % (_safe_filename(extracted.design), _safe_filename(corner_name))
            )
            write_spef(extracted, output)
            summary = extracted.summary()
            summary["spef"] = str(output)
            summaries.append(summary)
        rendered = json.dumps({"schema_version": 1, "corners": summaries}, indent=2, sort_keys=True) + "\n"
        if args.summary:
            args.summary.expanduser().parent.mkdir(parents=True, exist_ok=True)
            args.summary.expanduser().write_text(rendered)
        else:
            print(rendered, end="")
        return 0
    except (OSError, RCXError, ValueError, KeyError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
