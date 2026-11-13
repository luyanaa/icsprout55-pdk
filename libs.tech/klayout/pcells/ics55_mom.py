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
# Interdigitated metal-oxide-metal capacitor using M1..M5.
#   2 terminals : one comb pair (mom_2t)
#   3 terminals : one comb pair + M1 shield plate (mom_3t)
#   4 terminals : two stacked comb pairs, lower M2/M3 and upper M4/M5
#                 (mom_4t: a/b and a1/b1)
#   5 terminals : two stacked comb pairs + M1 shield plate (mom_5t)
# No foundry MOM density data is released. Reference estimates only:
#   thin-metal lateral coupling ~0.1-0.15 fF/um per facing edge pair
#   (LEF area caps to ground: M2-M4 1.107 fF/um2, M5 0.626 fF/um2).
# Template geometry; verify against foundry DRC before tapeout.
import klayout.db as db

M1 = db.LayerInfo(81, 1)
M2 = db.LayerInfo(82, 1); M3 = db.LayerInfo(83, 1)
M4 = db.LayerInfo(84, 1); M5 = db.LayerInfo(85, 1)
V2 = db.LayerInfo(92, 1); V3 = db.LayerInfo(93, 1); V4 = db.LayerInfo(94, 1)

WIRE = 0.1     # finger width (min width M2-5)
SPACE = 0.1    # finger space (min space M2-5)
PITCH = 0.2    # finger pitch
VIA = 0.09     # via size


class Ics55Mom(db.PCellDeclarationHelper):
    """Interdigitated MOM cap with 2, 3, 4 or 5 terminals.

    Params:
      fingers   : number of PLUS fingers per polarity per comb pair
      length    : finger length (um)
      layers    : metal layers used, 2 (M2-M3), 3 (M2-M4), 4 (M2-M5)
      terminals : 2 (mom_2t), 3 (mom_3t), 4 (mom_4t), 5 (mom_5t).
                  Terminals 4/5 split the stack into two comb pairs:
                  lower half = A/B, upper half = A1/B1.
    """

    def __init__(self):
        super().__init__()
        self.param("fingers", self.TypeInt, "Fingers per polarity per layer", default=10)
        self.param("length", self.TypeDouble, "Finger length (um)", default=10.0)
        self.param("layers", self.TypeInt, "Layer pairs (2/3/4)", default=3)
        self.param("terminals", self.TypeInt, "Terminals (2/3/4/5)", default=2)

    def display_text_impl(self):
        return "ics55_mom(f=%d L=%.1fu lv=%d t=%d)" % (
            self.fingers, self.length, self.layers, self.terminals)

    def coerce_parameters_impl(self):
        self.fingers = max(2, self.fingers)
        self.length = max(1.0, self.length)
        self.layers = max(2, min(4, self.layers))
        self.terminals = max(2, min(5, self.terminals))

    def _draw_pair(self, S, group, group_vias, n, x0, y0, length):
        u = lambda v: int(round(v / self.layout.dbu))
        tot = 2 * n * PITCH
        for li, m in enumerate(group):
            for f in range(n):
                for pol in (0, 1):
                    x = x0 + (2 * f + pol) * PITCH
                    S(m).insert(db.Box(u(x - WIRE / 2.0), u(y0),
                                      u(x + WIRE / 2.0), u(y0 + length)))
            # bus bars at both ends, common to the layers of this comb pair
            S(m).insert(db.Box(u(x0 - 0.2), u(y0 - 0.3), u(x0 + tot + 0.2), u(y0 - 0.1)))
            S(m).insert(db.Box(u(x0 - 0.2), u(y0 + length + 0.1),
                               u(x0 + tot + 0.2), u(y0 + length + 0.3)))
            if li > 0:
                for f in range(n):
                    for pol in (0, 1):
                        x = x0 + (2 * f + pol) * PITCH
                        v = group_vias[li - 1]
                        S(v).insert(db.Box(u(x - VIA / 2.0), u(y0 - 0.2),
                                           u(x + VIA / 2.0), u(y0 - 0.2 + VIA)))
                        S(v).insert(db.Box(u(x - VIA / 2.0), u(y0 + length + 0.2 - VIA),
                                           u(x + VIA / 2.0), u(y0 + length + 0.2)))

    def produce_impl(self):
        u = lambda v: int(round(v / self.layout.dbu))
        S = lambda li: self.cell.shapes(li)
        metals = [self.layout.layer(M2), self.layout.layer(M3),
                  self.layout.layer(M4), self.layout.layer(M5)]
        vias = [self.layout.layer(V2), self.layout.layer(V3), self.layout.layer(V4)]
        n = self.fingers
        tot = 2 * n * PITCH
        x0 = -tot / 2.0
        y0 = -self.length / 2.0

        if self.terminals >= 4:
            half = (self.layers + 1) // 2
            groups = [(metals[:half], vias[:max(0, half - 1)]),
                      (metals[half:self.layers], vias[half:self.layers - 1])]
        else:
            groups = [(metals[:self.layers], vias[:self.layers - 1])]

        for group, group_vias in groups:
            self._draw_pair(S, group, group_vias, n, x0, y0, self.length)

        if self.terminals in (3, 5):
            # M1 shield plate under the whole footprint, terminal P
            S(self.layout.layer(M1)).insert(
                db.Box(u(x0 - 0.3), u(y0 - 0.4), u(x0 + tot + 0.3), u(y0 + self.length + 0.4)))


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_mom" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_mom", Ics55Mom())
