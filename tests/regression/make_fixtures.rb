#!/usr/bin/env ruby
# ICS55 DRC fixture layout generator (KLayout RBA).
#
# Writes one tiny GDS per fixture (1 nm DBU, top cell TOP) into -rd out=<dir>.
# Fixture geometries are BEOL-only; rule values they exercise are tech-LEF
# exact (libs.tech/drc/rule_decks/ics55_rules.json), so the fixtures are
# deterministic and independent of the GDS-measured FEOL values.
#
# Usage:
#   klayout -b -r make_fixtures.rb -rd out=<dir>

require 'json'

OUT = File.expand_path($out)
Dir.mkdir(OUT) unless Dir.exist?(OUT)

LAYERS = {
  'M1' => RBA::LayerInfo.new(81, 1),
  'M2' => RBA::LayerInfo.new(82, 1),
  'V1' => RBA::LayerInfo.new(91, 1),
}

# name => [ [layer, x1_um, y1_um, x2_um, y2_um], ... ]
FIXTURES = {
  # clean: legal M1/M2/V1 (min widths/spaces/areas/enclosures respected)
  'clean' => [
    ['M1', 0, 0, 2, 1], ['M2', 0, 0, 2, 1],
    ['V1', 0.8, 0.3, 1.2, 0.7], ['M1', 3, 0, 5, 1],
  ],
  # 0.04 um < m1_width 0.09
  'm1_width' => [['M1', 0, 0, 5, 0.04]],
  # 0.02 um gap < m1_space 0.09
  'm1_space' => [['M1', 0, 0, 1, 1], ['M1', 1.02, 0, 2, 1]],
  # area 0.0225 um^2 < m1_area 0.042
  'm1_area' => [['M1', 0, 0, 0.15, 0.15]],
  # 0.04 um < v1_width 0.09
  'v1_width' => [['M1', 0, 0, 1, 1], ['M2', 0, 0, 1, 1], ['V1', 0.3, 0.3, 0.34, 0.34]],
  # V1 right enclosure 0 < 0.04 (v1_enc_lower/upper)
  'v1_enc' => [['M1', 0, 0, 1, 1], ['M2', 0, 0, 1, 1], ['V1', 0.5, 0.3, 1.0, 0.7]],
  # 0.03 um gap < v1_space 0.11 (also < array_space 0.13)
  'v1_space' => [
    ['M1', 0, 0, 2, 1], ['M2', 0, 0, 2, 1],
    ['V1', 0.4, 0.3, 0.8, 0.7], ['V1', 0.83, 0.3, 1.2, 0.7],
  ],
}

FIXTURES.each do |name, shapes|
  ly = RBA::Layout.new
  ly.dbu = 0.001
  top = ly.create_cell('TOP')
  li = {}
  shapes.each do |layer, x1, y1, x2, y2|
    li[layer] ||= ly.insert_layer(LAYERS[layer])
    box = RBA::Box.new((x1 * 1000).round, (y1 * 1000).round,
                       (x2 * 1000).round, (y2 * 1000).round)
    top.shapes(li[layer]).insert(box)
  end
  ly.write(File.join(OUT, "#{name}.gds"))
end

puts "fixtures written to #{OUT}"
