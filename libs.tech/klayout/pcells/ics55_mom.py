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

# ICsprout55 - MOM capacitor PCell (provisional template)
#
# Interdigitated metal-oxide-metal capacitor using M2..M5 (mom_2t / mom_3t).
# No foundry MOM density data is released. Reference estimates only:
#   thin-metal lateral coupling ~0.1-0.15 fF/um per facing edge pair
#   (LEF area caps to ground: M2-M4 1.107 fF/um2, M5 0.626 fF/um2).
# Template geometry; verify against foundry DRC before tapeout.
import klayout.db as db

M2 = db.LayerInfo(82, 1); M3 = db.LayerInfo(83, 1)
M4 = db.LayerInfo(84, 1); M5 = db.LayerInfo(85, 1)
V2 = db.LayerInfo(92, 1); V3 = db.LayerInfo(93, 1); V4 = db.LayerInfo(94, 1)

WIRE = 0.1     # finger width (min width M2-5)
SPACE = 0.1    # finger space (min space M2-5)
PITCH = 0.2    # finger pitch
VIA = 0.09     # via size


class Ics55Mom(db.PCellDeclarationHelper):
    """Interdigitated MOM cap, PLUS/MINUS combs on M2..M5 (optionally M5).

    Params:
      fingers : number of PLUS fingers per layer
      length  : finger length (um)
      layers  : 2 (M2-M3), 3 (M2-M4), 4 (M2-M5)
    """

    def __init__(self):
        super().__init__()
        self.param("fingers", self.TypeInt, "Fingers per polarity per layer", default=10)
        self.param("length", self.TypeDouble, "Finger length (um)", default=10.0)
        self.param("layers", self.TypeInt, "Layer pairs (2/3/4)", default=3)

    def display_text_impl(self):
        return "ics55_mom(f=%d L=%.1fu lv=%d)" % (self.fingers, self.length, self.layers)

    def coerce_parameters_impl(self):
        self.fingers = max(2, self.fingers)
        self.length = max(1.0, self.length)
        self.layers = max(2, min(4, self.layers))

    def produce_impl(self):
        dbu = self.layout.dbu
        u = lambda v: int(round(v / dbu))
        S = lambda li: self.cell.shapes(li)
        metals = [self.layout.layer(M2), self.layout.layer(M3),
                  self.layout.layer(M4), self.layout.layer(M5)]
        vias = [self.layout.layer(V2), self.layout.layer(V3), self.layout.layer(V4)]
        n = self.fingers
        tot = 2 * n * PITCH
        x0 = -tot / 2.0
        y0 = -self.length / 2.0
        for li in range(self.layers):
            m = metals[li]
            for f in range(n):
                for pol in (0, 1):
                    x = x0 + (2 * f + pol) * PITCH
                    S(m).insert(db.Box(u(x - WIRE / 2.0), u(y0), u(x + WIRE / 2.0), u(y0 + self.length)))
            # bus bars at both ends on each layer
            S(m).insert(db.Box(u(x0 - 0.2), u(y0 - 0.3), u(x0 + tot + 0.2), u(y0 - 0.1)))
            S(m).insert(db.Box(u(x0 - 0.2), u(y0 + self.length + 0.1), u(x0 + tot + 0.2), u(y0 + self.length + 0.3)))
            # vias between adjacent layers
            if li > 0:
                for f in range(n):
                    for pol in (0, 1):
                        x = x0 + (2 * f + pol) * PITCH
                        v = vias[li - 1]
                        S(v).insert(db.Box(u(x - VIA / 2.0), u(y0 - 0.2), u(x + VIA / 2.0), u(y0 - 0.2 + VIA)))
                        S(v).insert(db.Box(u(x - VIA / 2.0), u(y0 + self.length + 0.2 - VIA),
                                        u(x + VIA / 2.0), u(y0 + self.length + 0.2)))


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_mom" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_mom", Ics55Mom())
