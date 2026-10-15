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
    "poly_resistor": {"models": {"RE_PPO_SAB_2T": 1}, "distinct_resistor_terms": 1, "ports": 2},
    "metal_resistor": {"models": {"RE_M1_2T": 1}, "distinct_resistor_terms": 1, "ports": 2},
    "diode_marker": {"models": {"DIO_3P3_PP_NW_LP": 1}},
    "esd_marker_only": {"models": {}},
    "pad_m1_m5_bar": {"models": {"NM1P2_SVT_LP": 1}, "stack": "m1_m5", "ports": 1, "port_name": "PAD"},
    "pad_t4_bar": {"models": {"NM1P2_SVT_LP": 1}, "stack": "t4", "ports": 1, "port_name": "PAD"},
    "bulk_alias": {"models": {"NM1P2_SVT_LP": 1}, "bulk_aliases": "ground=gnd power=vdd"},
}


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
        if not fields or fields[0][0].upper() not in {"M", "R", "D"}:
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
        ]
        if kind == "nix":
            command = nix_shell_command(exe, command)
        else:
            command += ["--klayout", exe]
        return subprocess.run(command, capture_output=True, text=True, timeout=180)

    mismatch = case_dir / "mismatch.cdl"
    mismatch.write_text(".SUBCKT TOP X Y Z\n.ENDS TOP\n")
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
    print(
        f"{report['status']}: {len(cases) - len(fixture_failed)}/{len(cases)} fixtures; "
        f"verdict smoke {verdict_smoke['status']}; {report_path}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
