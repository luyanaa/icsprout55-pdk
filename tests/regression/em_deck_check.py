#!/usr/bin/env python3
"""EM fixture / stackup / de-embedding checks for the RF passives flow.

Verifies that
  * the manufacturing PCell carries no EM-fixture layers,
  * em_deck.py emits the expected fixture geometry for every variant,
  * the t4 stackup matches the LVS t4 metal stack and contains no M5,
  * the PGS_RTN fixture via and the ideal-ground variant are emitted only
    when requested,
  * the open-fixture Y de-embedding recovers a known series L/R.

KLayout-dependent checks need `--klayout` or `--librelane`; without either the
script still runs the stackup and de-embedding checks (--require-klayout makes
a missing KLayout a failure).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nix_shell import command as nix_shell_command  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "libs.tech" / "pex"))
sys.path.insert(0, str(ROOT / "libs.tech" / "pex" / "palace"))

import config_gen  # noqa: E402

EM_DECK = ROOT / "libs.tech" / "pex" / "palace" / "em_deck.py"
DEMO = ROOT / "libs.tech" / "klayout" / "pcells" / "ics55_pcell_demo.py"
LVS_CONNECTIONS = ROOT / "libs.tech" / "lvs" / "rule_decks" / "devices_connections.lvs"

FIXTURE_LAYERS = "81/1,300/1,301/1,302/1"
CONDUCTOR_LAYERS = "103/1,123/1,120/1,2/1"
INSPECTED = FIXTURE_LAYERS + "," + CONDUCTOR_LAYERS

VARIANTS = {
    "no_pgs": {"pgs": 0, "pgs_return": False, "ideal": False},
    "pgs_float": {"pgs": 2, "pgs_return": False, "ideal": False},
    "pgs": {"pgs": 2, "pgs_return": True, "ideal": False},
    "ideal_gnd": {"pgs": 2, "pgs_return": True, "ideal": True},
}

FAILURES: list[str] = []
PASSES = 0


def check(condition, message):
    global PASSES
    if condition:
        PASSES += 1
        print("  PASS", message)
    else:
        FAILURES.append(message)
        print("  FAIL", message)


def find_klayout(args):
    if args.skip_klayout:
        return None
    if args.klayout:
        return ("bin", args.klayout) if shutil.which(args.klayout) else None
    if args.librelane and Path(args.librelane).exists() and shutil.which("nix-shell"):
        return ("nix", str(args.librelane))
    if shutil.which("klayout"):
        return ("bin", "klayout")
    return None


def invoke(kind, exe, script, extra):
    base = ["-b", "-r", str(script)] + extra
    command = nix_shell_command(exe, ["klayout"] + base) if kind == "nix" else [exe] + base
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError("%s failed:\n%s\n%s"
                           % (script.name, result.stdout, result.stderr))
    return result.stdout


def inspect(kind, exe, gds, cell, layers=INSPECTED):
    extra = ["-rd", "gds=" + str(gds), "-rd", "layers=" + layers]
    if cell:
        extra += ["-rd", "cell=" + cell]
    out = invoke(kind, exe, HERE / "inspect_gds.py", extra)
    line = [ln for ln in out.splitlines() if ln.startswith("INSPECT:")][-1]
    return json.loads(line.split(":", 1)[1])


def build_deck(kind, exe, spec, tag):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(spec, handle)
        spec_path = handle.name
    out = invoke(kind, exe, EM_DECK, ["-rd", "spec=" + spec_path])
    line = [ln for ln in out.splitlines() if ln.startswith("EM deck:")][-1]
    info = json.loads(line.split(":", 1)[1])
    print("  built %s: %s" % (tag, {k: v for k, v in info["layers"].items() if v}))
    return info


def stackup_checks(tmp):
    print("stackups")
    t4 = tmp / "stackup_t4.xml"
    t4_ret = tmp / "stackup_t4_ret.xml"
    t4_ideal = tmp / "stackup_t4_ideal.xml"
    m5 = tmp / "stackup_m1_m5.xml"
    config_gen.emit_palace_stackup(
        config_gen.build_stack("typ", metal_stack="t4"), t4)
    config_gen.emit_palace_stackup(
        config_gen.build_stack("typ", metal_stack="t4"), t4_ret,
        pgs_return=True)
    config_gen.emit_palace_stackup(
        config_gen.build_stack("typ", metal_stack="t4"), t4_ideal,
        pgs_return=True, ideal_ground=True)
    config_gen.emit_palace_stackup(
        config_gen.build_stack("typ", metal_stack="m1_m5"), m5)

    def load(path):
        root = ET.parse(path).getroot()
        mats = {m.get("Name"): m for m in root.find("Materials")}
        layers = {l.get("Name"): l for l in root.find("ELayers/Layers")}
        return mats, layers

    _, layers = load(t4)
    metals = {name: l for name, l in layers.items()
              if l.get("Type") == "conductor" and name not in ("RDL", "PGS")}
    check(set(metals) == {"M1", "M2", "M3", "M4", "T4M1", "T4M2"},
          "t4 stackup metals are M1-M4 + T4M1 + T4M2")
    check("M5" not in layers, "t4 stackup has no M5")
    check(layers["T4M1"].get("Layer") == "102"
          and layers["T4M2"].get("Layer") == "103",
          "t4 thick metals use GDS 102/103")
    z = {name: float(l.get("Zmin")) for name, l in metals.items()}
    zmax = {name: float(l.get("Zmax")) for name, l in metals.items()}
    check(z["M1"] < z["M2"] < z["M3"] < z["M4"] < z["T4M1"] < z["T4M2"],
          "t4 metal z-order is monotonic")
    check("T4V1" in layers and "T4V2" in layers and "V4" not in layers,
          "t4 vias are V1-V3 + T4V1/T4V2")
    check(float(layers["T4V1"].get("Zmin")) == zmax["M4"]
          and float(layers["T4V1"].get("Zmax")) == z["T4M1"],
          "T4V1 spans M4 -> T4M1")
    check(float(layers["T4V2"].get("Zmin")) == zmax["T4M1"]
          and float(layers["T4V2"].get("Zmax")) == z["T4M2"],
          "T4V2 spans T4M1 -> T4M2")

    connections = LVS_CONNECTIONS.read_text()
    for term in ("connect(M4s, T4V1s)", "connect(T4V1s, T4M1s)",
                 "connect(T4M1s, T4V2s)", "connect(T4V2s, T4M2s)",
                 "connect(T4M2s, PAS)", "connect(T4M1s, T4M1LBL)",
                 "connect(T4M2s, T4M2LBL)", "connect(RV, PAS)"):
        check(term in connections, "LVS t4 chain has %s" % term)

    check("PGS_RTN" not in layers, "no PGS_RTN without --pgs-return")
    _, layers_ret = load(t4_ret)
    rtn = layers_ret["PGS_RTN"]
    check(rtn.get("Type") == "via" and rtn.get("Layer") == "302",
          "PGS_RTN is via 302")
    check(float(rtn.get("Zmin")) == float(layers_ret["PGS"].get("Zmax")),
          "PGS_RTN starts at the PGS top")
    check(float(rtn.get("Zmax")) == z["M1"],
          "PGS_RTN ends at the M1 bottom")

    mats_ideal, layers_ideal = load(t4_ideal)
    check(mats_ideal["Metal1"].get("Conductivity") == "1e+18",
          "ideal ground sets M1 sigma to 1e18")
    check(mats_ideal["PGSRTN"].get("Conductivity") == "1e+18",
          "ideal ground sets PGS_RTN sigma to 1e18")

    _, layers_m5 = load(m5)
    check("M5" in layers_m5 and "T4M1" not in layers_m5,
          "m1_m5 stackup keeps M5 and has no T4M1")


def production_checks(kind, exe, tmp):
    print("manufacturing PCell")
    gds = tmp / "ics55_pcells.gds"
    invoke(kind, exe, DEMO, ["-rd", "gds=" + str(gds)])
    counts = inspect(kind, exe, gds, "ics55_ind")
    for layer in ("81/1", "300/1", "301/1", "302/1"):
        check(counts[layer] == 0,
              "production ics55_ind has no fixture shape on %s" % layer)
    check(counts["103/1"] > 0 and counts["2/1"] > 0,
          "production ics55_ind still has the spiral and PGS")


def deck_checks(kind, exe, tmp):
    print("EM fixture decks")
    infos = {}
    for variant, cfg in VARIANTS.items():
        for device in ("dut", "open"):
            spec = {
                "out": str(tmp / ("%s_%s.gds" % (variant, device))),
                "cell": "ics55_ind_em" if device == "dut" else "ics55_ind_em_open",
                "device_variant": device,
                "pgs_return": cfg["pgs_return"],
                "device": {"turns": 2.5, "size": 150.0, "width": 4.0,
                           "space": 2.0, "pgs": cfg["pgs"],
                           "pgs_width": 2.0, "pgs_space": 2.0},
            }
            infos[(variant, device)] = build_deck(
                kind, exe, spec, "%s/%s" % (variant, device))

    for variant in VARIANTS:
        for device in ("dut", "open"):
            layers = infos[(variant, device)]["layers"]
            check(layers["81/1"] == 1 and layers["300/1"] == 1
                  and layers["301/1"] == 1,
                  "%s/%s has the M1 plane and both port lines" % (variant, device))
        layers = infos[(variant, "dut")]["layers"]
        expected_rtn = 4 if VARIANTS[variant]["pgs_return"] else 0
        check(layers["302/1"] == expected_rtn,
              "%s has %d PGS_RTN vias" % (variant, expected_rtn))
        expected_aa = 46 if VARIANTS[variant]["pgs"] else 0
        check(layers["2/1"] == expected_aa,
              "%s has %d AA/PGS shapes" % (variant, expected_aa))

    for variant in VARIANTS:
        dut = infos[(variant, "dut")]["layers"]
        opn = infos[(variant, "open")]["layers"]
        check(opn["103/1"] == 2 and opn["123/1"] == 2 and opn["120/1"] == 4,
              "%s open deck keeps only the terminal pads" % variant)
        check(dut["103/1"] > opn["103/1"],
              "%s open deck removes the spiral" % variant)

    for key in (("pgs", "dut"), ("pgs", "open")):
        same = {k: v for k, v in infos[key]["layers"].items()}
        ideal = infos[("ideal_gnd", key[1])]["layers"]
        check(same == ideal, "ideal_gnd geometry matches pgs for %s" % key[1])


def structure_checks(kind, exe, tmp):
    print("structure / feed variants")
    device = {"turns": 2.5, "size": 150.0, "width": 4.0, "space": 2.0,
              "pgs": 2, "pgs_width": 2.0, "pgs_space": 2.0}

    def deck(tag, **overrides):
        spec = {"out": str(tmp / (tag + ".gds")), "cell": tag,
                "device_variant": "dut", "device": dict(device)}
        spec.update(overrides)
        return build_deck(kind, exe, spec, tag)

    single = deck("single_via")
    xfmr = deck("transformer", structure="transformer",
                transformer={"gap": 20.0})
    check(xfmr["ports"] == 4, "transformer deck exposes 4 ports")
    check(all(xfmr["layers"][layer] == 1 for layer in
              ("300/1", "301/1", "310/1", "311/1")),
          "transformer deck has one source line on each port layer")
    check(xfmr["layers"]["302/1"] == 8,
          "transformer deck puts 4 PGS_RTN vias on each shield ring")
    check(xfmr["layers"]["2/1"] == 2 * single["layers"]["2/1"],
          "transformer deck draws two independent shield rings")
    check(xfmr["layers"]["103/1"] > single["layers"]["103/1"],
          "transformer deck draws two windings")
    open_xfmr = deck("transformer_open", structure="transformer",
                     device_variant="open")
    check(open_xfmr["layers"]["103/1"] == 4,
          "transformer open deck keeps the four terminal pads")

    single_nopgs = deck("single_nopgs", device=dict(device, pgs=0))
    cpw = deck("cpw_nopgs", feed="cpw", device=dict(device, pgs=0))
    check(cpw["layers"]["302/1"] == 8,
          "cpw deck ties 2 ground strips x 2 ends on each port to M1")
    check(cpw["layers"]["103/1"] == single_nopgs["layers"]["103/1"] + 4,
          "cpw deck adds four TM2 ground strips")
    cpw_pgs = deck("cpw_pgs", feed="cpw")
    check(cpw_pgs["layers"]["302/1"] == 12,
          "cpw + PGS keeps 4 shield vias and adds 8 ground vias")
    check(cpw_pgs["layers"]["2/1"] == single["layers"]["2/1"],
          "cpw does not change the shield/PGS geometry")

    try:
        deck("cpw_no_return", feed="cpw", pgs_return=False)
        check(False, "cpw feed without the PGS_RTN layer must fail closed")
    except RuntimeError:
        check(True, "cpw feed without the PGS_RTN layer fails closed")


def deembed_checks(tmp):
    print("open-fixture de-embedding")
    try:
        import numpy as np
    except ImportError:
        print("  SKIP numpy not available")
        return
    from extract_lq import (deembed, read_port_s, series_lq, s_to_y,
                            s_to_z, y_to_s, z_to_s)

    z0 = 50.0
    freq = [0.5, 1.0, 1.5]                       # GHz
    expected_l = 1.0e-9
    expected_r = 1.0
    expected_c = 50.0e-15

    def s_params(f_ghz):
        w = 2.0 * np.pi * f_ghz * 1e9
        yp = 1j * w * expected_c
        ys = 1.0 / (expected_r + 1j * w * expected_l)
        y_dut = np.array([[yp + ys, -ys], [-ys, yp + ys]])
        y_open = np.array([[yp, 0], [0, yp]])
        return y_to_s(y_dut, z0), y_to_s(y_open, z0)

    def write_csv(path, mats):
        header = "f (GHz)"
        for i in range(2):
            for j in range(2):
                header += ", |S[%d][%d]| (dB), arg(S[%d][%d]) (deg.)" % (
                    i + 1, j + 1, i + 1, j + 1)
        rows = [header]
        for f_ghz, S in zip(freq, mats):
            cells = [str(f_ghz)]
            for i in range(2):
                for j in range(2):
                    cells += [str(20.0 * np.log10(abs(S[i, j]))),
                              str(np.degrees(np.angle(S[i, j])))]
            rows.append(", ".join(cells))
        path.write_text("\n".join(rows) + "\n")

    dut_csv, open_csv = tmp / "dut.csv", tmp / "open.csv"
    pairs = [s_params(f) for f in freq]
    write_csv(dut_csv, [p[0] for p in pairs])
    write_csv(open_csv, [p[1] for p in pairs])

    S = pairs[1][0]
    check(np.allclose(y_to_s(s_to_y(S, z0), z0), S),
          "S -> Y -> S round trip")
    check(np.allclose(z_to_s(s_to_z(S, z0), z0), S),
          "S -> Z -> S round trip")

    read_freq, smats = read_port_s(dut_csv)
    _, csh_raw = series_lq(smats[1][0], freq[1], z0)
    check(abs(csh_raw - expected_c) < 0.02 * expected_c,
          "raw fixture shows the pad Csh")
    read_freq, mats = deembed(read_freq, smats, open_csv=str(open_csv), z0=z0)
    for f_ghz, S_dev in zip(read_freq, mats):
        zs, csh = series_lq(S_dev, f_ghz, z0)
        w = 2.0 * np.pi * f_ghz * 1e9
        check(abs(zs.imag / w - expected_l) < 0.01 * expected_l,
              "de-embedded L at %.1f GHz" % f_ghz)
        check(abs(zs.real - expected_r) < 0.01 * expected_r,
              "de-embedded R at %.1f GHz" % f_ghz)
        check(abs(csh) < 0.02 * expected_c,
              "de-embedding removes pad Csh at %.1f GHz" % f_ghz)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--klayout", help="KLayout executable (default: PATH)")
    ap.add_argument("--librelane", default="~/Documents/librelane",
                    help="LibreLane flake directory for nix-shell")
    ap.add_argument("--skip-klayout", action="store_true")
    ap.add_argument("--require-klayout", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="em_deck_check_") as tmpdir:
        tmp = Path(tmpdir)
        stackup_checks(tmp)
        deembed_checks(tmp)

        resolved = find_klayout(args)
        if resolved is None:
            print("KLayout checks skipped (no --klayout/--librelane)")
            if args.require_klayout:
                FAILURES.append("KLayout not found")
        else:
            kind, exe = resolved
            production_checks(kind, exe, tmp)
            deck_checks(kind, exe, tmp)
            structure_checks(kind, exe, tmp)

    print("")
    if FAILURES:
        print("FAIL: %d checks failed, %d passed" % (len(FAILURES), PASSES))
        for item in FAILURES:
            print("  -", item)
        return 1
    print("PASS: %d checks" % PASSES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
