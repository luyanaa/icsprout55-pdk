#!/usr/bin/env ruby
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
#
# Magic tech connectivity fixtures (KLayout RBA, 1 nm database unit).
#
# Writes magic_fixtures.gds with two top cells:
#
#   MAGIC_STACK  contact/via stacks drawn at *exactly* the same centre at
#                every level of the 1P6M1TM stack.  A coincident contact and
#                via must collapse to one extracted node; without
#                `stackable` Magic drops the lower contact.
#   MAGIC_TAP    an n+ tap inside nwell (must extract as an nw node) and a
#                p+ tap in the p-substrate (must extract as `substrate`).
#
# Usage:
#   klayout -b -r magic_fixtures.rb -rd out=<dir>

require 'fileutils'

OUT = File.expand_path($out || '.')
FileUtils.mkdir_p(OUT)

LAYERS = {
  'NW'   => [9, 1],
  'ACT'  => [2, 1],
  'NP'   => [52, 1],
  'PP'   => [53, 1],
  'POLY' => [41, 1],
  'CT'   => [72, 1],
  'M1'   => [81, 1],
  'V1'   => [91, 1],
  'M2'   => [82, 1],
  'V2'   => [92, 1],
  'M3'   => [83, 1],
  'V3'   => [93, 1],
  'M4'   => [84, 1],
  'V4'   => [94, 1],
  'M5'   => [85, 1],
  'TV2'  => [113, 1],
  'TM2'  => [103, 1],
}.freeze

def rect(layout, cell, layer, x1, y1, x2, y2)
  info = LAYERS.fetch(layer)
  cell.shapes(layout.layer(*info)).insert(
    RBA::Box.new((x1 * 1000).round, (y1 * 1000).round,
                 (x2 * 1000).round, (y2 * 1000).round)
  )
end

def text(layout, cell, layer, label, x, y)
  info = LAYERS.fetch(layer)
  cell.shapes(layout.layer(*info)).insert(
    RBA::Text.new(label, RBA::Trans.new((x * 1000).round, (y * 1000).round))
  )
end

layout = RBA::Layout.new
layout.dbu = 0.001

stack_cell = layout.create_cell('MAGIC_STACK')
tap_cell = layout.create_cell('MAGIC_TAP')

# ---------------------------------------------------------------------------
# MAGIC_STACK: every contact/via pair coincident at the same centre.
# ---------------------------------------------------------------------------
# A: poly -> CT -> M1 -> V1 -> M2  (CT and V1 share one centre)
rect(layout, stack_cell, 'POLY', -1.5, -1, 1.5, 1)
rect(layout, stack_cell, 'CT', -0.045, -0.045, 0.045, 0.045)
rect(layout, stack_cell, 'M1', -1.5, -1, 1.5, 1)
rect(layout, stack_cell, 'V1', -0.045, -0.045, 0.045, 0.045)
rect(layout, stack_cell, 'M2', -1.5, -1, 1.5, 1)
text(layout, stack_cell, 'POLY', 'P_CT_V1', -1, 0.5)
text(layout, stack_cell, 'M2', 'M2_CT_V1', 1, 0.5)

# B: M1 -> V1 -> M2 -> V2 -> M3  (V1 and V2 share one centre)
rect(layout, stack_cell, 'M1', 8.5, -1, 11.5, 1)
rect(layout, stack_cell, 'V1', 9.955, -0.045, 10.045, 0.045)
rect(layout, stack_cell, 'M2', 8.5, -1, 11.5, 1)
rect(layout, stack_cell, 'V2', 9.955, -0.045, 10.045, 0.045)
rect(layout, stack_cell, 'M3', 8.5, -1, 11.5, 1)
text(layout, stack_cell, 'M1', 'M1_V1_V2', 9, 0.5)
text(layout, stack_cell, 'M3', 'M3_V1_V2', 11, 0.5)

# C: M2 -> V2 -> M3 -> V3 -> M4
rect(layout, stack_cell, 'M2', 18.5, -1, 21.5, 1)
rect(layout, stack_cell, 'V2', 19.955, -0.045, 20.045, 0.045)
rect(layout, stack_cell, 'M3', 18.5, -1, 21.5, 1)
rect(layout, stack_cell, 'V3', 19.955, -0.045, 20.045, 0.045)
rect(layout, stack_cell, 'M4', 18.5, -1, 21.5, 1)
text(layout, stack_cell, 'M2', 'M2_V2_V3', 19, 0.5)
text(layout, stack_cell, 'M4', 'M4_V2_V3', 21, 0.5)

# D: M3 -> V3 -> M4 -> V4 -> M5
rect(layout, stack_cell, 'M3', 28.5, -1, 31.5, 1)
rect(layout, stack_cell, 'V3', 29.955, -0.045, 30.045, 0.045)
rect(layout, stack_cell, 'M4', 28.5, -1, 31.5, 1)
rect(layout, stack_cell, 'V4', 29.955, -0.045, 30.045, 0.045)
rect(layout, stack_cell, 'M5', 28.5, -1, 31.5, 1)
text(layout, stack_cell, 'M3', 'M3_V3_V4', 29, 0.5)
text(layout, stack_cell, 'M5', 'M5_V3_V4', 31, 0.5)

# E: M4 -> V4 -> M5 -> TV2 -> TM2
rect(layout, stack_cell, 'M4', 38.5, -1, 41.5, 1)
rect(layout, stack_cell, 'V4', 39.955, -0.045, 40.045, 0.045)
rect(layout, stack_cell, 'M5', 38.5, -1, 41.5, 1)
rect(layout, stack_cell, 'TV2', 39.955, -0.045, 40.045, 0.045)
rect(layout, stack_cell, 'TM2', 38.5, -1, 41.5, 1)
text(layout, stack_cell, 'M4', 'M4_V4_TV2', 39, 0.5)
text(layout, stack_cell, 'TM2', 'TM2_V4_TV2', 41, 0.5)

# ---------------------------------------------------------------------------
# MAGIC_TAP: n+ tap in nwell and p+ tap in the substrate.
# ---------------------------------------------------------------------------
# nwell tap: NW + ACT + NP + CT + M1
rect(layout, tap_cell, 'NW', -2, -2, 2, 2)
rect(layout, tap_cell, 'ACT', -1, -1, 1, 1)
rect(layout, tap_cell, 'NP', -1, -1, 1, 1)
rect(layout, tap_cell, 'CT', -0.045, -0.045, 0.045, 0.045)
rect(layout, tap_cell, 'M1', -0.5, -0.5, 0.5, 0.5)
text(layout, tap_cell, 'M1', 'VDDTAP', 0, 0)
# an isolated nwell with no tap (must stay a separate nw node)
rect(layout, tap_cell, 'NW', -2, 5, 2, 9)

# p+ tap in the p-substrate: ACT + PP + CT + M1 (no NW)
rect(layout, tap_cell, 'ACT', -1, 11, 1, 13)
rect(layout, tap_cell, 'PP', -1, 11, 1, 13)
rect(layout, tap_cell, 'CT', -0.045, 11.955, 0.045, 12.045)
rect(layout, tap_cell, 'M1', -0.5, 11.5, 0.5, 12.5)
text(layout, tap_cell, 'M1', 'VSSTAP', 0, 12)

# ---------------------------------------------------------------------------
# MAGIC_CAP_*: one 10x10 um plate per cell, used to calibrate the area and
# perimeter capacitance in the extract section.  Separate cells keep the
# per-layer labels unambiguous (coincident stacked plates would attach every
# label to the highest plane).
# ---------------------------------------------------------------------------
{ 'M1' => 'm1', 'M2' => 'm2', 'TM2' => 'tm2' }.each do |suffix, layer|
  cell = layout.create_cell("MAGIC_CAP_#{suffix}")
  rect(layout, cell, layer.upcase, 0, 0, 10, 10)
  text(layout, cell, layer.upcase, "P_#{layer}", 5, 5)
end

layout.write(File.join(OUT, 'magic_fixtures.gds'))
puts "wrote #{File.join(OUT, 'magic_fixtures.gds')}"
