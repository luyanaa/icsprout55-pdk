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

"""Regression for the promoted Magic tech and the netgen LVS flow.

Checks, all against `libs.tech/magic/ics55.tech`:

1. A contact and a via drawn at exactly the same centre connect at every
   level (CT+V1, V1+V2, V2+V3, V3+V4, V4+TV2).  This is the `stackable`
   regression: without it the lower contact is dropped.
2. An n+ tap inside nwell extracts as an nw node; a p+ tap in the
   p-substrate extracts as the substrate node; an untapped nwell island
   stays separate.
3. A 10x10 um metal plate extracts the released LEF area + edge
   capacitance (M1/M2/TM2) within 0.5%, which pins the aF/lambda^2 and
   aF/lambda units in the extract section.
4. Representative standard cells pass netgen LVS, and the documented
   foundry width mismatches report property errors (exit 1), not a
   topology mismatch.
5. Hierarchical macro LVS descends into a standard-cell child: once with
   the child subckts inline in the reference CDL, and once as a top-only
   CDL plus `--library`.
6. A p+ and an n+ junction under the DIODE marker extract exactly one diode
   each with the calibrated area/perimeter, and plain contacted taps with
   no DIODE marker extract no diode at all.
7. A four-segment SAB poly resistor extracts one device per segment; the
   runner's X->R rewrite and netgen's series combination fold them into the
   CDL's single W/L.

Run:
  python3 tests/regression/magic_lvs_check.py [-v]

Exit status: 0 all checks pass, 1 a check failed, 2 the environment is
missing a required tool.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
PDK_ROOT = HERE.parents[1]
MAGICRC = PDK_ROOT / "libs.tech/magic/ics55.magicrc"
RUN_LVS = PDK_ROOT / "libs.tech/netgen/run_lvs.py"
FIXTURES_RB = HERE / "magic_fixtures.rb"
HIER_FIXTURES_RB = HERE / "magic_hier_fixture.rb"
DIODE_FIXTURES_RB = HERE / "magic_diode_fixture.rb"
RESISTOR_FIXTURES_RB = HERE / "magic_resistor_fixture.rb"
NETGEN_SETUP = PDK_ROOT / "libs.tech/netgen/ics55.tcl"
STDHCR_CDL = PDK_ROOT / "libs.ref/ics55_LLSC_H7CR/cdl/ics55_LLSC_H7CR.cdl"

# (library, cell, expected exit of run_lvs.py)
CELL_MATRIX = (
    ("ics55_LLSC_H7CR", "INVX1H7R", 0),
    ("ics55_LLSC_H7CR", "NAND2X1H7R", 0),
    ("ics55_LLSC_H7CR", "AND2X1H7R", 0),
    ("ics55_LLSC_H7CR", "SDFFNRX2H7R", 0),
    ("ics55_LLSC_H7CL", "NAND2X1H7L", 0),
    ("ics55_LLSC_H7CH", "NAND2X1H7H", 0),
    # Foundry data: drawn widths deviate >10% from the CDL.  Topology must
    # still match, so the expected status is 1 (property errors), not 2.
    ("ics55_LLSC_H7CR", "OAI33X0P5H7R", 1),
    ("ics55_LLSC_H7CR", "INVX16H7R", 1),
)

STACK_PAIRS = (
    ("P_CT_V1", "M2_CT_V1"),
    ("M1_V1_V2", "M3_V1_V2"),
    ("M2_V2_V3", "M4_V2_V3"),
    ("M3_V3_V4", "M5_V3_V4"),
    ("M4_V4_TV2", "TM2_V4_TV2"),
)


class Checker:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.failures: List[str] = []
        self.passes = 0

    def check(self, condition: bool, message: str) -> None:
        if condition:
            self.passes += 1
            print(f"  PASS  {message}")
        else:
            self.failures.append(message)
            print(f"  FAIL  {message}")


def run(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(item) for item in cmd],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        errors="replace",
    )


def parse_ext(path: Path) -> Tuple[Dict[str, str], List[Tuple[str, str]], List[str]]:
    nodes: Dict[str, str] = {}
    equivs: List[Tuple[str, str]] = []
    substrates: List[str] = []
    for line in path.read_text(errors="ignore").splitlines():
        if line.startswith("node "):
            match = re.match(
                r'^node\s+"([^"]+)"\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)',
                line,
            )
            if match:
                nodes[match.group(1)] = match.group(2)
        elif line.startswith("equiv "):
            match = re.match(r'^equiv\s+"([^"]+)"\s+"([^"]+)"', line)
            if match:
                equivs.append((match.group(1), match.group(2)))
        elif line.startswith("substrate "):
            match = re.match(r'^substrate\s+"([^"]+)"', line)
            if match:
                substrates.append(match.group(1))
    return nodes, equivs, substrates


class UnionFind:
    def __init__(self) -> None:
        self.parent: Dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: str, right: str) -> None:
        self.parent[self.find(right)] = self.find(left)


def extract_fixtures(klayout: str, magic: str, work: Path) -> None:
    generated = run([klayout, "-b", "-r", FIXTURES_RB, "-rd", f"out={work}"], cwd=work)
    if generated.returncode != 0:
        raise SystemExit(f"klayout fixture generation failed:\n{generated.stderr}")
    gds = work / "magic_fixtures.gds"
    script = work / "extract.tcl"
    script.write_text(
        "\n".join(
            [
                "drc off",
                f"gds read {{{gds}}}",
                "load MAGIC_STACK",
                "select top cell",
                "extract do local",
                "extract all",
                "load MAGIC_TAP",
                "select top cell",
                "extract do local",
                "extract all",
                "load MAGIC_CAP_M1",
                "select top cell",
                "extract all",
                "load MAGIC_CAP_M2",
                "select top cell",
                "extract all",
                "load MAGIC_CAP_TM2",
                "select top cell",
                "extract all",
                "quit -noprompt",
                "",
            ]
        )
    )
    extracted = run(
        [magic, "-dnull", "-noconsole", "-rcfile", MAGICRC, script], cwd=work
    )
    if extracted.returncode != 0 or not (work / "MAGIC_STACK.ext").is_file():
        raise SystemExit(
            "magic fixture extraction failed:\n"
            + (extracted.stdout + extracted.stderr)[-4000:]
        )


def check_connectivity(checker: Checker, work: Path) -> None:
    nodes, equivs, substrates = parse_ext(work / "MAGIC_STACK.ext")
    all_names = set(nodes)
    for left, right in equivs:
        all_names.update((left, right))
    connected = UnionFind()
    for left, right in equivs:
        connected.union(left, right)
    print("contact/via stacks (exact centre)")
    for low, high in STACK_PAIRS:
        present = low in all_names and high in all_names
        same = present and connected.find(low) == connected.find(high)
        checker.check(present and same, f"{low} <-> {high} one node")

    tap_nodes, tap_equivs, tap_substrates = parse_ext(work / "MAGIC_TAP.ext")
    print("tap connectivity")
    checker.check(tap_nodes.get("VDDTAP") == "nw", "n+ tap extracts as an nw node")
    checker.check(
        "VSSTAP" in tap_substrates, "p+ tap is the substrate node"
    )
    separate = [
        name for name, kind in tap_nodes.items() if kind == "nw" and name != "VDDTAP"
    ]
    checker.check(bool(separate), "untapped nwell island stays separate")


# Released LEF RC seeds (N551P6M.lef / N551P6M_ecos.lef), pF/um^2 and
# pF/um.  A 10x10 um plate has 100 um^2 of area and 40 um of perimeter.
CAP_SEEDS = {
    "M1": (0.000763, 0.0000339),
    "M2": (0.0011069, 0.0000391),
    "TM2": (0.0001299, 0.0000368),
}
CAP_PLATE_AREA_UM2 = 100.0
CAP_PLATE_PERIM_UM = 40.0
CAP_TOLERANCE = 0.005


def check_capacitance(checker: Checker, work: Path) -> None:
    print("PEX capacitance calibration (10x10 um plate)")
    for layer, (area_pf_um2, edge_pf_um) in CAP_SEEDS.items():
        path = work / f"MAGIC_CAP_{layer}.ext"
        if not path.is_file():
            checker.check(False, f"{layer}: missing {path.name}")
            continue
        caps = {}
        for line in path.read_text(errors="ignore").splitlines():
            match = re.match(r'^node\s+"([^"]+)"\s+\S+\s+(\S+)', line)
            if match:
                caps[match.group(1)] = float(match.group(2))
        expected = (
            area_pf_um2 * CAP_PLATE_AREA_UM2 + edge_pf_um * CAP_PLATE_PERIM_UM
        ) * 1000.0  # pF -> fF
        actual = caps.get(f"P_{layer.lower()}")
        if actual is None:
            checker.check(False, f"{layer}: no labelled plate node in {path.name}")
            continue
        relative = abs(actual - expected) / expected
        checker.check(
            relative <= CAP_TOLERANCE,
            f"{layer}: {actual:.3f} fF vs LEF {expected:.3f} fF "
            f"({relative * 100:.3f}%)",
        )


def check_hierarchy(checker: Checker, klayout: str, work: Path) -> None:
    """MAGIC_HIER = one INVX1H7R instance with labelled top-level pins.

    Two references are exercised: one CDL that already contains the child
    subckts, and a top-only CDL plus `--library` (the macro-flow shape that
    lets netgen descend into the standard cells).

    `--mode stdcell` is required: the released standard-cell GDS has no
    physical well taps, so its bulk terminals only resolve through the
    global VDD/VSS tie that the released CDL assumes.
    """
    print("hierarchical macro LVS")
    out = work / "hier"
    out.mkdir(parents=True, exist_ok=True)
    generated = run(
        [klayout, "-b", "-r", HIER_FIXTURES_RB, "-rd", f"out={out}"], cwd=out
    )
    if generated.returncode != 0:
        checker.check(
            False,
            "MAGIC_HIER: fixture generation failed\n"
            + (generated.stdout + generated.stderr)[-2000:],
        )
        return

    gds = out / "magic_hier.gds"
    top_cdl = out / "magic_hier_top.cdl"
    top_cdl.write_text(
        "* macro top only; the child subckts come from --library\n"
        ".SUBCKT MAGIC_HIER A VDD VSS Y\n"
        "XINV_0 A VDD VSS Y INVX1H7R\n"
        ".ENDS\n"
        ".END\n"
    )

    cases = (
        (
            "MAGIC_HIER: exit 0 (expected 0)",
            "inline",
            ["--netlist", out / "magic_hier.cdl"],
        ),
        (
            "MAGIC_HIER --library: exit 0 (expected 0)",
            "library",
            ["--netlist", top_cdl, "--library", STDHCR_CDL],
        ),
    )

    for message, slug, args in cases:
        if any(Path(item) == STDHCR_CDL for item in args) and not STDHCR_CDL.is_file():
            checker.check(False, f"MAGIC_HIER: missing {STDHCR_CDL}")
            continue
        report = out / f"{slug}.rpt"
        summary = out / f"{slug}.json"
        case_work = out / f"{slug}_work"
        proceeded = run(
            [
                sys.executable,
                RUN_LVS,
                "--layout",
                gds,
                "--top",
                "MAGIC_HIER",
                *args,
                "--mode",
                "stdcell",
                "--report",
                report,
                "--json",
                summary,
                "--workdir",
                case_work,
            ]
        )
        status = proceeded.returncode
        detail = ""
        if summary.is_file():
            try:
                data = json.loads(summary.read_text())
                detail = data.get("verdict", "")
                if slug == "library":
                    merged = case_work / "reference.cdl"
                    merged_text = (
                        merged.read_text(errors="ignore") if merged.is_file() else ""
                    )
                    detail += ", reference={}".format(
                        "children+top"
                        if ".SUBCKT INVX1H7R" in merged_text
                        and ".SUBCKT MAGIC_HIER" in merged_text
                        else "incomplete"
                    )
                    if "children+top" not in detail:
                        status = -1
            except json.JSONDecodeError:
                detail = "invalid JSON"
        report_text = report.read_text(errors="ignore") if report.is_file() else ""
        matched = "circuits match uniquely" in report_text.lower()
        checker.check(status == 0 and matched, f"{message} {detail}".rstrip())
        if status != 0 or not matched or checker.verbose:
            print((proceeded.stdout + proceeded.stderr)[-2000:])


# (cell, device class, model, area um^2, perimeter um, junction nets)
DIODE_EXPECT = (
    ("MAGIC_PDIO", "pdiode", "dio_1p2_pp_nw_lvt_lp", 10.0, 14.0,
     {"ANODE", "CATHODE"}),
    ("MAGIC_NDIO", "ndiode", "dio_1p2_np_pw_lvt_lp", 10.0, 13.0,
     {"ANODE2", "CATHODE2"}),
)


def check_diodes(checker: Checker, klayout: str, magic: str, work: Path) -> None:
    """DIODE-marker junctions become one diode; plain taps become none.

    `.ext` device geometry is in 1e-4 um^2 (area) and 1e-2 um (perimeter).
    """
    print("junction diode extraction")
    out = work / "diode"
    out.mkdir(parents=True, exist_ok=True)
    generated = run(
        [klayout, "-b", "-r", DIODE_FIXTURES_RB, "-rd", f"out={out}"], cwd=out
    )
    if generated.returncode != 0:
        checker.check(
            False,
            "diode fixture generation failed\n"
            + (generated.stdout + generated.stderr)[-2000:],
        )
        return

    cells = [row[0] for row in DIODE_EXPECT] + ["MAGIC_TAPS"]
    script_lines = ["drc off", f"gds read {{{out / 'magic_diode.gds'}}}"]
    for cell in cells:
        script_lines += [
            f"load {cell}",
            "select top cell",
            "extract do local",
            "extract all",
        ]
    script_lines += ["quit -noprompt", ""]
    script = out / "extract.tcl"
    script.write_text("\n".join(script_lines))
    extracted = run(
        [magic, "-dnull", "-noconsole", "-rcfile", MAGICRC, script], cwd=out
    )
    if extracted.returncode != 0:
        checker.check(
            False,
            "diode fixture extraction failed\n"
            + (extracted.stdout + extracted.stderr)[-4000:],
        )
        return

    def diodes(cell: str):
        path = out / f"{cell}.ext"
        found = []
        if not path.is_file():
            return found
        for line in path.read_text(errors="ignore").splitlines():
            if not line.startswith("device "):
                continue
            tokens = line.split()
            params = dict(
                token.split("=", 1) for token in tokens if "=" in token
            )
            nodes = set(re.findall(r'"([^"]+)"', line))
            found.append((tokens[1], tokens[2], params, nodes))
        return [item for item in found if item[0] in ("pdiode", "ndiode")]

    for cell, kind, model, area, pj, nets in DIODE_EXPECT:
        found = diodes(cell)
        ok = len(found) == 1 and found[0][0] == kind and found[0][1] == model
        detail = f"{len(found)} diode(s)"
        if ok:
            _, _, params, nodes = found[0]
            got_area = float(params["a"]) * 1e-4
            got_pj = float(params["p"]) * 1e-2
            ok = (
                abs(got_area - area) / area <= 0.01
                and abs(got_pj - pj) / pj <= 0.01
                and nets <= nodes
            )
            detail = (
                f"{model} area={got_area:g} pj={got_pj:g} "
                f"nodes={sorted(nodes)}"
            )
        checker.check(ok, f"{cell}: {detail}")

    taps = diodes("MAGIC_TAPS")
    checker.check(
        not taps, f"MAGIC_TAPS: 0 diodes (got {len(taps)})"
    )


def check_resistors(
    checker: Checker, klayout: str, magic: str, netgen: str, work: Path
) -> None:
    """SNAKE = four 3.64 x 1.0 um SAB poly segments in series.

    Verifies that Magic extracts one `re_ppo_sab_2t` per segment and that
    run_lvs' X->R rewrite + netgen series combination folds them into the
    CDL's single W=1u / L=14.56u device.
    """
    print("folded poly-resistor extraction")
    out = work / "resistor"
    out.mkdir(parents=True, exist_ok=True)
    generated = run(
        [klayout, "-b", "-r", RESISTOR_FIXTURES_RB, "-rd", f"out={out}"], cwd=out
    )
    if generated.returncode != 0:
        checker.check(
            False,
            "resistor fixture generation failed\n"
            + (generated.stdout + generated.stderr)[-2000:],
        )
        return

    script = out / "extract.tcl"
    script.write_text(
        "\n".join(
            [
                "drc off",
                f"gds read {{{out / 'magic_resistor.gds'}}}",
                "load SNAKE",
                "select top cell",
                "extract do local",
                "extract all",
                "ext2spice lvs",
                f"ext2spice -o {{{out / 'SNAKE.spice'}}}",
                "quit -noprompt",
                "",
            ]
        )
    )
    extracted = run(
        [magic, "-dnull", "-noconsole", "-rcfile", MAGICRC, script], cwd=out
    )
    if extracted.returncode != 0 or not (out / "SNAKE.ext").is_file():
        checker.check(
            False,
            "resistor fixture extraction failed\n"
            + (extracted.stdout + extracted.stderr)[-4000:],
        )
        return

    ext = out / "SNAKE.ext"
    segments = [
        line
        for line in ext.read_text(errors="ignore").splitlines()
        if line.startswith("device rsubckt re_ppo_sab_2t")
    ]
    geometry_ok = len(segments) == 4 and all(
        " l=364 " in line and " w=100 " in line for line in segments
    )
    checker.check(
        geometry_ok,
        f"SNAKE: {len(segments)} segments, expected 4x (l=3.64 um, w=1 um)",
    )

    # Wrap the top-level ext2spice output in a subckt, then run the same
    # post-processing the LVS runner uses (X -> R, um -> m).
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_lvs", RUN_LVS)
    run_lvs = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(run_lvs)

    spice_text = (out / "SNAKE.spice").read_text(errors="ignore").splitlines()
    wrapped = out / "SNAKE_wrapped.spice"
    wrapped.write_text(
        ".subckt SNAKE POS NEG\n"
        + "\n".join(line for line in spice_text if line.startswith("X"))
        + "\n.ends\n"
    )
    prepared = out / "SNAKE.lvs.spice"
    run_lvs.postprocess(wrapped, prepared, "SNAKE", ["POS", "NEG"], False, False)
    reference = out / "SNAKE_ref.spice"
    reference.write_text(
        run_lvs.convert_resistor_instances(
            "* folded resistor reference\n"
            ".SUBCKT SNAKE POS NEG\n"
            "R0 POS NEG re_ppo_sab_2t W=1u L=14.56u M=1\n"
            ".ENDS\n"
            ".END\n"
        )
    )
    report = out / "SNAKE.lvs.rpt"
    proceeded = run(
        [
            netgen,
            "-batch",
            "lvs",
            f"{prepared} SNAKE",
            f"{reference} SNAKE",
            NETGEN_SETUP,
            report,
        ],
        cwd=out,
    )
    report_text = report.read_text(errors="ignore") if report.is_file() else ""
    matched = "match uniquely" in report_text.lower()
    clean = "property error" not in report_text.lower()
    checker.check(
        proceeded.returncode == 0 and matched and clean,
        "SNAKE: 4 series segments -> 1 folded resistor, zero property errors",
    )


def check_cells(checker: Checker, verbose: bool, work: Path) -> None:
    print("standard-cell LVS")
    for library, cell, expected in CELL_MATRIX:
        gds = PDK_ROOT / "libs.ref" / library / "gds" / f"{library}.gds"
        if not gds.is_file():
            checker.check(False, f"{cell}: missing {gds}")
            continue
        report = work / f"{cell}.lvs.rpt"
        summary = work / f"{cell}.lvs.json"
        proceeded = run(
            [
                sys.executable,
                RUN_LVS,
                "--layout",
                gds,
                "--top",
                cell,
                "--report",
                report,
                "--json",
                summary,
            ]
        )
        status = proceeded.returncode
        detail = ""
        if summary.is_file():
            try:
                data = json.loads(summary.read_text())
                detail = data.get("verdict", "")
                if expected == 1:
                    detail += ", property_errors={}".format(
                        data.get("property_errors")
                    )
                    if data.get("property_errors") is not True:
                        status = -1
            except json.JSONDecodeError:
                detail = "invalid JSON"
        checker.check(
            status == expected,
            f"{cell}: exit {status} (expected {expected}) {detail}".rstrip(),
        )
        if status != expected or verbose:
            print((proceeded.stdout + proceeded.stderr)[-2000:])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    missing = [
        tool for tool in ("magic", "netgen", "klayout") if shutil.which(tool) is None
    ]
    if missing:
        print(f"error: missing tools: {', '.join(missing)}", file=sys.stderr)
        return 2
    magic = shutil.which("magic")
    netgen = shutil.which("netgen")
    klayout = shutil.which("klayout")
    assert magic and netgen and klayout

    tmp_root = Path("/tmp/opencode")
    work = Path(
        tempfile.mkdtemp(
            prefix="magic_lvs_check_",
            dir=str(tmp_root) if tmp_root.is_dir() else None,
        )
    )
    checker = Checker(verbose=args.verbose)
    try:
        extract_fixtures(klayout, magic, work)
        check_connectivity(checker, work)
        check_capacitance(checker, work)
        check_diodes(checker, klayout, magic, work)
        check_resistors(checker, klayout, magic, netgen, work)
        check_hierarchy(checker, klayout, work)
        check_cells(checker, args.verbose, work)
    finally:
        if not args.verbose:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"work dir: {work}")

    total = checker.passes + len(checker.failures)
    print(f"\n{checker.passes}/{total} checks passed")
    if checker.failures:
        print("failed checks:")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
