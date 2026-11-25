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
# Hierarchical macro LVS fixture (KLayout RBA, 1 nm database unit).
#
# Writes magic_hier.gds with one top cell:
#
#   MAGIC_HIER  one INVX1H7R instance at the identity transform, plus a small
#               M1 pad and an M1 label at each child pin centre.  The pads
#               exist only so `extract`/`esMakePorts` can attach the
#               top-level pin names; they do not change the child topology.
#
# Also writes magic_hier.cdl: the released H7CR standard-cell CDL followed by
# `.SUBCKT MAGIC_HIER`, i.e. the shape a macro LVS reference needs (children
# plus the macro top).  run_lvs.py reaches the same result with --library.
#
# Usage:
#   klayout -b -r magic_hier_fixture.rb -rd out=<dir>

require 'fileutils'

OUT = File.expand_path($out || '.')
FileUtils.mkdir_p(OUT)

PDK = File.expand_path('../..', __dir__)
SRC_GDS = File.join(PDK, 'libs.ref/ics55_LLSC_H7CR/gds/ics55_LLSC_H7CR.gds')
SRC_CDL = File.join(PDK, 'libs.ref/ics55_LLSC_H7CR/cdl/ics55_LLSC_H7CR.cdl')

M1 = [81, 1].freeze
M1LBL = [81, 6].freeze

# Child pin centres in MAGIC_HIER coordinates (nm).
PINS = {
  'A' => [100, 700],
  'Y' => [500, 900],
  'VDD' => [200, 1400],
  'VSS' => [200, 0],
}.freeze

layout = RBA::Layout.new
layout.dbu = 0.001
layout.read(SRC_GDS)

inv = layout.cell('INVX1H7R')
top = layout.create_cell('MAGIC_HIER')
top.insert(RBA::CellInstArray.new(inv.cell_index, RBA::Trans.new))

PINS.each do |name, (x, y)|
  top.shapes(layout.layer(*M1)).insert(RBA::Box.new(x - 20, y - 20, x + 20, y + 20))
  text = RBA::Text.new
  text.move(RBA::Point.new(x, y))
  text.string = name
  top.shapes(layout.layer(*M1LBL)).insert(text)
end

gds = File.join(OUT, 'magic_hier.gds')
layout.write(gds)
puts "wrote #{gds} (#{top.bbox})"

cdl = File.join(OUT, 'magic_hier.cdl')
File.open(cdl, 'w') do |io|
  io.write(File.read(SRC_CDL))
  io.write("\n.SUBCKT MAGIC_HIER A VDD VSS Y\n")
  io.write("XINV_0 A VDD VSS Y INVX1H7R\n")
  io.write(".ENDS\n")
end
puts "wrote #{cdl}"
