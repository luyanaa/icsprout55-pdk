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

# ICsprout55 GDS rule-value measurement (per-cell).
#
# Measures the drawn minimum width / spacing / area of every layer and the
# minimum separation / enclosure of selected layer pairs.  Measurements are
# taken per cell (the library GDS places all cells at the origin, so
# library-wide merging would connect shapes of different cells), then reduced
# to the library minimum with the observing cell recorded for provenance.
#
# The foundry's own cells are DRC-clean, so drawn minima bound the design
# rules.  Values are recorded as `gds` provenance in
# libs.tech/drc/rule_decks/ics55_rules.json.
#
# Usage:
#   klayout -b -r tools/measure_gds.rb \
#     -rd input=<library.gds> -rd out=measurements_<lib>.json
#
# Output JSON (lengths um, areas um^2):
#   {
#     "gds": "<path>", "cells": 785,
#     "layers": {
#       "ACT": { "min_width_um": 0.09, "min_space_um": 0.11, "min_area_um2": 0.08,
#                "min_width_cell": "INVX1H7R", "min_space_cell": "..." }
#     },
#     "seps": { "POLY:ACT": { "min_sep_um": 0.05, "min_sep_cell": "..." } },
#     "encs": { "NW:ACT":  { "min_enc_um": 0.04, "min_enc_cell": "..." } },
#     "gates": { "min_gate_width_um": 0.06, "min_poly_ext_um": ..., "min_act_enc_gate_um": ... }
#   }

require 'json'

DBU_UM = 0.001
# Drop degenerate fill/tap slivers (e.g. FILLTAPH7R draws sub-resolution shapes
# on every layer).  Real features are >= CT (0.0081 um^2) / gate (0.06*L) size;
# anything below 0.004 um^2 is a fill artifact, not a rule-defining feature.
AREA_MIN_DBU2 = (0.004 / (DBU_UM * DBU_UM)).round

LAYERS = {
  "ACT"    => [2, 1],   "NW"     => [9, 1],   "LVTN"   => [17, 1],
  "LVTP"   => [18, 1],  "HVTN"   => [21, 1],  "HVTP"   => [22, 1],
  "IOWELL" => [28, 1],  "POLY"   => [41, 1],  "PPO"    => [41, 4],
  "NP"     => [52, 1],  "PP"     => [53, 1],  "ESD"    => [55, 1],
  "IOACT"  => [71, 1],  "CT"     => [72, 1],  "M1"     => [81, 1],
  "M2"     => [82, 1],  "M3"     => [83, 1],  "M4"     => [84, 1],
  "M5"     => [85, 1],  "V1"     => [91, 1],  "V2"     => [92, 1],
  "V3"     => [93, 1],  "V4"     => [94, 1],  "TM2"    => [103, 1],
  "TV2"    => [113, 1], "PADM"   => [120, 1], "ALPAD"  => [121, 1]
}

SEP_PAIRS = [
  %w[POLY ACT], %w[POLY NP], %w[POLY PP], %w[POLY NW],
  %w[ACT NP], %w[ACT PP], %w[ACT NW], %w[NP PP],
  %w[CT POLY], %w[CT ACT], %w[CT M1], %w[CT NP], %w[CT PP],
  %w[M1 V1], %w[V1 M2], %w[M2 V2], %w[V2 M3], %w[M3 V3], %w[V3 M4],
  %w[M4 V4], %w[V4 M5], %w[M5 TV2], %w[TV2 TM2],
  %w[ESD NW], %w[ESD PP], %w[IOACT NP], %w[IOACT PP], %w[IOACT NW], %w[IOWELL ACT]
]

ENC_PAIRS = [
  %w[NW ACT], %w[NW PP], %w[NP ACT], %w[PP ACT], %w[NP CT], %w[PP CT],
  %w[POLY CT], %w[ACT CT], %w[M1 CT], %w[M1 V1], %w[M2 V1], %w[M2 V2],
  %w[M3 V2], %w[M3 V3], %w[M4 V3], %w[M4 V4], %w[M5 V4], %w[M5 TV2],
  %w[TM2 TV2], %w[IOWELL IOACT], %w[IOWELL ACT], %w[NW ESD], %w[ALPAD PADM]
]

def um(dbu)
  (dbu * DBU_UM).round(4)
end

# Largest d (dbu) with zero violations => min value = d + 1 dbu.
def min_violating(check, hi_dbu)
  lo = 0
  hi = hi_dbu
  15.times do
    mid = (lo + hi) / 2
    if check.call(mid).zero?
      lo = mid
    else
      hi = mid
    end
  end
  lo + 1
end

def min_area_um2(region)
  min_a = nil
  region.each do |poly|
    a = poly.area * DBU_UM * DBU_UM
    min_a = a if min_a.nil? || a < min_a
  end
  min_a&.round(6)
end

def keep_min(best, key, value, cell)
  if best[key].nil? || value < best[key][0]
    best[key] = [value, cell]
  end
end

def measure(ly, cells)
  out = { "cells" => cells.size, "layers" => {}, "seps" => {}, "encs" => {}, "gates" => {} }
  layer_best = {}
  sep_best = {}
  enc_best = {}
  gate_best = {}

  regs = {}
  LAYERS.each_key { |name| regs[name] = [] }

  # per-cell regions for every layer of interest
  cells.each do |ci|
    # fill/tap cells draw serrated sub-resolution fill patterns (1 nm necks on
    # large-area combs); they define no design rules - exclude them
    next if ci.name =~ /FILL|TAP/

    LAYERS.each do |name, (l, d)|
      li = ly.find_layer(RBA::LayerInfo.new(l, d))
      next if li.nil?

      sh = ci.shapes(li)
      next if sh.size.zero?

      r = RBA::Region.new
      ci.shapes(li).each do |s|
        next unless s.is_polygon? || s.is_box?

        p = s.polygon
        r.insert(p) if p.area >= AREA_MIN_DBU2
      end
      next if r.count.zero?

      regs[name] << [ci.name, r]
    end
  end

  # per-cell width / space / area minima
  LAYERS.each_key do |name|
    next if regs[name].empty?

    layer_best = {}
    cells_regs = regs[name]
    cells_regs.each do |cname, r|
      raw = r
      # cells with huge regular arrays (IO via fills) do not set new minima -
      # their drawn features match the small cells' minima; skip their search
      next if raw.count > 5000

      keep_min(layer_best, :width, um(min_violating(->(d0) { raw.width_check(d0).size }, 400)), cname)
      keep_min(layer_best, :space, um(min_violating(->(d0) { raw.space_check(d0).size }, 400)), cname)
      keep_min(layer_best, :area, min_area_um2(raw), cname) if min_area_um2(raw)
    end
    out["layers"][name] = {
      "min_width_um" => layer_best[:width] && layer_best[:width][0],
      "min_width_cell" => layer_best[:width] && layer_best[:width][1],
      "min_space_um" => layer_best[:space] && layer_best[:space][0],
      "min_space_cell" => layer_best[:space] && layer_best[:space][1],
      "min_area_um2" => layer_best[:area] && layer_best[:area][0],
      "min_area_cell" => layer_best[:area] && layer_best[:area][1],
      "cells_with_layer" => cells_regs.size
    }
    puts "  layer #{name}: width=#{out['layers'][name]['min_width_um']} (#{out['layers'][name]['min_width_cell']}) space=#{out['layers'][name]['min_space_um']} (#{out['layers'][name]['min_space_cell']})"
  end

  # per-cell separation / enclosure minima
  SEP_PAIRS.each do |a, b|
    next if regs[a].empty? || regs[b].empty?
    # via-fill arrays (100k+ shapes) are regular: pair spacing follows the
    # array pitch and adds nothing beyond the LEF via rules - skip
    next if regs[a].sum { |_n, r| r.count } > 100_000 || regs[b].sum { |_n, r| r.count } > 100_000

    regs[a].each do |an, ra|
      regs[b].each do |bn, rb|
        next unless an == bn

        d = min_violating(->(d0) { ra.separation_check(rb, d0).size }, 400)
        keep_min(sep_best, "#{a}:#{b}", um(d), an) if d < 400
      end
    end
    if sep_best["#{a}:#{b}"]
      out["seps"]["#{a}:#{b}"] = { "min_sep_um" => sep_best["#{a}:#{b}"][0], "min_sep_cell" => sep_best["#{a}:#{b}"][1] }
    end
  end

  ENC_PAIRS.each do |a, b|
    next if regs[a].empty? || regs[b].empty?
    next if regs[a].sum { |_n, r| r.count } > 100_000 || regs[b].sum { |_n, r| r.count } > 100_000

    regs[a].each do |an, ra|
      regs[b].each do |bn, rb|
        next unless an == bn

        d = min_violating(->(d0) { ra.enclosing_check(rb, d0).size }, 300)
        keep_min(enc_best, "#{a}:#{b}", um(d), an) if d < 300
      end
    end
    if enc_best["#{a}:#{b}"]
      out["encs"]["#{a}:#{b}"] = { "min_enc_um" => enc_best["#{a}:#{b}"][0], "min_enc_cell" => enc_best["#{a}:#{b}"][1] }
    end
  end

  # gate interactions (per cell, both POLY and ACT present)
  if regs["POLY"].any? && regs["ACT"].any?
    regs["POLY"].each do |cn, rp|
      ra = regs["ACT"].assoc(cn)&.last
      next if ra.nil?

      gates = rp.and(ra)
      next if gates.size.zero?

      keep_min(gate_best, :gate_width, um(min_violating(->(d0) { gates.width_check(d0).size }, 300)), cn)
    end
    out["gates"] = {
      "min_gate_width_um" => gate_best[:gate_width] && gate_best[:gate_width][0],
      "min_gate_width_cell" => gate_best[:gate_width] && gate_best[:gate_width][1]
    }
    puts "  gates: L=#{out['gates']['min_gate_width_um']}"
  end

  out
end

ly = RBA::Layout.new
ly.read($input)
cells = []
ly.each_cell { |ci| cells << ci }
result = measure(ly, cells)
result["gds"] = $input.to_s
File.write($out, JSON.pretty_generate(result))
puts "measured #{cells.size} cells -> #{$out}"
