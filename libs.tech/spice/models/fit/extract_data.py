#!/usr/bin/env python3
"""Extract per-state leakage + pin caps from ICS55 Liberty/CDL data.

Each output entry contains the Liberty input pins, pin capacitances, state
leakage targets, and the matching flattened CDL transistor netlist.
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdl_parser as cp


def parse_liberty(path):
    """Return cell -> {inputs, caps, states, cell_leak}."""
    text = open(path).read()
    out = {}
    for m in re.finditer(r"cell \((\w+)\) \{(.*?)(?=\n  cell |\Z)",
                         text, re.S):
        name = m.group(1)
        block = m.group(2)
        inputs = []
        caps = {}
        states = []
        cell_leak = None
        cm = re.search(r"cell_leakage_power\s*:\s*([\d.eE+\-]+)", block)
        if cm:
            cell_leak = float(cm.group(1))
        for pm in re.finditer(r"pin \((\w+)\) \{(.*?)(?=\n    pin |\n  \})",
                              block, re.S):
            pname = pm.group(1)
            pblock = pm.group(2)
            dm = re.search(r"direction\s*:\s*(\w+)", pblock)
            capm = re.search(r"capacitance\s*:\s*([\d.eE+\-]+)", pblock)
            if dm and dm.group(1) == "input":
                inputs.append(pname)
            if capm:
                caps[pname] = float(capm.group(1))
        for lm in re.finditer(r"leakage_power \(\) \{(.*?)\n    \}",
                              block, re.S):
            lb = lm.group(1)
            vm = re.search(r"value\s*:\s*([\d.eE+\-]+)", lb)
            wm = re.search(r"when\s*:\s*\"(.*?)\"", lb)
            pgm = re.search(r"related_pg_pin\s*:\s*(\w+)", lb)
            if vm and pgm and pgm.group(1) == "VDD":
                states.append((wm.group(1) if wm else "", float(vm.group(1))))
        out[name] = {"inputs": inputs, "caps": caps, "states": states,
                     "cell_leak": cell_leak}
    return out


def extract_records(flavor, cdl, lib, cell_set):
    """Return extracted records without writing a split-specific JSON file."""
    cells = cp.load(cdl, cell_filter=cell_set)
    libdata = parse_liberty(lib)
    result = {}
    for name in cell_set:
        if name not in cells or name not in libdata:
            continue
        c = cells[name]
        l = libdata[name]
        result[name] = {
            "inputs": l["inputs"],
            "caps": l["caps"],
            "states": l["states"],
            "cell_leak": l["cell_leak"],
            "wn": c["wn"], "wp": c["wp"], "mos": c["mcount"],
            "pins": c["pins"],
            "netlist": c["body"],
        }
    return result


def extract(flavor, cdl, lib, cell_set, out_path):
    result = extract_records(flavor, cdl, lib, cell_set)
    with open(out_path, "w") as stream:
        json.dump(result, stream, indent=1)
    print("%s: %d cells -> %s" % (flavor, len(result), out_path))
    return result


# Historical 20-cell release sample.  It contains sequential/pass-gate cells;
# data_fit removes the three whose static DC states are not well-defined.
MAIN_CELLS = [
    "INVX1", "INVX3", "NAND2X1", "AND2X1", "AND2X0P5", "BUFX2",
    "ADDFX1", "XNOR2X1", "DFFX1", "NOR2X1", "AND2X2", "NOR2X2",
    "XOR2X1", "TBUFX2", "AOI21X1", "MUX2X1", "DFFQX1", "OR2X1",
    "INVX4", "NAND3X1",
]
VAL_CELLS = [
    "AND2X2", "NOR2X2", "XOR2X1", "MUX2X1", "TBUFX2", "AOI21X1",
    "DFFQX1", "OR2X1", "INVX4", "NAND3X1",
]
UNSTABLE_CELLS = {"DFFX1", "MUX2X1", "DFFQX1"}

# Disjoint, combinational cell sets used for honest holdout checks.  They span
# topology and drive strength while avoiding sequential and pass-gate cells.
HOLDOUT_CELLS = [
    "INVX2", "INVX5", "BUFX4", "NAND2X3", "NOR2X3", "AND2X3",
    "OR2X3", "XOR2X2", "XNOR2X2", "NAND3X2", "NOR3X2", "AND3X2",
    "OR3X2", "AOI21X2", "OAI21X2", "AOI22X2", "OAI22X2", "AND4X2",
    "NOR4X2", "NAND4X2",
]
HOLDOUT2_CELLS = [
    "INVX20", "BUFX8", "NAND2X4", "NOR2X4", "AND2X4", "OR2X4",
    "XOR2X3", "XNOR2X3", "NAND3X3", "NOR3X3", "AND3X3", "OR3X3",
    "AOI21X3", "OAI21X3", "AOI22X3", "OAI22X3", "AND4X3", "NOR4X3",
    "NAND4X3", "OR4X3",
]


def suffixed(names, tag):
    return ["%sH7%s" % (name, tag[-1]) for name in names]


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "libs.ref")
    fitdir = os.path.dirname(os.path.abspath(__file__))
    for flavor, tag in [("svt", "H7CR"), ("lvt", "H7CL"), ("hvt", "H7CH")]:
        cdl = "%s/ics55_LLSC_%s/cdl/ics55_LLSC_%s.cdl" % (base, tag, tag)
        lib = "%s/ics55_LLSC_%s/liberty/ics55_LLSC_%s_typ_tt_1p2_25_nldm.lib" % (base, tag, tag)
        splits = {
            "main": MAIN_CELLS,
            "val": VAL_CELLS,
            "all": list(dict.fromkeys(MAIN_CELLS + VAL_CELLS)),
            "fit": [x for x in MAIN_CELLS if x not in UNSTABLE_CELLS],
            "holdout": HOLDOUT_CELLS,
            "holdout2": HOLDOUT2_CELLS,
        }
        extracted = {}
        for split, names in splits.items():
            path = os.path.join(fitdir, "data_%s_%s.json" % (split, flavor))
            extracted[split] = extract(flavor, cdl, lib, suffixed(names, tag), path)
        train = dict(extracted["fit"])
        train.update(extracted["holdout"])
        with open(os.path.join(fitdir, "data_train37_%s.json" % flavor), "w") as stream:
            json.dump(train, stream, indent=1)
        # Preserve the original short output name for older notebooks.
        with open(os.path.join(fitdir, "data_%s.json" % flavor), "w") as stream:
            json.dump(extracted["fit"], stream, indent=1)
