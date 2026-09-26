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

# ICsprout55 - multi-finger analog/RF MOS PCell (provisional template)
#
# Geometry derived from std-cell GDS analysis of the released digital PDK:
#   gate L = 0.06 um, gate (poly) pitch = 0.25 um, CT = 0.09 um,
#   CT-to-gate edge = 0.06 um, ACT-to-CT overhang = 0.015 um,
#   NP/PP implant margin ~0.2 um, poly gate overhang >= 0.14 um.
# These are DRAWN-TEMPLATE values, NOT foundry DRC rules (no DRC released).
# Always verify against the foundry DRC before tapeout.
#
# Layer numbers per libs.tech/klayout/tech/ics55.lyp:
#   ACT 2/1, NW 9/1, POLY 41/1, NP 52/1, PP 53/1, CT 72/1, M1 81/1
#
# Usage (KLayout GUI): Macro Development -> load this file -> run.
# Registers library "ICsprout55" with PCell "ics55_mos_analog".
# CLI example GDS generation: see ics55_pcell_demo.py
import klayout.db as db

L_ACT = db.LayerInfo(2, 1)    # active
L_NW = db.LayerInfo(9, 1)     # n-well
L_POLY = db.LayerInfo(41, 1)  # gate poly
L_NP = db.LayerInfo(52, 1)    # N+ implant
L_PP = db.LayerInfo(53, 1)    # P+ implant
L_CT = db.LayerInfo(72, 1)    # contact
L_M1 = db.LayerInfo(81, 1)    # metal 1

CT_SIZE = 0.09       # contact size (um)
GATE_L = 0.06        # drawn gate length (um)
PITCH = 0.25         # poly/gate pitch (um)
CT_GATE = 0.06       # contact edge to gate edge (um)
ACT_OV = 0.015       # active beyond contact (um)
IMPL_M = 0.2         # implant margin around active (um)
POLY_OV = 0.15       # poly gate overhang beyond active (um)
CT_M1_OV = 0.05      # M1 overhang around contact (um)


class Ics55MosAnalog(db.PCellDeclarationHelper):
    """Multi-finger analog/RF MOS with optional guard ring.

    Params:
      dev_type   : 'n' or 'p' channel
      w          : gate width per finger (um)
      l          : gate length (um, default 0.06)
      fingers    : number of gate fingers (m)
      guard_ring : 0 = none, 1 = guard ring with tie
      ring_metal : draw M1 ring strap over the ring (1/0)
    """

    def __init__(self):
        super().__init__()
        self.param("dev_type", self.TypeString, "Device type (n/p)", default="n")
        self.param("w", self.TypeDouble, "Gate width per finger W (um)", default=1.0)
        self.param("l", self.TypeDouble, "Gate length L (um)", default=GATE_L)
        self.param("fingers", self.TypeInt, "Number of fingers (m)", default=2)
        self.param("guard_ring", self.TypeInt, "Guard ring (0/1)", default=1)
        self.param("ring_metal", self.TypeInt, "M1 strap on guard ring (0/1)", default=1)
        self.param("gr_spacing", self.TypeDouble, "Guard ring to device spacing (um)", default=1.0)
        self.param("gr_width", self.TypeDouble, "Guard ring width (um)", default=0.5)

    def display_text_impl(self):
        return "ics55_mos_analog(%s W=%.3fu L=%.3fu m=%d ring=%d)" % (
            self.dev_type, self.w, self.l, self.fingers, self.guard_ring)

    def coerce_parameters_impl(self):
        if self.dev_type not in ("n", "p"):
            self.dev_type = "n"
        self.fingers = max(1, self.fingers)
        self.w = max(0.12, self.w)
        self.l = max(0.05, self.l)
        self.gr_spacing = max(0.2, self.gr_spacing)
        self.gr_width = max(0.2, self.gr_width)

    def produce_impl(self):
        dbu = self.layout.dbu
        u = lambda v: int(round(v / dbu))  # um -> dbu
        S = lambda li: self.cell.shapes(li)
        act = self.layout.layer(L_ACT)
        nw = self.layout.layer(L_NW)
        poly = self.layout.layer(L_POLY)
        np = self.layout.layer(L_NP)
        pp = self.layout.layer(L_PP)
        ct = self.layout.layer(L_CT)
        m1 = self.layout.layer(L_M1)

        dev_n = (self.dev_type == "n")
        W, L, m = self.w, self.l, self.fingers

        # active: one strip per finger, height = W
        sd = CT_GATE + CT_SIZE + ACT_OV          # source/drain half
        act_x = L + 2.0 * sd
        dev_x = act_x + (m - 1) * PITCH
        x0 = -dev_x / 2.0
        y0 = -W / 2.0
        gates = []
        for f in range(m):
            gx = x0 + f * PITCH
            gates.append(gx)
            S(act).insert(db.Box(u(gx - sd), u(y0), u(gx + sd), u(y0 + W)))
            S(poly).insert(db.Box(u(gx - L / 2.0), u(y0 - POLY_OV),
                               u(gx + L / 2.0), u(y0 + W + POLY_OV)))
            for side in (-1, 1):
                cx = gx + side * (L / 2.0 + CT_GATE)
                S(ct).insert(db.Box(u(cx - CT_SIZE / 2.0), u(y0 + W / 2.0 - CT_SIZE / 2.0),
                                 u(cx + CT_SIZE / 2.0), u(y0 + W / 2.0 + CT_SIZE / 2.0)))
        # gate contact extension on the middle finger
        gm = gates[m // 2]
        poly_gc = db.Box(u(gm - L / 2.0 - 0.12), u(y0 + W / 2.0 + POLY_OV),
                         u(gm + L / 2.0 + 0.06), u(y0 + W / 2.0 + POLY_OV + 0.12))
        S(poly).insert(poly_gc)
        S(ct).insert(db.Box(u(gm + L / 2.0 + 0.03), u(y0 + W / 2.0 + POLY_OV + 0.03),
                         u(gm + L / 2.0 + 0.03 + CT_SIZE),
                         u(y0 + W / 2.0 + POLY_OV + 0.03 + CT_SIZE)))

        # implant
        imp = db.Region(self.cell.begin_shapes_rec(act)).sized(u(IMPL_M))
        if dev_n:
            S(np).insert(imp)
        else:
            S(pp).insert(imp)

        # well for PMOS
        if not dev_n:
            S(nw).insert(db.Region(self.cell.begin_shapes_rec(act)).sized(u(IMPL_M + 0.3)))

        # M1 source/drain straps + gate strap
        S(m1).insert(db.Region(self.cell.begin_shapes_rec(act)).sized(u(CT_M1_OV)))
        S(m1).insert(db.Region(poly_gc).sized(u(CT_M1_OV)))

        # guard ring
        if self.guard_ring:
            half_x = dev_x / 2.0
            half_y = W / 2.0
            ring = db.Box(u(-half_x - self.gr_spacing - self.gr_width),
                          u(-half_y - self.gr_spacing - self.gr_width),
                          u(half_x + self.gr_spacing + self.gr_width),
                          u(half_y + self.gr_spacing + self.gr_width))
            inner = db.Box(u(-half_x - self.gr_spacing), u(-half_y - self.gr_spacing),
                           u(half_x + self.gr_spacing), u(half_y + self.gr_spacing))
            ring_act = db.Region(ring) - db.Region(inner)
            S(act).insert(ring_act)
            if dev_n:
                S(pp).insert(ring_act.sized(u(0.05)))   # p+ ring, tie VSS
            else:
                S(np).insert(ring_act.sized(u(0.05)))   # n+ ring, tie VDD
                S(nw).insert(db.Region(ring).sized(u(0.3)))
            if self.ring_metal:
                S(m1).insert(ring_act.sized(u(CT_M1_OV)))


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_mos_analog" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_mos_analog", Ics55MosAnalog())
