#!/usr/bin/env python3
"""Robust VTH0 fit: coarse 2D grid scan + coordinate refinement.

Leakage data per cell (state-averaged) from the liberty files; simulation
via Xyce with the PTM candidate (GIDL disabled by default).
"""
import json
import math
import sys

sys.path.insert(0, "/Users/yanlu/Documents/icsprout55-pdk/libs.tech/spice/models/fit")
import simulate as sm


def cell_rms(data, pm, n_name, p_name, vn, vp, no_gidl=True):
    cards = sm.make_model_cards(pm, n_name, p_name, vn, vp, no_gidl=no_gidl)
    res = sm.sim_leakage(data, cards)
    bycell = {}
    for (_, cell, si, meas, sim) in res:
        if sim is None:
            return None
        bycell.setdefault(cell, []).append((meas, sim))
    errs = []
    for cell in bycell:
        rows = bycell[cell]
        m = sum(r[0] for r in rows) / len(rows)
        s = sum(max(r[1], 1e-9) for r in rows) / len(rows)
        errs.append(math.log10(s / m))
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def grid_fit(data, pm, n_name, p_name, vn_range, vp_range, no_gidl=True):
    best = None
    grid = {}
    for vn in vn_range:
        for vp in vp_range:
            e = cell_rms(data, pm, n_name, p_name, vn, vp, no_gidl)
            if e is None:
                continue
            grid[(vn, vp)] = e
            if best is None or e < best[0]:
                best = (e, vn, vp)
                print("  grid vn=%.3f vp=%.3f rms=%.4f" % (vn, vp, e))
    return best, grid


def refine(data, pm, n_name, p_name, vn, vp, span=0.05, no_gidl=True, depth=6):
    for _ in range(depth):
        # coordinate descent with golden section on each axis
        for axis in (0, 1):
            lo = (vn - span, vp)[axis]
            hi = (vn + span, vp)[axis]
            # golden section search
            gr = (math.sqrt(5) - 1) / 2
            a, b = lo, hi
            x1 = b - gr * (b - a)
            x2 = a + gr * (b - a)
            f1 = cell_rms(data, pm, n_name, p_name, *( (x1, vp) if axis == 0 else (vn, x1) ), no_gidl=no_gidl)
            f2 = cell_rms(data, pm, n_name, p_name, *( (x2, vp) if axis == 0 else (vn, x2) ), no_gidl=no_gidl)
            for _ in range(12):
                if f1 < f2:
                    b, x2, f2 = x2, x1, f1
                    x1 = b - gr * (b - a)
                    f1 = cell_rms(data, pm, n_name, p_name, *( (x1, vp) if axis == 0 else (vn, x1) ), no_gidl=no_gidl)
                else:
                    a, x1, f1 = x1, x2, f2
                    x2 = a + gr * (b - a)
                    f2 = cell_rms(data, pm, n_name, p_name, *( (x2, vp) if axis == 0 else (vn, x2) ), no_gidl=no_gidl)
            v = (a + b) / 2
            if axis == 0:
                vn = v
            else:
                vp = v
        span *= 0.4
        e = cell_rms(data, pm, n_name, p_name, vn, vp, no_gidl)
        print("  refine vn=%.4f vp=%.4f rms=%.4f" % (vn, vp, e))
    return vn, vp, cell_rms(data, pm, n_name, p_name, vn, vp, no_gidl)


if __name__ == "__main__":
    data = json.load(open(sys.argv[1]))
    pm = sys.argv[2]
    n_name = sys.argv[3] if len(sys.argv) > 3 else "nm1p2_svt_lp"
    p_name = sys.argv[4] if len(sys.argv) > 4 else "pm1p2_svt_lp"
    vn_range = [round(0.35 + 0.05 * i, 2) for i in range(14)]   # 0.35..1.0
    vp_range = [round(0.35 + 0.05 * i, 2) for i in range(14)]
    best, grid = grid_fit(data, pm, n_name, p_name, vn_range, vp_range)
    e, vn, vp = best
    print("GRID BEST vn=%.3f vp=%.3f rms=%.4f" % (vn, vp, e))
    vn, vp, e = refine(data, pm, n_name, p_name, vn, vp)
    print("FITTED vth0n=%.4f vth0p=%.4f rms(log10)=%.4f" % (vn, vp, e))
