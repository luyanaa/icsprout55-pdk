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
# Folded poly-resistor fixture (KLayout RBA, 1 nm database unit).
#
# Writes magic_resistor.gds with one cell:
#
#   SNAKE  four 3.64 x 1.0 um silicide-blocked p+ poly segments
#          (POLY 41/1, POLYres 41/4, SAB 71/1, PP 53/1), wired in series
#          by alternating M1 straps, with POS/NEG labels.
#
# Magic extracts four `re_ppo_sab_2t` segments (w=1 um, l=3.64 um each);
# run_lvs.py rewrites them to primitive R devices and netgen's series
# combination folds them into the CDL's W=1u L=14.56u.
#
# Usage:
#   klayout -b -r magic_resistor_fixture.rb -rd out=<dir>

require 'fileutils'

OUT = File.expand_path($out || '.')
FileUtils.mkdir_p(OUT)

L = {
  'PP'      => [53, 1],
  'POLY'    => [41, 1],
  'POLYRES' => [41, 4],
  'SAB'     => [71, 1],
  'CT'      => [72, 1],
  'M1'      => [81, 1],
  'M1LBL'   => [81, 6],
}

def box(x0, y0, x1, y1)
  RBA::Box.new((x0 * 1000).round, (y0 * 1000).round, (x1 * 1000).round, (y1 * 1000).round)
end

def rect(ly, cell, layer, x0, y0, x1, y1)
  cell.shapes(ly.layer(*L[layer])).insert(box(x0, y0, x1, y1))
end

def label(ly, cell, text, x, y)
  t = RBA::Text.new
  t.move(RBA::Point.new((x * 1000).round, (y * 1000).round))
  t.string = text
  cell.shapes(ly.layer(*L['M1LBL'])).insert(t)
end

ly = RBA::Layout.new
ly.dbu = 0.001
cell = ly.create_cell('SNAKE')

xs, xe = 1.0, 4.64
h = 1.0
ew = 0.2
ys = [0.0, 1.72, 3.44, 5.16]

ys.each do |y|
  rect(ly, cell, 'POLY', xs - ew, y, xe + ew, y + h)
  rect(ly, cell, 'POLYRES', xs, y, xe, y + h)
  rect(ly, cell, 'SAB', xs, y, xe, y + h)
  rect(ly, cell, 'PP', xs, y, xe, y + h)
  rect(ly, cell, 'CT', xs - ew + 0.05, y + 0.1, xs - 0.05, y + 0.9)
  rect(ly, cell, 'CT', xe + 0.05, y + 0.1, xe + ew - 0.05, y + 0.9)
end

rect(ly, cell, 'M1', xs - ew - 0.1, -0.2, xs, ys[0] + h + 0.2)
rect(ly, cell, 'M1', xe - 0.15, ys[0] - 0.2, xe + ew + 0.1, ys[1] + h + 0.2)
rect(ly, cell, 'M1', xs - ew - 0.1, ys[1] - 0.2, xs + 0.15, ys[2] + h + 0.2)
rect(ly, cell, 'M1', xe - 0.15, ys[2] - 0.2, xe + ew + 0.1, ys[3] + h + 0.2)
rect(ly, cell, 'M1', xs - ew - 0.1, ys[3] - 0.2, xs + 0.15, ys[3] + h + 0.2)

label(ly, cell, 'POS', xs - ew + 0.02, 0.5)
label(ly, cell, 'NEG', xs - ew + 0.02, ys[3] + 0.5)

gds = File.join(OUT, 'magic_resistor.gds')
ly.write(gds)
puts "wrote #{gds}"
