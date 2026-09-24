# ICsprout55 - PCell demo / smoke test
#
# Registers the ICsprout55 PCell library and instantiates each PCell into a
# test layout, then writes the result to GDS (default ./ics55_pcells.gds).
#
# Usage:
#   klayout -b -r ics55_pcell_demo.py -z
#   klayout -b -r ics55_pcell_demo.py -z -rd gds=/tmp/ics55_pcells.gds
import sys
import klayout.lay as lay
import klayout.db as db

here = "/Users/yanlu/Documents/icsprout55-pdk/libs.tech/klayout/pcells"
sys.path.insert(0, here)

import ics55_mos_analog  # noqa: F401  (registers lib)
import ics55_guard_ring  # noqa: F401
import ics55_res_poly    # noqa: F401
import ics55_mom         # noqa: F401

out = "/Users/yanlu/Documents/icsprout55-pdk/libs.tech/klayout/pcells/ics55_pcells.gds"
try:
    from klayout import config  # not available; kept for clarity
except Exception:
    pass
for a in sys.argv:
    if a.startswith("gds="):
        out = a.split("=", 1)[1]

ly = db.Layout()
ly.dbu = 0.001
top = ly.create_cell("TOP")

# instantiate pcells by (lib, pcell) name
def add(pcell_name, params, x, y):
    c = ly.create_cell(pcell_name, "ICsprout55", params)
    t = db.Trans(db.Vector(int(round(x / ly.dbu)), int(round(y / ly.dbu))))
    top.insert(db.CellInstArray(c.cell_index(), t))
    return c

add("ics55_mos_analog", {"dev_type": "n", "w": 1.0, "l": 0.06, "fingers": 3,
                         "guard_ring": 1, "ring_metal": 1}, 4.0, 4.0)
add("ics55_mos_analog", {"dev_type": "p", "w": 1.0, "l": 0.06, "fingers": 3,
                         "guard_ring": 1, "ring_metal": 1}, 12.0, 4.0)
add("ics55_guard_ring", {"ring_type": "pring", "w": 0.5, "spacing": 1.0}, 4.0, 12.0)
add("ics55_res_poly", {"w": 2.0, "l": 10.0, "rsq": 850.0}, 12.0, 12.0)
add("ics55_mom", {"fingers": 8, "length": 10.0, "layers": 3}, 4.0, 20.0)

ly.write(out)
print("wrote", out, "cells:", len(list(ly.each_cell())))
