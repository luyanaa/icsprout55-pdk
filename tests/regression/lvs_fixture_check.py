#!/usr/bin/env python3
"""KLayout LVS extraction and compare-verdict fixtures for the ICS55 rule deck.

These verify observable extraction, matching, and mismatch behavior—not
Calibre equivalence. Run with KLayout directly or through the public
LibreLane nix shell.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from nix_shell import command as nix_shell_command

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DECK = ROOT / "libs.tech" / "lvs" / "ics55.lvs"
RUNNER = ROOT / "libs.tech" / "lvs" / "run_lvs.py"
GENERATOR = HERE / "make_lvs_fixtures.rb"
ALL_MODELS = {
    "NM1P2_SVT_LP", "NM1P2_LVT_LP", "NM1P2_HVT_LP",
    "PM1P2_SVT_LP", "PM1P2_LVT_LP", "PM1P2_HVT_LP",
    "NM3P3_LP", "PM3P3_LP", "RE_PPO_SAB_2T", "RE_M1_2T",
    "RE_M2_2T", "RE_M3_2T", "RE_M4_2T", "RE_M5_2T",
    "RE_TM1_2T", "RE_TM2_2T", "RE_ALPA_2T", "RE_M1_3T",
    "RE_M2_3T", "RE_M3_3T", "RE_M4_3T", "RE_M5_3T",
    "RE_TM1_3T", "RE_TM2_3T", "RE_ALPA_3T", "DIO_3P3_PP_NW_LP",
    "VAR1P2_NPD_NW_LP", "VAR2P5_NPD_NW_LP",
    "VAR1P2_NPD_NW_DNW_LP", "VAR2P5_NPD_NW_DNW_LP",
    "ICS55_RF_NMOS_SVT_5T", "ICS55_RF_NMOS_LVT_5T", "ICS55_RF_NMOS_HVT_5T",
    "ICS55_RF_NMOS_SVT_6T", "ICS55_RF_NMOS_LVT_6T", "ICS55_RF_NMOS_HVT_6T",
    "ICS55_RF_PMOS_SVT_5T", "ICS55_RF_PMOS_LVT_5T", "ICS55_RF_PMOS_HVT_5T",
    "ICS55_IND", "MOM_2T", "MOM_3T",
}

# Exact extracted classes are asserted, including absence of competing selectors.
FIXTURES: dict[str, dict[str, Any]] = {
    "core_svt_n": {"models": {"NM1P2_SVT_LP": 1}},
    "core_lvt_n_ctbar": {"models": {"NM1P2_LVT_LP": 1}},
    "core_hvt_p": {"models": {"PM1P2_HVT_LP": 1}},
    "io_tgox_n": {"models": {"NM3P3_LP": 1}},
    "io_tgox_p": {"models": {"PM3P3_LP": 1}},
    "dgo_only_n": {"models": {}},
    "tgox_dgox_n": {"models": {}},
    "tgox_esdioe_n": {"models": {"NM3P3_LP": 1}},
    "poly_resistor": {
        "models": {"RE_PPO_SAB_2T": 1}, "distinct_resistor_terms": 1, "ports": 2,
        # 1.0 x 0.2 um drawn body: 725.7 ohm/sq * 5 squares.  Guards against
        # wiring the SAB device to the non-SAB rsh_rppo=10.252 (51.26 ohm).
        "resistance": 3628.5, "resistance_rtol": 0.01,
    },
    "metal_resistor": {"models": {"RE_M1_2T": 1}, "distinct_resistor_terms": 1, "ports": 2},
    "diode_marker": {"models": {"DIO_3P3_PP_NW_LP": 1}},
    "esd_marker_only": {"models": {}},
    "varactor_1p2": {"models": {"VAR1P2_NPD_NW_LP": 1}},
    "varactor_2p5": {"models": {"VAR2P5_NPD_NW_LP": 1}},
    "varactor_dnw_1p2": {"models": {"VAR1P2_NPD_NW_DNW_LP": 1}},
    "varactor_dnw_2p5": {"models": {"VAR2P5_NPD_NW_DNW_LP": 1}},
    "rf_nmos_5t": {"models": {"ICS55_RF_NMOS_SVT_5T": 1}},
    "rf_nmos_6t": {"models": {"ICS55_RF_NMOS_SVT_6T": 1}},
    "rf_pmos_5t": {"models": {"ICS55_RF_PMOS_SVT_5T": 1}},
    # 4T RF MOS has no DNW and no RF marker: the drawn device is the plain
    # core MOS, which is what the 4T wrapper aliases to.
    "rf_nmos_4t": {"models": {"NM1P2_SVT_LP": 1}},
    "inductor_1tm_alpa": {
        "models": {"ICS55_IND": 1}, "ports": 2, "inductor_terminal_match": "distinct",
    },
    # Negative controls: a cut TM2 lead leaves no winding, and an RDL strap
    # between the terminal pads collapses PLUS and MINUS onto one net.
    "inductor_1tm_alpa_open": {"models": {}, "ports": 2},
    "inductor_1tm_alpa_short": {
        "models": {"ICS55_IND": 1}, "ports": 2, "inductor_terminal_match": "same",
    },
    # 3 fingers x 2.0 um on M2-M4: LF = length - SPACE, NF = finger count.
    "mom_2t": {
        "models": {"MOM_2T": 1}, "ports": 2, "mom_terminal_match": "distinct",
        "mom_params": {"LF": 1.9, "NF": 3, "BM": 2, "TM": 4, "MR": 1},
    },
    "mom_3t": {
        "models": {"MOM_3T": 1}, "ports": 3, "mom_terminal_match": "distinct",
        "mom_params": {"LF": 1.9, "NF": 3, "BM": 2, "TM": 4, "MR": 1, "SHIELDING": 1},
    },
    # Negative controls: a broken PLUS bus leaves no complete device, and a
    # PLUS/MINUS strap collapses both capacitor terminals onto one net.
    "mom_2t_open": {"models": {}, "ports": 2},
    "mom_2t_short": {
        "models": {"MOM_2T": 1}, "ports": 2, "mom_terminal_match": "same",
    },
    "pad_m1_m5_bar": {"models": {"NM1P2_SVT_LP": 1}, "stack": "m1_m5", "ports": 1, "port_name": "PAD"},
    "pad_t4_bar": {"models": {"NM1P2_SVT_LP": 1}, "stack": "t4", "ports": 1, "port_name": "PAD"},
    "bulk_alias": {"models": {"NM1P2_SVT_LP": 1}, "bulk_aliases": "ground=gnd power=vdd"},
    "strict_flat_parent": {"models": {"NM1P2_SVT_LP": 1}, "ports": 3},
}


# ERC smoke cases.  well-tied fixtures exercise the standard-cell convention;
# the physical-tap cases run with no_well_ties so the contacted taps are real.
# "checks" are the ERC SELECT CHECK set and drive ICS55_ERC; "diagnostics" are
# the unselected bare PATHCHK statements and must never affect the verdict.
ERC_SMOKE: dict[str, dict[str, Any]] = {
    "erc_clean": {"no_well_ties": False, "verdict": "PASS",
                  "checks": {}, "diagnostics": {}},
    "erc_mn2pg": {"no_well_ties": False, "verdict": "FAIL",
                  "checks": {"erc_mn2pg": 1}, "diagnostics": {}},
    "erc_pathchk_ground": {"no_well_ties": False, "verdict": "PASS",
                           "checks": {}, "diagnostics": {"erc_pathchk_ground_not_power": 1}},
    "erc_pathchk_power": {"no_well_ties": False, "verdict": "PASS",
                          "checks": {}, "diagnostics": {"erc_pathchk_power_not_ground": 1}},
    "erc_unlabeled": {"gds": "core_svt_n", "no_well_ties": False, "verdict": "FAIL",
                      "checks": {"erc_pathcheck_bad": 3},
                      "diagnostics": {"erc_pathchk_unlabeled": 3}},
    "erc_bad_ptap": {"no_well_ties": True, "verdict": "FAIL",
                     "checks": {"erc_pTap_to_power": 1,
                                "erc_pWell_not_to_ground": 1,
                                "erc_ptap_outside_dnw_non_ground": 1},
                     "diagnostics": {}},
    "erc_bad_ntap": {"no_well_ties": True, "verdict": "FAIL",
                     "checks": {"erc_nTap_to_ground": 1,
                                "erc_nWell_not_to_power": 1},
                     "diagnostics": {}},
}

ERC_CHECK_COUNT = 10
ERC_DIAGNOSTIC_COUNT = 3


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_klayout(args: argparse.Namespace) -> tuple[str, str] | None:
    if args.klayout:
        return ("bin", args.klayout) if shutil.which(args.klayout) else None
    if args.librelane and Path(args.librelane).exists() and shutil.which("nix-shell"):
        return ("nix", str(args.librelane))
    if shutil.which("klayout"):
        return ("bin", "klayout")
    return None


def invoke_klayout(
    kind: str, exe: str, script: Path, extra: list[str]
) -> subprocess.CompletedProcess[str]:
    base = ["-b", "-r", str(script)] + extra
    command = nix_shell_command(exe, ["klayout"] + base) if kind == "nix" else [exe] + base
    return subprocess.run(command, capture_output=True, text=True, timeout=120)


def model_counts(netlist: Path) -> tuple[collections.Counter[str], dict[str, list[str]]]:
    counts: collections.Counter[str] = collections.Counter()
    device_lines: dict[str, list[str]] = {}
    for line in netlist.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("*", ".", "+")):
            continue
        fields = stripped.replace(",", " ").split()
        if not fields or fields[0][0].upper() not in {"M", "R", "D", "C", "L", "X"}:
            continue
        for index, field in enumerate(fields):
            model = field.upper()
            if model in ALL_MODELS:
                counts[model] += 1
                device_lines.setdefault(model, []).append(" ".join(fields[:index + 1]))
                break
    return counts, device_lines


def run_case(
    args: argparse.Namespace,
    kind: str,
    exe: str,
    name: str,
    gds: Path,
    out: Path,
) -> dict[str, Any]:
    expected = FIXTURES[name]
    case_dir = out / "cases" / name
    case_dir.mkdir(parents=True, exist_ok=True)
    netlist = case_dir / "extracted.cir"
    report = case_dir / "extraction.lvsdb"
    netlist.unlink(missing_ok=True)
    report.unlink(missing_ok=True)
    extra = [
        "-rd", f"input={gds}", "-rd", "top=TOP", "-rd", "net_only=true",
        "-rd", "metal_stack=auto", "-rd", f"target_netlist={netlist}",
        "-rd", f"report={report}",
    ]
    schematic = None
    if name == "bulk_alias":
        schematic = case_dir / "bulk_alias.cdl"
        schematic.write_text(".SUBCKT TOP vdd gnd A\n.ENDS TOP\n")
        extra.extend(["-rd", f"schematic={schematic}"])

    try:
        run = invoke_klayout(kind, exe, DECK, extra)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"fixture": name, "status": "FAIL", "error": str(error)}
    combined = run.stdout + "\n" + run.stderr
    result: dict[str, Any] = {
        "fixture": name,
        "status": "PASS",
        "returncode": run.returncode,
        "gds_sha256": sha256(gds),
        "netlist": str(netlist),
        "output": combined.strip(),
    }
    issues: list[str] = []
    if run.returncode != 0:
        issues.append(f"KLayout exited {run.returncode}")
    actual: collections.Counter[str] = collections.Counter()
    device_lines: dict[str, list[str]] = {}
    if not netlist.is_file():
        issues.append("target extraction netlist was not written")
    else:
        actual, device_lines = model_counts(netlist)
    expected_counts = collections.Counter(expected["models"])
    observed = collections.Counter({model: actual[model] for model in ALL_MODELS if actual[model]})
    result["models"] = dict(sorted(observed.items()))
    if observed != expected_counts:
        issues.append(f"device model counts expected {dict(expected_counts)}, observed {dict(observed)}")

    port_match = re.search(r"ports=(\d+)", combined)
    if "ports" in expected:
        if not port_match:
            issues.append("port summary missing from extraction log")
        else:
            result["ports"] = int(port_match.group(1))
            if result["ports"] != expected["ports"]:
                issues.append(f"expected {expected['ports']} ports, observed {result['ports']}")
    if "port_name" in expected:
        subckt = next((line for line in netlist.read_text(errors="replace").splitlines()
                       if line.strip().upper().startswith(".SUBCKT TOP")), "") if netlist.is_file() else ""
        result["subckt"] = subckt.strip()
        if expected["port_name"].upper() not in subckt.upper().split():
            issues.append(f"{expected['port_name']} absent from extracted top-level pins")
    if "stack" in expected:
        expected_stack = f"Metal stack: {expected['stack']} (requested auto)"
        if expected_stack not in combined:
            issues.append(f"expected stack selection log {expected_stack!r}")
    if "bulk_aliases" in expected:
        expected_aliases = f"Bulk aliases: {expected['bulk_aliases']}"
        if expected_aliases not in combined:
            issues.append(f"expected schematic-derived aliases {expected_aliases!r}")
    if expected.get("distinct_resistor_terms"):
        model = next(iter(expected_counts))
        lines = [line for line in netlist.read_text(errors="replace").splitlines()
                 if model in line.upper() and line.split() and line.split()[0][0].upper() == "R"] if netlist.is_file() else []
        result["resistor_lines"] = lines
        if len(lines) != expected["distinct_resistor_terms"]:
            issues.append(f"expected {expected['distinct_resistor_terms']} resistor device line(s), observed {len(lines)}")
        for line in lines:
            fields = line.replace(",", " ").split()
            model_index = next((i for i, field in enumerate(fields) if field.upper() == model), -1)
            if model_index < 3 or fields[1] == fields[2]:
                issues.append(f"resistor endpoints are not distinct in extracted device: {line}")
            if "resistance" in expected:
                try:
                    value = float(fields[model_index - 1])
                except (ValueError, IndexError):
                    issues.append(f"resistor value is not numeric in extracted device: {line}")
                    continue
                result["resistance"] = value
                expected_value = expected["resistance"]
                rtol = expected.get("resistance_rtol", 0.01)
                if abs(value - expected_value) > abs(expected_value) * rtol:
                    issues.append(
                        f"resistor value expected {expected_value:g} ohm "
                        f"(+/-{rtol:.1%}), observed {value:g} ohm"
                    )

    if "inductor_terminal_match" in expected:
        model = next(iter(expected_counts))
        lines = [line for line in netlist.read_text(errors="replace").splitlines()
                 if line.split() and line.split()[0][0].upper() == "X"
                 and any(field.upper() == model for field in line.replace(",", " ").split())] if netlist.is_file() else []
        result["inductor_lines"] = lines
        if len(lines) != expected["models"][model]:
            issues.append(
                f"expected {expected['models'][model]} {model} device line(s), observed {len(lines)}"
            )
        for line in lines:
            fields = line.replace(",", " ").split()
            model_index = next((i for i, field in enumerate(fields) if field.upper() == model), -1)
            terminals = fields[1:model_index]
            if expected["inductor_terminal_match"] == "distinct" and len(set(terminals)) != len(terminals):
                issues.append(f"inductor terminals are shorted in extracted device: {line}")
            if expected["inductor_terminal_match"] == "same" and len(set(terminals)) != 1:
                issues.append(f"expected a shorted inductor terminal pair: {line}")

    if "mom_params" in expected:
        model = next(iter(expected_counts))
        lines = [line for line in netlist.read_text(errors="replace").splitlines()
                 if line.split() and line.split()[0][0].upper() == "X"
                 and any(field.upper() == model for field in line.replace(",", " ").split())] if netlist.is_file() else []
        result["mom_lines"] = lines
        if len(lines) != expected["models"][model]:
            issues.append(
                f"expected {expected['models'][model]} {model} device line(s), observed {len(lines)}"
            )
        for line in lines:
            fields = line.replace(",", " ").split()
            model_index = next((i for i, field in enumerate(fields) if field.upper() == model), -1)
            terminals = fields[1:model_index]
            if expected.get("mom_terminal_match") == "distinct" and len(set(terminals)) != len(terminals):
                issues.append(f"capacitor terminals are shorted in extracted device: {line}")
            if expected.get("mom_terminal_match") == "same" and len(set(terminals)) != 1:
                issues.append(f"expected a shorted capacitor terminal pair: {line}")
            params = dict(re.findall(r"([A-Za-z_]\w*)=([-+0-9.eE]+)", line))
            result["mom_params"] = params
            for key, want in expected["mom_params"].items():
                try:
                    got = float(params[key])
                except (KeyError, ValueError):
                    issues.append(f"MOM parameter {key} missing from extracted device: {line}")
                    continue
                if abs(got - want) > 1e-6 * max(1.0, abs(want)):
                    issues.append(f"MOM parameter {key} expected {want:g}, observed {got:g}")

    if issues:
        result["status"] = "FAIL"
        result["issues"] = issues
    return result


def run_compare_verdict_smoke(
    kind: str, exe: str, gds: Path, out: Path
) -> dict[str, Any]:
    case_dir = out / "verdict_smoke"
    case_dir.mkdir(parents=True, exist_ok=True)
    source = case_dir / "matching_reference.cir"
    source_report = case_dir / "matching_extract.lvsdb"
    source.unlink(missing_ok=True)
    source_report.unlink(missing_ok=True)
    try:
        extraction = invoke_klayout(kind, exe, DECK, [
            "-rd", f"input={gds}", "-rd", "top=TOP", "-rd", "net_only=true",
            "-rd", f"target_netlist={source}", "-rd", f"report={source_report}",
        ])
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "fixture": "compare_verdicts",
            "status": "FAIL",
            "error": str(error),
            "issues": ["matching reference extraction did not complete"],
        }
    if extraction.returncode != 0 or not source.is_file():
        output = (extraction.stdout + "\n" + extraction.stderr).strip()
        return {
            "fixture": "compare_verdicts",
            "status": "FAIL",
            "output": output,
            "issues": ["could not produce a fresh matching reference netlist"],
        }

    def run_wrapper(netlist: Path, target: Path, report: Path) -> subprocess.CompletedProcess[str]:
        command = [
            "python3" if kind == "nix" else sys.executable,
            str(RUNNER),
            "--layout", str(gds),
            "--top", "TOP",
            "--netlist", str(netlist),
            "--target-netlist", str(target),
            "--report", str(report),
            "--no-erc",
        ]
        if kind == "nix":
            command = nix_shell_command(exe, command)
        else:
            command += ["--klayout", exe]
        return subprocess.run(command, capture_output=True, text=True, timeout=180)

    mismatch = case_dir / "mismatch.cdl"
    # A device-free TOP is dropped by the schematic purge, which hides the
    # comparer behind a "no schematic counterpart" error.  Perturb an extracted
    # MOS width instead so the mismatch reaches the netlist comparer.
    mismatch_text, substitutions = re.subn(
        r"W=([0-9.]+)[uU]",
        lambda match: f"W={float(match.group(1)) * 1.25:.3f}U",
        source.read_text(),
        count=1,
    )
    if not substitutions:
        mismatch_text = ".SUBCKT TOP X Y Z\nM1 X Y Z Z NM1P2_SVT_LP W=0.7U L=0.1U\n.ENDS TOP\n"
    mismatch.write_text(mismatch_text)
    matching_target = case_dir / "matching_extracted.cir"
    matching_report = case_dir / "matching.lvsdb"
    mismatch_target = case_dir / "mismatch_extracted.cir"
    mismatch_report = case_dir / "mismatch.lvsdb"
    for path in (matching_target, matching_report, mismatch_target, mismatch_report):
        path.unlink(missing_ok=True)
    try:
        matching_run = run_wrapper(
            Path(os.path.relpath(source, Path.cwd())),
            Path(os.path.relpath(matching_target, Path.cwd())),
            Path(os.path.relpath(matching_report, Path.cwd())),
        )
        mismatch_run = run_wrapper(
            Path(os.path.relpath(mismatch, Path.cwd())),
            Path(os.path.relpath(mismatch_target, Path.cwd())),
            Path(os.path.relpath(mismatch_report, Path.cwd())),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "fixture": "compare_verdicts",
            "status": "FAIL",
            "error": str(error),
            "issues": ["LVS wrapper compare smoke did not complete"],
        }

    matching_output = (matching_run.stdout + "\n" + matching_run.stderr).strip()
    mismatch_output = (mismatch_run.stdout + "\n" + mismatch_run.stderr).strip()
    matching_passed = (
        matching_run.returncode == 0
        and matching_target.is_file()
        and matching_report.is_file()
        and "ICS55_LVS_COMPARE=PASS" in matching_output
    )
    mismatch_rejected = (
        mismatch_run.returncode != 0
        and mismatch_target.is_file()
        and mismatch_report.is_file()
        and "ICS55_LVS_COMPARE=FAIL" in mismatch_output
        and "ERROR: netlists do not match." in mismatch_output
    )
    issues = []
    if not matching_passed:
        issues.append("matching extracted/reference netlists did not produce a pass verdict")
    if not mismatch_rejected:
        issues.append("mismatching source netlist did not produce a fail-closed verdict")
    return {
        "fixture": "compare_verdicts",
        "status": "PASS" if not issues else "FAIL",
        "matching_returncode": matching_run.returncode,
        "mismatch_returncode": mismatch_run.returncode,
        "matching_output": matching_output,
        "mismatch_output": mismatch_output,
        "output": f"MATCH:\n{matching_output}\nMISMATCH:\n{mismatch_output}",
        "issues": issues,
    }


def run_strict_flat_mode_smoke(kind: str, exe: str, gds: Path, out: Path) -> dict[str, Any]:
    """Strict default must compare a child layout against the flat source."""
    source = ".SUBCKT TOP D G S\nM1 D G S S nm1p2_svt_lp W=0.6u L=0.1u\n.ENDS TOP\n"
    cases = []
    for name, mode, reference, expected in (
        ("default", None, source, True),
        ("explicit_flat", "flat", source, True),
        ("explicit_deep", "deep", source, False),
        ("width_mismatch", None, source.replace("W=0.6u", "W=0.61u"), False),
    ):
        directory = out / "strict_flat_modes" / name
        directory.mkdir(parents=True, exist_ok=True)
        schematic, target, report = (directory / name for name in ("reference.sp", "extracted.cir", "lvs.lvsdb"))
        schematic.write_text(reference)
        target.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
        extra = [
            "-rd", f"input={gds}", "-rd", "top=TOP",
            "-rd", f"schematic={schematic}", "-rd", f"target_netlist={target}",
            "-rd", f"report={report}", "-rd", "strict_topology=true",
            "-rd", "no_well_ties=true", "-rd", "no_erc=true",
        ]
        if mode is not None:
            extra.extend(["-rd", f"run_mode={mode}"])
        try:
            run = invoke_klayout(kind, exe, DECK, extra)
            output = (run.stdout + "\n" + run.stderr).strip()
            artifacts_written = target.is_file() and report.is_file()
            passed = (run.returncode == 0 and artifacts_written
                      and "ICS55_LVS_COMPARE=PASS" in output
                      and "ICS55_LVS_COMPARE=FAIL" not in output)
            rejected = (artifacts_written and "ICS55_LVS_COMPARE=FAIL" in output
                        and "ICS55_LVS_COMPARE=PASS" not in output)
            cases.append({
                "name": name, "status": "PASS" if (passed if expected else rejected) else "FAIL",
                "expected_match": expected, "native_matched": passed, "returncode": run.returncode,
                "gds_sha256": sha256(gds), "reference": str(schematic),
                "target_netlist": str(target), "report": str(report), "output": output,
            })
        except (OSError, subprocess.TimeoutExpired) as error:
            cases.append({"name": name, "status": "FAIL", "error": str(error)})
    return {
        "fixture": "strict_flat_modes",
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "cases": cases,
    }


def run_erc_smoke(
    kind: str, exe: str, fixture_dir: Path, out: Path
) -> dict[str, Any]:
    """Clean and violating layouts must produce exact ERC check counts."""
    check_pattern = re.compile(r"^ERC: (?:diagnostic )?(\w+): (\d+) violation\(s\)$", re.MULTILINE)
    verdict_pattern = re.compile(r"^ICS55_ERC=(PASS|FAIL)$", re.MULTILINE)
    summary_pattern = re.compile(
        r"^ICS55_ERC_SUMMARY checks=(\d+) selected_violations=(\d+) "
        r"diagnostics=(\d+) diagnostic_violations=(\d+)$",
        re.MULTILINE,
    )
    cases = []
    for name, expected in ERC_SMOKE.items():
        directory = out / "erc_smoke" / name
        directory.mkdir(parents=True, exist_ok=True)
        gds = fixture_dir / f"{expected.get('gds', name)}.gds"
        reference = directory / "reference.cir"
        reference_report = directory / "reference.lvsdb"
        target = directory / "extracted.cir"
        report = directory / "lvs.lvsdb"
        reference.unlink(missing_ok=True)
        reference_report.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
        well_flag = ["-rd", "no_well_ties=true"] if expected["no_well_ties"] else []
        try:
            extraction = invoke_klayout(kind, exe, DECK, [
                "-rd", f"input={gds}", "-rd", "top=TOP", "-rd", "net_only=true",
                *well_flag,
                "-rd", f"target_netlist={reference}",
                "-rd", f"report={reference_report}",
            ])
            if extraction.returncode != 0 or not reference.is_file():
                output = (extraction.stdout + "\n" + extraction.stderr).strip()
                cases.append({
                    "name": name, "status": "FAIL",
                    "error": "reference extraction did not complete", "output": output,
                })
                continue
            run = invoke_klayout(kind, exe, DECK, [
                "-rd", f"input={gds}", "-rd", "top=TOP",
                "-rd", f"schematic={reference}", "-rd", f"target_netlist={target}",
                "-rd", f"report={report}", *well_flag,
            ])
        except (OSError, subprocess.TimeoutExpired) as error:
            cases.append({"name": name, "status": "FAIL", "error": str(error)})
            continue

        output = (run.stdout + "\n" + run.stderr).strip()
        observed = {check: int(count) for check, count in check_pattern.findall(output)}
        verdict_match = verdict_pattern.search(output)
        summary_match = summary_pattern.search(output)
        issues = []
        if run.returncode != 0:
            issues.append(f"KLayout exited {run.returncode}")
        if not target.is_file() or not report.is_file():
            issues.append("extracted netlist or report was not written")
        if "ICS55_LVS_COMPARE=PASS" not in output:
            issues.append("ERC smoke run did not pass the netlist comparison")
        verdict = verdict_match.group(1) if verdict_match else None
        if verdict != expected["verdict"]:
            issues.append(f"expected ICS55_ERC={expected['verdict']}, observed {verdict}")
        selected_total = diagnostic_total = None
        if not summary_match:
            issues.append("ERC summary line missing")
        else:
            checks_reported = int(summary_match.group(1))
            selected_total = int(summary_match.group(2))
            diagnostics_reported = int(summary_match.group(3))
            diagnostic_total = int(summary_match.group(4))
            if checks_reported != ERC_CHECK_COUNT:
                issues.append(f"expected {ERC_CHECK_COUNT} ERC checks, observed {checks_reported}")
            if diagnostics_reported != ERC_DIAGNOSTIC_COUNT:
                issues.append(
                    f"expected {ERC_DIAGNOSTIC_COUNT} ERC diagnostics, "
                    f"observed {diagnostics_reported}"
                )
        expected_counts = {**expected["checks"], **expected["diagnostics"]}
        for check, count in expected_counts.items():
            if observed.get(check, 0) != count:
                issues.append(f"expected {check}={count}, observed {observed.get(check, 0)}")
        unexpected = {
            check: count for check, count in observed.items()
            if count and check not in expected_counts
        }
        if unexpected:
            issues.append(f"unexpected ERC violations: {unexpected}")
        if selected_total is not None and selected_total != sum(expected["checks"].values()):
            issues.append(
                f"expected {sum(expected['checks'].values())} selected violations, "
                f"observed {selected_total}"
            )
        if diagnostic_total is not None and diagnostic_total != sum(expected["diagnostics"].values()):
            issues.append(
                f"expected {sum(expected['diagnostics'].values())} diagnostic violations, "
                f"observed {diagnostic_total}"
            )
        cases.append({
            "name": name,
            "status": "PASS" if not issues else "FAIL",
            "no_well_ties": expected["no_well_ties"],
            "expected_verdict": expected["verdict"],
            "verdict": verdict,
            "checks": observed,
            "selected_violations": selected_total,
            "diagnostic_violations": diagnostic_total,
            "gds_sha256": sha256(gds),
            "target_netlist": str(target),
            "report": str(report),
            "output": output,
            "issues": issues,
        })
    return {
        "fixture": "erc_smoke",
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "cases": cases,
    }


def run_device_smoke(
    kind: str, exe: str, fixture_dir: Path, out: Path,
    name: str, reference_fixture: str, fixtures: tuple[tuple[str, bool], ...],
) -> dict[str, Any]:
    """A valid passive must match; open and shorted variants must fail closed."""
    directory = out / name
    directory.mkdir(parents=True, exist_ok=True)
    reference = directory / f"{reference_fixture}_reference.cir"
    reference_report = directory / f"{reference_fixture}_reference.lvsdb"
    reference.unlink(missing_ok=True)
    reference_report.unlink(missing_ok=True)
    try:
        extraction = invoke_klayout(kind, exe, DECK, [
            "-rd", f"input={fixture_dir / (reference_fixture + '.gds')}", "-rd", "top=TOP",
            "-rd", "net_only=true", "-rd", f"target_netlist={reference}",
            "-rd", f"report={reference_report}",
        ])
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"fixture": name, "status": "FAIL", "error": str(error)}
    if extraction.returncode != 0 or not reference.is_file():
        output = (extraction.stdout + "\n" + extraction.stderr).strip()
        return {
            "fixture": name, "status": "FAIL",
            "error": f"{reference_fixture} reference extraction did not complete",
            "output": output,
        }

    cases = []
    for case_name, expected_match in fixtures:
        target = directory / f"{case_name}_extracted.cir"
        report_path = directory / f"{case_name}.lvsdb"
        target.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        try:
            run = invoke_klayout(kind, exe, DECK, [
                "-rd", f"input={fixture_dir / (case_name + '.gds')}", "-rd", "top=TOP",
                "-rd", f"schematic={reference}", "-rd", f"target_netlist={target}",
                "-rd", f"report={report_path}", "-rd", "run_mode=flat",
                "-rd", "no_erc=true",
            ])
        except (OSError, subprocess.TimeoutExpired) as error:
            cases.append({"name": case_name, "status": "FAIL", "error": str(error)})
            continue
        output = (run.stdout + "\n" + run.stderr).strip()
        matched = ("ICS55_LVS_COMPARE=PASS" in output
                   and "ICS55_LVS_COMPARE=FAIL" not in output
                   and target.is_file())
        rejected = ("ICS55_LVS_COMPARE=FAIL" in output
                    and "ICS55_LVS_COMPARE=PASS" not in output)
        cases.append({
            "name": case_name,
            "status": "PASS" if (matched if expected_match else rejected) else "FAIL",
            "expected_match": expected_match, "native_matched": matched,
            "returncode": run.returncode, "target_netlist": str(target),
            "report": str(report_path), "output": output,
        })
    return {
        "fixture": name,
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "cases": cases,
    }


def run_mom_smoke(
    kind: str, exe: str, fixture_dir: Path, out: Path
) -> dict[str, Any]:
    """A valid MOM must match; an open or shorted MOM must fail closed."""
    return run_device_smoke(
        kind, exe, fixture_dir, out, "mom_smoke", "mom_2t",
        (("mom_2t", True), ("mom_2t_open", False), ("mom_2t_short", False)),
    )


def run_inductor_smoke(
    kind: str, exe: str, fixture_dir: Path, out: Path
) -> dict[str, Any]:
    """A valid inductor must match; a cut winding or pad strap must fail closed."""
    return run_device_smoke(
        kind, exe, fixture_dir, out, "inductor_smoke", "inductor_1tm_alpa",
        (("inductor_1tm_alpa", True),
         ("inductor_1tm_alpa_open", False),
         ("inductor_1tm_alpa_short", False)),
    )


# name, fixture, top ports, instance card, expected compare, expected model.
# The 4T wrapper aliases to the drawn core MOS (W = wf*nf), so its geometry is
# checked; the 5T/6T/PMOS wrappers carry extra terminals and stay on the
# dedicated RF extractor classes.
RF_WRAPPER_CASES = (
    ("nmos_4t", "rf_nmos_4t", "D G S",
     "X1 D G S VSS ics55_rf_nmos_svt_4t wf=0.3u nf=2 l=0.1u",
     True, "NM1P2_SVT_LP"),
    ("nmos_4t_width_mismatch", "rf_nmos_4t", "D G S",
     "X1 D G S VSS ics55_rf_nmos_svt_4t wf=0.45u nf=2 l=0.1u",
     False, "NM1P2_SVT_LP"),
    ("nmos_5t", "rf_nmos_5t", "D G S B DNW",
     "X1 D G S B DNW ics55_rf_nmos_svt_5t wf=0.5u nf=1 l=0.1u",
     True, "ICS55_RF_NMOS_SVT_5T"),
    ("nmos_6t", "rf_nmos_6t", "D G S B DNW PSUB",
     "X1 D G S B DNW PSUB ics55_rf_nmos_svt_6t wf=0.5u nf=1 l=0.1u",
     True, "ICS55_RF_NMOS_SVT_6T"),
    ("pmos_5t", "rf_pmos_5t", "D G S B SUB",
     "X1 D G S B SUB ics55_rf_pmos_svt_5t wf=0.5u nf=1 l=0.1u",
     True, "ICS55_RF_PMOS_SVT_5T"),
)


def run_rf_wrapper_smoke(
    kind: str, exe: str, fixture_dir: Path, out: Path
) -> dict[str, Any]:
    """RF wrapper schematics must map onto their extracted device classes."""
    directory = out / "rf_wrapper_smoke"
    directory.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, fixture, ports, instance, expected_match, expected_model in RF_WRAPPER_CASES:
        reference = directory / f"{name}.cdl"
        reference.write_text(
            f".SUBCKT TOP {ports}\n{instance}\n.ENDS TOP\n"
        )
        target = directory / f"{name}_extracted.cir"
        report = directory / f"{name}.lvsdb"
        target.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
        try:
            run = invoke_klayout(kind, exe, DECK, [
                "-rd", f"input={fixture_dir / f'{fixture}.gds'}", "-rd", "top=TOP",
                "-rd", f"schematic={reference}", "-rd", f"target_netlist={target}",
                "-rd", f"report={report}", "-rd", "no_erc=true",
            ])
        except (OSError, subprocess.TimeoutExpired) as error:
            cases.append({"name": name, "status": "FAIL", "error": str(error)})
            continue
        output = (run.stdout + "\n" + run.stderr).strip()
        matched = ("ICS55_LVS_COMPARE=PASS" in output
                   and "ICS55_LVS_COMPARE=FAIL" not in output)
        rejected = ("ICS55_LVS_COMPARE=FAIL" in output
                    and "ICS55_LVS_COMPARE=PASS" not in output)
        models = model_counts(target)[0] if target.is_file() else collections.Counter()
        issues = []
        if expected_match and not matched:
            issues.append("wrapper did not match the extracted device")
        if not expected_match and not rejected:
            issues.append("wrong-width wrapper was not rejected")
        if models.get(expected_model) != 1:
            issues.append(f"expected 1 {expected_model}, observed {dict(models)}")
        cases.append({
            "name": name, "status": "PASS" if not issues else "FAIL",
            "fixture": fixture, "expected_match": expected_match,
            "expected_model": expected_model, "issues": issues,
            "returncode": run.returncode, "target_netlist": str(target),
            "report": str(report), "output": output,
        })
    return {
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--klayout", help="KLayout executable; otherwise use PATH or --librelane")
    parser.add_argument("--librelane", default="~/Documents/librelane", help="LibreLane flake directory for nix-shell")
    parser.add_argument("--out", type=Path, default=HERE / "out" / "lvs_fixtures")
    parser.add_argument("--fixtures", help="comma-separated fixture names (default: all)")
    args = parser.parse_args()
    args.librelane = str(Path(args.librelane).expanduser()) if args.librelane else None
    selected = list(FIXTURES)
    if args.fixtures:
        selected = [item.strip() for item in args.fixtures.split(",") if item.strip()]
        unknown = sorted(set(selected) - set(FIXTURES))
        if unknown:
            parser.error(f"unknown fixture(s): {', '.join(unknown)}")

    executable = find_klayout(args)
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "lvs_fixture_check.json"
    if executable is None:
        report_path.write_text(json.dumps({
            "status": "BLOCKED", "reason": "KLayout unavailable", "fixtures": selected,
            "official_oracle": "UNAVAILABLE", "cross_tool_equivalence": "BLOCKED",
        }, indent=2) + "\n")
        print(f"BLOCKED: KLayout unavailable; report: {report_path}", file=sys.stderr)
        return 2

    kind, exe = executable
    fixture_dir = args.out / "gds"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    generated = invoke_klayout(kind, exe, GENERATOR, ["-rd", f"out={fixture_dir}"])
    if generated.returncode != 0:
        report_path.write_text(json.dumps({
            "status": "FAIL", "stage": "fixture_generation", "returncode": generated.returncode,
            "output": (generated.stdout + "\n" + generated.stderr).strip(),
        }, indent=2) + "\n")
        print("FAIL: fixture generation failed", file=sys.stderr)
        return 1

    cases = [run_case(args, kind, exe, name, fixture_dir / f"{name}.gds", args.out) for name in selected]
    fixture_failed = [case for case in cases if case["status"] != "PASS"]
    verdict_smoke = run_compare_verdict_smoke(
        kind, exe, fixture_dir / "core_svt_n.gds", args.out
    )
    failed = fixture_failed + (
        [] if verdict_smoke["status"] == "PASS" else [verdict_smoke]
    )
    strict_modes = run_strict_flat_mode_smoke(
        kind, exe, fixture_dir / "strict_flat_parent.gds", args.out
    )
    if strict_modes["status"] != "PASS":
        failed.append(strict_modes)
    erc_smoke = run_erc_smoke(kind, exe, fixture_dir, args.out)
    if erc_smoke["status"] != "PASS":
        failed.append(erc_smoke)
    mom_smoke = run_mom_smoke(kind, exe, fixture_dir, args.out)
    if mom_smoke["status"] != "PASS":
        failed.append(mom_smoke)
    inductor_smoke = run_inductor_smoke(kind, exe, fixture_dir, args.out)
    if inductor_smoke["status"] != "PASS":
        failed.append(inductor_smoke)
    rf_wrapper_smoke = run_rf_wrapper_smoke(kind, exe, fixture_dir, args.out)
    if rf_wrapper_smoke["status"] != "PASS":
        failed.append(rf_wrapper_smoke)
    report = {
        "status": "FAIL" if failed else "PASS",
        "klayout_kind": kind,
        "klayout_executable": exe,
        "official_oracle": "UNAVAILABLE",
        "cross_tool_equivalence": "BLOCKED",
        "fixture_generator_sha256": sha256(GENERATOR),
        "lvs_deck_sha256": sha256(DECK),
        "cases": cases,
        "verdict_smoke": verdict_smoke,
        "strict_flat_modes": strict_modes,
        "erc_smoke": erc_smoke,
        "mom_smoke": mom_smoke,
        "inductor_smoke": inductor_smoke,
        "rf_wrapper_smoke": rf_wrapper_smoke,
        "fixture_failed": len(fixture_failed),
        "failed": len(failed),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    for case in cases:
        state = case["status"]
        summary = ", ".join(f"{name}={count}" for name, count in case.get("models", {}).items()) or "no devices"
        print(f"{state}: {case['fixture']}: {summary}")
        for issue in case.get("issues", []):
            print(f"  - {issue}")
        if state != "PASS" and case.get("output"):
            print(case["output"])
    print(
        f"{verdict_smoke['status']}: LVS compare verdicts "
        f"(match exit={verdict_smoke.get('matching_returncode')}, "
        f"mismatch exit={verdict_smoke.get('mismatch_returncode')})"
    )
    for issue in verdict_smoke.get("issues", []):
        print(f"  - {issue}")
    if verdict_smoke["status"] != "PASS" and verdict_smoke.get("output"):
        print(verdict_smoke["output"])
    print(f"{strict_modes['status']}: strict physical-flat default and explicit-mode controls")
    for case in strict_modes["cases"]:
        if case["status"] != "PASS":
            print(case.get("output", case.get("error")))
    print(f"{erc_smoke['status']}: ERC clean/violation smoke ({len(erc_smoke['cases'])} cases)")
    for case in erc_smoke["cases"]:
        if case["status"] != "PASS":
            print(f"  - {case['name']}: {'; '.join(case.get('issues', []))}")
            print(case.get("output", case.get("error", "")))
    print(f"{mom_smoke['status']}: MOM match/open/short smoke ({len(mom_smoke['cases'])} cases)")
    for case in mom_smoke["cases"]:
        if case["status"] != "PASS":
            print(f"  - {case['name']}: expected_match={case['expected_match']}")
            print(case.get("output", case.get("error", "")))
    print(f"{inductor_smoke['status']}: inductor match/open/short smoke ({len(inductor_smoke['cases'])} cases)")
    for case in inductor_smoke["cases"]:
        if case["status"] != "PASS":
            print(f"  - {case['name']}: expected_match={case['expected_match']}")
            print(case.get("output", case.get("error", "")))
    print(f"{rf_wrapper_smoke['status']}: RF wrapper smoke ({len(rf_wrapper_smoke['cases'])} cases)")
    for case in rf_wrapper_smoke["cases"]:
        if case["status"] != "PASS":
            print(f"  - {case['name']}: {'; '.join(case.get('issues', []))}")
            print(case.get("output", case.get("error", "")))
    print(
        f"{report['status']}: {len(cases) - len(fixture_failed)}/{len(cases)} fixtures; "
        f"verdict smoke {verdict_smoke['status']}; ERC smoke {erc_smoke['status']}; "
        f"MOM smoke {mom_smoke['status']}; inductor smoke {inductor_smoke['status']}; "
        f"RF wrapper smoke {rf_wrapper_smoke['status']}; {report_path}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
