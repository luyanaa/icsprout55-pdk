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

# ICsprout55 - guard ring PCell (provisional template)
#
# Rectangular guard ring: p+ ring (PP, ACT, CT, M1 strap) for NMOS islands
# tied to VSS, or n+ ring in NWELL for PMOS islands tied to VDD.
# Layer numbers per libs.tech/klayout/tech/ics55.lyp.
# Template geometry; verify against foundry DRC before tapeout.
#
# CLI example generation: see ics55_pcell_demo.py
import klayout.db as db

L_ACT = db.LayerInfo(2, 1)
L_NW = db.LayerInfo(9, 1)
L_NP = db.LayerInfo(52, 1)
L_PP = db.LayerInfo(53, 1)
L_CT = db.LayerInfo(72, 1)
L_M1 = db.LayerInfo(81, 1)


class Ics55GuardRing(db.PCellDeclarationHelper):
    """Guard ring around a rectangular island.

    Params:
      ring_type : 'nring' (n+ ring for PMOS, in NWELL, tie VDD)
                  'pring' (p+ ring for NMOS, tie VSS)
      w         : ring width (um)
      spacing   : spacing between island edge and ring (um)
      metal     : draw M1 strap over the ring (0/1)
    """

    def __init__(self):
        super().__init__()
        self.param("ring_type", self.TypeString, "Ring type (nring/pring)", default="pring")
        self.param("w", self.TypeDouble, "Ring width (um)", default=0.5)
        self.param("spacing", self.TypeDouble, "Ring to island spacing (um)", default=1.0)
        self.param("metal", self.TypeInt, "M1 strap (0/1)", default=1)

    def display_text_impl(self):
        return "ics55_guard_ring(%s w=%.2fu sp=%.2fu)" % (self.ring_type, self.w, self.spacing)

    def coerce_parameters_impl(self):
        if self.ring_type not in ("nring", "pring"):
            self.ring_type = "pring"
        self.w = max(0.2, self.w)
        self.spacing = max(0.2, self.spacing)

    def produce_impl(self):
        dbu = self.layout.dbu
        u = lambda v: int(round(v / dbu))
        S = lambda li: self.cell.shapes(li)
        act = self.layout.layer(L_ACT); nw = self.layout.layer(L_NW)
        np = self.layout.layer(L_NP); pp = self.layout.layer(L_PP)
        ct = self.layout.layer(L_CT); m1 = self.layout.layer(L_M1)

        # ring around origin (island assumed placed inside; ring at spacing)
        half = self.spacing
        w = self.w
        outer = db.Box(u(-half - w), u(-half - w), u(half + w), u(half + w))
        inner = db.Box(u(-half), u(-half), u(half), u(half))
        ring = db.Region(outer) - db.Region(inner)
        S(act).insert(ring)
        if self.ring_type == "pring":
            S(pp).insert(ring.sized(u(0.05)))
        else:
            S(np).insert(ring.sized(u(0.05)))
            S(nw).insert(db.Region(outer).sized(u(0.3)))
        if self.metal:
            S(m1).insert(ring.sized(u(0.05)))
        # ring taps: contacts on the ring center line, corners excluded
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx = sx * (half + w / 2.0)
                cy = sy * (half + w / 2.0)
                c = db.Box(u(cx - 0.045), u(cy - 0.045), u(cx + 0.045), u(cy + 0.045))
                S(ct).insert(c)


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_guard_ring" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_guard_ring", Ics55GuardRing())
