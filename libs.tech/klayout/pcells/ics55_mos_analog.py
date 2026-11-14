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

# ICsprout55 - multi-finger analog/RF MOS PCell
#
# Geometry follows the Calibre rule deck of the same process family
# (SMIC_CalDRC_55LLULPGE_0912182533_V1.13_REV1_0, see the constants below for
# the line references) plus the released std-cell dimensions:
#   gate L = 0.06 um, poly pitch = 0.26 um (0.055 + CT 0.09 + 0.055),
#   CT = 0.09 um square, active enclosure of CT 0.03 um,
#   active beyond gate 0.17 um (rule 0.115), poly beyond active 0.15 um
#   (rule 0.14), implant margin 0.3 um (0.15 beyond the 0.15 poly overhang).
#
# The source/drain straps are interdigitated: one M1 island per contact, even
# contacts to a bus below the active, odd contacts to a bus above, and a
# separate gate island.  A single M1 rectangle over the active (the previous
# template) shorts source, drain and gate - the LVS extractor reports
# M$1 $1 $2 $1 / M$2 $1 $1 $1 for that layout.
#
# Validate with:
#   klayout -b -r ics55.lvs ...   (extracts one W=m*W device, S/G/D separate)
#   klayout -b -r ics55_drc.drc ...   (partial deck; see docs/ics55_pdk_repair.md)
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

# Rules below are taken from the SMIC 55LL ULP RF Calibre deck
# (SMIC_CalDRC_55LLULPGE_..._V1.13_REV1_0.drc), not guessed:
#   CT fixed size 0.09 square                      (CT_W_1)
#   CT space 0.11 (0.14 different nets)            (CT_S_1 / CT_S_2)
#   GATE to diffusion contact 0.055 (0.9/1.2 V)    (CT_S_4)
#   CT enclosure by AA 0.015, by poly 0.01/0.04    (4911/4936/4944)
#   M1 enclosure of CT 0.025                       (4961)
#   M1 width/space 0.09                            (5058/5063)
#   AA extension outside GT 0.115                  (3914)
#   poly extension outside AA 0.14                 (3920)
CT_SIZE = 0.09       # fixed contact size (um)
GATE_L = 0.06        # drawn gate length (um)
CT_GATE = 0.055      # contact edge to gate edge (um, CT_S_4)
ACT_OV = 0.03        # active beyond contact (um, rule 0.015)
IMPL_M = 0.3         # implant margin around active (um): 0.15 poly
                     # overhang + 0.15 NP_EN_3/PP_EN_3 enclosure
POLY_OV = 0.15       # poly gate overhang beyond active (um, rule 0.14)
M1_OV = 0.025        # M1 enclosure of contact (um, rule 0.025)
GATE_PAD = 0.17      # poly pad for the gate contact (0.09 + 2*0.04)


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
        self.param("lvt", self.TypeInt, "LVT implant for PMOS (0/1)", default=0)
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
        lvtp = self.layout.layer(db.LayerInfo(18, 1))  # LVTP

        dev_n = (self.dev_type == "n")
        W, L, m = self.w, self.l, self.fingers

        # One shared active strip; the gates cross it.  The contact pitch
        # follows the gate length: gate + 0.055 + CT 0.09 + 0.055.  (A fixed
        # pitch is only correct for L=0.06; for longer gates it puts the
        # contact inside the gate.)
        pitch = L + 2.0 * CT_GATE + CT_SIZE
        side = L / 2.0 + CT_GATE + CT_SIZE + ACT_OV
        dev_x = (m - 1) * pitch + 2.0 * side
        x0 = -dev_x / 2.0
        y0 = -W / 2.0
        gate0 = x0 + side                      # first gate centre
        S(act).insert(db.Box(u(x0), u(y0), u(x0 + dev_x), u(y0 + W)))

        # Gates, plus a poly bus that ties every finger to the same gate net.
        # The bus sits above the source/drain straps so it does not collide
        # with them.
        for f in range(m):
            gx = gate0 + f * pitch
            S(poly).insert(db.Box(u(gx - L / 2.0), u(y0 - POLY_OV),
                               u(gx + L / 2.0), u(y0 + W + 0.33)))
        bus_y0 = y0 + W + 0.25
        S(poly).insert(db.Box(u(gate0 - L / 2.0), u(bus_y0),
                           u(gate0 + (m - 1) * pitch + L / 2.0),
                           u(bus_y0 + 0.08)))

        # m+1 shared source/drain contacts, 0.25 apart.
        # first contact sits ACT_OV from the active edge; the 0.25 pitch then
        # keeps 0.05 to every gate edge and 0.03 active enclosure at both ends
        ct_x = [x0 + ACT_OV + CT_SIZE / 2.0 + f * pitch for f in range(m + 1)]
        for cx in ct_x:
            S(ct).insert(db.Box(u(cx - CT_SIZE / 2.0), u(y0 + W / 2.0 - CT_SIZE / 2.0),
                             u(cx + CT_SIZE / 2.0), u(y0 + W / 2.0 + CT_SIZE / 2.0)))

        # Gate contact on a poly pad over the bus (0.04 poly enclosure).
        gm = gate0 + (m // 2) * pitch
        pad_y = bus_y0 + 0.04
        S(poly).insert(db.Box(u(gm - GATE_PAD / 2.0), u(pad_y),
                           u(gm + GATE_PAD / 2.0), u(pad_y + GATE_PAD)))
        gy = pad_y + GATE_PAD / 2.0
        S(ct).insert(db.Box(u(gm - CT_SIZE / 2.0), u(gy - CT_SIZE / 2.0),
                         u(gm + CT_SIZE / 2.0), u(gy + CT_SIZE / 2.0)))

        # implant.  The poly gate bus and its contact pad are PO-with-CT and
        # must be covered by the implant too (PO_R_2): the plain active+sized
        # margin leaves the pad poly above the bus uncovered.  The box covers
        # the active + margin plus the bus/pad region (top bus_y0+0.36 so the
        # 0.21 pad gets the 0.15 implant enclosure).
        imp = db.Region(self.cell.begin_shapes_rec(act)).sized(u(IMPL_M))
        bus_cover = db.Box(u(x0 - IMPL_M), u(bus_y0 - 0.10),
                           u(x0 + dev_x + IMPL_M), u(bus_y0 + 0.36))
        imp = imp + db.Region(bus_cover)
        if dev_n:
            S(np).insert(imp)
        else:
            S(pp).insert(imp)

        # well for PMOS: the implant box now reaches bus_y0+0.36, so the well
        # must enclose it (act+sized(0.65) covers it for every finger count).
        if not dev_n:
            S(nw).insert(db.Region(self.cell.begin_shapes_rec(act)).sized(u(IMPL_M + 0.65)))
            if self.lvt:
                S(lvtp).insert(db.Region(self.cell.begin_shapes_rec(act)).sized(u(0.3)))

        # M1: one island per source/drain contact and two interdigitated
        # straps - even contacts to a bus below the active, odd contacts to a
        # bus above.  Without the straps the fingers are a series chain; the
        # old code poured one M1 rectangle over the whole active instead,
        # shorting every terminal.
        for k, cx in enumerate(ct_x):
            if k % 2 == 0:
                S(m1).insert(db.Box(u(cx - CT_SIZE / 2.0 - M1_OV), u(y0 - 0.16),
                                 u(cx + CT_SIZE / 2.0 + M1_OV), u(y0 + W - 0.07)))
            else:
                S(m1).insert(db.Box(u(cx - CT_SIZE / 2.0 - M1_OV), u(y0 + 0.10),
                                 u(cx + CT_SIZE / 2.0 + M1_OV), u(y0 + W + 0.16)))
        even = [cx for k, cx in enumerate(ct_x) if k % 2 == 0]
        odd = [cx for k, cx in enumerate(ct_x) if k % 2 == 1]
        if len(even) > 1:
            S(m1).insert(db.Box(u(even[0] - CT_SIZE / 2.0 - M1_OV), u(y0 - 0.16),
                             u(even[-1] + CT_SIZE / 2.0 + M1_OV), u(y0 - 0.02)))
        if len(odd) > 1:
            S(m1).insert(db.Box(u(odd[0] - CT_SIZE / 2.0 - M1_OV), u(y0 + W + 0.02),
                             u(odd[-1] + CT_SIZE / 2.0 + M1_OV), u(y0 + W + 0.16)))
        # gate island grows upward only: 0.14 x 0.32 keeps it clear of the
        # source/drain straps while meeting the tech-LEF M1 AREA 0.042 um^2
        S(m1).insert(db.Box(u(gm - CT_SIZE / 2.0 - M1_OV), u(gy - CT_SIZE / 2.0 - M1_OV),
                         u(gm + CT_SIZE / 2.0 + M1_OV), u(gy + 0.25)))

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
                S(m1).insert(ring_act.sized(u(M1_OV)))


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_mos_analog" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_mos_analog", Ics55MosAnalog())
