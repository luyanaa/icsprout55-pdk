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

# ICsprout55 - PCell demo / smoke test
#
# Registers the ICsprout55 PCell library and instantiates each PCell into a
# test layout, then writes the result to GDS (default ./ics55_pcells.gds).
#
# Usage:
#   klayout -b -r ics55_pcell_demo.py -z
#   klayout -b -r ics55_pcell_demo.py -z -rd gds=/tmp/ics55_pcells.gds
import os
import sys
import klayout.lay as lay
import klayout.db as db

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

import ics55_mos_analog  # noqa: F401  (registers lib)
import ics55_guard_ring  # noqa: F401
import ics55_res_poly    # noqa: F401
import ics55_mom         # noqa: F401
import ics55_ind         # noqa: F401

# `klayout -rd gds=<path>` lands here as a global; default next to the script.
out = globals().get("gds") or os.path.join(here, "ics55_pcells.gds")

# `klayout -rd em=1` builds the default Palace EM fixture through
# libs.tech/pex/palace/em_deck.py (PGS on, PGS tied to the M1 reference
# plane).  The fixture layers never enter the manufacturing cell.
if globals().get("em"):
    sys.path.insert(0, os.path.abspath(
        os.path.join(here, "..", "..", "pex", "palace")))
    import em_deck
    em_deck.build({
        "out": out, "cell": "ics55_ind_em", "device_variant": "dut",
        "pgs_return": True, "ground_mode": "m1",
        "device": {"turns": 2.5, "size": 150.0, "width": 4.0, "space": 2.0,
                   "pgs": 2, "pgs_width": 2.0, "pgs_space": 2.0},
    })
    print("wrote", out, "EM deck")
    sys.exit(0)

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
add("ics55_res_poly", {"w": 2.0, "l": 10.0, "rsq": 725.7}, 12.0, 12.0)
add("ics55_mom", {"fingers": 8, "length": 10.0, "layers": 3}, 4.0, 20.0)
add("ics55_ind", {"turns": 2.5, "size": 150.0, "width": 4.0, "space": 2.0,
                  "pgs": 2}, 4.0, 140.0)

ly.write(out)
print("wrote", out, "cells:", len(list(ly.each_cell())))
