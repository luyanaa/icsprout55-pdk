# ============================================================================
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
# ============================================================================
# Netgen LVS setup file for the ICsprout55 55nm LLULP 1P6M1TM process.
#
# This file is sourced by `netgen` (via the `lvs` proc).  It must define the
# `cells1` and `cells2` lists: LibreLane's `netgen/setup.tcl` sources this
# file and then uses them to equate cell-name prefixes and to apply
# LVS_FLATTEN_CELLS / LVS_IGNORE_CELLS.
#
# Device classes are the official CDL model names emitted by the Magic tech
# file (`libs.tech/magic/ics55.tech`):
#
#   nm1p2_svt_lp / pm1p2_svt_lp   H7CR core, regular Vt
#   nm1p2_lvt_lp / pm1p2_lvt_lp   H7CL core, low Vt
#   nm1p2_hvt_lp / pm1p2_hvt_lp   H7CH core, high Vt
#   nm3p3_lp     / pm3p3_lp       3.3V IO
#
# The property tolerance matches the official KLayout LVS deck
# (`libs.tech/lvs/ics55.lvs`): L is compared exactly, W uses the released
# 10% relative tolerance.  The foundry still ships cells whose drawn widths
# deviate more than 10% from the CDL (OAI33, INVX7, INVX16); netgen reports
# those truthfully as property errors - see `libs.tech/lvs/README.md`.
# ============================================================================

permute default
property default
property parallel none

# Allow override of default #columns in the output format.
catch {format $env(NETGEN_COLUMNS)}

#---------------------------------------------------------------
# Cell lists for the LibreLane setup wrapper.
#---------------------------------------------------------------
set cells1 [cells list -all -circuit1]
set cells2 [cells list -all -circuit2]

#---------------------------------------------------------------
# MOS devices.
#---------------------------------------------------------------
set devices {}
lappend devices nm1p2_svt_lp
lappend devices pm1p2_svt_lp
lappend devices nm1p2_lvt_lp
lappend devices pm1p2_lvt_lp
lappend devices nm1p2_hvt_lp
lappend devices pm1p2_hvt_lp
lappend devices nm3p3_lp
lappend devices pm3p3_lp

foreach dev $devices {
    if {[lsearch $cells1 $dev] >= 0} {
	# Fingers of one large device share D/G/S/B; merging them lets a
	# single-device CDL entry (INVX16 and similar) compare against the
	# multi-finger layout.  Different source/drain nets never merge.
	property "-circuit1 $dev" parallel enable
	property "-circuit1 $dev" tolerance {w 0.10} {l 0.01}
	# Diffusion area/perimeter are extraction-only; the CDL does not
	# carry them, and they must never influence the compare.
	property "-circuit1 $dev" delete ad as pd ps
    }
    if {[lsearch $cells2 $dev] >= 0} {
	property "-circuit2 $dev" parallel enable
	property "-circuit2 $dev" tolerance {w 0.10} {l 0.01}
	property "-circuit2 $dev" delete ad as pd ps
    }
}

#---------------------------------------------------------------
# Junction diodes (IO ESD diodes).
#
# The CDL gives each diode an M multiplier and a per-instance AREA/PJ;
# netgen expands M into parallel devices, so `parallel enable` merges them
# back into the single continuous junction that Magic extracts.  The
# official Calibre deck compares A/P with `dio_err` = 10% relative
# tolerance; netgen's tolerance is also relative.
#---------------------------------------------------------------
set diode_devices {}
lappend diode_devices dio_1p2_pp_nw_lvt_lp
lappend diode_devices dio_1p2_np_pw_lvt_lp
lappend diode_devices dio_3p3_pp_nw_lp

foreach dev $diode_devices {
    if {[lsearch $cells1 $dev] >= 0} {
	# Netgen multiplies an "add" property by the device multiplier M
	# while combining parallel devices (see netcmp.c), which turns the
	# CDL's per-finger AREA/PJ into the total junction geometry that
	# Magic extracts after the parallel merge.
	property "-circuit1 $dev" merge {area add} {pj add}
	property "-circuit1 $dev" parallel enable
	property "-circuit1 $dev" tolerance {area 0.10} {pj 0.10}
    }
    if {[lsearch $cells2 $dev] >= 0} {
	property "-circuit2 $dev" merge {area add} {pj add}
	property "-circuit2 $dev" parallel enable
	property "-circuit2 $dev" tolerance {area 0.10} {pj 0.10}
    }
}

#---------------------------------------------------------------
# Poly resistors (silicide-blocked p+ poly, `re_ppo_sab_2t`).
#
# A wide resistor is drawn as several parallel poly segments, and a
# folded one as several series segments.  `property default` already
# marks `l` series-add / parallel-critical and `w` series-critical, but
# its parallel rule for `w` is the harmonic resistor formula; a wider
# resistor needs the widths to add (4u || 4u = 8u), so override the
# parallel width combine to "add" and enable parallel merging.
#---------------------------------------------------------------
set resistor_devices {}
lappend resistor_devices re_ppo_sab_2t

foreach dev $resistor_devices {
    foreach circuit {-circuit1 -circuit2} {
	if {[lsearch [expr {$circuit eq "-circuit1" ? $cells1 : $cells2}] $dev] >= 0} {
	    property "$circuit $dev" parallel {w add}
	    property "$circuit $dev" parallel enable
	}
    }
}
