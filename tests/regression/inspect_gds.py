#!/usr/bin/env python3
"""KLayout helper: count shapes per layer in one GDS cell.

Usage:
    klayout -b -r inspect_gds.py -rd gds=<file> [-rd cell=<name>] \
            -rd layers=81/1,300/1,301/1
Prints one line: INSPECT:{ "<layer/datatype>": <shape count>, ... }
"""

import json

import klayout.db as db

layout = db.Layout()
layout.read(globals()["gds"])
name = globals().get("cell")
cell = layout.cell(name) if name else layout.top_cell()
counts = {}
for spec in globals().get("layers", "").split(","):
    layer, datatype = (int(v) for v in spec.split("/"))
    index = layout.layer(layer, datatype)
    counts[spec] = sum(1 for _ in cell.shapes(index).each())
print("INSPECT:" + json.dumps(counts, sort_keys=True))
