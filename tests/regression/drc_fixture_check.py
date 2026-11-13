#!/usr/bin/env python3
"""ICS55 DRC fixture regression (KLayout self-consistency).

Generates FEOL/BEOL core-rule layouts and asserts exact category sets, including
threshold boundaries, marker waivers, and rotated via enclosure. Fixtures are
written by KLayout itself (`tests/regression/make_fixtures.rb`); they do not
reimplement GDS encoding. This verifies only the KLayout port, never Calibre
parity.

KLayout is selected from PATH / `--klayout`, or from the LibreLane nix shell
(`--librelane`). Missing tools or failed runs are BLOCKED, not PASS.

Usage:
  python3 drc_fixture_check.py [--librelane ~/Documents/librelane]
                               [--klayout PATH] [--out tests/regression/out]
                               [--jobs N]

Exit codes: 0 exact fixture match, 1 category mismatch, 2 blocked/harness error.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from nix_shell import command as nix_shell_command

ROOT = Path(__file__).resolve().parents[2]
DRC_DECK = ROOT / "libs.tech" / "drc" / "ics55_drc.drc"
ANTENNA_DECK = ROOT / "libs.tech" / "drc" / "ics55_antenna.drc"
MAKE_FIXTURES = Path(__file__).resolve().parent / "make_fixtures.rb"

# KLayout self-consistency profiles. Main covers FEOL/BEOL/dummy/special;
# density and MOM run separately so each fixture exercises the selected family.
# These are source-behavior fixtures, not a Calibre differential.
DRC_PROFILES = {
    "main": {
        "tables": "main", "no_feol": False, "no_beol": False,
        "no_density": True,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
    },
    "density": {
        "tables": "density", "no_feol": False, "no_beol": False,
        "no_density": False,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
    },
    "mom": {
        "tables": "mom", "no_feol": False, "no_beol": False,
        "no_density": True,
        "no_mom": False, "cell_exclusion": False, "run_mode": "deep",
    },
    "beol": {
        "tables": "beol", "no_feol": True, "no_beol": False,
        "no_density": True,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
    },
    "special": {
        "tables": "special", "no_feol": True, "no_beol": True,
        "no_density": True,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
    },
    # Off-profile thick-metal switch: T4M1 selected with vendor top_metal=2.
    "t4m1": {
        "tables": "main", "no_feol": True, "no_beol": False,
        "no_density": True,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
        "total_metal": 6, "top_metal": 2,
        "T4V1_T4M1": True, "T4V2_T4M2": False,
    },
    # Recommended rules as report categories (default mode is warn).
    "recommended": {
        "tables": "main", "no_feol": False, "no_beol": False,
        "no_density": True,
        "no_mom": True, "cell_exclusion": False, "run_mode": "deep",
        "recommended": "error",
    },
    # Antenna ratios need netlist extraction, so they live in a separate deck.
    "antenna": {
        "deck": "antenna",
    },
}

# fixture name -> exact expected rule-category set; profile-specific families
# are mapped separately below.
FIXTURES: dict[str, frozenset[str]] = {
    # Legacy synthetic fixtures predate the batch-9 TG/DG, implant
    # gate-extension, U-shape AA, SAB and voltage-implant rules. Their minimal
    # geometry also trips those stricter predicates, so the incidental TG_*,
    # implant.*gate*, active.act.u_space and SAB_* categories below are
    # recorded rather than waived.
    "clean": frozenset(),
    "act_area": frozenset({"active.act.area"}),
    "act_area_at_limit": frozenset(),
    "act_area_nodrc_waived": frozenset(),
    "act_width_bad": frozenset({"active.act.width"}),
    "act_width_at_limit": frozenset(),
    # The 0.3 um wide AA also trips the wide-AA spacing rule (gap < 0.125),
    # which is the source's intended stricter limit for wide AA.
    "act_spacing_bad": frozenset({"active.act.spacing", "active.act.wide_space"}),
    "act_spacing_at_limit": frozenset({"active.act.wide_space"}),
    "act_tg_spacing_bad": frozenset({"TG_EN_1", "TG_S_2", "active.act.tg_spacing"}),
    "act_tg_spacing_at_limit": frozenset({"TG_EN_1", "TG_S_2"}),
    "act_nw_nact_space_bad": frozenset({"active.nw.nact.space.pw", "well.nw.floating"}),
    "act_nw_nact_space_at_limit": frozenset({"well.nw.floating"}),
    "act_nw_nact_tg_space_bad": frozenset({
        "TG_EN_1", "TG_S_4", "TG_W_1", "active.nw.nact.space.tg", "well.nw.floating",
    }),
    "act_nw_nact_tg_space_at_limit": frozenset({"TG_EN_1", "TG_S_4", "TG_W_1", "well.nw.floating"}),
    "act_nw_pact_space_bad": frozenset({"active.nw.pact.space", "well.nw.floating"}),
    "act_nw_pact_space_at_limit": frozenset({"well.nw.floating"}),
    "act_nact_nw_enclosure_bad": frozenset({"active.nact.nw.enclosure", "well.nw.floating"}),
    "act_nact_nw_enclosure_at_limit": frozenset({"well.nw.floating"}),
    "act_pact_nw_enclosure_bad": frozenset({"active.pact.nw.enclosure", "well.nw.floating"}),
    "act_pact_nw_enclosure_at_limit": frozenset({"well.nw.floating"}),
    "act_pact_nw_tg_enclosure_bad": frozenset({"TG_EX_2", "active.pact.nw_tg.enclosure", "well.nw.floating"}),
    "act_pact_nw_tg_enclosure_at_limit": frozenset({"TG_EX_2", "well.nw.floating"}),
    "act_hole": frozenset({"active.act.enclosed_area"}),
    "act_hole_at_limit": frozenset(),
    # With no implant drawn at all, NP_EN_1 has no edges inside NP to check,
    # so only the AA coverage rule can fire.
    "act_implant_coverage_bad": frozenset({"active.act.implant_coverage"}),
    "act_implant_coverage_nw1res_waived": frozenset(),
    "act_channel_width_bad": frozenset({
        "active.act.u_space",
        "active.gate.channel_width",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.lshape_aa",
        "poly.po.lshape_po",
        "poly.po.sti_space",
    }),
    "act_channel_width_at_limit": frozenset({
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.lshape_aa",
        "poly.po.lshape_po",
        "poly.po.sti_space",
    }),
    "act_io_channel_width_bad": frozenset({
        "active.act.u_space",
        "active.gate.io_channel_width",
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.dg",
        "poly.po.sti_space",
    }),
    "act_io_channel_width_at_limit": frozenset({
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.dg",
        "poly.po.sti_space",
    }),
    "act_angle_width_bad": frozenset({"active.act.angle_width"}),
    "act_angle_width_at_limit": frozenset(),
    "act_angle_space_bad": frozenset({"active.act.angle_space"}),
    "act_angle_space_at_limit": frozenset(),
    "act_wide_space_bad": frozenset({"active.act.wide_space"}),
    "act_wide_space_at_limit": frozenset(),
    "act_nw_dnw_space_bad": frozenset({"active.nw_dnw.nact.space"}),
    "act_nw_dnw_space_at_limit": frozenset(),
    "poly_area": frozenset({"poly.poly.area"}),
    "poly_area_at_limit": frozenset(),
    "poly_area_nodrc_waived": frozenset(),
    "poly_area_partial_marker": frozenset({"poly.poly.area"}),
    "poly_width_bad": frozenset({"poly.poly.width"}),
    "poly_width_at_limit": frozenset(),
    "poly_spacing_bad": frozenset({"poly.poly.spacing"}),
    "poly_spacing_at_limit": frozenset(),
    "poly_hole": frozenset({"poly.poly.enclosed_area"}),
    "poly_hole_at_limit": frozenset(),
    "np_area": frozenset({"implant.np.area"}),
    "np_area_at_limit": frozenset(),
    "pp_area": frozenset({"implant.pp.area"}),
    "pp_area_at_limit": frozenset(),
    "np_width_bad": frozenset({"implant.np.width"}),
    "np_width_at_limit": frozenset(),
    "np_spacing_bad": frozenset({"implant.np.spacing"}),
    "np_spacing_at_limit": frozenset(),
    "pp_width_bad": frozenset({"implant.pp.width"}),
    "pp_width_at_limit": frozenset(),
    "pp_spacing_bad": frozenset({"implant.pp.spacing"}),
    "pp_spacing_at_limit": frozenset(),
    "np_act_overlap_bad": frozenset({
        "implant.np.act.overlap", "implant.np.nact_pw.enclosure",
    }),
    "np_act_overlap_at_limit": frozenset(),
    "pp_act_overlap_bad": frozenset({"implant.pp.act.overlap"}),
    "pp_act_overlap_at_limit": frozenset(),
    # The overlap violates NP_S_4 and PP_S_4 symmetrically and also PP_R_1.
    # The shared N+ edge lies on the NP boundary, so NP_EN_2 has no edge
    # inside NP there and reports nothing.
    "np_s4_bad": frozenset({
        "implant.np.pact.overlap", "implant.pp.nact.overlap", "implant.np_pp.overlap",
    }),
    "np_s4_sram_waived": frozenset({"implant.np_pp.overlap"}),
    "pp_s4_bad": frozenset({
        "implant.pp.nact.overlap", "implant.np.pact.overlap", "implant.np_pp.overlap",
    }),
    "pp_r1_bad": frozenset({"implant.np_pp.overlap"}),
    "np_tap_area_bad": frozenset({"implant.np.tap_area"}),
    "np_tap_area_at_limit": frozenset(),
    "pp_tap_area_bad": frozenset({"implant.pp.tap_area"}),
    "pp_tap_area_at_limit": frozenset(),
    # Approaching the opposite AA closer than its implant cover margin also
    # overlaps the opposite implant, so PP_R_1 fires in the bad cases.
    "np_pact_space_bad": frozenset({
        "implant.np.pact_space", "implant.np_pp.overlap",
    }),
    "np_pact_space_at_limit": frozenset(),
    # The 0.02 um PP cover is below the 0.12 um PP_O_1 overlap margin.
    "np_ptap_space_bad": frozenset({
        "implant.np.ptap_space", "implant.np_pp.overlap", "implant.pp.act.overlap",
    }),
    "np_ptap_space_at_limit": frozenset({"implant.pp.act.overlap"}),
    "pp_nact_space_bad": frozenset({
        "implant.pp.nact_space", "implant.np_pp.overlap",
    }),
    "pp_nact_space_at_limit": frozenset(),
    "pp_ntap_space_bad": frozenset({
        "implant.pp.ntap_space", "implant.np_pp.overlap",
    }),
    "pp_ntap_space_at_limit": frozenset({"implant.np_pp.overlap"}),
    "np_gate_space_bad": frozenset({"implant.np.gate_space", "implant.pp.gate_aa.enclosure"}),
    "np_gate_space_at_limit": frozenset({"implant.pp.gate_aa.enclosure"}),
    "pp_gate_space_bad": frozenset({"implant.np.gate_aa.enclosure", "implant.pp.gate_space"}),
    "pp_gate_space_at_limit": frozenset({"implant.np.gate_aa.enclosure"}),
    # The same 0.01/0.02 um cover also violates the 0.12 um overlap margin.
    "np_aa_enclosure_bad": frozenset({
        "implant.np.aa.enclosure", "implant.np.act.overlap",
    }),
    "np_aa_enclosure_at_limit": frozenset({"implant.np.act.overlap"}),
    "pp_ptap_enclosure_bad": frozenset({
        "implant.pp.ptap.enclosure", "implant.pp.act.overlap",
    }),
    "pp_ptap_enclosure_at_limit": frozenset({"implant.pp.act.overlap"}),
    "np_nact_pw_enclosure_bad": frozenset({
        "implant.np.nact_pw.enclosure", "implant.np.act.overlap",
    }),
    "np_nact_pw_enclosure_at_limit": frozenset(),
    "pp_pact_nw_enclosure_bad": frozenset({
        "implant.pp.pact_nw.enclosure", "implant.pp.act.overlap",
    }),
    "pp_pact_nw_enclosure_at_limit": frozenset(),
    "np_po_enclosure_bad": frozenset({"implant.np.po.enclosure"}),
    "np_po_enclosure_at_limit": frozenset(),
    "pp_po_enclosure_bad": frozenset({"implant.pp.po.enclosure"}),
    "pp_po_enclosure_at_limit": frozenset(),
    "psub_area_bad": frozenset({"implant.psub.area"}),
    "psub_area_at_limit": frozenset(),
    "psub_area_nodrc_waived": frozenset(),
    "psub_hole_area_bad": frozenset({"implant.psub.enclosed_area"}),
    "psub_hole_area_at_limit": frozenset(),
    "psub_width_bad": frozenset({"implant.psub.width"}),
    "psub_width_at_limit": frozenset(),
    "psub_space_bad": frozenset({"implant.psub.spacing"}),
    "psub_space_at_limit": frozenset(),
    # The NW in the spacing fixtures carries no tap, so it is flagged floating.
    "psub_nw_space_bad": frozenset({"implant.psub.nw_space", "well.nw.floating"}),
    "psub_nw_space_at_limit": frozenset({"well.nw.floating"}),
    "psub_mos_space_bad": frozenset({"implant.psub.mos_space"}),
    "psub_mos_space_at_limit": frozenset(),
    "psub_channel_width_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.channel_width_min",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_channel_width_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_channel_width_max_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.channel_width_max",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_core_length_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.core_length_min",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_core_length_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_core_length_max_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.core_length_max",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_io1_length_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.io1_length_min",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_io1_length_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_io1_length_max_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.io1_length_max",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_io2_length_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.io2_length",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_io2_length_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_gate_ext_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.gate_ext",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_gate_ext_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_dnw_overlap_bad": frozenset({"implant.psub.dnw.overlap"}),
    "psub_dnw_coincident_bad": frozenset({"implant.psub.dnw.coincident"}),
    "psub_pp_gate_overlap_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.psub.pp_gate.overlap",
        "latchup.s2_ptap",
        "poly.po.sti_space",
    }),
    "psub_multi_aa_bad": frozenset({"implant.psub.multi_aa"}),
    "psub_multi_aa_indall_waived": frozenset(),
    "ct_outside_required_layers": frozenset({
        "cont.ct.inside", "cont.ct.m1.coverage", "cont.ct.m1.not_interacting",
    }),
    "ct_active_enclosure_bad": frozenset({"cont.ct.active.enclosure"}),
    "ct_active_enclosure_at_limit": frozenset(),
    "ct_active_enclosure_dir_ok": frozenset(),
    "ct_active_enclosure_dir_bad": frozenset({"cont.ct.active.enclosure.dir"}),
    "ct_width_bad": frozenset({"cont.ct.width"}),
    "ct_width_at_limit": frozenset(),
    "ct_width_efuse_bad": frozenset({"cont.ct.width.efuse"}),
    "ct_width_sram_bad": frozenset({"cont.ct.width.sram"}),
    "ct_width_grid_bad": frozenset({"cont.ct.width.grid"}),
    "ct_width_grid_ring_waived": frozenset({"SRCK_13a"}),
    "ct_bar_width_bad": frozenset({"cont.ct.width", "cont.ct.bar.width"}),
    "ct_bar_at_limit": frozenset(),
    "ct_spacing_bad": frozenset({
        "cont.ct.spacing",
        "cont.ct.spacing.diff_net",
    }),
    "ct_spacing_at_limit": frozenset({
        "cont.ct.spacing.diff_net",
    }),
    "ct_s1a_bad": frozenset({"cont.ct.spacing.neighbor"}),
    "ct_s1a_at_limit": frozenset(),
    "ct_en4d_bad": frozenset({"cont.ct.m1.enclosure.wide"}),
    "ct_en4d_at_limit": frozenset(),
    # The field-poly stub is only 0.05 um inside NP, so NP_EN_3 also fires.
    "ct_poly_active_space_bad": frozenset({
        "cont.ct.poly.aa.space",
        "implant.np.po.enclosure",
        "poly.po.implant",
        "poly.po.sti_space",
    }),
    "ct_poly_active_space_at_limit": frozenset({
        "implant.np.po.enclosure",
        "poly.po.implant",
        "poly.po.sti_space",
    }),
    "ct_core_gate_space_bad": frozenset({
        "cont.ct.core_gate.space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "ct_core_gate_space_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "ct_io_gate_space_bad": frozenset({
        "cont.ct.io_gate.space",
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.dg",
    }),
    "ct_io_gate_space_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.dg",
    }),
    "ct_active_coverage_bad": frozenset({"cont.ct.active.coverage"}),
    "ct_poly_coverage_bad": frozenset({
        "cont.ct.poly.coverage",
        "poly.po.implant",
    }),
    "ct_poly_enclosure_bad": frozenset({
        "cont.ct.poly.enclosure",
        "cont.ct.poly.enclosure.all",
        "poly.po.implant",
    }),
    "ct_poly_enclosure_at_limit": frozenset({
        "poly.po.implant",
    }),
    "ct_poly_enclosure_directional_ok": frozenset({
        "poly.po.implant",
    }),
    "ct_poly_enclosure_all_bad": frozenset({
        "cont.ct.poly.enclosure.all",
        "poly.po.implant",
    }),
    "ct_m1_enclosure_directional_ok": frozenset(),
    "ct_m1_enclosure_all_bad": frozenset({"cont.ct.m1.enclosure"}),
    "ct_m1_coverage_bad": frozenset({"cont.ct.inside", "cont.ct.m1.coverage"}),
    "ct_m1_not_interacting": frozenset({"cont.ct.m1.not_interacting"}),
    "ct_on_gate": frozenset({
        "cont.ct.on_gate",
        "implant.np.gate_aa.enclosure",
        "implant.np.po.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "ct_sab": frozenset({"SAB_A_1", "SAB_W_1", "cont.ct.sab"}),
    "ct_rotated": frozenset({"cont.ct.width", "cont.ct.rotated"}),
    "ct_rotated_sring_waived": frozenset({"SRCK_14a_CT"}),
    "ct_tap_bad": frozenset({"cont.ct.tap", "well.nw.floating"}),
    "ct_tap_with_ct": frozenset({"well.nw.floating"}),
    "nw_area": frozenset({"well.nw.area"}),
    "nw_area_at_limit": frozenset(),
    "nw_hole": frozenset({
        "well.nw.enclosed_area",
        "well.nw.lv.space",
    }),
    "nw_hole_at_limit": frozenset({
        "well.nw.lv.space",
    }),
    "nw_width_bad": frozenset({"well.nw.width"}),
    "nw_width_at_limit": frozenset(),
    "nw_space_bad": frozenset({
        "well.nw.lv.space",
        "well.nw.space",
    }),
    "nw_space_at_limit": frozenset({
        "well.nw.lv.space",
    }),
    "nw_floating": frozenset({"well.nw.floating"}),
    "nw_floating_tapped": frozenset(),
    "dnw_clean": frozenset(),
    "dnw_width_bad": frozenset({"well.dnw.width"}),
    "dnw_width_at_limit": frozenset(),
    "dnw_space_bad": frozenset({"well.dnw.space"}),
    "dnw_space_at_limit": frozenset(),
    "dnw_nsdi_space_bad": frozenset({"well.dnw.nsdi.space"}),
    "dnw_nsdi_space_at_limit": frozenset(),
    "dnw_nw_enclosure_bad": frozenset({"well.dnw.nw.enclosure"}),
    "dnw_nw_enclosure_at_limit": frozenset(),
    "dnw_nw_coincident_bad": frozenset({"well.dnw.nw.coincident"}),
    "dnw_nw_coverage_bad": frozenset({"well.dnw.nw.coverage"}),
    "dnw_o1_bad": frozenset({"well.dnw.nw.coverage", "well.dnw.nw.overlap"}),
    "dnw_o1_at_limit": frozenset({"well.dnw.nw.coverage"}),
    "dnw_tpw_floating": frozenset({"well.dnw.tpw.floating"}),
    # The P+ pickup is 0.19 um from the NMOS gate, so PP_S_5 (not NP_S_5)
    # co-fires with the DNW enclosure check.
    "dnw_nact_enclosure_bad": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.pp.gate_space",
        "poly.po.endcap",
        "well.dnw.nact.enclosure",
        "well.dnw.nw.coverage",
    }),
    "dnw_nact_enclosure_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.pp.gate_space",
        "poly.po.endcap",
        "well.dnw.nw.coverage",
    }),
    "m1_area": frozenset({"metal.m1.area"}),
    "m1_area_at_limit": frozenset(),
    "m1_area_nodrc_waived": frozenset(),
    "m1_spacing_bad": frozenset({"metal.m1.spacing"}),
    "m1_spacing_at_limit": frozenset(),
    "m1_slot_spacing_ignored": frozenset({"SL_W_1_L_1"}),
    "m1_hole": frozenset({"metal.m1.min_hole"}),
    "m1_hole_at_limit": frozenset(),
    "t4m2_area": frozenset({"metal.tm2.area"}),
    "t4m2_area_at_limit": frozenset(),
    "t4m2_hole": frozenset({"metal.tm2.min_hole"}),
    "t4m2_hole_at_limit": frozenset(),
    "m1_width_bad": frozenset({"metal.m1.width"}),
    "m1_width_at_limit": frozenset(),
    "m1_max_width_bad": frozenset({"metal.m1.max_width"}),
    "m1_max_width_at_limit": frozenset(),
    "m1_angle_width_bad": frozenset({"metal.m1.angle_width"}),
    "m1_angle_width_at_limit": frozenset(),
    "m1_angle_space_bad": frozenset({"metal.m1.angle_space"}),
    "m1_angle_space_at_limit": frozenset(),
    "m1_wide_space_bad": frozenset({"metal.m1.wide_space"}),
    "m1_wide_space_at_limit": frozenset(),
    "m1_wide_space_short_run": frozenset(),
    "m1_wide_space_narrow": frozenset(),
    "m1_wider_space_bad": frozenset({"metal.m1.wider_space"}),
    "m1_wider_space_at_limit": frozenset(),
    "m1_wider_space_narrow": frozenset(),
    "m1_eol_space_bad": frozenset({"metal.m1.eol_space"}),
    "m1_eol_space_at_limit": frozenset(),
    "m1_eol_jog_exempt": frozenset(),
    "m1_void_width_bad": frozenset({"metal.m1.void_width"}),
    "m1_void_width_at_limit": frozenset(),
    "m2_width_bad": frozenset({"metal.m2.width"}),
    "m2_width_at_limit": frozenset(),
    "t4m2_width_bad": frozenset({"metal.tm2.width"}),
    "t4m2_width_at_limit": frozenset(),
    "t4m2_max_width_bad": frozenset({"metal.tm2.max_width"}),
    "t4m2_max_width_at_limit": frozenset(),
    "t4m2_spacing_bad": frozenset({"metal.tm2.spacing"}),
    "t4m2_spacing_at_limit": frozenset(),
    "t4m2_wide_space_bad": frozenset({"metal.tm2.wide_space"}),
    "t4m2_wide_space_at_limit": frozenset(),
    "v1_wrong_square": frozenset({"via.v1.width"}),
    "v1_square_at_limit": frozenset(),
    "v1_bar_in_w1_union": frozenset({
        "via.v1.width", "via.v1.cover.lower", "via.v1.cover.upper",
    }),
    "v1_uncovered_lower_metal": frozenset({"via.v1.cover.lower"}),
    "v1_uncovered_nodrc_waived": frozenset(),
    "v1_diagonal_edges": frozenset({"via.v1.width", "via.v1.rotated"}),
    "v1_diagonal_sringblk_waived": frozenset({"SRCK_13b_13c"}),
    "v1_grid_exclusion": frozenset(),
    "v1_spacing_bad": frozenset({
        "via.v1.s2_spacing",
        "via.v1.s3_spacing",
        "via.v1.spacing",
    }),
    "v1_spacing_at_limit": frozenset({
        "via.v1.s2_spacing",
        "via.v1.s3_spacing",
    }),
    "v1_upper_enclosure_bad": frozenset({"via.v1.enclosure.upper"}),
    "v1_upper_enclosure_at_limit": frozenset(),
    "t4v2_spacing_bad": frozenset({"via.tv2.spacing"}),
    "t4v2_spacing_at_limit": frozenset(),
    "t4v2_bar_width_bad": frozenset({"via.tv2.bar.width"}),
    "t4v2_bar_width_at_limit": frozenset(),
    "t4v2_lower_enclosure_bad": frozenset({"via.tv2.enclosure.lower"}),
    "t4v2_lower_enclosure_at_limit": frozenset(),
    "t4v2_upper_enclosure_bad": frozenset({"via.tv2.enclosure.upper"}),
    "t4v2_upper_enclosure_at_limit": frozenset(),
    "t4v2_width_bad": frozenset({"via.tv2.width"}),
    "t4v2_width_at_limit": frozenset(),
    "t4v2_s2_array_bad": frozenset({"via.tv2.array.spacing"}),
    "t4v2_s2_array_at_limit": frozenset(),

    "rv_wrong_rectangle": frozenset({"pad.rv.width"}),
    "rv_grid_exclusion": frozenset(),
    "rv_exact_rectangle": frozenset(),
    "rv_outside_rdl": frozenset({"pad.rv.cover.rdl"}),
    "rv_space_bad": frozenset({"pad.rv.space"}),
    "rv_space_at_limit": frozenset(),
    "rv_cb_space_bad": frozenset({"pad.rv.cb.space"}),
    "rv_cb_space_at_limit": frozenset(),
    "rv_enc_metal_bad": frozenset({"pad.rv.enc.metal"}),
    "rv_enc_metal_at_limit": frozenset(),
    "rv_enc_rdl_bad": frozenset({"pad.rv.enc.rdl"}),
    "rv_enc_rdl_at_limit": frozenset(),
    "rv_single_bad": frozenset({"pad.rv.single"}),
    "rdl_width_bad": frozenset({"pad.rdl.width"}),
    "rdl_width_at_limit": frozenset(),
    "rdl_width_max_bad": frozenset({"pad.rdl.width"}),
    "rdl_width_max_at_limit": frozenset(),
    "rdl_space_bad": frozenset({"pad.rdl.space"}),
    "rdl_space_at_limit": frozenset(),
    "rdl_wide_space_bad": frozenset({"pad.rdl.wide.space"}),
    "rdl_wide_space_at_limit": frozenset(),
    # A >35um ALPA polygon necessarily trips the RDL maximum width too.
    "rdl_wider_space_bad": frozenset({"pad.rdl.width", "pad.rdl.wider.space"}),
    "rdl_wider_space_at_limit": frozenset({"pad.rdl.width"}),
    "cover_outside_alpa": frozenset({"pad.cover.alpa_full", "pad.cover.length", "pad.cover.width"}),
    "cb_outside_alpad": frozenset({"pad.cb.alpad_full", "pad.cb.enclosure", "pad.cb.width"}),
    "cb_width_bad": frozenset({"pad.cb.width"}),
    "cb_width_at_limit": frozenset(),
    "cb_space_bad": frozenset({"pad.cb.space", "pad.rdl.space"}),
    "cb_space_at_limit": frozenset(),
    "cb_enc_bad": frozenset({"pad.cb.enclosure"}),
    "cb_enc_at_limit": frozenset(),
    "cover_width_bad": frozenset({"pad.cover.width", "pad.cover.length"}),
    "cover_width_at_limit": frozenset(),
    "cover_length_bad": frozenset({"pad.cover.length"}),
    "cover_length_at_limit": frozenset(),
    "cover_space_bad": frozenset({"pad.cover.space"}),
    "cover_space_at_limit": frozenset(),
    "cover_enc_alpa_bad": frozenset({"pad.cover.enc.alpa"}),
    "cover_enc_alpa_at_limit": frozenset(),
    "cover_pad_space_bad": frozenset({"pad.cover.t4m2.pad.space"}),
    "cover_pad_space_at_limit": frozenset(),
    "act_dummy_valid": frozenset(),
    "act_dummy_invalid": frozenset({"AADUM_W_1"}),
    "act_dummy_ct_overlap": frozenset({"AADUM_R_1", "AADUM_S_4"}),
    "poly_dummy_valid": frozenset(),
    "poly_dummy_invalid": frozenset({"PODUM_W_1"}),
    "m1_dummy_invalid": frozenset({"M1DUM_W_1"}),
    "t4m2_dummy_valid_rotated": frozenset(),
    "slot_cb_overlap": frozenset({
        "SL_R_1", "SL_W_1_L_1", "pad.cb.enclosure", "pad.cb.width",
    }),
    "efu_fuse_without_efuse": frozenset({"EFU_1b_G"}),
    "efu_efuse_uncovered_by_fuse": frozenset({"EFU_1c_G", "EFU_2b_G"}),
    "efu_po_block_uncovered": frozenset({"EFU_2c_G"}),
    "efu_nodrc_waived": frozenset(),
    "deupad_r2": frozenset({
        "DEUPAD_R_2", "DEUPAD_R_3", "DEUPAD_R_7", "pad.cb.enclosure", "pad.cb.width",
    }),
    "deupad_r2_nodrc_waived": frozenset({
        "DEUPAD_R_3", "DEUPAD_R_7", "pad.cb.enclosure", "pad.cb.width",
    }),
    "deupad_r5": frozenset({
        "DEUPAD_R_3", "DEUPAD_R_5", "DEUPAD_R_7", "pad.cb.enclosure", "pad.cb.width",
    }),
    "deupad_r6_v4bar": frozenset({
        "DEUPAD_R_3", "DEUPAD_R_6", "DEUPAD_R_7", "pad.cb.enclosure",
        "pad.cb.width", "via.v4.width",
    }),
    "deupad_r3_bad": frozenset({"DEUPAD_R_3"}),
    "deupad_r3_at_limit": frozenset(),
    "deupad_r7_bad": frozenset({"DEUPAD_R_7"}),
    "deupad_r7_at_limit": frozenset(),
    "esd_area": frozenset({"ESD_A_1"}),
    "esd_area_at_limit": frozenset(),
    "esd_area_nodrc_waived": frozenset(),
    "esd_hole": frozenset({"ESD_A_2"}),
    "esd_hole_at_limit": frozenset(),
    "esd_width_bad": frozenset({"ESD_W_1"}),
    "esd_width_at_limit": frozenset(),
    "esd_space_bad": frozenset({"ESD_S_1"}),
    "esd_space_at_limit": frozenset(),
    # ESD protection-device rules under the special profile. The implant
    # gate-space fixture also trips ESDN_10 because the 0.2 um implant gap is
    # below both 0.4 um thresholds; the gate-overlap fixture trips ESDN_10 for
    # the same reason and ESDN_11 by direct overlap (ESDN_9 is an EXT space
    # check, so an overlap is not a spacing violation).
    "esd_nmos_clean": frozenset(),
    "esd_nmos_ct_act_enc_bad": frozenset({"ESDN_1_SEDP_1"}),
    "esd_nmos_ct_act_enc_at_limit": frozenset(),
    "esd_nmos_ct_gate_space_bad": frozenset({"ESDN_1_SEDP_1", "ESDN_2_ESDP_2"}),
    "esd_nmos_ct_gate_space_at_limit": frozenset(),
    "esd_nmos_sab_gate_ovl_bad": frozenset({"ESDN_4_ESDP_4"}),
    "esd_nmos_sab_hole_gate_space_bad": frozenset({"ESDN_5_ESDP_5"}),
    "esd_nmos_sab_hole_gate_space_at_limit": frozenset(),
    "esd_nmos_sab_hole_ct_enc_bad": frozenset({"ESDN_6_ESDP_6"}),
    "esd_nmos_sab_act_space_bad": frozenset({"ESDN_7_ESDP_7"}),
    "esd_nmos_sab_hole_drain_enc_bad": frozenset({"ESDN_8_ESDP_8"}),
    "esd_nmos_sab_hole_drain_enc_at_limit": frozenset(),
    "esd_nmos_implant_gate_space_bad": frozenset({"ESDN_9", "ESDN_10"}),
    "esd_nmos_implant_act_enc_bad": frozenset({"ESDN_10"}),
    "esd_nmos_implant_gate_overlap_bad": frozenset({"ESDN_10", "ESDN_11"}),
    "esd_nmos_finger_width_bad": frozenset({"ESDN_12"}),
    "esd_nmos_finger_width_min_at_limit": frozenset(),
    "esd_nmos_finger_width_max_bad": frozenset({"ESDN_12"}),
    "esd_nmos_finger_width_max_at_limit": frozenset(),
    "esd_pmos_finger_width_bad": frozenset({"ESDP_9"}),
    "esd_hv_nmos_length_bad": frozenset({"ESDN_3"}),
    "esd_hv_nmos_length_at_limit": frozenset(),
    "esd_hv_pmos_length_low_bad": frozenset({"ESDP_3"}),
    "esd_hv_pmos_length_high_bad": frozenset({"ESDP_3"}),
    "esd_hv_pmos_length_at_limit": frozenset(),
    "esd_hv_pmos_length_max_at_limit": frozenset(),
    "density_act_low": frozenset({"ACT_D_1_min", "ACT_D_4_min"}),
    "density_act_small_low": frozenset({"ACT_D_1_min", "ACT_D_4_min"}),
    "density_act_exact_min": frozenset({"ACT_D_4_min"}),
    "density_act_exact_max": frozenset({"ACT_D_4_max"}),
    "density_act_near_min": frozenset({"ACT_D_1_min", "ACT_D_4_min"}),
    "density_act_near_max": frozenset({"ACT_D_1_max", "ACT_D_4_max"}),
    "density_backup_min": frozenset({"ACT_D_1_min"}),
    "density_nodrc_waived": frozenset(),
    "density_act_dummy_low": frozenset({"ACT_D_1_min", "ACT_D_2", "ACT_D_4_min"}),
    "density_m1_dummy_low": frozenset({"MET1_D_1_min", "MET1_D_2"}),
    "density_t4m2_dummy_low": frozenset({"T4M2_D_1_min", "T4M2_D_2"}),
    "mom_v1_m1mom": frozenset({"mom.MOM_R_1.V1.MET1MOM"}),
    "mom_v1bar_m1mom": frozenset({"mom.MOM_R_1.V1.MET1MOM"}),
    "mom_v1_nodrc_waived": frozenset(),
    "mom_forbidden_m1_cap23": frozenset({
        "mom.MOM_R_2.forbidden_stack.MET1MOM.23",
        "mom.MOM_R_2.missing_marker.23",
    }),
    "mom_cap12_missing_label": frozenset({"mom.MOM_R_2.label_stack.12"}),
    "mom_cap12_valid_label": frozenset(),
    "mom_cap12_missing_marker": frozenset({"mom.MOM_R_2.missing_marker.12"}),

    # Batch 5 dummy spacing / slot rules. The dummy-only S_6 fixtures leave a
    # floating NW, the AADUM_S_7 fixture uses bare FUSEALL, and the T4M2DUM
    # S_7/S_8 fixtures use dummies of another size class whose metal spacing
    # fires alongside the rule under test.
    "aadum_s1_bad": frozenset({"AADUM_S_1"}),
    "aadum_s1_at_limit": frozenset(),
    "aadum_s2_bad": frozenset({"AADUM_S_2"}),
    "aadum_s2_at_limit": frozenset(),
    "aadum_s3_bad": frozenset({"AADUM_S_3"}),
    "aadum_s3_at_limit": frozenset(),
    "aadum_s4_bad": frozenset({"AADUM_S_4"}),
    "aadum_s4_at_limit": frozenset(),
    "aadum_s5_bad": frozenset({"AADUM_S_5"}),
    "aadum_s5_at_limit": frozenset(),
    "aadum_s6_bad": frozenset({"AADUM_S_6", "well.nw.floating"}),
    "aadum_s6_at_limit": frozenset({"well.nw.floating"}),
    "aadum_s7_bad": frozenset({"AADUM_S_7", "EFU_1b_G"}),
    "aadum_s7_at_limit": frozenset({"EFU_1b_G"}),
    "aadum_s8_bad": frozenset({"AADUM_S_8"}),
    "aadum_s8_at_limit": frozenset(),
    "aadum_s9_bad": frozenset({"AADUM_S_9"}),
    "aadum_s9_at_limit": frozenset(),
    "aadum_s10_bad": frozenset({"AADUM_S_10"}),
    "aadum_s10_at_limit": frozenset(),
    "aadum_s11_bad": frozenset({"AADUM_S_11", "CHIPEDGE_EN_1"}),
    "aadum_s11_at_limit": frozenset({"CHIPEDGE_EN_1"}),
    "aadum_s12_bad": frozenset({"AADUM_S_12"}),
    "aadum_s12_at_limit": frozenset(),
    "aadum_s13_bad": frozenset({"AADUM_S_13"}),
    "aadum_s13_at_limit": frozenset(),
    "podum_s1_bad": frozenset({"PODUM_S_1"}),
    "podum_s1_at_limit": frozenset(),
    "podum_s2_bad": frozenset({"PODUM_S_2"}),
    "podum_s2_at_limit": frozenset(),
    "podum_s3_bad": frozenset({"PODUM_S_3"}),
    "podum_s3_at_limit": frozenset(),
    "podum_s4_bad": frozenset({"PODUM_S_4"}),
    "podum_s4_at_limit": frozenset(),
    "podum_s5_bad": frozenset({"PODUM_S_5"}),
    "podum_s5_at_limit": frozenset(),
    "podum_s6_bad": frozenset({"PODUM_S_6", "well.nw.floating"}),
    "podum_s6_at_limit": frozenset({"well.nw.floating"}),
    "podum_s7_bad": frozenset({"PODUM_S_7"}),
    "podum_s7_at_limit": frozenset(),
    "podum_s8_bad": frozenset({"PODUM_S_8"}),
    "podum_s8_at_limit": frozenset(),
    "podum_s9_bad": frozenset({"PODUM_S_9"}),
    "podum_s9_at_limit": frozenset(),
    "podum_s10_bad": frozenset({"CHIPEDGE_EN_1", "PODUM_S_10"}),
    "podum_s10_at_limit": frozenset({"CHIPEDGE_EN_1"}),
    "podum_s11_bad": frozenset({"PODUM_S_11"}),
    "podum_s11_at_limit": frozenset(),
    "podum_s12_bad": frozenset({"PODUM_S_12"}),
    "podum_s12_at_limit": frozenset(),
    "t4m2dum_s1_bad": frozenset({"T4M2DUM_S_1"}),
    "t4m2dum_s1_at_limit": frozenset(),
    "t4m2dum_s2_bad": frozenset({"T4M2DUM_S_2"}),
    "t4m2dum_s2_at_limit": frozenset(),
    "t4m2dum_s3_bad": frozenset({"T4M2DUM_S_3"}),
    "t4m2dum_s3_at_limit": frozenset(),
    "t4m2dum_s4_bad": frozenset({"T4M2DUM_S_4"}),
    "t4m2dum_s4_at_limit": frozenset(),
    "t4m2dum_s5_bad": frozenset({"T4M2DUM_S_5"}),
    "t4m2dum_s5_at_limit": frozenset(),
    "t4m2dum_s6_bad": frozenset({"T4M2DUM_S_6"}),
    "t4m2dum_s6_at_limit": frozenset(),
    "t4m2dum_s7_bad": frozenset({"T4M2DUM_S_2", "T4M2DUM_S_7"}),
    "t4m2dum_s7_at_limit": frozenset({"T4M2DUM_S_2"}),
    "t4m2dum_s8_bad": frozenset({"T4M2DUM_S_4", "T4M2DUM_S_8"}),
    "t4m2dum_s8_at_limit": frozenset({"T4M2DUM_S_4"}),
    "t4m2dum_s9_bad": frozenset({"EFU_1b_G", "T4M2DUM_S_9"}),
    "t4m2dum_s9_at_limit": frozenset({"EFU_1b_G"}),
    "t4m2dum_s10_bad": frozenset({"T4M2DUM_S_10"}),
    "t4m2dum_s10_at_limit": frozenset(),
    "t4m2dum_s11_bad": frozenset({"T4M2DUM_S_11"}),
    "t4m2dum_s11_at_limit": frozenset(),
    "t4m2dum_s12_bad": frozenset({"T4M2DUM_S_12"}),
    "t4m2dum_s12_at_limit": frozenset(),
    "t4m2dum_s13_bad": frozenset({"T4M2DUM_S_13"}),
    "t4m2dum_s13_at_limit": frozenset(),
    "chipedge_en1_bad": frozenset({"CHIPEDGE_EN_1"}),
    "chipedge_en1_at_limit": frozenset(),
    "chipedge_en2_bad": frozenset({"CHIPEDGE_EN_2"}),
    "chipedge_en2_at_limit": frozenset(),
    "chipedge_en3_bad": frozenset({"CHIPEDGE_EN_3"}),
    "chipedge_en3_at_limit": frozenset(),
    "t4m2dum_s14_bad": frozenset({"T4M2DUM_S_14"}),
    "t4m2dum_s14_at_limit": frozenset(),
    "t4m2dum_s15_bad": frozenset({"T4M2DUM_S_15"}),
    "t4m2dum_s15_at_limit": frozenset(),
    "sl_s_1_bad": frozenset({"SL_S_1"}),
    "sl_s_1_at_limit": frozenset(),
    "sl_w_1_l_1_bad": frozenset({"SL_W_1_L_1"}),
    "sl_w_1_l_1_at_limit": frozenset(),
    "srck_m1_at_limit": frozenset(),
    "srck_m1_bad": frozenset({"SRCK_3_M", "SRCK_4_M", "SRCK_5_M", "SRCK_6_M"}),
    "srck_t4m2_at_limit": frozenset(),
    "srck_t4m2_bad": frozenset({
        "SRCK_3_T4M2", "SRCK_4_T4M2", "SRCK_5_T4M2", "SRCK_6_T4M2",
    }),
    "srck_rdl_at_limit": frozenset(),
    "srck_rdl_bad": frozenset({"SRCK_7_RDL", "SRCK_8_RDL"}),
    "srck_rv_at_limit": frozenset(),
    "srck_rv_edge_bad": frozenset({"SRCK_9_RV"}),
    "srck_rv_width_bad": frozenset({"SRCK_10_RV"}),
    "srck_ct_at_limit": frozenset(),
    "srck_ct_bar_enc_bad": frozenset({"SRCK_14a_CT"}),
    "srck_ct_square_enc_bad": frozenset({"SRCK_15a_CT"}),
    "srck_ct_space_bad": frozenset({"SRCK_16a"}),
    "srck_ct_square_size_bad": frozenset({"SRCK_13a"}),
    "srck_ct_bar_width_bad": frozenset({"SRCK_11a"}),
    "srck_v1_at_limit": frozenset(),
    "srck_v1_bad": frozenset({
        "SRCK_13b_13c", "SRCK_14b_14c", "SRCK_15b_v1", "SRCK_16b_16c",
    }),
    "srck_v1_bar_width_bad": frozenset({"SRCK_11b"}),
    "srck_v2_bad": frozenset({"SRCK_14b_14c"}),
    "srck_tv2_at_limit": frozenset(),
    "srck_tv2_bad": frozenset({
        "SRCK_13e_13f", "SRCK_14d_14e_14f", "SRCK_15d_15e_15f",
        "SRCK_16d_16e_16f",
    }),
    "srck_tv2_bar_width_bad": frozenset({"SRCK_11d_12e"}),

    # --- Batch 9: TG/DG gate-oxide markers ---
    "tg_width_bad": frozenset({"TG_W_1"}),
    "tg_width_at_limit": frozenset(),
    "tg_space_bad": frozenset({"TG_S_1"}),
    "tg_space_at_limit": frozenset(),
    "tg_mos_space_bad": frozenset({"TG_S_2"}),
    "tg_mos_space_at_limit": frozenset(),
    "tg_gate_space_bad": frozenset({
        "TG_S_3",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "tg_gate_space_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "tg_nw_space_bad": frozenset({"TG_S_4"}),
    "tg_nw_space_at_limit": frozenset(),
    "tg_psub_space_bad": frozenset({"TG_S_5"}),
    "tg_psub_space_at_limit": frozenset(),
    "tg_nw_ext_bad": frozenset({
        "TG_EX_1",
        "well.nw.lv.space",
    }),
    "tg_nw_ext_at_limit": frozenset({
        "well.nw.lv.space",
    }),
    "tg_nw_ext2_bad": frozenset({"TG_EX_2"}),
    "tg_nw_ext2_at_limit": frozenset(),
    "tg_psub_ext_bad": frozenset({"TG_EX_3"}),
    "tg_psub_ext_at_limit": frozenset(),
    "tg_nw_overlap_bad": frozenset({"TG_O_1"}),
    "tg_nw_overlap_at_limit": frozenset(),
    "tg_psub_overlap_bad": frozenset({"TG_O_2"}),
    "tg_psub_overlap_at_limit": frozenset(),
    "tg_aa_enc_bad": frozenset({
        "TG_EN_1",
        "TG_EN_2",
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.tg_n",
    }),
    "tg_aa_enc_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.tg_n",
    }),
    "tg_aa_gate_enc_bad": frozenset({
        "TG_EN_3",
        "implant.np.gate_aa.enclosure",
        "implant.np.gate_ext",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.length.tg_n",
    }),
    "tg_aa_gate_enc_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.np.gate_ext",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.length.tg_n",
    }),
    "dg_width_bad": frozenset({"DG_W_1"}),
    "dg_width_at_limit": frozenset(),
    "dg_space_bad": frozenset({"DG_S_1"}),
    "dg_space_at_limit": frozenset(),
    "dg_mos_space_bad": frozenset({"DG_S_2"}),
    "dg_mos_space_at_limit": frozenset(),
    "dg_gate_space_bad": frozenset({
        "DG_S_3",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "dg_gate_space_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "dg_nw_space_bad": frozenset({"DG_S_4"}),
    "dg_nw_space_at_limit": frozenset(),
    "dg_psub_space_bad": frozenset({"DG_S_5"}),
    "dg_psub_space_at_limit": frozenset(),
    "dg_nw_ext_bad": frozenset({
        "DG_EX_1",
        "well.nw.lv.space",
    }),
    "dg_nw_ext_at_limit": frozenset({
        "well.nw.lv.space",
    }),
    "dg_nw_ext2_bad": frozenset({"DG_EX_2"}),
    "dg_nw_ext2_at_limit": frozenset(),
    "dg_psub_ext_bad": frozenset({"DG_EX_3"}),
    "dg_psub_ext_at_limit": frozenset(),
    "dg_nw_overlap_bad": frozenset({"DG_O_1"}),
    "dg_nw_overlap_at_limit": frozenset(),
    "dg_psub_overlap_bad": frozenset({"DG_O_2"}),
    "dg_psub_overlap_at_limit": frozenset(),
    "dg_aa_enc_bad": frozenset({
        "DG_EN_1",
        "DG_EN_2",
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.dg",
    }),
    "dg_aa_enc_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.length.dg",
    }),
    "dg_aa_gate_enc_bad": frozenset({
        "DG_EN_3",
        "implant.np.gate_aa.enclosure",
        "implant.np.gate_ext",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.length.dg",
    }),
    "dg_aa_gate_enc_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "implant.np.gate_ext",
        "latchup.guard_ring",
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.length.dg",
    }),
    # The shared TG-to-DG space and overlap checks both report TG_S_6.
    "tg_dg_space_bad": frozenset({"TG_S_6"}),
    "tg_dg_space_at_limit": frozenset(),
    "tg_dg_overlap": frozenset({"TG_S_6"}),

    # --- Batch 9: SAB ---
    "sab_width_bad": frozenset({"SAB_W_1"}),
    "sab_width_at_limit": frozenset(),
    "sab_space_bad": frozenset({"SAB_S_1"}),
    "sab_space_at_limit": frozenset(),
    "sab_po_space_bad": frozenset({"SAB_S_2"}),
    "sab_po_space_at_limit": frozenset(),
    "sab_aa_space_bad": frozenset({"SAB_S_3"}),
    "sab_aa_space_at_limit": frozenset(),
    "sab_gate_space_bad": frozenset({
        "SAB_S_4",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "sab_gate_space_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "sab_aa_ext_bad": frozenset({"SAB_EX_1"}),
    "sab_aa_ext_at_limit": frozenset(),
    "sab_aa_ext_outside_bad": frozenset({"SAB_EX_2"}),
    "sab_aa_ext_outside_at_limit": frozenset(),
    "sab_field_poly_space_bad": frozenset({"SAB_S_5"}),
    "sab_field_poly_space_at_limit": frozenset(),
    "sab_field_poly_ext_bad": frozenset({"SAB_EX_3"}),
    "sab_field_poly_ext_at_limit": frozenset(),
    "sab_ct_space_bad": frozenset({"SAB_S_6"}),
    "sab_ct_space_at_limit": frozenset(),
    "sab_area_bad": frozenset({"SAB_A_1"}),
    "sab_area_at_limit": frozenset(),
    "sab_hole_bad": frozenset({"SAB_A_2"}),
    "sab_hole_at_limit": frozenset(),
    # SAB over GATE trips both the overlap clause of S_4 and R_2.
    "sab_gate_overlap_bad": frozenset({
        "SAB_R_2",
        "SAB_S_4",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.endcap",
    }),
    # Coincident SAB edges intentionally trip the whole coupled family.
    "sab_coincident_poly_bad": frozenset({"SAB_EX_3", "SAB_R_1", "SAB_S_5"}),
    "sab_coincident_aa_bad": frozenset({"SAB_EX_1", "SAB_EX_2", "SAB_R_1", "SAB_S_3"}),

    # --- Batch 9: HRP ---
    "hrp_width_bad": frozenset({"HRP_W_1"}),
    "hrp_width_at_limit": frozenset(),
    "hrp_space_bad": frozenset({"HRP_S_1"}),
    "hrp_space_at_limit": frozenset(),
    "hrp_poly_width_bad": frozenset({"HRP_W_2"}),
    "hrp_poly_width_at_limit": frozenset(),
    "hrp_po_space_bad": frozenset({
        "HRP_S_2",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "hrp_po_space_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "hrp_sab_ct_space_bad": frozenset({
        "HRP_S_3",
        "poly.po.implant",
    }),
    "hrp_sab_ct_space_at_limit": frozenset({
        "poly.po.implant",
    }),
    "hrp_pp_sab_ovl_bad": frozenset({"HRP_O_1"}),
    "hrp_pp_sab_ovl_at_limit": frozenset(),
    "hrp_po_enc_bad": frozenset({"HRP_EN_1"}),
    "hrp_po_enc_at_limit": frozenset(),
    # SAB beyond the resistor POLY also trips the SAB field-poly extension.
    "hrp_sab_ext_bad": frozenset({"HRP_EX_1", "SAB_EX_3"}),
    "hrp_sab_ext_at_limit": frozenset(),
    "hrp_np_mid_bad": frozenset({"HRP_R_1"}),
    "hrp_sab_align_bad": frozenset({"HRP_R_2"}),

    # --- Batch 9: ULLD ---
    "ulld_width_bad": frozenset({"ULLD_W_1"}),
    "ulld_width_at_limit": frozenset(),
    "ulld_space_bad": frozenset({"ULLD_S_1"}),
    "ulld_space_at_limit": frozenset(),
    "ulld_gate_space_bad": frozenset({
        "ULLD_EX_3b",
        "ULLD_S_5",
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "ulld_gate_space_at_limit": frozenset({
        "ULLD_EX_3b",
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "ulld_ex1_bad": frozenset({"ULLD_EX_1"}),
    "ulld_ex1_at_limit": frozenset(),
    "ulld_ex2_bad": frozenset({
        "ULLD_EX_2",
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "ulld_ex2_at_limit": frozenset({
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "ulld_ex3a_bad": frozenset({
        "ULLD_EX_3a",
        "ULLD_EX_3b",
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "ulld_ex3a_at_limit": frozenset({
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "ulld_area_bad": frozenset({"ULLD_A_1"}),
    "ulld_area_at_limit": frozenset(),
    "ulld_hole_bad": frozenset({"ULLD_A_2"}),
    "ulld_hole_at_limit": frozenset(),
    # The AA-space fixtures also trip the tighter S_6 AA-direction limit.
    "ulld_aa_space_bad": frozenset({"ULLD_S_2", "ULLD_S_6"}),
    "ulld_aa_space_at_limit": frozenset(),
    "ulld_nact_space_bad": frozenset({"ULLD_S_4", "ULLD_S_6"}),
    "ulld_nact_space_at_limit": frozenset(),
    "ulld_r2_bad": frozenset({"ULLD_R_2"}),
    "ulld_psub_overlap_bad": frozenset({"ULLD_R_1"}),

    # --- Batch 9: voltage-class implants ---
    "nvt1_width_bad": frozenset({"NVT1_W_1"}),
    "nvt1_space_bad": frozenset({"NVT1_S_1"}),
    "nvt1_aa_space_bad": frozenset({"NVT1_S_3"}),
    "nvt1_gate_space_bad": frozenset({
        "NVT1_S_2",
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "nvt1_gate_ext_bad": frozenset({
        "NVT1_EX_1",
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "nvt1_aa_gate_ext_bad": frozenset({
        "NVT1_EX_2",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "nvt1_area_bad": frozenset({"NVT1_A_1"}),
    "nvt1_hole_bad": frozenset({"NVT1_A_2"}),
    "nvt1_psub_overlap_bad": frozenset({"NVT1_R_1"}),
    "nvt3_width_bad": frozenset({"NVT3_W_1"}),
    "nvt3_space_bad": frozenset({"NVT3_S_1"}),
    "nvt3_aa_space_bad": frozenset({"NVT3_S_3"}),
    "nvt3_gate_space_bad": frozenset({
        "NVT3_S_2",
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "nvt3_gate_ext_bad": frozenset({
        "NVT3_EX_1",
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "nvt3_aa_gate_ext_bad": frozenset({
        "NVT3_EX_2",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "nvt3_area_bad": frozenset({"NVT3_A_1"}),
    "nvt3_hole_bad": frozenset({"NVT3_A_2"}),
    "nvt3_psub_overlap_bad": frozenset({"NVT3_R_1"}),
    "pvt1_width_bad": frozenset({"PVT1_W_1"}),
    "pvt1_space_bad": frozenset({"PVT1_S_1"}),
    "pvt1_aa_space_bad": frozenset({"PVT1_S_3"}),
    "pvt1_gate_space_bad": frozenset({
        "PVT1_S_2",
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "pvt1_gate_ext_bad": frozenset({
        "PVT1_EX_1",
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "pvt1_aa_gate_ext_bad": frozenset({
        "PVT1_EX_2",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "pvt1_area_bad": frozenset({"PVT1_A_1"}),
    "pvt1_hole_bad": frozenset({"PVT1_A_2"}),
    "pvt1_psub_overlap_bad": frozenset({"PVT1_R_1"}),
    "pvt3_width_bad": frozenset({"PVT3_W_1"}),
    "pvt3_space_bad": frozenset({"PVT3_S_1"}),
    "pvt3_aa_space_bad": frozenset({"PVT3_S_3"}),
    "pvt3_gate_space_bad": frozenset({
        "PVT3_S_2",
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "pvt3_gate_ext_bad": frozenset({
        "PVT3_EX_1",
        "active.act.u_space",
        "implant.pp.gate_aa.enclosure",
        "poly.po.endcap",
    }),
    "pvt3_aa_gate_ext_bad": frozenset({"PVT3_EX_2", "implant.pp.gate_aa.enclosure"}),
    "pvt3_area_bad": frozenset({"PVT3_A_1"}),
    "pvt3_hole_bad": frozenset({"PVT3_A_2"}),
    "pvt3_psub_overlap_bad": frozenset({"PVT3_R_1"}),
    "nvt3_sab_aa_space_bad": frozenset({"NVT3_S_4"}),
    "nvt3_sab_aa_space_at_limit": frozenset(),
    "pvt3_sab_aa_space_bad": frozenset({"PVT3_S_4"}),
    "pvt3_sab_aa_space_at_limit": frozenset(),
    # NVT1 carries the full at-limit set; the other families are bad-only.
    "nvt1_width_at_limit": frozenset(),
    "nvt1_space_at_limit": frozenset(),
    "nvt1_aa_space_at_limit": frozenset(),
    "nvt1_gate_space_at_limit": frozenset({
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "nvt1_gate_ext_at_limit": frozenset({
        "active.act.u_space",
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
        "poly.po.endcap",
    }),
    "nvt1_aa_gate_ext_at_limit": frozenset({
        "implant.np.gate_aa.enclosure",
        "latchup.s2_ptap",
    }),
    "nvt1_sab_aa_space_bad": frozenset({"NVT1_S_4"}),
    "nvt1_sab_aa_space_at_limit": frozenset(),
    "nvt1_area_at_limit": frozenset(),
    "nvt1_hole_at_limit": frozenset(),

    # --- Batch 9: DGR_3 (INDDMY waiver) ---
    "dgr_3_bad": frozenset({"DGR_3"}),
    "dgr_3_inddmy_waived": frozenset(),
    "dgr_3_45_ok": frozenset(),

    # --- Batch 9: Calibre-semantics approximations ---
    "act_u_shape_bad": frozenset({"active.act.u_space"}),
    "act_u_shape_at_limit": frozenset(),
    "act_o_shape_bad": frozenset({"active.act.o_space", "active.act.u_space"}),
    "act_o_shape_at_limit": frozenset(),
    "act_l1_ct_bad": frozenset({"active.act.max_length_ct"}),
    "act_l1_ct_at_limit": frozenset(),
    "act_l1_end_bad": frozenset({"active.act.max_length_end"}),
    "act_l1_end_at_limit": frozenset(),
    "act_l2_bad": frozenset({"active.act.sd_length"}),
    "act_l2_at_limit": frozenset(),
    "po_l1_ct_bad": frozenset({
        "poly.po.ct_length",
        "poly.po.implant",
        "poly.po.wide_space",
    }),
    "po_l1_ct_at_limit": frozenset({
        "poly.po.implant",
        "poly.po.wide_space",
    }),
    "po_l1_end_bad": frozenset({
        "poly.po.implant",
        "poly.po.length",
        "poly.po.wide_space",
    }),
    "po_l1_end_at_limit": frozenset({
        "poly.po.implant",
        "poly.po.wide_space",
    }),
    "po_l1_gate_bad": frozenset({
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.endcap",
        "poly.po.gate_length",
        "poly.po.implant",
    }),
    "po_l1_gate_at_limit": frozenset({
        "latchup.s2_ptap",
        "poly.po.aa_ext",
        "poly.po.endcap",
        "poly.po.implant",
    }),
    "np_s6_bad": frozenset({"implant.np.ptap_gate.space",
                            "implant.pp.gate_space",
                            "implant.np.gate_ext"}),
    "np_s6_at_limit": frozenset(),
    "pp_s6_bad": frozenset({"implant.pp.ntap_gate.space",
                            "implant.np.gate_space",
                            "implant.pp.gate_ext"}),
    "pp_s6_at_limit": frozenset(),
    "np_ex1_bad": frozenset({"implant.np.gate_aa.enclosure"}),
    "np_ex1_at_limit": frozenset(),
    "pp_ex1_bad": frozenset({"implant.pp.gate_aa.enclosure"}),
    "pp_ex1_at_limit": frozenset(),
    "np_ex1a_bad": frozenset({
        "implant.np.gate_ext",
        "poly.po.aa_ext",
    }),
    "np_ex1a_at_limit": frozenset(),
    "pp_ex1a_bad": frozenset({
        "implant.pp.gate_ext",
        "poly.po.aa_ext",
    }),
    "pp_ex1a_at_limit": frozenset(),
    "pp_r3_bad": frozenset({"implant.np_pp.sab_coincident"}),
    "pp_r3_at_limit": frozenset(),
    "dnw_s3_bad": frozenset({
        "well.dnw.nw.coverage",
        "well.dnw.nw.space",
        "well.dnw.tpw.floating",
        "well.dnw.tpw.space",
    }),
    "dnw_s3_at_limit": frozenset({
        "well.dnw.nw.coverage",
        "well.dnw.nw.space",
        "well.dnw.tpw.floating",
    }),
    "dnw_s4_bad": frozenset({
        "well.dnw.nw.coverage",
        "well.dnw.nw.space",
        "well.dnw.pw_dgtg.space",
        "well.dnw.tpw.floating",
        "well.dnw.tpw.space",
        "well.dnw.tpw_dgtg.space",
    }),
    "dnw_s4_at_limit": frozenset({
        "well.dnw.nw.coverage",
        "well.dnw.nw.space",
        "well.dnw.tpw.floating",
    }),
    "mom_s1_bad": frozenset({"mom.MOM_S_1.V1.MET1MOM"}),
    "mom_s1_at_limit": frozenset(),
    # Antenna ratios (separate netlist-extraction deck). Two cumulative-via
    # fixtures also trip the single-layer limit: with each via at or below the
    # single limit (0.2 um^2 on a 0.01 um^2 gate) the cumulative sum of VIA1+VIA2
    # cannot exceed 0.5 um^2, so isolating AR_6_9_VIA1/VIA2 is impossible.
    "ant_clean": frozenset(),
    "ant_ar1_bad": frozenset({"antenna.AR_1"}),
    "ant_ar1_at_limit": frozenset(),
    "ant_ar2_bad": frozenset({"antenna.AR_2"}),
    "ant_ar2_at_limit": frozenset(),
    "ant_ar3_bad": frozenset({"antenna.AR_3"}),
    "ant_ar3_at_limit": frozenset(),
    "ant_m1_bad": frozenset({"antenna.AR_5_10_M1"}),
    "ant_m1_at_limit": frozenset(),
    "ant_m1_18_bad": frozenset({"antenna.AR18_5_10_M1"}),
    "ant_m1_18_at_limit": frozenset(),
    "ant_m2_bad": frozenset({"antenna.AR_5_10_M2"}),
    "ant_m2_at_limit": frozenset(),
    "ant_m2_18_bad": frozenset({"antenna.AR18_5_10_M2"}),
    "ant_m2_18_at_limit": frozenset(),
    "ant_m3_bad": frozenset({"antenna.AR_5_10_M3"}),
    "ant_m3_18_bad": frozenset({"antenna.AR18_5_10_M3"}),
    "ant_m4_bad": frozenset({"antenna.AR_5_10_M4"}),
    "ant_m4_18_bad": frozenset({"antenna.AR18_5_10_M4"}),
    "ant_m5_bad": frozenset({"antenna.AR_5_10_M5"}),
    "ant_m5_18_bad": frozenset({"antenna.AR18_5_10_M5"}),
    "ant_t4m2_bad": frozenset({"antenna.AR_5_10_T4M2"}),
    "ant_t4m2_18_bad": frozenset({"antenna.AR18_5_10_T4M2"}),
    "ant_via1_bad": frozenset({"antenna.AR_4_VIA1"}),
    "ant_via1_at_limit": frozenset(),
    "ant_via1_cum_bad": frozenset({"antenna.AR_4_VIA1", "antenna.AR_6_9_VIA1"}),
    "ant_via2_bad": frozenset({"antenna.AR_4_VIA2"}),
    "ant_via2_cum_bad": frozenset({"antenna.AR_4_VIA1", "antenna.AR_6_9_VIA2"}),
    "ant_via3_bad": frozenset({"antenna.AR_4_VIA3"}),
    "ant_via3_cum_bad": frozenset({"antenna.AR_6_9_VIA3"}),
    "ant_via4_bad": frozenset({"antenna.AR_4_VIA4"}),
    "ant_via4_cum_bad": frozenset({"antenna.AR_6_9_VIA4"}),
    "ant_t4v2_bad": frozenset({"antenna.AR_4_T4V2"}),
    "ant_t4v2_at_limit": frozenset(),
    "ant_t4v2_cum_bad": frozenset({"antenna.AR_6_9_T4V2"}),
    "ant_t4v2_cum_at_limit": frozenset(),
    "ant_rdv_io_bad": frozenset({"antenna.AR_7_11_io"}),
    "ant_rdv_io_at_limit": frozenset(),
    "ant_rdv_core_bad": frozenset({"antenna.AR_7_11_core"}),
    "ant_rdv_core_at_limit": frozenset(),
    "ant_rdl_bad": frozenset({"antenna.AR_8_12"}),
    "ant_rdl_at_limit": frozenset(),
    "ant_m1_diode_waived": frozenset(),
    "ant_m1_diode_boundary": frozenset({"antenna.AR_5_10_M1"}),
    "ant_stage_split": frozenset({"antenna.AR_5_10_M1", "antenna.AR_5_10_M2"}),
    # Batch 10: resistor, latch-up, via-hbar, thick-metal and recommended.
    "resistor_aa_width_bad": frozenset({"resistor.aa.width"}),
    "via_v1_hbar_bad": frozenset({"via.v1.hbar"}),
    "latchup_guard_width_bad": frozenset({"latchup.guard_width"}),
    "thick_t4m1_width_bad": frozenset({"T4M1_W_1"}),
    "recommended_act_spacing_bad": frozenset({"ACT_S_1_R"}),
    # Batch 11: PO/well/via/resistor/latch-up fixtures for the batch-10 rules.
    # Minimal geometry also trips unrelated implant coverage, gate-extension,
    # CT-coverage and latch-up tap rules; those incidental categories are
    # recorded rather than waived.
    "po_core_length_bad": frozenset({
        "active.act.implant_coverage", "poly.po.length.core", "poly.poly.width"}),
    "po_dg_length_bad": frozenset({"active.act.implant_coverage", "poly.po.length.dg"}),
    "po_tg_length_bad": frozenset({"implant.np.gate_aa.enclosure", "poly.po.length.tg_n"}),
    "po_field45_bad": frozenset({"poly.po.field45.space", "poly.po.field45.width"}),
    "po_wide_space_bad": frozenset({"poly.po.wide_space"}),
    "po_aa_space_bad": frozenset({
        "active.act.implant_coverage", "poly.po.aa_space", "poly.poly.spacing"}),
    "po_endcap_bad": frozenset({"active.act.implant_coverage", "poly.po.endcap"}),
    "po_bent_bad": frozenset({"active.act.implant_coverage", "poly.po.bent"}),
    "po_implant_bad": frozenset({
        "active.act.implant_coverage", "cont.ct.active.coverage",
        "cont.ct.poly.aa.space", "poly.po.implant"}),
    "po_sab_space_bad": frozenset({"SAB_EX_3", "poly.po.sab_space"}),
    "po_line_end_bad": frozenset({"poly.po.line_end"}),
    "po_large_space_bad": frozenset({
        "implant.np.gate_aa.enclosure", "latchup.s2_ptap", "poly.po.large_space"}),
    "po_aa_ext_bad": frozenset({"active.act.implant_coverage", "poly.po.aa_ext"}),
    "po_sti_space_bad": frozenset({"poly.po.sti_space"}),
    "po_tg_space_bad": frozenset({
        "TG_EN_1", "implant.np.gate_aa.enclosure",
        "poly.po.length.tg_n", "poly.po.tg_space"}),
    "well_nw_lv_bad": frozenset({"well.nw.floating", "well.nw.lv.space"}),
    "well_nw_hv_bad": frozenset({
        "TG_EX_2", "TG_S_1", "well.nw.floating",
        "well.nw.hv.diff_space", "well.nw.hv.space"}),
    "well_nw_lv_hv_bad": frozenset({
        "TG_EX_2", "TG_S_4", "well.nw.floating", "well.nw.lv_hv.space"}),
    "well_dnw_nw_bad": frozenset({
        "well.dnw.nw.coverage", "well.dnw.nw.space", "well.dnw.tpw.floating",
        "well.dnw.width", "well.nw.floating"}),
    "via_tv2_no_upper_bad": frozenset({"via.tv2.cover.upper"}),
    "via_tv2_no_lower_bad": frozenset({"via.tv2.cover.lower"}),
    "via_tv2_rotated_bad": frozenset({"via.tv2.rotated", "via.tv2.width"}),
    "ct_diff_net_space_bad": frozenset({"cont.ct.spacing.diff_net"}),
    "podum_ct_bad": frozenset({"PODUM_R_1", "cont.ct.inside"}),
    "thick_t4m2_dummy_bad": frozenset({"T4M2DUM_W_1"}),
    "resistor_aa_body_bad": frozenset({
        "SAB_EX_2", "SAB_W_1", "implant.np.act.overlap",
        "implant.np.nact_pw.enclosure", "resistor.aa.implant_enc",
        "resistor.aa.marker_ext", "resistor.aa.width"}),
    "resistor_aa_silicide_bad": frozenset({"resistor.aa.silicide_ct"}),
    "resistor_aa_pp_nw_bad": frozenset({"SAB_EX_2", "resistor.aa.pp_nw"}),
    "resistor_aa_dogbone_bad": frozenset({"SAB_EX_2", "resistor.aa.dogbone"}),
    "resistor_nw_width_bad": frozenset({
        "cont.ct.sab", "resistor.nw.count",
        "resistor.nw.width", "resistor.nw_sti.marker_ext"}),
    "resistor_nw_sti_width_bad": frozenset({
        "resistor.nw.sab_cover", "resistor.nw_sti.aa_touch", "resistor.nw_sti.width"}),
    "resistor_poly_width_bad": frozenset({"SAB_EX_3", "resistor.poly.width"}),
    "resistor_poly_squares_bad": frozenset({"SAB_EX_3", "resistor.poly.squares"}),
    "latchup_s2_ntap_bad": frozenset({
        "implant.pp.gate_aa.enclosure", "latchup.s2_ntap", "well.nw.floating"}),
    "latchup_s2_ptap_bad": frozenset({"implant.np.gate_aa.enclosure", "latchup.s2_ptap"}),
    "latchup_s1_bad": frozenset({
        "TG_EN_3", "active.act.implant_coverage",
        "implant.np.gate_aa.enclosure", "implant.pp.gate_aa.enclosure",
        "latchup.guard_ring", "latchup.s1a", "latchup.s1c", "latchup.s1d",
        "poly.po.length.tg_n", "poly.po.length.tg_p"}),
    "density_t4m2_high_bad": frozenset({"T4M2_D_1_max"}),
}
FIXTURE_PROFILES = {
    name: (
        "antenna" if name.startswith("ant_")
        else "density" if name.startswith("density_")
        else "mom" if name.startswith("mom_")
        else "special" if name.startswith(("esd_nmos_", "esd_pmos_", "esd_hv_"))
        else "beol"
    )
    for name in FIXTURES
    if name.startswith(("density_", "mom_", "srck_", "esd_nmos_", "esd_pmos_",
                        "esd_hv_", "ant_"))
}
FIXTURE_PROFILES.update({
    "via_v1_hbar_bad": "beol",
    "via_tv2_no_upper_bad": "beol",
    "via_tv2_no_lower_bad": "beol",
    "via_tv2_rotated_bad": "beol",
    "thick_t4m1_width_bad": "t4m1",
    "recommended_act_spacing_bad": "recommended",
})

RULE_INPUTS = [
    DRC_DECK,
    ANTENNA_DECK,
    *sorted((ROOT / "libs.tech" / "drc" / "rule_decks").rglob("*.drc")),
    ROOT / "libs.tech" / "drc" / "rule_decks" / "ics55_rules.json",
    ROOT / "techfile" / "icsprout55.layermap",
    ROOT / "libs.tech" / "klayout" / "tech" / "ics55.map",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_klayout(args) -> tuple[str, str] | None:
    """Return (kind, executable) with kind 'bin' (direct) or 'nix' (nix shell)."""
    if args.klayout:
        return ("bin", args.klayout) if shutil.which(args.klayout) else None
    if args.librelane and Path(args.librelane).exists() and shutil.which("nix-shell"):
        return ("nix", str(args.librelane))
    if shutil.which("klayout"):
        return ("bin", "klayout")
    return None

def get_klayout_version(kind: str, exe: str) -> str | None:
    if kind == "nix":
        cmd = nix_shell_command(exe, ["klayout", "-v"])
    else:
        cmd = [exe, "-v"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return None
    if run.returncode != 0:
        return None
    return next(
        (line.strip() for line in (run.stdout + "\n" + run.stderr).splitlines()
         if line.strip().startswith("KLayout ")),
        None,
    )


def run_klayout(kind: str, exe: str, script: Path, extra: list[str]) -> subprocess.CompletedProcess:
    base = ["-b", "-r", str(script)] + extra
    if kind == "nix":
        cmd = nix_shell_command(exe, ["klayout"] + base)
    else:
        cmd = [exe] + base
    return subprocess.run(cmd, capture_output=True, text=True)


def run_drc(kind: str, exe: str, gds: Path, report: Path, profile: dict[str, Any]) -> subprocess.CompletedProcess:
    deck = ANTENNA_DECK if profile.get("deck") == "antenna" else DRC_DECK
    switches = [] if "tables" not in profile else ["-rd", f"tables={profile['tables']}"]
    switches.extend(
        argument
        for key, value in profile.items()
        if key not in ("tables", "deck")
        for argument in ("-rd", f"{key}={str(value).lower()}")
    )
    extra = ["-rd", f"input={gds}", "-rd", "top=TOP", "-rd", f"report={report}"] + switches
    base = ["-b", "-r", str(deck)] + extra
    if kind == "nix":
        cmd = nix_shell_command(exe, ["klayout"] + base)
    else:
        cmd = [exe] + base
    return subprocess.run(cmd, capture_output=True, text=True)


def read_violation_categories(report: Path) -> list[str]:
    """Item categories from a KLayout .lyrdb (XML)."""
    root = ET.parse(report).getroot()
    cats = []
    for item in root.findall(".//item"):
        cat = item.findtext("category", "")
        cats.append(cat.strip("'").strip())
    return sorted(set(c for c in cats if c))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--librelane", default=Path.home() / "Documents" / "librelane")
    ap.add_argument("--klayout", default=None)
    ap.add_argument("--out", default=ROOT / "tests" / "regression" / "out" / "drc_fixtures")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1),
                    help="parallel fixture runs (default: min(4, CPUs))")
    args = ap.parse_args()
    args.librelane = str(Path(args.librelane).expanduser()) if args.librelane else None

    klayout = find_klayout(args)
    out_dir = Path(args.out).resolve()
    fx_dir = out_dir / "fixtures"
    fx_dir.mkdir(parents=True, exist_ok=True)

    if not klayout:
        (out_dir / "drc_fixture_check.json").write_text(json.dumps({
            "schema": "ics55-drc-fixture-check/1.3",
            "status": "BLOCKED",
            "reason": "KLayout not found (PATH, --klayout, or --librelane nix shell)",
        }, indent=2))
        print("BLOCKED (KLayout not found)")
        return 2

    kind, exe = klayout
    version = get_klayout_version(kind, exe)
    if version is None:
        (out_dir / "drc_fixture_check.json").write_text(json.dumps({
            "schema": "ics55-drc-fixture-check/1.3",
            "status": "BLOCKED",
            "klayout": {"kind": kind, "executable": exe},
            "reason": "KLayout version could not be recorded",
        }, indent=2))
        print("BLOCKED (KLayout version unavailable)")
        return 2

    # generate fixtures with klayout itself (no hand-rolled GDS writer)
    gen = run_klayout(kind, exe, MAKE_FIXTURES, ["-rd", f"out={fx_dir}"])
    if gen.returncode != 0:
        (out_dir / "drc_fixture_check.json").write_text(json.dumps({
            "schema": "ics55-drc-fixture-check/1.3",
            "status": "BLOCKED",
            "reason": f"fixture generation failed: {gen.stderr.strip().splitlines()[-3:]}",
        }, indent=2))
        print("BLOCKED (fixture generation failed)")
        return 2

    def check_fixture(item: tuple[str, frozenset[str]]) -> dict[str, Any]:
        name, expected = item
        profile_name = FIXTURE_PROFILES.get(name, "main")
        profile = DRC_PROFILES[profile_name]
        # KLayout itself is multithreaded; one thread per process avoids
        # oversubscription when several fixtures run at once.
        if args.jobs > 1:
            profile = dict(profile, threads=1)
        gds = fx_dir / f"{name}.gds"
        report = fx_dir / f"{name}.lyrdb"
        # Do not let a prior run's report mask a failed or incomplete run.
        report.unlink(missing_ok=True)
        r = run_drc(kind, exe, gds, report, profile)
        rec: dict[str, Any] = {
            "fixture": name,
            "profile": profile_name,
            "expected_categories": sorted(expected),
        }
        if gds.exists():
            rec["gds_sha256"] = sha256(gds)
        if r.returncode != 0 or not report.exists():
            rec["status"] = "BLOCKED"
            detail = r.stderr.strip().splitlines()[-3:] or ["no stderr"]
            rec["reason"] = f"DRC run failed (rc={r.returncode}): {' | '.join(detail)}"
            return rec
        try:
            cats = read_violation_categories(report)
        except Exception as e:
            rec["status"] = "BLOCKED"
            rec["reason"] = f"lyrdb parse failed: {e}"
            return rec
        rec["categories"] = cats
        expected_categories = set(expected or ())
        actual_categories = set(cats)
        missing = sorted(expected_categories - actual_categories)
        unexpected = sorted(actual_categories - expected_categories)
        rec["status"] = "PASS" if not missing and not unexpected else "FAIL"
        if missing or unexpected:
            rec["issues"] = []
            if missing:
                rec["issues"].append(f"expected categories absent: {missing}")
            if unexpected:
                rec["issues"].append(f"unexpected categories present: {unexpected}")
        return rec

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(check_fixture, FIXTURES.items()))
    if any(r["status"] == "BLOCKED" for r in results):
        rc = 2
    elif any(r["status"] == "FAIL" for r in results):
        rc = 1
    else:
        rc = 0

    profile_sha256 = hashlib.sha256(
        json.dumps(DRC_PROFILES, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (out_dir / "drc_fixture_check.json").write_text(json.dumps({
        "schema": "ics55-drc-fixture-check/1.3",
        "status": "PASS" if rc == 0 else ("FAIL" if rc == 1 else "BLOCKED"),
        "profiles": DRC_PROFILES,
        "jobs": args.jobs,
        "klayout": {"kind": kind, "executable": exe, "version": version},
        "profile_sha256": profile_sha256,
        "rule_inputs_sha256": {
            str(path.relative_to(ROOT)): sha256(path) for path in RULE_INPUTS
        },
        "results": results,
        "deck_sha256": sha256(DRC_DECK),
        "antenna_deck_sha256": sha256(ANTENNA_DECK),
        "fixture_generator_sha256": sha256(MAKE_FIXTURES),
        "fixture_runner_sha256": sha256(Path(__file__).resolve()),
    }, indent=2))
    for r in results:
        print(f"{r['status']:9s} {r['fixture']}" + (f"  - {r.get('issues')}" if r.get("issues") else ""))
    return rc


if __name__ == "__main__":
    sys.exit(main())
