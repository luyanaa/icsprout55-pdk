#!/usr/bin/env python3
"""Fit VTH0 (N and P) of a PTM BSIM4 candidate to ICS55 std-cell leakage.

Levenberg-Marquardt on log10(sim/meas) residuals over all (cell, state)
instances, using full-cell Xyce simulations.  VTH0 is clamped to a physical
LP range; the PMOS vth0 sign is handled by make_model_cards.
"""
import sys
import json
import math

sys.path.insert(0, "/Users/yanlu/Documents/icsprout55-pdk/libs.tech/spice/models/fit")
import simulate as sm
import fit as F


def res_vec(res):
    """log10(sim/meas) per CELL, averaged over its states (robust to
    per-state characterization quirks in the liberty data)."""
    bycell = {}
    for (_, cell, si, meas, sim) in res:
        bycell.setdefault(cell, []).append((meas, sim))
    out = []
    for cell in bycell:
        rows = bycell[cell]
        m = sum(r[0] for r in rows) / len(rows)
        s = sum(max(r[1], 1e-6) for r in rows) / len(rows)
        out.append(math.log10(s / m))
    return out


def lm_fit(data, pm, n_name, p_name, maxiter=20, lam=1.0, verbose=True):
    defaults = F.parse_defaults(pm)
    vn = min(1.4, max(0.2, defaults["nmos"]))
    vp = min(1.4, max(0.2, abs(defaults["pmos"])))

    def run(vn, vp):
        cards = sm.make_model_cards(pm, n_name, p_name, vn, vp)
        return sm.sim_leakage(data, cards)

    res = run(vn, vp)
    r = res_vec(res)
    err = math.sqrt(sum(x * x for x in r) / len(r))
    if verbose:
        print("start vth0n=%.4f vth0p=%.4f rms=%.4f" % (vn, vp, err))
    for it in range(maxiter):
        d = 2e-4
        rn = res_vec(run(vn + d, vp))
        rp = res_vec(run(vn, vp + d))
        J = [[(rn[i] - r[i]) / d, (rp[i] - r[i]) / d] for i in range(len(r))]
        n = len(r)
        jtj = [[sum(J[i][a] * J[i][b] for i in range(n)) for b in (0, 1)] for a in (0, 1)]
        jtr = [sum(J[i][a] * r[i] for i in range(n)) for a in (0, 1)]
        jtj[0][0] += lam
        jtj[1][1] += lam
        det = jtj[0][0] * jtj[1][1] - jtj[0][1] * jtj[1][0]
        dvn = -(jtj[1][1] * jtr[0] - jtj[0][1] * jtr[1]) / det
        dvp = -(jtj[0][0] * jtr[1] - jtj[1][0] * jtr[0]) / det
        vn2 = min(1.4, max(0.2, vn + dvn))
        vp2 = min(1.4, max(0.2, vp + dvp))
        res2 = run(vn2, vp2)
        err2 = math.sqrt(sum(x * x for x in res_vec(res2)) / n)
        if err2 <= err:
            vn, vp, res, r, err = vn2, vp2, res2, res_vec(res2), err2
            lam = max(lam * 0.5, 1e-4)
            if verbose:
                print("  it%d rms=%.4f vn=%.4f vp=%.4f" % (it, err, vn, vp))
            if err < 1e-4:
                break
        else:
            lam *= 10
            if verbose:
                print("  it%d reject lam=%.0e" % (it, lam))
    return vn, vp, err, res


if __name__ == "__main__":
    data = json.load(open(sys.argv[1]))
    pm = sys.argv[2]
    n_name = sys.argv[3] if len(sys.argv) > 3 else "nm1p2_svt_lp"
    p_name = sys.argv[4] if len(sys.argv) > 4 else "pm1p2_svt_lp"
    vn, vp, err, res = lm_fit(data, pm, n_name, p_name)
    print("FITTED vth0n=%.4f vth0p=%.4f rms(log10)=%.4f" % (vn, vp, err))
