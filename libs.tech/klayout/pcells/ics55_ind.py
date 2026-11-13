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

# ICsprout55 - 1TM + ALPA spiral inductor PCell (provisional template)
#
# Single-ended square spiral on the 9 kA Cu top metal (TM2 103/1) with an
# RDL (123/1) underpass brought out through 3x3 um RV (120/1) transition pads
# enclosed by 1.5 um on TM2 and RDL, matching RV_W_1 / RV_EN_1_2 / RV_EN_3_4
# and the redundant-RV recommendation RV_R_1.
#
# Marker stack (drawn over the whole footprint):
#   INDALL   302/12  inductor keep-out: disables metal dummy, M1/M2/T4M2
#                    spacing and top-metal density checks in the area
#   INDDMY   301/12  base-layer 45-degree exemption for the PGS region
#   NOSHRINK 356/12  keep the RF geometry out of the 0.9 shrink
#   DMYBLK   359/12  block automatic dummy fill
#   PSUB     261/12  p-substrate declaration under the shield
#
# PGS: parallel AA stripes (PP implanted, ohmically tied to PSUB through the
# p+ active) inside a solid AA ring that ties the stripes together, with
# optional POLY stripes in the AA slots (pgs=2).  All PGS edges are orthogonal,
# so no 45-degree relaxation is required.
#
# Inductance in the display text is a modified-Wheeler estimate for a square
# spiral; it is not an EM result.  Template geometry; verify with the
# foundry DRC/EM flow before tapeout.
import math

import klayout.db as db

L_ACT = db.LayerInfo(2, 1)
L_POLY = db.LayerInfo(41, 1)
L_PP = db.LayerInfo(53, 1)
L_TM2 = db.LayerInfo(103, 1)
L_RV = db.LayerInfo(120, 1)
L_RDL = db.LayerInfo(123, 1)
L_PSUB = db.LayerInfo(261, 12)
L_INDDMY = db.LayerInfo(301, 12)
L_INDALL = db.LayerInfo(302, 12)
L_NOSHRINK = db.LayerInfo(356, 12)
L_DMYBLK = db.LayerInfo(359, 12)
# EM flow layers (gds2palace port sources + fixture ground; see
# libs.tech/pex/palace/run_model.py)
L_EM_P1 = db.LayerInfo(300, 1)
L_EM_P2 = db.LayerInfo(301, 1)
L_EM_GND = db.LayerInfo(81, 1)      # M1 fixture ground plane (EM deck only)

RV = 3.0            # RV_W_1 fixed size
RV_ENC = 1.5        # RV_EN_1_2 / RV_EN_3_4 enclosure
RV_SPACE = 3.0      # RV_S_1
PAD_L = 2 * RV + RV_SPACE + 2 * RV_ENC   # 12 um, carries two RVs
PAD_W = RV + 2 * RV_ENC                  # 6 um
PAD_GAP = 2.5       # spiral edge to transition pad
PGS_MARGIN = 4.0    # shield overhang beyond the spiral
PGS_RING = 3.0      # solid AA ring that ties the stripes together (ground)
MARK_MARGIN = 8.0   # marker overhang beyond the footprint


class Ics55Ind(db.PCellDeclarationHelper):
    """1TM (TM2) + ALPA (RDL) spiral inductor, two terminals.

    Params:
      turns     : number of turns (quarter-turn resolution)
      size      : outer footprint side of the spiral (um)
      width     : TM2 trace width (um)
      space     : TM2 turn-to-turn space (um)
      pgs       : patterned ground shield: 0 off, 1 AA, 2 AA + POLY
      pgs_width : AA stripe width (um)
      pgs_space : AA stripe space (um)
    """

    def __init__(self):
        super().__init__()
        self.param("turns", self.TypeDouble, "Turns", default=2.5)
        self.param("size", self.TypeDouble, "Outer spiral size (um)", default=150.0)
        self.param("width", self.TypeDouble, "TM2 trace width (um)", default=4.0)
        self.param("space", self.TypeDouble, "TM2 turn space (um)", default=2.0)
        self.param("pgs", self.TypeInt, "PGS: 0 off, 1 AA, 2 AA+POLY", default=2)
        self.param("pgs_width", self.TypeDouble, "PGS AA stripe width (um)", default=1.0)
        self.param("pgs_space", self.TypeDouble, "PGS AA stripe space (um)", default=1.0)
        self.param("em_ports", self.TypeInt, "Emit Palace port shapes 300/301 (0/1)", default=0)

    def _estimate_nh(self):
        d_out = self.size
        d_in = max(1.0, d_out - 2.0 * self.turns * (self.width + self.space))
        d_avg = 0.5 * (d_out + d_in)
        rho = (d_out - d_in) / (d_out + d_in)
        # modified Wheeler: L = K1 * mu0 * n^2 * d_avg / (1 + K2 * rho)
        return 2.34 * 4.0e-7 * math.pi * self.turns ** 2 * d_avg * 1e-6 \
            / (1.0 + 2.75 * rho) * 1e9

    def display_text_impl(self):
        return "ics55_ind(n=%.2f D=%.0fu w=%.1fu L~%.2fnH)" % (
            self.turns, self.size, self.width, self._estimate_nh())

    def coerce_parameters_impl(self):
        self.width = max(0.5, self.width)
        self.space = max(0.5, self.space)
        self.turns = max(2.0, min(8.0, self.turns))
        # keep an empty inner hole large enough for the 2-RV inner pad
        min_size = 2.0 * (self.turns * (self.width + self.space) + self.width + 25.0)
        self.size = max(self.size, min_size)
        self.pgs = max(0, min(2, self.pgs))
        self.pgs_width = max(0.3, self.pgs_width)
        self.pgs_space = max(0.3, self.pgs_space)

    def produce_impl(self):
        u = lambda v: int(round(v / self.layout.dbu))
        S = lambda li: self.cell.shapes(li)

        act = self.layout.layer(L_ACT)
        poly = self.layout.layer(L_POLY)
        pp = self.layout.layer(L_PP)
        tm2 = self.layout.layer(L_TM2)
        rv = self.layout.layer(L_RV)
        rdl = self.layout.layer(L_RDL)
        psub = self.layout.layer(L_PSUB)
        inddmy = self.layout.layer(L_INDDMY)
        indall = self.layout.layer(L_INDALL)
        noshrink = self.layout.layer(L_NOSHRINK)
        dmyblk = self.layout.layer(L_DMYBLK)

        w, s = self.width, self.space
        pitch = w + s
        half = self.size / 2.0
        n_legs = max(8, int(round(self.turns * 4)))
        h0 = half - w / 2.0
        d = [h0 - i * pitch / 4.0 for i in range(n_legs + 1)]

        pts = [(d[0], 0.0)]
        for i in range(n_legs):
            k = i % 4
            if k == 0:
                pts.append((d[i], d[i + 1]))
            elif k == 1:
                pts.append((-d[i + 1], d[i]))
            elif k == 2:
                pts.append((-d[i], -d[i + 1]))
            else:
                pts.append((d[i + 1], -d[i]))

        # 45-degree chamfers at every interior corner
        chamfer = w
        path_pts = [pts[0]]
        for i in range(1, len(pts) - 1):
            ax, ay = pts[i - 1]
            bx, by = pts[i]
            cx, cy = pts[i + 1]
            l1 = math.hypot(bx - ax, by - ay)
            l2 = math.hypot(cx - bx, cy - by)
            c = min(chamfer, l1 / 2.5, l2 / 2.5)
            path_pts.append((bx - (bx - ax) / l1 * c, by - (by - ay) / l1 * c))
            path_pts.append((bx + (cx - bx) / l2 * c, by + (cy - by) / l2 * c))
        path_pts.append(pts[-1])

        S(tm2).insert(db.Path([db.Point(u(x), u(y)) for x, y in path_pts], u(w)).polygon())

        # ---- terminal A: outer end, straight TM2 lead (no underpass) -------
        # The RV pad group is required by the LVS inductor extractor: both
        # terminals must expose an RV terminal cluster.
        rv_off = RV_SPACE / 2.0 + RV / 2.0
        pad_a = (half + PAD_GAP + PAD_L / 2.0, 0.0)
        S(tm2).insert(db.Box(u(h0), u(-w / 2.0), u(half + PAD_GAP), u(w / 2.0)))
        S(tm2).insert(db.Box(u(pad_a[0] - PAD_L / 2.0), u(-PAD_W / 2.0),
                             u(pad_a[0] + PAD_L / 2.0), u(PAD_W / 2.0)))
        S(rdl).insert(db.Box(u(pad_a[0] - PAD_L / 2.0), u(-PAD_W / 2.0),
                             u(pad_a[0] + PAD_L / 2.0), u(PAD_W / 2.0)))
        for dx in (-rv_off, rv_off):
            S(rv).insert(db.Box(u(pad_a[0] + dx - RV / 2.0), u(-RV / 2.0),
                                u(pad_a[0] + dx + RV / 2.0), u(RV / 2.0)))

        # ---- terminal B: inner end, RDL underpass --------------------------
        ex, ey = pts[-1]
        k = (n_legs - 1) % 4
        # keep the pad's outward end flush with the trace edge so the pad
        # never reaches the previous turn (pitch - w/2 - w/2 = 2 um gap)
        t = PAD_L / 2.0 - w / 2.0
        if k == 0:      # last leg up, tap pad long in y, exit +x
            tap = (ex, ey - t)
            tap_box = (PAD_W, PAD_L)
            rv_dirs = [(0.0, -RV_SPACE / 2.0 - RV / 2.0), (0.0, RV_SPACE / 2.0 + RV / 2.0)]
            exit_dir = (1.0, 0.0)
        elif k == 1:    # last leg left, tap pad long in x, exit +y
            tap = (ex + t, ey)
            tap_box = (PAD_L, PAD_W)
            rv_dirs = [(-RV_SPACE / 2.0 - RV / 2.0, 0.0), (RV_SPACE / 2.0 + RV / 2.0, 0.0)]
            exit_dir = (0.0, 1.0)
        elif k == 2:    # last leg down, tap pad long in y, exit -x
            tap = (ex, ey + t)
            tap_box = (PAD_W, PAD_L)
            rv_dirs = [(0.0, -RV_SPACE / 2.0 - RV / 2.0), (0.0, RV_SPACE / 2.0 + RV / 2.0)]
            exit_dir = (-1.0, 0.0)
        else:           # last leg right, tap pad long in x, exit -y
            tap = (ex - t, ey)
            tap_box = (PAD_L, PAD_W)
            rv_dirs = [(-RV_SPACE / 2.0 - RV / 2.0, 0.0), (RV_SPACE / 2.0 + RV / 2.0, 0.0)]
            exit_dir = (0.0, -1.0)

        tw, th = tap_box
        S(tm2).insert(db.Box(u(tap[0] - tw / 2.0), u(tap[1] - th / 2.0),
                             u(tap[0] + tw / 2.0), u(tap[1] + th / 2.0)))
        S(rdl).insert(db.Box(u(tap[0] - tw / 2.0), u(tap[1] - th / 2.0),
                             u(tap[0] + tw / 2.0), u(tap[1] + th / 2.0)))
        for dx, dy in rv_dirs:
            S(rv).insert(db.Box(u(tap[0] + dx - RV / 2.0), u(tap[1] + dy - RV / 2.0),
                                u(tap[0] + dx + RV / 2.0), u(tap[1] + dy + RV / 2.0)))

        pad_b = (half + PAD_GAP + PAD_L / 2.0, tap[1]) if exit_dir[0] != 0 else \
                (tap[0], half + PAD_GAP + PAD_L / 2.0)
        if exit_dir[0] < 0:
            pad_b = (-pad_b[0], pad_b[1])
        if exit_dir[1] < 0:
            pad_b = (pad_b[0], -pad_b[1])
        pbw, pbh = (PAD_L, PAD_W) if exit_dir[0] != 0 else (PAD_W, PAD_L)
        S(tm2).insert(db.Box(u(pad_b[0] - pbw / 2.0), u(pad_b[1] - pbh / 2.0),
                             u(pad_b[0] + pbw / 2.0), u(pad_b[1] + pbh / 2.0)))
        S(rdl).insert(db.Box(u(pad_b[0] - pbw / 2.0), u(pad_b[1] - pbh / 2.0),
                             u(pad_b[0] + pbw / 2.0), u(pad_b[1] + pbh / 2.0)))
        rv_b = ([(pad_b[0] + dx, pad_b[1]) for dx in (-rv_off, rv_off)]
                if exit_dir[0] != 0 else
                [(pad_b[0], pad_b[1] + dy) for dy in (-rv_off, rv_off)])
        for cx, cy in rv_b:
            S(rv).insert(db.Box(u(cx - RV / 2.0), u(cy - RV / 2.0),
                                u(cx + RV / 2.0), u(cy + RV / 2.0)))

        # RDL underpass: tap pad to terminal-B pad
        if exit_dir[0] != 0:
            x0 = min(tap[0], pad_b[0])
            x1 = max(tap[0], pad_b[0])
            S(rdl).insert(db.Box(u(x0), u(tap[1] - PAD_W / 2.0), u(x1), u(tap[1] + PAD_W / 2.0)))
        else:
            y0 = min(tap[1], pad_b[1])
            y1 = max(tap[1], pad_b[1])
            S(rdl).insert(db.Box(u(tap[0] - PAD_W / 2.0), u(y0), u(tap[0] + PAD_W / 2.0), u(y1)))

        # ---- patterned ground shield --------------------------------------
        if self.pgs > 0:
            sh = half + PGS_MARGIN
            grid = self.pgs_width + self.pgs_space
            n = max(1, int(math.floor((2.0 * sh - self.pgs_width) / grid)) + 1)
            total = (n - 1) * grid + self.pgs_width
            start = -total / 2.0 + self.pgs_width / 2.0
            for i in range(n):
                x = start + i * grid
                S(act).insert(db.Box(u(x - self.pgs_width / 2.0), u(-sh),
                                     u(x + self.pgs_width / 2.0), u(sh)))
            # solid ring: the stripes are otherwise floating islands and
            # cannot carry a return current (required for both EM and the
            # real shield, which is tied to the substrate ground).
            rw = PGS_RING
            S(act).insert(db.Box(u(-sh - rw), u(sh), u(sh + rw), u(sh + rw)))
            S(act).insert(db.Box(u(-sh - rw), u(-sh - rw), u(sh + rw), u(-sh)))
            S(act).insert(db.Box(u(-sh - rw), u(-sh), u(-sh), u(sh)))
            S(act).insert(db.Box(u(sh), u(-sh), u(sh + rw), u(sh)))
            # one implant rectangle: PP encloses every AA stripe by 0.2 um
            S(pp).insert(db.Box(u(-sh - rw - 0.2), u(-sh - rw - 0.2),
                                u(sh + rw + 0.2), u(sh + rw + 0.2)))
            if self.pgs == 2:
                pw = self.pgs_space - 0.2
                if pw > 0.2:
                    for i in range(n - 1):
                        x = start + i * grid + grid / 2.0
                        S(poly).insert(db.Box(u(x - pw / 2.0), u(-sh), u(x + pw / 2.0), u(sh)))
            S(psub).insert(db.Box(u(-sh - rw - 1.0), u(-sh - rw - 1.0),
                                  u(sh + rw + 1.0), u(sh + rw + 1.0)))

        # ---- inductor markers ---------------------------------------------
        ext = half + PAD_GAP + PAD_L + MARK_MARGIN
        for layer in (indall, inddmy, noshrink, dmyblk):
            S(layer).insert(db.Box(u(-ext), u(-ext), u(ext), u(ext)))

        # ---- Palace EM deck: via ports and fixture ground ---------------------
        # gds2palace/IHP via-port recipe: the source shape is a thin line under
        # the signal pad and the port becomes a vertical 50 ohm sheet from
        # M1.zmax up to TM2.zmin (direction z).  A solid AA pad keeps the PGS
        # under each signal pad; the shared return is the M1 plane below.
        if self.em_ports:
            p1 = self.layout.layer(L_EM_P1)
            p2 = self.layout.layer(L_EM_P2)
            sg = self.layout.layer(L_EM_GND)
            em_pad = 8.0
            for (px, py) in (pad_a, pad_b):
                S(act).insert(db.Box(u(px - em_pad / 2.0), u(py - em_pad / 2.0),
                                     u(px + em_pad / 2.0), u(py + em_pad / 2.0)))
                S(pp).insert(db.Box(u(px - em_pad / 2.0 - 0.2), u(py - em_pad / 2.0 - 0.2),
                                    u(px + em_pad / 2.0 + 0.2), u(py + em_pad / 2.0 + 0.2)))
            # fixture ground plane (M1, EM deck only): solid plane under the
            # whole footprint, as in the IHP gds2palace reference flow.  Using
            # only a frame around the PGS ring forces the two-port return
            # current around the outside of the spiral and adds ~1.2 nH and
            # ~285 ohm; the solid plane puts the return path directly below
            # the winding.  M1 sits 0.05 um above the PGS, so the two
            # conductors never touch (gds2palace rejects touching conductors).
            sh = half + PGS_MARGIN
            outer = sh + 31.0
            S(sg).insert(db.Box(u(-outer), u(-outer), u(outer), u(outer)))
            # port 1: line along x at the centre of pad A
            S(p1).insert(db.Box(u(pad_a[0] - 5.0), u(-0.005),
                                u(pad_a[0] + 5.0), u(0.005)))
            # port 2: line along the pad-B exit axis
            if exit_dir[0] != 0:
                S(p2).insert(db.Box(u(pad_b[0] - 5.0), u(pad_b[1] - 0.005),
                                    u(pad_b[0] + 5.0), u(pad_b[1] + 0.005)))
            else:
                S(p2).insert(db.Box(u(pad_b[0] - 0.005), u(pad_b[1] - 5.0),
                                    u(pad_b[0] + 0.005), u(pad_b[1] + 5.0)))


# register library (idempotent: all ICsprout55 PCell modules share one library)
lib = db.Library.library_by_name("ICsprout55")
if lib is None:
    lib = db.Library()
    lib.name = "ICsprout55"
    lib.description = "ICsprout55 provisional analog PCells"
    lib.register("ICsprout55")
if "ics55_ind" not in lib.layout().pcell_names():
    lib.layout().register_pcell("ics55_ind", Ics55Ind())
