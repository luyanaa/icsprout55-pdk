#!/usr/bin/env python3
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
# ============================================================================
# make_em_deck.py - generate the EM fixture decks and their stackups
# ============================================================================
# Writes, for the requested variants:
#
#   ics55_ind_em[<variant>].gds        fixture + production PCell geometry
#   ics55_ind_em[<variant>]_open.gds   pad-only open reference (de-embedding)
#   ics55_stackup_em[_ideal].xml       Palace stackup aligned to the deck
#
# Variants (process value is the same; only the shield/ground fixture differs):
#
#   no_pgs      PGS off, M1 reference plane
#   pgs_float   PGS on, floating (legacy deck)
#   pgs         PGS on, PGS_RTN vias tie the shield to M1 (default)
#   ideal_gnd   as pgs, M1/PGS_RTN PEC-like (sigma 1e18 S/m)
#
# Structures:
#
#   inductor     one PCell, ports 1-2 on 300/1-301/1 (default)
#   transformer  two PCell instances side by side along y, ports 1-2 on the
#                primary and 3-4 on the secondary (310/1-311/1, run_model.py
#                --transformer); still an EM fixture, not a released device
#
# Feed styles:
#
#   via   vertical M1 -> TM2 port sheet alone (default)
#   cpw   grounded-coplanar launch: TM2 ground strips flank each port line and
#         are tied to M1 through 302/1 fixture vias (implies the PGS_RTN
#         stackup layer even without the PGS)
#
# The --metal-stack default is t4 (M1-M4 + T4M1 + T4M2), matching the LVS
# metal_stack=t4 profile that the thick-metal inductor sits in; the stackup
# has no M5.  Use --metal-stack m1_m5 for the released routing profile.
#
# Usage:
#   python3 make_em_deck.py --variant all --open
#   python3 make_em_deck.py --variant pgs --metal-stack m1_m5
#   python3 make_em_deck.py --structure transformer --variant pgs
#   python3 make_em_deck.py --feed cpw --variant no_pgs --open
# ============================================================================

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import config_gen  # noqa: E402

VARIANTS = {
    "no_pgs":    {"pgs": 0, "pgs_return": False, "ideal": False},
    "pgs_float": {"pgs": 2, "pgs_return": False, "ideal": False},
    "pgs":       {"pgs": 2, "pgs_return": True,  "ideal": False},
    "ideal_gnd": {"pgs": 2, "pgs_return": True,  "ideal": True},
}


def deck_path(out_dir, name, variant, device, feed="via"):
    if variant == "pgs":
        base = name if device == "dut" else name + "_open"
    else:
        base = "%s_%s" % (name, variant)
        if device == "open":
            base += "_open"
    if feed != "via":
        base += "_" + feed
    return Path(out_dir) / (base + ".gds")


def stackup_path(out_dir, variant, metal_stack):
    suffix = "_ideal" if VARIANTS[variant]["ideal"] else ""
    if metal_stack != "t4":
        suffix = "_%s%s" % (metal_stack, suffix)
    return Path(out_dir) / ("ics55_stackup_em%s.xml" % suffix)


def build_deck(em_deck_script, klayout, spec, cwd=None):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(spec, handle)
        spec_path = handle.name
    try:
        subprocess.run([klayout, "-b", "-r", str(em_deck_script),
                        "-rd", "spec=" + spec_path],
                       check=True, cwd=cwd)
    finally:
        os.unlink(spec_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", choices=tuple(VARIANTS) + ("all",),
                    default="pgs")
    ap.add_argument("--open", action="store_true",
                    help="also write the pad-only open de-embedding deck")
    ap.add_argument("--out-dir", default=str(HERE))
    ap.add_argument("--name",
                    help="deck basename (default: ics55_ind_em / ics55_xfmr_em)")
    ap.add_argument("--structure", choices=("inductor", "transformer"),
                    default="inductor")
    ap.add_argument("--feed", choices=("via", "cpw"), default="via")
    ap.add_argument("--transformer-gap", type=float, default=20.0,
                    help="transformer winding-to-winding clearance (um)")
    ap.add_argument("--cpw-gap", type=float, default=6.0,
                    help="cpw: signal-line edge to coplanar ground (um)")
    ap.add_argument("--cpw-ground-width", type=float, default=8.0,
                    help="cpw: coplanar ground strip width (um)")
    ap.add_argument("--metal-stack", choices=tuple(config_gen.METAL_STACKS),
                    default="t4")
    ap.add_argument("--corner", default="typ")
    ap.add_argument("--source", choices=("starrc", "lef"), default="starrc")
    ap.add_argument("--klayout", default=os.environ.get("KLAYOUT", "klayout"))
    ap.add_argument("--turns", type=float, default=2.5)
    ap.add_argument("--size", type=float, default=150.0)
    ap.add_argument("--width", type=float, default=4.0)
    ap.add_argument("--space", type=float, default=2.0)
    ap.add_argument("--pgs-width", type=float, default=2.0)
    ap.add_argument("--pgs-space", type=float, default=2.0)
    args = ap.parse_args()

    variants = list(VARIANTS) if args.variant == "all" else [args.variant]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    em_deck_script = HERE / "em_deck.py"
    name = args.name or ("ics55_ind_em" if args.structure == "inductor"
                         else "ics55_xfmr_em")
    # A grounded-coplanar launch returns through the 302/1 fixture via, so the
    # PGS_RTN stackup layer is required even when the PGS itself is off.
    cpw = args.feed == "cpw"

    stack = config_gen.build_stack(args.corner, source=args.source,
                                   metal_stack=args.metal_stack)
    # One stackup may serve several variants; keep the PGS_RTN layer if any
    # variant in this run needs it.
    stackups = {}
    for variant in variants:
        path = stackup_path(out_dir, variant, args.metal_stack)
        ret = VARIANTS[variant]["pgs_return"] or cpw
        if path in stackups:
            ret = ret or stackups[path][0]
        stackups[path] = (ret, VARIANTS[variant]["ideal"])
    for path, (pgs_return, ideal) in stackups.items():
        config_gen.emit_palace_stackup(stack, path, pgs_return=pgs_return,
                                       ideal_ground=ideal)
        print("stackup ->", path)

    manifest = []
    for variant in variants:
        cfg = VARIANTS[variant]
        stack_out = stackup_path(out_dir, variant, args.metal_stack)
        for device in ("dut", "open"):
            if device == "open" and not args.open:
                continue
            gds = deck_path(out_dir, name, variant, device, args.feed)
            spec = {
                "out": str(gds),
                "cell": name if device == "dut" else name + "_open",
                "device_variant": device,
                "structure": args.structure,
                "feed": args.feed,
                "pgs_return": cfg["pgs_return"] or cpw,
                "ground_mode": "ideal" if cfg["ideal"] else "m1",
                "transformer": {"gap": args.transformer_gap},
                "cpw": {"gap": args.cpw_gap,
                        "ground_width": args.cpw_ground_width},
                "device": {
                    "turns": args.turns, "size": args.size,
                    "width": args.width, "space": args.space,
                    "pgs": cfg["pgs"],
                    "pgs_width": args.pgs_width,
                    "pgs_space": args.pgs_space,
                },
            }
            build_deck(em_deck_script, args.klayout, spec, cwd=str(HERE))
            ports = ["300/1", "301/1"]
            if args.structure == "transformer":
                ports += ["310/1", "311/1"]
            manifest.append({
                "variant": variant, "device": device,
                "gds": gds.name, "stackup": stack_out.name,
                "metal_stack": args.metal_stack, "corner": args.corner,
                "structure": args.structure, "feed": args.feed,
                "pgs": cfg["pgs"], "pgs_return": cfg["pgs_return"] or cpw,
                "ideal_ground": cfg["ideal"],
                "ports": ports, "ground": "81/1",
                "pgs_return_layer": "302/1",
            })
            print("deck ->", gds)

    manifest_path = out_dir / "EM_DECKS.json"
    manifest_path.write_text(json.dumps({
        "generator": "libs.tech/pex/palace/make_em_deck.py",
        "metal_stack": args.metal_stack, "corner": args.corner,
        "source": args.source, "decks": manifest},
        indent=2) + "\n")
    print("manifest ->", manifest_path)


if __name__ == "__main__":
    main()
