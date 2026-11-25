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
# Diode extraction fixture (KLayout RBA, 1 nm database unit).
#
# Writes magic_diode.gds with two top cells:
#
#   MAGIC_PDIO  2.0 x 5.0 um p+ junction inside nwell (DIODE 191/12, PVT1),
#               contacted p+ anode and an n+ nwell tap as cathode.
#               Junction area 10.0 um^2, perimeter 14.0 um.
#   MAGIC_NDIO  2.5 x 4.0 um n+ junction in the p substrate (DIODE, NVT1),
#               contacted n+ cathode and a p+ substrate tap as anode.
#               Junction area 10.0 um^2, perimeter 13.0 um.
#   MAGIC_TAPS  contacted n+ tap in nwell and p+ tap in the substrate, with
#               no DIODE marker.  Must extract zero diodes: a shared contact
#               tile that leaks the diode device mask produces one bogus
#               diode per cut here.
#
# The junction rectangles are fully covered by CT arrays, which is the case
# that splits a device region that lives on the active plane; the derived
# junction therefore lives on its own `diodeactive` plane.
#
# Usage:
#   klayout -b -r magic_diode_fixture.rb -rd out=<dir>

require 'fileutils'

OUT = File.expand_path($out || '.')
FileUtils.mkdir_p(OUT)

L = {
  'ACT'   => [2, 1],
  'NW'    => [9, 1],
  'NVT1'  => [17, 1],
  'PVT1'  => [18, 1],
  'NP'    => [52, 1],
  'PP'    => [53, 1],
  'CT'    => [72, 1],
  'M1'    => [81, 1],
  'M1LBL' => [81, 6],
  'DIODE' => [191, 12],
}

def box(x0, y0, x1, y1)
  RBA::Box.new((x0 * 1000).round, (y0 * 1000).round, (x1 * 1000).round, (y1 * 1000).round)
end

def rect(ly, cell, layer, x0, y0, x1, y1)
  cell.shapes(ly.layer(*L[layer])).insert(box(x0, y0, x1, y1))
end

def label(ly, cell, layer, text, x, y)
  t = RBA::Text.new
  t.move(RBA::Point.new((x * 1000).round, (y * 1000).round))
  t.string = text
  cell.shapes(ly.layer(*L[layer])).insert(t)
end

def ct_array(ly, cell, x0, y0, x1, y1, pitch = 0.2, size = 0.09)
  x = x0 + 0.1
  while x + size / 2 <= x1
    y = y0 + 0.1
    while y + size / 2 <= y1
      rect(ly, cell, 'CT', x - size / 2, y - size / 2, x + size / 2, y + size / 2)
      y += pitch
    end
    x += pitch
  end
end

ly = RBA::Layout.new
ly.dbu = 0.001

# ---------------------------------------------------------------- p diode
pcell = ly.create_cell('MAGIC_PDIO')
rect(ly, pcell, 'NW', 0.4, -0.6, 9.6, 5.6)
rect(ly, pcell, 'ACT', 1.0, 0.0, 3.0, 5.0)
rect(ly, pcell, 'PP', 1.0, 0.0, 3.0, 5.0)
rect(ly, pcell, 'PVT1', 0.7, -0.3, 3.3, 5.3)
rect(ly, pcell, 'DIODE', 0.9, -0.1, 3.1, 5.1)
ct_array(ly, pcell, 1.0, 0.0, 3.0, 5.0)
rect(ly, pcell, 'M1', 0.9, -0.2, 3.1, 5.2)
label(ly, pcell, 'M1LBL', 'ANODE', 2.0, 2.5)

# n+ tap inside the same nwell = cathode
rect(ly, pcell, 'ACT', 7.5, 0.0, 8.5, 5.0)
rect(ly, pcell, 'NP', 7.5, 0.0, 8.5, 5.0)
ct_array(ly, pcell, 7.5, 0.0, 8.5, 5.0)
rect(ly, pcell, 'M1', 7.4, -0.2, 8.6, 5.2)
label(ly, pcell, 'M1LBL', 'CATHODE', 8.0, 2.5)

# ---------------------------------------------------------------- n diode
ncell = ly.create_cell('MAGIC_NDIO')
rect(ly, ncell, 'ACT', 1.0, 0.0, 3.5, 4.0)
rect(ly, ncell, 'NP', 1.0, 0.0, 3.5, 4.0)
rect(ly, ncell, 'NVT1', 0.7, -0.3, 3.8, 4.3)
rect(ly, ncell, 'DIODE', 0.9, -0.1, 3.6, 4.1)
ct_array(ly, ncell, 1.0, 0.0, 3.5, 4.0)
rect(ly, ncell, 'M1', 0.9, -0.2, 3.6, 4.2)
label(ly, ncell, 'M1LBL', 'CATHODE2', 2.25, 2.0)

# p+ substrate tap = anode (substrate node)
rect(ly, ncell, 'ACT', 6.0, 0.0, 7.0, 4.0)
rect(ly, ncell, 'PP', 6.0, 0.0, 7.0, 4.0)
ct_array(ly, ncell, 6.0, 0.0, 7.0, 4.0)
rect(ly, ncell, 'M1', 5.9, -0.2, 7.1, 4.2)
label(ly, ncell, 'M1LBL', 'ANODE2', 6.5, 2.0)

# ------------------------------------------------------- taps, no junction
# Both a contacted n+ tap (inside an nwell) and a contacted p+ tap (in the
# substrate), with no DIODE marker.  These are the shapes that produced the
# bogus 90x90 nm diodes when the device mask leaked the shared `ct` type.
tapcell = ly.create_cell('MAGIC_TAPS')
rect(ly, tapcell, 'NW', 0.0, -1.0, 4.0, 6.0)
rect(ly, tapcell, 'ACT', 1.0, 0.0, 2.0, 5.0)
rect(ly, tapcell, 'NP', 1.0, 0.0, 2.0, 5.0)
ct_array(ly, tapcell, 1.0, 0.0, 2.0, 5.0)
rect(ly, tapcell, 'M1', 0.9, -0.2, 2.1, 5.2)
label(ly, tapcell, 'M1LBL', 'TAPN', 1.5, 2.5)
rect(ly, tapcell, 'ACT', 7.0, 0.0, 8.0, 5.0)
rect(ly, tapcell, 'PP', 7.0, 0.0, 8.0, 5.0)
ct_array(ly, tapcell, 7.0, 0.0, 8.0, 5.0)
rect(ly, tapcell, 'M1', 6.9, -0.2, 8.1, 5.2)
label(ly, tapcell, 'M1LBL', 'TAPP', 7.5, 2.5)

gds = File.join(OUT, 'magic_diode.gds')
ly.write(gds)
puts "wrote #{gds}"
