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
# ============================================================================
# em_deck.py - build the gds2palace / openEMS fixture for ics55_ind
# ============================================================================
# The manufacturing PCell (libs.tech/klayout/pcells/ics55_ind.py) carries only
# the released process layers.  Everything that exists solely for the field
# solver lives here, in the EM fixture:
#
#   81/1    M1 reference plane (fixture ground, never in the product GDS)
#   300/1   port 1 source line (gds2palace via-port recipe)
#   301/1   port 2 source line
#   310/1   transformer port 3 source line (secondary winding)
#   311/1   transformer port 4 source line (secondary winding)
#   302/1   PGS_RTN fixture via: ties the PGS shield ring to the M1 plane, so
#           the shield has an explicit return instead of floating; the same
#           fixture via ties the coplanar ground strips of --feed cpw to M1
#   2/1     solid AA landing pad under each signal pad (PGS variants only)
#
# The fixture instantiates the production PCell, flattens it, and adds these
# shapes on top.  "open" decks clip TM2/RDL/RV to the two terminal pads and
# drop the winding/underpass, giving the open fixture used to de-embed the
# pad + port + shield parasitics (see extract_lq.py --open).
#
# Structures (spec "structure"):
#   inductor     one PCell, ports 1-2 on 300/1-301/1 (default)
#   transformer  two PCell instances stacked along y, ports 1-2 on the
#                primary and 3-4 on the secondary (310/1-311/1)
#
# Feed styles (spec "feed"):
#   via   vertical M1 -> TM2 port sheet alone (default)
#   cpw   grounded-coplanar launch: TM2 ground strips flank each port line
#         and are tied to the M1 plane with 302/1 fixture vias.  The port
#         excitation is still the vertical sheet, so this models a GSG launch
#         rather than a floating-CPW port.
#
# Run through make_em_deck.py, or directly:
#   klayout -b -r em_deck.py -rd spec=<spec.json>
# ============================================================================

import json
import os
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
PCELLS = os.path.abspath(os.path.join(HERE, "..", "..", "klayout", "pcells"))
if PCELLS not in sys.path:
    sys.path.insert(0, PCELLS)
import ics55_ind  # noqa: E402,F401  (registers the ICsprout55 PCell library)

PORT1 = db.LayerInfo(300, 1)
PORT2 = db.LayerInfo(301, 1)
PORT3 = db.LayerInfo(310, 1)
PORT4 = db.LayerInfo(311, 1)
WINDING_PORTS = ((PORT1, PORT2), (PORT3, PORT4))
GND = db.LayerInfo(81, 1)
PGS_RTN = db.LayerInfo(302, 1)
INDALL = db.LayerInfo(302, 12)
INDVIA = db.LayerInfo(303, 12)
ACT = db.LayerInfo(2, 1)
PP = db.LayerInfo(53, 1)
TM2 = db.LayerInfo(103, 1)
RDL = db.LayerInfo(123, 1)
RV = db.LayerInfo(120, 1)

CONDUCTORS = (TM2, RDL, RV)
PAD_AA_UM = 8.0
PAD_AA_PP_UM = 0.2
PORT_LINE_HALF_UM = 5.0
PORT_LINE_W_UM = 0.01
GND_MARGIN_UM = 12.5     # beyond the INDALL marker box
PGS_RING_W_UM = 3.0
PGS_RTN_UM = 0.36        # same square as T4V2/TV2
CPW_GAP_UM = 6.0         # signal-line edge to coplanar ground
CPW_GROUND_W_UM = 8.0
CPW_VIA_UM = 0.36
TRANSFORMER_GAP_UM = 20.0


def boxes(cell, layer):
    return [s.bbox() for s in cell.shapes(layer).each()]


def max_abs_um(layout, boxes_):
    dbu = layout.dbu
    return max(max(abs(b.p1.x), abs(b.p2.x), abs(b.p1.y), abs(b.p2.y))
               for b in boxes_) * dbu


def ub(layout, value_um):
    """Microns -> database units (integer Box edges)."""
    return int(round(value_um / layout.dbu))


def box_union(boxes_):
    xmin = min(b.p1.x for b in boxes_)
    ymin = min(b.p1.y for b in boxes_)
    xmax = max(b.p2.x for b in boxes_)
    ymax = max(b.p2.y for b in boxes_)
    return db.Box(xmin, ymin, xmax, ymax)


def translate(box, dy):
    return db.Box(box.p1.x, box.p1.y + dy, box.p2.x, box.p2.y + dy)


def add_landing_pad(top, layout, cx, cy):
    half = ub(layout, PAD_AA_UM / 2.0)
    top.shapes(layout.layer(ACT)).insert(
        db.Box(cx - half, cy - half, cx + half, cy + half))
    pp = ub(layout, PAD_AA_PP_UM)
    top.shapes(layout.layer(PP)).insert(
        db.Box(cx - half - pp, cy - half - pp,
               cx + half + pp, cy + half + pp))


def add_port_line(top, layout, layer, box):
    """10 um thin source line along the pad exit axis."""
    cx, cy = box.center().x, box.center().y
    if box.width() >= box.height():    # pad exits along x
        line = db.Box(cx - ub(layout, PORT_LINE_HALF_UM),
                      cy - ub(layout, PORT_LINE_W_UM / 2.0),
                      cx + ub(layout, PORT_LINE_HALF_UM),
                      cy + ub(layout, PORT_LINE_W_UM / 2.0))
    else:                              # pad exits along y
        line = db.Box(cx - ub(layout, PORT_LINE_W_UM / 2.0),
                      cy - ub(layout, PORT_LINE_HALF_UM),
                      cx + ub(layout, PORT_LINE_W_UM / 2.0),
                      cy + ub(layout, PORT_LINE_HALF_UM))
    top.shapes(layout.layer(layer)).insert(line)


def add_cpw_launch(top, layout, pad, cpw):
    """Grounded-coplanar ground strips beside one port line, tied to M1."""
    gap = ub(layout, cpw["gap"])
    width = ub(layout, cpw["ground_width"])
    via = ub(layout, CPW_VIA_UM)
    reach = ub(layout, PORT_LINE_HALF_UM)
    cx, cy = pad.center().x, pad.center().y
    along_x = pad.width() >= pad.height()
    for sign in (-1, 1):
        offset = sign * (gap + width // 2)
        if along_x:
            strip = db.Box(cx - reach, cy + offset - width // 2,
                           cx + reach, cy + offset + width // 2)
            via_centres = ((cx - reach, cy + offset), (cx + reach, cy + offset))
        else:
            strip = db.Box(cx + offset - width // 2, cy - reach,
                           cx + offset + width // 2, cy + reach)
            via_centres = ((cx + offset, cy - reach), (cx + offset, cy + reach))
        top.shapes(layout.layer(TM2)).insert(strip)
        for vx, vy in via_centres:
            top.shapes(layout.layer(PGS_RTN)).insert(
                db.Box(vx - via // 2, vy - via // 2,
                       vx + via // 2, vy + via // 2))


def add_pgs_returns(top, layout, ring_boxes):
    """Four fixture vias on the corners of one PGS shield ring."""
    ring = box_union(ring_boxes)
    inset = ub(layout, PGS_RING_W_UM / 2.0)
    half = ub(layout, PGS_RTN_UM / 2.0)
    for x in (ring.p1.x + inset, ring.p2.x - inset):
        for y in (ring.p1.y + inset, ring.p2.y - inset):
            top.shapes(layout.layer(PGS_RTN)).insert(
                db.Box(x - half, y - half, x + half, y + half))


def build(spec):
    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell(spec.get("cell", "ics55_ind_em"))

    structure = spec.get("structure", "inductor")
    feed = spec.get("feed", "via")
    if structure not in ("inductor", "transformer"):
        raise RuntimeError("unknown structure %r" % structure)
    if feed not in ("via", "cpw"):
        raise RuntimeError("unknown feed %r" % feed)
    if feed == "cpw" and not spec.get("pgs_return", True):
        raise RuntimeError("cpw feed needs the 302/1 PGS_RTN stackup layer")

    device = dict(spec.get("device", {}))
    device.setdefault("turns", 2.5)
    device.setdefault("size", 150.0)
    device.setdefault("width", 4.0)
    device.setdefault("space", 2.0)
    device.setdefault("pgs", 2)
    device.setdefault("pgs_width", 2.0)
    device.setdefault("pgs_space", 2.0)

    cell = layout.create_cell("ics55_ind", "ICsprout55", device)
    lib_pads = boxes(cell, layout.layer(INDVIA))
    if len(lib_pads) != 2:
        raise RuntimeError("expected 2 INDVIA terminal pads, found %d"
                           % len(lib_pads))
    # pad A sits on the x axis, pad B on the exit axis: sort by |y| first
    lib_pads.sort(key=lambda b: (abs(b.center().y), b.center().x))
    lib_rings = boxes(cell, layout.layer(ACT)) if device["pgs"] else []
    lib_markers = boxes(cell, layout.layer(INDALL))
    if not lib_markers:
        raise RuntimeError("device has no INDALL marker box")

    if structure == "transformer":
        gap = spec.get("transformer", {}).get("gap", TRANSFORMER_GAP_UM)
        offset = cell.bbox().height() + ub(layout, gap)
        offsets = [0, -offset]
    else:
        offsets = [0]
    for dy in offsets:
        top.insert(db.CellInstArray(cell.cell_index(), db.Trans(0, dy)))
    top.flatten(-1, True)              # single flat cell for the solver

    windings = [[translate(b, dy) for b in lib_pads] for dy in offsets]
    pads = [b for winding in windings for b in winding]
    if len(boxes(top, layout.layer(INDVIA))) != len(pads):
        raise RuntimeError("flattened INDVIA pad count does not match instances")

    device_variant = spec.get("device_variant", "dut")
    if device_variant == "open":
        # Keep only the terminal pads (TM2/RDL/RV) - the open reference.
        keep = db.Region()
        for b in pads:
            keep.insert(b)
        for layer in CONDUCTORS:
            region = db.Region(top.shapes(layout.layer(layer)))
            region &= keep
            top.shapes(layout.layer(layer)).clear()
            top.shapes(layout.layer(layer)).insert(region)

    # ---- fixture ground plane (M1, EM only) --------------------------------
    markers = [translate(b, dy) for dy in offsets for b in lib_markers]
    extent_um = max_abs_um(layout, markers)
    outer = ub(layout, extent_um + GND_MARGIN_UM)
    top.shapes(layout.layer(GND)).insert(db.Box(-outer, -outer, outer, outer))

    # ---- signal pads on the PGS + port source lines ------------------------
    cpw = {
        "gap": spec.get("cpw", {}).get("gap", CPW_GAP_UM),
        "ground_width": spec.get("cpw", {}).get("ground_width", CPW_GROUND_W_UM),
    }
    for index, winding in enumerate(windings):
        for pad_index, pad in enumerate(winding):
            if device["pgs"]:
                add_landing_pad(top, layout, pad.center().x, pad.center().y)
            add_port_line(top, layout, WINDING_PORTS[index][pad_index], pad)
            if feed == "cpw":
                add_cpw_launch(top, layout, pad, cpw)

    # ---- PGS return: four fixture vias per shield ring ---------------------
    if device["pgs"] and spec.get("pgs_return", True):
        for dy in offsets:
            add_pgs_returns(top, layout,
                            [translate(b, dy) for b in lib_rings])

    out = spec["out"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    layout.write(out)

    layers = (GND, PORT1, PORT2, PORT3, PORT4, PGS_RTN, ACT, TM2, RDL, RV)
    counts = {str(li): len(boxes(top, layout.layer(li))) for li in layers}
    return {"gds": out, "cell": top.name, "device_variant": device_variant,
            "structure": structure, "feed": feed,
            "ports": 2 * len(windings), "layers": counts}


def main():
    spec_path = globals().get("spec")
    if not spec_path:
        raise SystemExit("usage: klayout -b -r em_deck.py -rd spec=<spec.json>")
    with open(spec_path) as handle:
        spec = json.load(handle)
    info = build(spec)
    print("EM deck:", json.dumps(info, sort_keys=True))


if __name__ == "__main__":
    main()
