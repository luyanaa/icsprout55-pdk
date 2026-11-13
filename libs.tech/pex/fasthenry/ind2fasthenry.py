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

# ICsprout55 - 1TM (TM2) + ALPA (RDL) spiral inductor -> FastHenry deck.
#
# The routed.json contract used by ext2fasthenry.py is Manhattan-only, so an
# inductor cannot be expressed there (45-degree chamfers, shared winding
# nodes).  This generator emits the winding directly from the same geometry
# as the KLayout PCell (libs.tech/klayout/pcells/ics55_ind.py): one bar per
# centreline segment, nodes shared between neighbours, the RDL underpass and
# the TM2->RDL transition vias as vertical bars.  Keep the geometry block in
# sync with the PCell.
#
# FastHenry units: .units uM, so coordinates are um and sigma is 1/(um*ohm)
# (= S/m / 1e6), matching ext2fasthenry.py.
import argparse
import math
from pathlib import Path

# Stack (libs.tech/pex/palace/ics55_stackup.xml, source=starrc typ)
TM2_Z = 202.22          # (201.77 + 202.67) / 2
TM2_H = 0.90
TM2_SIGMA = 4.649e7
RDL_Z = 205.045         # (204.32 + 205.77) / 2
RDL_H = 1.45
RDL_SIGMA = 4.567e7
RV_R = 0.08             # ITF VIA RV RPV; two RVs in parallel per pad
RV_CUT = 3.0
# NOTE: z=0 is the BOTTOM of the 200 um substrate; the silicon surface and
# therefore the PGS sit at z=200 (PMD spans 200.0..200.15 in the stackup).
PGS_Z = 200.10          # PGS top surface, 0.1 um thick (200.0..200.1)
PGS_H = 0.10
PGS_SIGMA = 1.0e6       # silicide sheet x 50% duty (S/m of the solid sheet)

PAD_L = 12.0            # 2 x RV + 3.0 space + 2 x 1.5 enclosure
PAD_W = 6.0
PAD_GAP = 2.5
RV_SPACE = 3.0


def spiral(turns, size, width, space):
    """Return (path_points, outer_start, inner_end, last_leg_index).

    Mirrors ics55_ind.py: a square spiral of half-pitch steps with 45-degree
    chamfers at every interior corner.
    """
    pitch = width + space
    half = size / 2.0
    n_legs = max(8, int(round(turns * 4)))
    h0 = half - width / 2.0
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

    chamfer = width
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        l1 = math.hypot(bx - ax, by - ay)
        l2 = math.hypot(cx - bx, cy - by)
        c = min(chamfer, l1 / 2.5, l2 / 2.5)
        out.append((bx - (bx - ax) / l1 * c, by - (by - ay) / l1 * c))
        out.append((bx + (cx - bx) / l2 * c, by + (cy - by) / l2 * c))
    out.append(pts[-1])
    return out, pts, (n_legs - 1) % 4


def build_deck(a):
    path_pts, pts, k = spiral(a.turns, a.size, a.width, a.space)
    half = a.size / 2.0
    w = a.width

    nodes = {}
    segs = []

    def node(key, x, y, z):
        if key not in nodes:
            nodes[key] = ("n%d" % (len(nodes) + 1), x, y, z)
        return nodes[key][0]

    def bar(key1, key2, wd, ht, sigma):
        n1 = node(key1, *key1[1:])
        n2 = node(key2, *key2[1:])
        segs.append((n1, n2, wd, ht, sigma))
        return n2

    # --- TM2 winding --------------------------------------------------------
    for i in range(len(path_pts) - 1):
        x1, y1 = path_pts[i]
        x2, y2 = path_pts[i + 1]
        bar(("s", x1, y1, TM2_Z), ("s", x2, y2, TM2_Z), w, TM2_H, TM2_SIGMA)

    # --- terminal A: TM2 lead + pad, port at the pad's outer edge -----------
    a0 = (half - w / 2.0, 0.0)
    a1 = (half + PAD_GAP, 0.0)
    a2 = (a1[0] + PAD_L, 0.0)
    bar(("s", a0[0], a0[1], TM2_Z), ("a1", a1[0], a1[1], TM2_Z), w, TM2_H, TM2_SIGMA)
    port_a_node = bar(("a1", a1[0], a1[1], TM2_Z), ("portA", a2[0], a2[1], TM2_Z),
                      PAD_W, TM2_H, TM2_SIGMA)

    # --- inner tap: TM2 pad, two RVs in parallel, RDL underpass -------------
    ex, ey = pts[-1]
    t = PAD_L / 2.0 - w / 2.0
    if k == 0:
        tap = (ex, ey - t)
        leg = (0.0, 1.0)       # pad long axis
        exit_dir = (1.0, 0.0)
    elif k == 1:
        tap = (ex + t, ey)
        leg = (1.0, 0.0)
        exit_dir = (0.0, 1.0)
    elif k == 2:
        tap = (ex, ey + t)
        leg = (0.0, 1.0)
        exit_dir = (-1.0, 0.0)
    else:
        tap = (ex - t, ey)
        leg = (1.0, 0.0)
        exit_dir = (0.0, -1.0)
    pad_half = PAD_L / 2.0
    tap_far = (tap[0] + leg[0] * pad_half, tap[1] + leg[1] * pad_half)
    bar(("s", ex, ey, TM2_Z), ("tap", tap[0], tap[1], TM2_Z), PAD_W, TM2_H, TM2_SIGMA)
    bar(("tap", tap[0], tap[1], TM2_Z), ("tapf", tap_far[0], tap_far[1], TM2_Z),
        PAD_W, TM2_H, TM2_SIGMA)

    rv_sigma = (RDL_Z - TM2_Z) * 1e-6 / ((RV_R / 2.0) * (RV_CUT * 1e-6) ** 2)
    bar(("tap", tap[0], tap[1], TM2_Z), ("tapl", tap[0], tap[1], RDL_Z),
        RV_CUT, RV_CUT, rv_sigma)

    # --- terminal B: RDL underpass + pad + RVs ------------------------------
    pad_b = (half + PAD_GAP + PAD_L / 2.0, tap[1]) if exit_dir[0] != 0 else \
        (tap[0], half + PAD_GAP + PAD_L / 2.0)
    if exit_dir[0] < 0:
        pad_b = (-pad_b[0], pad_b[1])
    if exit_dir[1] < 0:
        pad_b = (pad_b[0], -pad_b[1])
    bar(("tapl", tap[0], tap[1], RDL_Z), ("bl", pad_b[0], pad_b[1], RDL_Z),
        PAD_W, RDL_H, RDL_SIGMA)
    bar(("bl", pad_b[0], pad_b[1], RDL_Z), ("bt", pad_b[0], pad_b[1], TM2_Z),
        RV_CUT, RV_CUT, rv_sigma)
    port_b = (pad_b[0] + exit_dir[0] * PAD_L / 2.0,
              pad_b[1] + exit_dir[1] * PAD_L / 2.0)
    port_b_node = bar(("bt", pad_b[0], pad_b[1], TM2_Z),
                      ("portB", port_b[0], port_b[1], TM2_Z),
                      PAD_W, TM2_H, TM2_SIGMA)

    # --- ground plane -------------------------------------------------------
    # NOTE: do NOT add "file=NONE" - FastHenry then silently skips the plane
    # (verified: filament count drops back to the winding-only value).
    half_pl = half + a.plane_margin
    if a.pgs:
        plane = dict(z=PGS_Z, thick=PGS_H, sigma=a.pgs_sigma / 1e6)
    else:
        plane = dict(z=0.0, thick=200.0, sigma=10.0 / 1e6)

    L = ["* ICsprout55 1TM(TM2)+ALPA(RDL) inductor (ind2fasthenry.py)",
         ".units uM", "",
         "* equivalent ground: PGS solid sheet" if a.pgs else "* lossy substrate",
         "g1 x1=%.4f y1=%.4f z1=%.4f" % (-half_pl, -half_pl, plane["z"]),
         "+  x2=%.4f y2=%.4f z2=%.4f" % (half_pl, -half_pl, plane["z"]),
         "+  x3=%.4f y3=%.4f z3=%.4f" % (half_pl, half_pl, plane["z"]),
         "+  thick=%.4f sigma=%.6g" % (plane["thick"], plane["sigma"]),
         "+  seg1=%d seg2=%d" % (a.pgs_seg, a.pgs_seg),
         ""]
    for key, (name, x, y, z) in nodes.items():
        L.append("%s x=%.4f y=%.4f z=%.4f" % (name, x, y, z))
    L.append("")
    for n1, n2, wd, ht, sigma in segs:
        L.append("e%s_%s %s %s w=%.4f h=%.4f sigma=%.6g nwinc=%d nhinc=%d"
                 % (n1, n2, n1, n2, wd, ht, sigma / 1e6, a.nwinc, a.nhinc))
    # One differential port between the two terminals: Z11 = R + jwL.
    L += ["", ".external %s %s" % (port_a_node, port_b_node), "",
          ".freq fmin=%.6g fmax=%.6g ndec=%d" % (a.fmin, a.fmax, a.ndec),
          ".end"]
    return L, nodes, segs


def main(argv=None):
    ap = argparse.ArgumentParser(description="1TM+ALPA inductor -> FastHenry")
    ap.add_argument("--turns", type=float, default=2.5)
    ap.add_argument("--size", type=float, default=150.0)
    ap.add_argument("--width", type=float, default=4.0)
    ap.add_argument("--space", type=float, default=2.0)
    ap.add_argument("--pgs", type=int, default=1, help="1: PGS solid sheet, 0: bare substrate")
    ap.add_argument("--pgs-sigma", type=float, default=PGS_SIGMA,
                    help="effective conductivity of the PGS solid sheet (S/m)")
    ap.add_argument("--pgs-seg", type=int, default=20,
                    help="ground-plane mesh divisions per side")
    ap.add_argument("--plane-margin", type=float, default=50.0,
                    help="ground-plane overhang beyond the spiral (um)")
    ap.add_argument("--fmin", type=float, default=1e6)
    ap.add_argument("--fmax", type=float, default=20e9)
    ap.add_argument("--ndec", type=int, default=10)
    ap.add_argument("--nwinc", type=int, default=4)
    ap.add_argument("--nhinc", type=int, default=2)
    ap.add_argument("--out", type=Path, default=Path("ind.inp"))
    a = ap.parse_args(argv)
    lines, nodes, segs = build_deck(a)
    a.out.write_text("\n".join(lines) + "\n")
    print("wrote %s: %d nodes, %d segments" % (a.out, len(nodes), len(segs)))


if __name__ == "__main__":
    main()
