#!/usr/bin/env python3
"""Minimal CT / V1 stack test for the ics55 Magic tech.

    python3 make_stack.py          # -> via_stack.gds
    magic -dnull -noconsole -rcfile ics55_pex.magicrc extract_stack.tcl

Two independent stacks:
  * poly -- CT -- M1      (gate-contact connectivity)
  * M1   -- V1 -- M2      (via connectivity)

The expected extraction is one node per stack; the current tech reports the
two sides as separate nodes (CT/V1 are aliased to active/metal1 and are not
treated as cut types by the GDS extractor).
"""
import os

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "via_stack.gds")

L_POLY = (41, 1)
L_CT = (72, 1)
L_M1 = (81, 1)
L_V1 = (91, 1)
L_M2 = (82, 1)


def main():
    ly = db.Layout()
    ly.dbu = 0.001
    top = ly.create_cell("STACK")

    def box(layer, x1, y1, x2, y2):
        top.shapes(ly.layer(*layer)).insert(
            db.Box(int(x1 * 1000), int(y1 * 1000),
                   int(x2 * 1000), int(y2 * 1000)))

    def text(layer, s, x, y):
        top.shapes(ly.layer(*layer)).insert(
            db.Text(s, db.Trans(int(x * 1000), int(y * 1000))))

    # CT stack: poly -- CT -- M1
    box(L_POLY, -1.0, -1.0, 1.0, 1.0)
    text(L_POLY, "P", -0.5, 0.0)
    box(L_CT, -0.045, -0.045, 0.045, 0.045)
    box(L_M1, -1.0, -1.0, 1.0, 1.0)
    text(L_M1, "M1_CT", 0.5, 0.0)

    # V1 stack: M1 -- V1 -- M2
    box(L_M1, 3.0, -1.0, 5.0, 1.0)
    text(L_M1, "M1_V", 3.5, 0.0)
    box(L_V1, 3.955, -0.045, 4.045, 0.045)
    box(L_M2, 3.0, -1.0, 5.0, 1.0)
    text(L_M2, "M2_V", 4.5, 0.0)

    ly.write(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
