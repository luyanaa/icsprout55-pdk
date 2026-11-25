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

"""Standalone Magic + netgen LVS for ICsprout55.

The flow has four steps:

1. Magic reads the GDS, extracts the top cell and writes an LVS SPICE
   netlist (`ext2spice lvs`).  Magic emits micrometre W/L values and no
   ports on the `.subckt` line.
2. This script injects the CDL port order and converts W/L from um to m
   (the released CDL is SI).  Diode area/perimeter are likewise converted
   from um^2/um to m^2/m.  It also collapses every ground-domain net
   (`VSS*`, the Calibre deck's `LVS GROUND NAME "?VSS?"`) onto one net in
   both netlists, because a p+ substrate tap physically connects the
   grounds a flat extraction sees.  In the default standard-cell mode it also
   ties the PMOS bulk to VDD and the NMOS bulk to VSS, because the released
   standard-cell GDS has no well taps; the KLayout deck does the same
   global tie in its standard-cell mode.
3. netgen compares the layout netlist with the reference CDL using the
   PDK setup file (`libs.tech/netgen/ics55.tcl`).  Extra `--library`
   CDLs are merged into the reference so a hierarchical macro top can
   resolve its child subcircuits.
4. The result is classified and a JSON summary is written next to the
   comparison report.

Usage:
  python3 run_lvs.py --layout <lib.gds> --top <CELL> \
      [--netlist <lib.cdl>] [--library <lib.cdl> ...] [--mode stdcell|macro] \
      [--report <CELL>.lvs.rpt] [--json <CELL>.lvs.json] \
      [--magicrc <ics55.magicrc>] [--setup <ics55.tcl>] \
      [--no-well-ties] [--keep-work] [-v]

Exit status:
  0  circuits match uniquely (no property errors)
  1  topology matches uniquely but property errors were found
  2  topology mismatch, missing input, or a tool failure

`--mode macro` keeps the extracted body connections untouched; use it for a
macro that has physical well/substrate taps.  `--mode stdcell` (default) is
the global well tie used by standalone standard-cell LVS.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
PDK_ROOT = HERE.parents[1]

DEFAULT_MAGICRC = PDK_ROOT / "libs.tech/magic/ics55.magicrc"
DEFAULT_SETUP = HERE / "ics55.tcl"

MOS_MODELS = (
    "nm1p2_svt_lp",
    "pm1p2_svt_lp",
    "nm1p2_lvt_lp",
    "pm1p2_lvt_lp",
    "nm1p2_hvt_lp",
    "pm1p2_hvt_lp",
    "nm3p3_lp",
    "pm3p3_lp",
)

_SPICE_SUFFIX = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
    "t": 1e12,
}


def log(verbose: bool, message: str) -> None:
    if verbose:
        print(message, file=sys.stderr)


def run(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        errors="replace",
    )


def find_netlist(top: str, layout: Path) -> Path:
    """Locate the reference CDL for *top*.

    Order: `<layout dir>/<top>.cdl`, then any `libs.ref/*/cdl/*.cdl` file
    that defines `.SUBCKT <top>`.
    """
    local = layout.parent / f"{top}.cdl"
    if local.is_file():
        return local
    ref_root = PDK_ROOT / "libs.ref"
    for cdl in sorted(ref_root.glob("*/cdl/*.cdl")):
        try:
            text = cdl.read_text(errors="ignore")
        except OSError:
            continue
        if re.search(rf"(?mi)^\.subckt\s+{re.escape(top)}(\s|$)", text):
            return cdl
    raise SystemExit(f"error: no reference CDL found for {top!r}; use --netlist")


def cdl_ports(cdl: Path, top: str) -> List[str]:
    """Return the port list of `.SUBCKT <top>` (continuation lines joined)."""
    statements: List[str] = []
    for raw in cdl.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("+"):
            if not statements:
                continue
            statements[-1] += " " + line[1:].strip()
            continue
        statements.append(line)
    for statement in statements:
        match = re.match(r"(?i)^\.subckt\s+(\S+)(.*)$", statement)
        if match and match.group(1) == top:
            return match.group(2).split()
    raise SystemExit(f"error: {cdl} has no .SUBCKT {top}")


def merge_libraries(netlist: Path, libraries: List[Path], work: Path) -> Path:
    """Merge *netlist* and *libraries* into one reference netlist.

    Each chunk keeps its own `.SUBCKT` definitions; only its trailing
    top-level `.END` is dropped, and a single `.END` is appended.  The
    user's input files are never modified.
    """
    chunks: List[str] = []
    for path in [netlist, *libraries]:
        lines = path.read_text(errors="ignore").splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and re.match(r"(?i)^\s*\.end\s*$", lines[-1]):
            lines.pop()
        chunks.append("\n".join(lines).rstrip() + "\n")
    merged = work / "reference.cdl"
    merged.write_text("\n".join(chunks) + ".END\n")
    return merged


def scale_value(token: str, power: float) -> str:
    """Scale a SPICE numeric token by 10**power, preserving its spelling."""
    match = re.match(r"^([0-9.eE+\-]+)([a-zA-Z]*)$", token)
    if not match:
        return token
    value = float(match.group(1)) * (10.0 ** power)
    return f"{value:.9g}"


def parse_assignment(token: str) -> Optional[Tuple[str, str]]:
    match = re.match(r"(?i)^([a-z][a-z0-9_]*)\s*=\s*(\S+)$", token)
    if not match:
        return None
    return match.group(1).lower(), match.group(2)


def postprocess(
    spice: Path,
    out: Path,
    top: str,
    ports: List[str],
    tie_wells: bool,
    verbose: bool,
    resistor_prefix: str = "re_",
) -> Dict[str, object]:
    """Inject ports, convert um -> m, optionally tie bodies.

    Returns counters for the JSON summary.
    """
    statements: List[str] = []
    for raw in spice.read_text(errors="ignore").splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("+"):
            if statements:
                statements[-1] += " " + line[1:].strip()
            continue
        statements.append(line)

    pmos = 0
    nmos = 0
    diodes = 0
    resistors = 0
    other = 0
    output: List[str] = []
    for statement in statements:
        norm = statement.lstrip()
        low = norm.lower()
        if low.startswith(".subckt"):
            match = re.match(r"(?i)^\.subckt\s+(\S+)(.*)$", norm)
            name = match.group(1) if match else ""
            if name.lower() == top.lower():
                output.append(f".subckt {top} " + " ".join(ports))
            else:
                output.append(statement)
            continue
        # Resistor-subcircuit lines: X<name> <n1> <n2> <model> [w=... l=...].
        # `device rsubcircuit` makes ext2spice write an X call, but netgen
        # only applies series/parallel combination to primitive R devices.
        # Rewrite the call as R and convert um -> m, like MOS W/L.
        if low.startswith("x"):
            tokens = norm.split()
            model = None
            for token in tokens:
                if "=" in token:
                    break
                model = token
            if model and model.lower().startswith(resistor_prefix.lower()):
                resistors += 1
                rebuilt: List[str] = []
                for index, token in enumerate(tokens):
                    if index == 0:
                        rebuilt.append("R" + token[1:])
                        continue
                    assignment = parse_assignment(token)
                    if assignment is None:
                        rebuilt.append(token)
                        continue
                    key, value = assignment
                    if key in ("w", "l"):
                        rebuilt.append(f"{key}={scale_value(value, -6)}")
                    else:
                        rebuilt.append(token)
                output.append(" ".join(rebuilt))
                continue
            output.append(statement)
            continue
        # Diode lines: D<name> <anode> <cathode> <model> [area=... pj=...]
        # Magic writes area in um^2 and the junction perimeter in um; the
        # released CDL is in m^2 / m.
        if low.startswith("d"):
            tokens = norm.split()
            if len(tokens) >= 4:
                diodes += 1
                rebuilt: List[str] = []
                for token in tokens:
                    assignment = parse_assignment(token)
                    if assignment is None:
                        rebuilt.append(token)
                        continue
                    key, value = assignment
                    if key == "area":
                        rebuilt.append(f"{key}={scale_value(value, -12)}")
                    elif key in ("pj", "perim"):
                        rebuilt.append(f"{key}={scale_value(value, -6)}")
                    else:
                        rebuilt.append(token)
                output.append(" ".join(rebuilt))
                continue
            output.append(statement)
            continue
        if not (low.startswith("m") and not low.startswith(".model")):
            output.append(statement)
            continue

        tokens = norm.split()
        if len(tokens) < 6:
            output.append(statement)
            continue

        model = tokens[5]
        is_pmos = model.startswith("pm")
        is_nmos = model.startswith("nm")
        if is_pmos:
            pmos += 1
        elif is_nmos:
            nmos += 1
        else:
            other += 1

        # tokens: name drain gate source bulk model [key=value ...]
        # Magic writes W/L in um; the released CDL is in metres.
        rebuilt: List[str] = []
        for index, token in enumerate(tokens):
            assignment = parse_assignment(token)
            if assignment is None:
                rebuilt.append(token)
                continue
            key, value = assignment
            if key in ("w", "l"):
                rebuilt.append(f"{key}={scale_value(value, -6)}")
            elif key in ("ad", "as"):
                rebuilt.append(f"{key}={scale_value(value, -12)}")
            elif key in ("pd", "ps"):
                rebuilt.append(f"{key}={scale_value(value, -6)}")
            elif key in ("m", "mult", "nf"):
                rebuilt.append(f"{key}={value}")
            else:
                rebuilt.append(token)

        if tie_wells and len(rebuilt) >= 5:
            if is_pmos:
                rebuilt[4] = "VDD"
            elif is_nmos:
                rebuilt[4] = "VSS"

        output.append(" ".join(rebuilt))

    out.write_text("\n".join(output) + "\n")
    log(
        verbose,
        f"post-processed {out} ({pmos} PMOS, {nmos} NMOS, {diodes} diodes, "
        f"{resistors} resistors, {other} other)",
    )
    return {
        "pmos": pmos,
        "nmos": nmos,
        "diodes": diodes,
        "resistors": resistors,
        "other": other,
    }


def magic_extract(
    magic: str,
    gds: Path,
    top: str,
    work: Path,
    rcfile: Path,
    verbose: bool,
) -> Path:
    spice = work / f"{top}.extracted.spice"
    script = work / "extract.tcl"
    script.write_text(
        "\n".join(
            [
                "drc off",
                f"gds read {{{gds.resolve()}}}",
                f"load {top}",
                "select top cell",
                "extract do local",
                "extract all",
                "ext2spice lvs",
                f"ext2spice -o {{{spice.resolve()}}}",
                "quit -noprompt",
                "",
            ]
        )
    )
    proceeded = run(
        [magic, "-dnull", "-noconsole", "-rcfile", str(rcfile.resolve()), str(script)],
        cwd=work,
    )
    combined = proceeded.stdout + proceeded.stderr
    if proceeded.returncode != 0:
        raise SystemExit(
            "error: magic exited with "
            f"{proceeded.returncode}\n{combined[-4000:]}"
        )
    if not spice.is_file() or spice.stat().st_size == 0:
        raise SystemExit(f"error: magic produced no netlist\n{combined[-4000:]}")
    if re.search(r"(?i)could not find (cell|file)", combined):
        raise SystemExit(f"error: magic failed to load {top}\n{combined[-4000:]}")
    log(verbose, f"magic extracted {top} -> {spice}")
    return spice


def compare(
    netgen: str,
    layout_spice: Path,
    top: str,
    netlist: Path,
    setup: Path,
    report: Path,
    verbose: bool,
) -> Tuple[int, str, Dict[str, object]]:
    proceeded = run(
        [
            netgen,
            "-batch",
            "lvs",
            f"{layout_spice.resolve()} {top}",
            f"{netlist.resolve()} {top}",
            str(setup.resolve()),
            str(report.resolve()),
        ],
        cwd=layout_spice.parent,
    )
    combined = proceeded.stdout + proceeded.stderr
    lower = combined.lower()

    topology_match = bool(re.search(r"circuits? match uniqu", lower))
    topology_mismatch = bool(
        re.search(r"(netlists?|circuits?) do(es)? not match", lower)
        or "mismatch" in lower
    )
    property_errors = "property errors were found" in lower or "with property errors" in lower
    failed = proceeded.returncode != 0 or "failed to read" in lower or "error reading" in lower

    if property_errors and topology_match:
        status = 1
        verdict = "property-errors"
    elif topology_match and not topology_mismatch and not failed:
        status = 0
        verdict = "match"
    else:
        status = 2
        verdict = "mismatch" if topology_mismatch else "error"

    if verbose or status != 0:
        for line in combined.splitlines():
            if re.search(
                r"final result|match|mismatch|property error|error|warning",
                line,
                re.I,
            ):
                print(line, file=sys.stderr)

    summary = {
        "verdict": verdict,
        "topology_match": topology_match,
        "property_errors": property_errors,
        "returncode": proceeded.returncode,
    }
    return status, combined, summary


def equate_ground_nets(text: str, prefix: str = "VSS", canonical: str = "VSS") -> str:
    """Collapse every ground-domain net in *text* onto one canonical net.

    The Calibre deck does this with `LVS GROUND NAME "?VSS?" "?GND?"`: all
    VSS-named nets are ground and are therefore one node.  The Magic
    extraction needs the same convention because a p+ substrate tap is a
    physical connection: when a cell taps two grounds (e.g. VSS1 and VSSIO)
    into the same p-substrate, a flat extraction merges them.  The released
    CDL keeps the names separate, so both sides must collapse them the same
    way before the compare.

    Only net tokens on device/instance lines are rewritten.  `.SUBCKT` port
    lists are left alone, so the port names survive; the renamed devices
    simply connect to the `VSS` port (the other ground ports become
    disconnected on both sides and still match).  Continuation lines are
    joined first so a statement is rewritten as a unit.
    """
    if not prefix:
        return text
    statements: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("+"):
            if statements:
                statements[-1] += " " + line[1:].strip()
            continue
        statements.append(line)

    keep = (
        ".subckt",
        ".ends",
        ".model",
        ".param",
        ".global",
        ".include",
        ".lib",
        ".temp",
        ".options",
    )
    lowered = prefix.lower()
    rewritten: List[str] = []
    for statement in statements:
        stripped = statement.strip()
        low = stripped.lower()
        if low.startswith(keep) or stripped.startswith("*") or stripped.startswith("."):
            rewritten.append(stripped)
            continue
        tokens = stripped.split()
        out: List[str] = []
        for token in tokens:
            if "=" in token:
                out.append(token)
                continue
            base = token.strip("\"'")
            if base.lower().startswith(lowered):
                out.append(canonical)
            else:
                out.append(token)
        rewritten.append(" ".join(out))
    return "\n".join(rewritten) + "\n"


def convert_resistor_instances(text: str, prefix: str = "re_") -> str:
    """Rewrite `X... <re_*>` subcircuit calls as primitive `R` devices.

    The released IO CDL models a folded poly resistor as an empty 2-terminal
    subcircuit (`re_ppo_sab_2t`) with W/L parameters.  Magic extracts each
    straight segment as an `rsubcircuit`, which ext2spice writes as an `X`
    call too.  Netgen only applies its series/parallel combination to
    primitive resistor classes, so both sides are rewritten to `R`; the
    layout's four series segments then merge into the CDL's single folded
    W/L.  Property names stay as written (netgen matches them
    case-insensitively) and the reference values are already in SI units.
    """
    if not prefix:
        return text
    statements: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("+"):
            if statements:
                statements[-1] += " " + line[1:].strip()
            continue
        statements.append(line)

    lowered = prefix.lower()
    rewritten: List[str] = []
    i = 0
    while i < len(statements):
        stripped = statements[i].strip()
        match = re.match(r"(?i)^\.subckt\s+(\S+)", stripped)
        if match and match.group(1).lower().startswith(lowered):
            # The reference models a resistor as an empty 2-terminal subckt.
            # Once every X call is rewritten to R, that definition conflicts
            # with the primitive R class (netgen sees two classes with the
            # same name and different pins), so an empty definition is dropped.
            j = i + 1
            body: List[str] = []
            while j < len(statements) and not statements[j].strip().lower().startswith(
                ".ends"
            ):
                body.append(statements[j])
                j += 1
            if not body:
                i = j + 1
                continue
        tokens = stripped.split()
        model = None
        if tokens and tokens[0][:1].upper() == "X":
            for token in tokens[1:]:
                if "=" in token:
                    break
                model = token
        if (
            model is not None
            and model.lower().startswith(lowered)
            and len(tokens[0]) > 1
        ):
            tokens[0] = "R" + tokens[0][1:]
            rewritten.append(" ".join(tokens))
        else:
            rewritten.append(stripped)
        i += 1
    return "\n".join(rewritten) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Magic + netgen LVS for the ICsprout55 PDK.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Exit status:", 1)[1],
    )
    parser.add_argument("--layout", required=True, type=Path, help="input GDS")
    parser.add_argument("--top", required=True, help="top cell name")
    parser.add_argument(
        "--netlist",
        type=Path,
        help="reference CDL/SPICE; default: search the PDK libs.ref",
    )
    parser.add_argument(
        "--library",
        type=Path,
        action="append",
        default=[],
        help="extra CDL/SPICE library netlist (repeatable) merged into the reference",
    )
    parser.add_argument(
        "--mode",
        choices=("stdcell", "macro"),
        default="stdcell",
        help="stdcell ties PMOS bulk to VDD and NMOS bulk to VSS (default)",
    )
    parser.add_argument(
        "--ground-prefix",
        default="VSS",
        help="treat every net starting with this prefix as one ground "
        "(the Calibre deck's LVS GROUND NAME '?VSS?'); empty disables",
    )
    parser.add_argument(
        "--resistor-prefix",
        default="re_",
        help="treat X instances whose model starts with this prefix as "
        "primitive resistors so netgen can combine the folded segments "
        "(default re_; empty disables)",
    )
    parser.add_argument("--report", type=Path, help="netgen comparison report")
    parser.add_argument("--json", type=Path, help="JSON summary path")
    parser.add_argument("--magicrc", type=Path, default=DEFAULT_MAGICRC)
    parser.add_argument("--setup", type=Path, default=DEFAULT_SETUP)
    parser.add_argument(
        "--no-well-ties",
        action="store_true",
        help="same as --mode macro",
    )
    parser.add_argument("--workdir", type=Path, help="scratch directory")
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="keep the scratch directory even on success",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    magic = shutil.which("magic")
    netgen = shutil.which("netgen")
    if magic is None:
        print("error: magic not found on PATH", file=sys.stderr)
        return 2
    if netgen is None:
        print("error: netgen not found on PATH", file=sys.stderr)
        return 2

    layout = args.layout.resolve()
    if not layout.is_file():
        print(f"error: layout not found: {layout}", file=sys.stderr)
        return 2
    if not args.magicrc.is_file():
        print(f"error: magicrc not found: {args.magicrc}", file=sys.stderr)
        return 2
    if not args.setup.is_file():
        print(f"error: netgen setup not found: {args.setup}", file=sys.stderr)
        return 2

    netlist = (args.netlist or find_netlist(args.top, layout)).resolve()
    libraries = [path.resolve() for path in args.library]
    for path in libraries:
        if not path.is_file():
            print(f"error: library netlist not found: {path}", file=sys.stderr)
            return 2
    report = (args.report or Path.cwd() / f"{args.top}.lvs.rpt").resolve()
    summary_path = (args.json or report.with_suffix(".json")).resolve()
    if report in (layout, netlist, *libraries) or summary_path in (layout, netlist, *libraries):
        print("error: output paths must not collide with the inputs", file=sys.stderr)
        return 2
    if args.workdir:
        work = args.workdir.resolve()
        work.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        tmp_root = Path("/tmp/opencode")
        base = tmp_root if tmp_root.is_dir() else None
        work = Path(tempfile.mkdtemp(prefix=f"lvs_{args.top}_", dir=str(base) if base else None))
        cleanup = True

    tie_wells = not args.no_well_ties and args.mode == "stdcell"
    status = 2
    summary: Dict[str, object] = {
        "cell": args.top,
        "layout": str(layout),
        "netlist": str(netlist),
        "libraries": [str(path) for path in libraries],
        "mode": "macro" if args.no_well_ties else args.mode,
        "well_ties": tie_wells,
        "magic": magic,
        "netgen": netgen,
        "report": str(report),
        "workdir": str(work),
    }

    try:
        ports = cdl_ports(netlist, args.top)
        log(args.verbose, f"ports: {' '.join(ports)}")

        extracted = magic_extract(
            magic, layout, args.top, work, args.magicrc, args.verbose
        )
        prepared = work / f"{args.top}.lvs.spice"
        counters = postprocess(
            extracted,
            prepared,
            args.top,
            ports,
            tie_wells,
            args.verbose,
            args.resistor_prefix,
        )
        summary.update(counters)

        reference = merge_libraries(netlist, libraries, work)
        if libraries:
            summary["reference"] = str(reference)
            log(args.verbose, f"merged reference netlist: {reference}")

        reference.write_text(
            convert_resistor_instances(
                reference.read_text(errors="ignore"), args.resistor_prefix
            )
        )
        summary["resistor_prefix"] = args.resistor_prefix

        if args.ground_prefix:
            prepared.write_text(
                equate_ground_nets(
                    prepared.read_text(errors="ignore"), args.ground_prefix
                )
            )
            reference.write_text(
                equate_ground_nets(
                    reference.read_text(errors="ignore"), args.ground_prefix
                )
            )
            log(
                args.verbose,
                f"equated ground nets starting with {args.ground_prefix!r} to VSS",
            )
        summary["ground_prefix"] = args.ground_prefix

        report.parent.mkdir(parents=True, exist_ok=True)
        status, output, result = compare(
            netgen, prepared, args.top, reference, args.setup, report, args.verbose
        )
        summary.update(result)
        summary["status"] = status

        (work / "netgen.log").write_text(output)
    except SystemExit as exc:
        summary["status"] = 2
        summary["error"] = str(exc)
        print(str(exc), file=sys.stderr)
    finally:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        if cleanup and not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)

    print(f"{args.top}: {summary.get('verdict', 'error')}")
    if summary.get("property_errors"):
        print(f"  see {report}")
    if status == 2 and "error" not in summary:
        print(f"  see {report}")
    return status


if __name__ == "__main__":
    sys.exit(main())
