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

# ICsprout55 - SAB poly resistor PCell (provisional template)
#
# P+ poly resistor with salicide block (re_ppo_sab family).
# The SAB (71/1) is the resistor-defining layer: LVS extracts
# RES_POLY AND PP AND SAB, so a PCell without SAB is not a re_ppo_sab_2t.
# Sheet resistance is the released SAB value rsh_rpposab = 725.7 ohm/sq.
# (The released Calibre deck mistakenly wires the SAB device to rsh_rppo
#  = 10.252; do not copy that erratum into the PCell or the LVS port.)
#
# Layers: POLY 41/1 (body), PPO 41/4 (poly resistor marker, provisional),
# PP 53/1 (P+ implant), SAB 71/1 (silicide block), CT 72/1 (contacts),
# M1 81/1 (straps).
# Template geometry; verify against foundry DRC before tapeout.
import klayout.db as db

L_POLY = db.LayerInfo(41, 1)
L_PPO = db.LayerInfo(41, 4)
L_PP = db.LayerInfo(53, 1)
L_SAB = db.LayerInfo(71, 1)
L_CT = db.LayerInfo(72, 1)
L_M1 = db.LayerInfo(81, 1)

CT = 0.09       # contact size
CT_ENC = 0.04   # M1 enclosure over contact (LEF)
PPO_ENC = 0.1   # PPO marker overhang around poly body


class Ics55ResPoly(db.PCellDeclarationHelper):
    """Straight SAB poly resistor with two contacts and M1 straps.

    Params:
      w  : poly width (um)
      l  : poly length between contact edges (um)
      rsq: sheet resistance (ohm/sq), default 725.7 (SAB nominal)

    The multi-segment / nser parameter is intentionally absent until the
    serpentine geometry, shared contacts and extraction length are verified.
    """

    def __init__(self):
        super().__init__()
        self.param("w", self.TypeDouble, "Poly width W (um)", default=2.0)
        self.param("l", self.TypeDouble, "Poly length L (um)", default=10.0)
        self.param("rsq", self.TypeDouble, "Sheet resistance (ohm/sq)", default=725.7)

    def display_text_impl(self):
        return "ics55_res_poly(W=%.2fu L=%.2fu Rsq=%.0f) R~%.1f ohm" % (
            self.w, self.l, self.rsq, self.rsq * self.l / self.w)

    def coerce_parameters_impl(self):
        self.w = max(0.1, self.w)
        self.l = max(0.2, self.l)

    def produce_impl(self):
        dbu = self.layout.dbu
        u = lambda v: int(round(v / dbu))
        S = lambda li: self.cell.shapes(li)
        poly = self.layout.layer(L_POLY); ppo = self.layout.layer(L_PPO)
        pp = self.layout.layer(L_PP); sab = self.layout.layer(L_SAB)
        ct = self.layout.layer(L_CT)
        m1 = self.layout.layer(L_M1)

        W, L = self.w, self.l
        # bar along x; contacts on both ends, resistor body between the CT edges
        body_x = L + 2 * (CT + 0.06)
        x0 = -body_x / 2.0
        y0 = -W / 2.0
        S(poly).insert(db.Box(u(x0), u(y0), u(x0 + body_x), u(y0 + W)))
        S(ppo).insert(db.Region(db.Box(u(x0 - PPO_ENC), u(y0 - PPO_ENC),
                                    u(x0 + body_x + PPO_ENC), u(y0 + W + PPO_ENC))))
        S(pp).insert(db.Region(db.Box(u(x0 - 0.1), u(y0 - 0.1),
                                   u(x0 + body_x + 0.1), u(y0 + W + 0.1))))
        # Silicide block covers exactly the resistor body between the contacts.
        S(sab).insert(db.Box(u(x0 + CT + 0.06), u(y0),
                             u(x0 + body_x - CT - 0.06), u(y0 + W)))
        # contacts
        for cx in (x0 + CT / 2.0 + 0.06, x0 + body_x - CT / 2.0 - 0.06):
            S(ct).insert(db.Box(u(cx - CT / 2.0), u(y0 + W / 2.0 - CT / 2.0),
                             u(cx + CT / 2.0), u(y0 + W / 2.0 + CT / 2.0)))
        # M1 straps
        for cx in (x0 + CT / 2.0 + 0.06, x0 + body_x - CT / 2.0 - 0.06):
            S(m1).insert(db.Box(u(cx - 0.15), u(y0 - 0.1), u(cx + 0.15), u(y0 + W + 0.1)))


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_res_poly" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_res_poly", Ics55ResPoly())
