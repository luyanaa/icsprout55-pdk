#!/usr/bin/env python3
"""ICS55 DRC/LVS layer-mapping cross-check.

Verifies that every GDS layer binding used by the KLayout DRC/LVS port is
traceable to the official Calibre collateral, and that the frozen official
profile is fully covered by the port.

Sources cross-checked (all live files, hashed for provenance):
  1. pv/DRC/<deck>.drc  - official Calibre DRC LAYER MAP table  (authoritative)
  2. pv/LVS/<deck>.lvs  - official Calibre LVS LAYER MAP table   (authoritative)
  3. techfile/icsprout55.layermap - official GDS layer map (name/purpose/gds)
  4. libs.tech/klayout/tech/ics55.map - KLayout stream-in map
  5. libs.tech/drc/rule_decks/layers_def.drc, layers_definitions.lvs
     - input(g, d) layer usage of the KLayout decks

Checks (fail-closed: any parse failure => BLOCKED, exit 2):
  A. official DRC vs LVS LAYER MAP tables agree (shared keys, same internal
     number; drift between the two decks is reported).
  B. every official (g, d) is present in techfile/icsprout55.layermap
     (documented exceptions only).
  C. every KLayout map layer resolves to the same (g, d) officially, through
     the name crosswalk below; layers with no official counterpart are
     UNTRACEABLE.
  D. deck input(g, d) calls are covered by the KLayout map (or officially
     traceable); untraceable usage is flagged.
  E. frozen official profile coverage: TOTALMETAL=6 requires MET1..MET6;
     missing metals are reported as gaps (silent stream-in drops).

Status semantics (mirrors run_alignment.py): PASS (all checks), FAIL
(mapping disagreement, coverage gap, or layer untraceable to any official
source), BLOCKED (harness error / deck-structure drift).

Usage:
  python3 layer_map_check.py [--out tests/regression/out]

Exit codes: 0 all ok, 1 check failures, 2 harness error.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DRC_DECK = sorted((ROOT / "pv" / "DRC").glob("*.drc"))[0]
LVS_DECK = sorted((ROOT / "pv" / "LVS").glob("*.lvs"))[0]
LAYERMAP = ROOT / "techfile" / "icsprout55.layermap"
KLAYOUT_MAP = ROOT / "libs.tech" / "klayout" / "tech" / "ics55.map"
DRC_LAYERS = ROOT / "libs.tech" / "drc" / "rule_decks" / "layers_def.drc"
LVS_LAYERS = ROOT / "libs.tech" / "lvs" / "rule_decks" / "layers_definitions.lvs"

# KLayout stream-map name -> official layermap (name, purpose).  The KLayout
# map uses short names (M1, LVTN, ...) while the official layermap uses
# foundry names (MET1, NVT1, ...); purposes disambiguate text/dm/slot layers.
# Names not listed fall back to identity (name, drawing) / (name, mark).
CROSSWALK: dict[str, tuple[str, str]] = {
    "M1": ("MET1", "drawing"), "M2": ("MET2", "drawing"),
    "M3": ("MET3", "drawing"), "M4": ("MET4", "drawing"),
    "M5": ("MET5", "drawing"),
    "M1LBL": ("MET1", "text"), "M2LBL": ("MET2", "text"),
    "M3LBL": ("MET3", "text"), "M4LBL": ("MET4", "text"),
    "M5LBL": ("MET5", "text"),
    "V1": ("VIA1", "drawing"), "V2": ("VIA2", "drawing"),
    "V3": ("VIA3", "drawing"), "V4": ("VIA4", "drawing"),
    # TM2/TV2 are the IO top-metal layers (T4M2/T4V2), per the IO pad LEFs.
    "TM2": ("T4M2", "drawing"), "TM2LBL": ("T4M2", "text"),
    "TV2": ("T4V2", "drawing"),
    "LVTN": ("NVT1", "drawing"), "LVTP": ("PVT1", "drawing"),
    "HVTN": ("NVT3", "drawing"), "HVTP": ("PVT3", "drawing"),
    "NW": ("NW1", "drawing"), "VPW": ("PSUB", "mark"),
    "CTbar": ("CT", "bar"), "CTopcblk": ("CT", "opcblk"),
    "CELLBOUND": ("CHIPBLK", "mark"), "L313": ("SUBCKTLVS", "mark"),
    "L354": ("SRINGBLK", "mark"), "L356": ("NOSHRINK", "mark"),
    "L357": ("NODRC", "mark"),
    "PIN": ("MET1", "dm"),  # collides with official MET1 dm; see report
    "PPO": ("POLY", "res"),
}

# Official (g, d) entries with no layermap counterpart (checked in B).
OFFICIAL_LAYERMAP_EXCEPTIONS = {(354, 13), (999, 1111)}

# Official layermap (g, d) entries never referenced by the official DRC deck.
LAYERMAP_DRC_EXCEPTIONS = {(0, 1), (7, 12), (354, 12), (388, 12)}

# Deck input layers that are intentional local conventions, documented in the
# decks themselves (not present in the official GDS flow or KLayout stream map).
# See libs.tech/drc/rule_decks/mom.drc:19-20 (analog MOM / dummy-fill marks).
DOCUMENTED_AUX = {
    (60, 1): "MOM_MARKER",
    (60, 2): "DUMMY",
    (60, 3): "NO_FILL",
    (60, 4): "DM_EXCEL",
}

# Frozen official profile option values (klayout_alignment_manifest.json), in
# the official DRC deck's variable names (pv/DRC/<deck>.drc:34-60).  Used to
# evaluate which CHECK_* gates the deck enables for this profile.
FROZEN_PROFILE = {
    "total_metal": 6, "top_metal": 1,
    "T2V1_T2M1": 0, "T2V2_T2M2": 0, "T4V1_T4M1": 0, "T4V2_T4M2": 1,
    "T8V1_T8M1": 0, "T8V2_T8M2": 0,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_official_layermap(path: Path) -> dict[tuple[int, int], int]:
    """LAYER MAP <g> (DATATYPE|TEXTTYPE) <d> <internal> -> {(g, d): internal}."""
    out: dict[tuple[int, int], int] = {}
    for line in path.read_text().splitlines():
        m = re.match(r"\s*LAYER\s+MAP\s+(\d+)\s+(?:DATATYPE|TEXTTYPE)\s+(\d+)\s+(\d+)", line)
        if m:
            out[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
    return out


def parse_techfile_layermap(path: Path) -> dict[tuple[int, int], list[tuple[str, str]]]:
    """<name> <purpose> <g> <d> -> {(g, d): [(name, purpose), ...]}."""
    out: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 4:
            continue
        out.setdefault((int(p[2]), int(p[3])), []).append((p[0], p[1]))
    return out


def parse_klayout_map(path: Path) -> dict[str, list[tuple[int, int]]]:
    """<g> <d> <name> -> {name: [(g, d), ...]}."""
    out: dict[str, list[tuple[int, int]]] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 3:
            continue
        out.setdefault(p[2], []).append((int(p[0]), int(p[1])))
    return out


def parse_deck_inputs(path: Path) -> set[tuple[int, int]]:
    """input(g, d) calls in a KLayout deck."""
    return {(int(g), int(d)) for g, d in re.findall(r"input\(\s*(\d+)\s*,\s*(\d+)\s*\)", path.read_text())}


def _match_braced(text: str, i: int) -> tuple[str, int]:
    """text[i] == '{': return (inner body, index after closing '}')."""
    if text[i] != "{":
        raise ValueError("expected '{'")
    depth = 0
    j = i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    raise ValueError("unbalanced braces")


def _eval_tcl_condition(cond: str, opts: dict[str, int]) -> bool | None:
    """Evaluate a deck gate condition like `$total_metal == 6` or `$VAR == 0`.

    Returns None if the condition form is not recognized (deck drift => fail closed).
    """
    m = re.match(r"\s*\$(\w+)\s*==\s*(\d+)\s*$", cond)
    if not m:
        return None
    return opts.get(m.group(1)) == int(m.group(2))


def _walk_chain(body: str, opts: dict[str, int], enabled: dict[str, int], i: int) -> bool:
    """Walk an if/elseif/else chain inside `body` starting at index i (after `if`)."""
    matched = False
    pending_cond = True  # first clause of a chain always has a condition (if)
    while True:
        if pending_cond:
            s = body[i:]
            j = i + len(s) - len(s.lstrip())
            if not body[j:].startswith("{"):
                return False
            cbody, i = _match_braced(body, j)
            v = _eval_tcl_condition(cbody, opts)
            if v is None:
                return False
            take = v and not matched
        else:
            take = not matched  # else
        s = body[i:]
        j = i + len(s) - len(s.lstrip())
        if not body[j:].startswith("{"):
            return False
        bbody, i = _match_braced(body, j)
        if take:
            if not _walk_block(bbody, opts, enabled):
                return False
            matched = True
        s = body[i:]
        m = re.match(r"\s*(elseif|else)\b", s)
        if not m:
            return True
        i += m.end()
        pending_cond = m.group(1) == "elseif"


def _walk_block(body: str, opts: dict[str, int], enabled: dict[str, int]) -> bool:
    """Walk a block body: unconditional `set CHECK_X n` then an optional if-chain."""
    i = 0
    while i < len(body):
        s = body[i:]
        m = re.match(r"\s*set\s+(CHECK_\w+)\s+(\d+)", s)
        if m:
            enabled[m.group(1)] = int(m.group(2))
            i += m.end()
            continue
        m = re.match(r"\s*if\b", s)
        if m:
            return _walk_chain(body, opts, enabled, i + m.end())
        return True  # trailing whitespace/comments/puts - ignore


def official_enabled_checks(drc_text: str) -> tuple[dict[str, int] | None, str]:
    """Evaluate the CHECK_* gates enabled by the frozen profile.

    Returns (enabled, error); error is set (None result) on deck-structure drift.
    """
    defaults = {}
    for var, val in re.findall(r"^set\s+(CHECK_\w+)\s+(\d+)", drc_text, re.M):
        defaults[var] = int(val)
    needle = "if { $total_metal == 10 } {"
    start = drc_text.find(needle)
    if start == -1:
        return None, "total_metal gate chain not found"
    enabled = dict(defaults)
    # walk the full if/elseif chain from right after the leading `if`
    if not _walk_chain(drc_text, FROZEN_PROFILE, enabled, start + len("if")):
        return None, "gate structure not fully evaluable (deck drift?)"
    return enabled, ""


def resolve_klayout_name(name: str) -> tuple[str, str] | None:
    """Return (official name, purpose) for crosswalked layers, else None (identity)."""
    return CROSSWALK.get(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=ROOT / "tests" / "regression" / "out")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rec: dict[str, Any] = {"schema": "ics55-layer-map-check/1.0", "status": "PASS", "checks": {}}
    try:
        drc_map = parse_official_layermap(DRC_DECK)
        lvs_map = parse_official_layermap(LVS_DECK)
        layermap = parse_techfile_layermap(LAYERMAP)
        kl_map = parse_klayout_map(KLAYOUT_MAP)
        drc_inputs = parse_deck_inputs(DRC_LAYERS)
        lvs_inputs = parse_deck_inputs(LVS_LAYERS)
    except Exception as e:  # noqa: BLE001 - fail closed on any parse problem
        rec["status"] = "BLOCKED"
        rec["reason"] = f"parse failure: {e}"
        _emit(out_dir, rec)
        return 2

    rec["provenance"] = {p.name: sha256(p) for p in
                         [DRC_DECK, LVS_DECK, LAYERMAP, KLAYOUT_MAP, DRC_LAYERS, LVS_LAYERS]}
    issues: list[str] = []

    # A. official DRC vs LVS LAYER MAP agreement
    a: dict[str, Any] = {"drc_entries": len(drc_map), "lvs_entries": len(lvs_map)}
    only_drc = sorted(set(drc_map) - set(lvs_map))
    only_lvs = sorted(set(lvs_map) - set(drc_map))
    conflicts = sorted((k, drc_map[k], lvs_map[k]) for k in drc_map.keys() & lvs_map.keys()
                       if drc_map[k] != lvs_map[k])
    a["drc_only"] = [f"{g}/{d}" for g, d in only_drc]
    a["lvs_only"] = [f"{g}/{d}" for g, d in only_lvs]
    a["internal_conflicts"] = conflicts
    if conflicts:
        issues.append(f"A: internal layer conflicts between official DRC and LVS decks: {conflicts}")
    rec["checks"]["official_drc_vs_lvs"] = a

    # B. official (g, d) covered by techfile layermap
    b: dict[str, Any] = {}
    miss = sorted(set(drc_map) - set(layermap) - OFFICIAL_LAYERMAP_EXCEPTIONS)
    b["missing_from_layermap"] = [f"{g}/{d}" for g, d in miss]
    extra = sorted(set(layermap) - set(drc_map) - LAYERMAP_DRC_EXCEPTIONS)
    b["layermap_not_in_drc_deck"] = [f"{g}/{d}" for g, d in extra]
    if miss:
        issues.append(f"B: official (g,d) absent from techfile layermap: {miss}")
    rec["checks"]["layermap_coverage"] = b

    # C. KLayout map vs official (g, d)
    c: dict[str, Any] = {"unresolved": [], "wrong_numbers": [], "ambiguous": []}
    for name, kds in sorted(kl_map.items()):
        alias = resolve_klayout_name(name)
        for g, d in kds:
            official_hits = [(n, p) for n, p in layermap.get((g, d), [])]
            if not official_hits:
                c["unresolved"].append(f"{name} {g}/{d} -> no official (g,d)")
                continue
            if alias is None:
                # identity-resolved: same name with any purpose is a match
                match = any(n == name for n, p in official_hits)
            else:
                oname, opurpose = alias
                match = any(n == oname and p == opurpose for n, p in official_hits)
            if not match:
                c["wrong_numbers"].append(
                    f"{name} {g}/{d} -> official has {official_hits}"
                    + (f", expected ({alias[0]},{alias[1]})" if alias else f", expected name {name}"))
    if c["unresolved"]:
        issues.append("C: KLayout layers not traceable to official layermap: "
                      + "; ".join(c["unresolved"]))
    if c["wrong_numbers"]:
        issues.append("C: KLayout layer numbers disagree with official layermap: "
                      + "; ".join(c["wrong_numbers"]))
    rec["checks"]["klayout_map_vs_official"] = c

    # D. deck input() usage covered by KLayout map
    d: dict[str, Any] = {}
    for deck_name, inputs, layers_path in (
        ("drc", drc_inputs, DRC_LAYERS), ("lvs", lvs_inputs, LVS_LAYERS)):
        unmapped = sorted((g, d) for g, d in inputs
                          if (g, d) not in {gd for kds in kl_map.values() for gd in kds})
        aux = [f"{g}/{d} ({DOCUMENTED_AUX[(g, d)]})" for g, d in unmapped
               if (g, d) in DOCUMENTED_AUX]
        real = [f"{g}/{d}" for g, d in unmapped if (g, d) not in DOCUMENTED_AUX]
        d[deck_name] = {
            "inputs": len(inputs),
            "documented_local_aux": aux,
            "unmapped": real,
            "layers_def_sha256": sha256(layers_path),
        }
        if real:
            issues.append(f"D: {deck_name} deck uses layers absent from KLayout map: {real}")
    rec["checks"]["deck_usage_vs_map"] = d

    # E. frozen profile coverage: every official gate enabled for the frozen
    # profile (TOTALMETAL=6, TOP_METAL_NUM=SINGLE) must be mapped and checked
    # by the KLayout port.  Enabled gates are evaluated from the official DRC
    # deck's own gating (fail-closed on deck-structure drift).
    e: dict[str, Any] = {"profile": "TOTALMETAL=6, TOP_METAL_NUM=SINGLE (frozen)",
                         "frozen_options": FROZEN_PROFILE}
    enabled, err = official_enabled_checks(DRC_DECK.read_text())
    if err:
        rec["status"] = "BLOCKED"
        rec["reason"] = f"E: official deck gating not evaluable: {err}"
        _emit(out_dir, rec)
        return 2
    e["enabled_gates"] = {k: v for k, v in sorted(enabled.items()) if v}
    # gate -> official layer name
    gate_layer = {
        "CHECK_M1": "MET1", "CHECK_M2": "MET2", "CHECK_M3": "MET3",
        "CHECK_M4": "MET4", "CHECK_M5": "MET5", "CHECK_M6": "MET6",
        "CHECK_M7": "MET7", "CHECK_M8": "MET8",
        "CHECK_T2M1": "T2M1", "CHECK_T2M2": "T2M2",
        "CHECK_T4M1": "T4M1", "CHECK_T4M2": "T4M2",
        "CHECK_T8M1": "T8M1", "CHECK_T8M2": "T8M2",
        "CHECK_V1": "VIA1", "CHECK_V2": "VIA2", "CHECK_V3": "VIA3",
        "CHECK_V4": "VIA4", "CHECK_V5": "VIA5", "CHECK_V6": "VIA6",
        "CHECK_V7": "VIA7", "CHECK_V8": "VIA8",
        "CHECK_T2V1": "T2V1", "CHECK_T2V2": "T2V2",
        "CHECK_T4V1": "T4V1", "CHECK_T4V2": "T4V2",
        "CHECK_T8V1": "T8V1", "CHECK_T8V2": "T8V2",
    }
    kl_mapped = {gd for kds in kl_map.values() for gd in kds}
    gaps = []
    for gate, val in enabled.items():
        if not val:
            continue
        layer = gate_layer.get(gate)
        if layer is None:
            continue
        gds = [(g, d) for (g, d), ents in layermap.items()
               if any(n == layer and p == "drawing" for n, p in ents)]
        if not gds:
            gaps.append(f"{layer}: no official layermap drawing entry (gate {gate} enabled)")
            continue
        for g, d in gds:
            if (g, d) not in kl_mapped:
                gaps.append(f"{layer} {g}/{d}: enabled officially but not in KLayout map")
            if (g, d) not in drc_inputs:
                gaps.append(f"{layer} {g}/{d}: enabled officially but not checked by KLayout DRC deck")
    e["gaps"] = gaps
    # shipped option defaults in the official deck must still match the frozen
    # profile (the deck is the source the manifest was frozen from)
    deck_opts = {}
    for line in DRC_DECK.read_text().splitlines():
        m = re.match(r"\s*set\s+(\w+)\s+(\d+)\s*;", line)
        if m and m.group(1) in FROZEN_PROFILE:
            deck_opts[m.group(1)] = int(m.group(2))
    e["deck_defaults_vs_frozen"] = deck_opts
    drifted = {k: (deck_opts[k], FROZEN_PROFILE[k]) for k in FROZEN_PROFILE
               if k in deck_opts and deck_opts[k] != FROZEN_PROFILE[k]}
    if drifted:
        issues.append(f"E: official deck defaults drifted from frozen profile: {drifted}")
    if gaps:
        issues.append("E: profile coverage gaps: " + "; ".join(gaps))
    rec["checks"]["profile_coverage"] = e

    rec["status"] = "FAIL" if issues else "PASS"
    rec["issues"] = issues
    _emit(out_dir, rec)
    print(rec["status"])
    for i in issues:
        print("  -", i)
    return 1 if issues else 0


def _emit(out_dir: Path, rec: dict[str, Any]) -> None:
    (out_dir / "layer_map_check.json").write_text(json.dumps(rec, indent=2))


if __name__ == "__main__":
    sys.exit(main())
