#!/usr/bin/env ruby
# Deterministic LVS extraction fixtures built with KLayout RBA.
#
# Usage: klayout -b -r make_lvs_fixtures.rb -rd out=<directory>

require 'fileutils'

OUT = File.expand_path($out)
FileUtils.mkdir_p(OUT)
LAYERS = {
'ACT' => [2, 1], 'ACTDUM' => [2, 2], 'ACTDUMB' => [2, 3], 'ACTRES' => [2, 4],
  'NW' => [9, 1], 'ULLD' => [152, 12], 'UD' => [153, 12], 'OD' => [154, 12],
  'LVTN' => [17, 1], 'LVTP' => [18, 1], 'HVTN' => [21, 1], 'HVTP' => [22, 1],
  'DGOX' => [27, 1], 'TGOX' => [28, 1], 'POLY' => [41, 1], 'POLYDUM' => [41, 2],
  'PPO' => [41, 4], 'HRP' => [54, 1], 'HRPBLK' => [385, 12],
  'NP' => [52, 1], 'PP' => [53, 1], 'ESD' => [55, 1], 'SAB' => [71, 1],
  'ESDIOE' => [232, 12], 'VARAM' => [193, 12], 'BJT' => [195, 12],
  'SRAMALL' => [171, 12], 'PSUB_MARKER' => [261, 12], 'RES3TPOLY' => [329, 12],
  'RESCKTLVS' => [314, 12], 'CT' => [72, 1], 'CTBAR' => [72, 7],
  'CTOPCBLK' => [72, 5],
  'M1' => [81, 1], 'M1DUM' => [81, 2], 'M1RES' => [81, 4], 'M1LBL' => [81, 6],
  'M2' => [82, 1], 'M2DUM' => [82, 2], 'M2RES' => [82, 4], 'M2LBL' => [82, 6],
  'M3' => [83, 1], 'M3DUM' => [83, 2], 'M3RES' => [83, 4], 'M3LBL' => [83, 6],
  'M4' => [84, 1], 'M4DUM' => [84, 2], 'M4RES' => [84, 4], 'M4LBL' => [84, 6],
  'M5' => [85, 1], 'M5DUM' => [85, 2], 'M5RES' => [85, 4], 'M5LBL' => [85, 6],
  'V1' => [91, 1], 'V1BAR' => [91, 7], 'V2' => [92, 1], 'V2BAR' => [92, 7],
  'V3' => [93, 1], 'V3BAR' => [93, 7], 'V4' => [94, 1], 'V4BAR' => [94, 7],
  'T4M1' => [102, 1], 'T4M1DUM' => [102, 2], 'T4M1RES' => [102, 4],
  'T4M1LBL' => [102, 6], 'T4V1' => [112, 1], 'T4V1BAR' => [112, 7],
  'T4M2' => [103, 1], 'T4M2DUM' => [103, 2], 'T4M2RES' => [103, 4],
  'T4M2LBL' => [103, 6], 'T4V2' => [113, 1], 'T4V2BAR' => [113, 7],
  'ALPAD' => [122, 1], 'ALPADRES' => [122, 4], 'ALPADLBL' => [122, 6],
  'RDLLBL' => [123, 6], 'CB' => [121, 1], 'RV' => [120, 1], 'RDL' => [123, 1],
  'COVER' => [124, 1], 'DIODE' => [191, 12]
}

def box(layer, x1, y1, x2, y2)
  [layer, :box, x1, y1, x2, y2]
end

def label(layer, text, x, y)
  [layer, :text, text, x, y]
end

def mos_fixture(implant, markers = [], contact = 'CT')
  shapes = [
    box('ACT', 0, 0, 1.0, 0.6),
    box('POLY', 0.45, -0.1, 0.55, 0.7),
    box(implant, 0, 0, 1.0, 0.6),
    box(contact, 0.10, 0.20, 0.25, 0.40),
    box(contact, 0.75, 0.20, 0.90, 0.40),
    box('M1', 0.08, 0.18, 0.27, 0.42),
    box('M1', 0.73, 0.18, 0.92, 0.42)
  ]
  shapes << box('NW', 0, 0, 1.0, 0.6) if implant == 'PP'
  markers.each { |name| shapes << box(name, 0, -0.1, 1.0, 0.7) }
  shapes
end

poly_resistor = [
  box('POLY', 0, 0, 1.0, 0.2), box('PPO', 0, 0, 1.0, 0.2),
  box('PP', 0, 0, 1.0, 0.2), box('SAB', 0, 0, 1.0, 0.2),
  box('CT', -0.1, 0, 0.1, 0.2), box('CT', 0.9, 0, 1.1, 0.2),
  box('M1', -0.1, 0, 0.1, 0.2), box('M1', 0.9, 0, 1.1, 0.2),
  label('M1LBL', 'A', 0.0, 0.1), label('M1LBL', 'B', 1.0, 0.1)
]

metal_resistor = [
  box('M1', 0, 0, 1.4, 0.2), box('M1RES', 0.2, 0, 1.2, 0.2),
  label('M1LBL', 'A', 0.1, 0.1), label('M1LBL', 'B', 1.3, 0.1)
]

diode_fixture = [
  box('ACT', 0, 0, 1.0, 0.6), box('PP', 0, 0, 1.0, 0.6),
  box('NW', 0, 0, 1.0, 0.6), box('TGOX', 0, 0, 1.0, 0.6),
  box('DIODE', 0, 0, 1.0, 0.6), box('CT', 0.15, 0.20, 0.35, 0.40),
  box('M1', 0.12, 0.17, 0.38, 0.43)
]
esd_only_fixture = diode_fixture.reject { |shape| shape[0] == 'DIODE' } + [box('ESD', 0, 0, 1.0, 0.6)]

pad_m1_m5 = [
  box('M1DUM', 0, 0, 1, 1), box('M2', 0, 0, 1, 1),
  box('M3', 0, 0, 1, 1), box('M4', 0, 0, 1, 1), box('M5', 0, 0, 1, 1),
  box('V1BAR', 0.4, 0.4, 0.6, 0.6), box('V2BAR', 0.4, 0.4, 0.6, 0.6),
  box('V3BAR', 0.4, 0.4, 0.6, 0.6), box('V4BAR', 0.4, 0.4, 0.6, 0.6),
  box('CB', 0.4, 0.4, 0.6, 0.6), box('ALPAD', 0, 0, 1, 1), box('RDL', 0, 0, 1, 1),
  label('M1LBL', 'PAD', 0.5, 0.5), label('ALPADLBL', 'PAD', 0.5, 0.5),
  label('RDLLBL', 'PAD', 0.5, 0.5)
]

pad_t4 = [
  box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1),
  box('M3', 0, 0, 1, 1), box('M4', 0, 0, 1, 1),
  box('T4M1', 0, 0, 1, 1), box('T4M2', 0, 0, 1, 1),
  box('V1BAR', 0.4, 0.4, 0.6, 0.6), box('V2BAR', 0.4, 0.4, 0.6, 0.6),
  box('V3BAR', 0.4, 0.4, 0.6, 0.6), box('T4V1BAR', 0.4, 0.4, 0.6, 0.6),
  box('T4V2BAR', 0.4, 0.4, 0.6, 0.6), box('CB', 0.4, 0.4, 0.6, 0.6),
  box('ALPAD', 0, 0, 1, 1), box('RDL', 0, 0, 1, 1),
  label('M1LBL', 'PAD', 0.5, 0.5), label('T4M1LBL', 'PAD', 0.5, 0.5),
  label('T4M2LBL', 'PAD', 0.5, 0.5), label('ALPADLBL', 'PAD', 0.5, 0.5)
]

fixtures = {
  'core_svt_n': mos_fixture('NP'),
  'core_lvt_n_ctbar': mos_fixture('NP', ['LVTN'], 'CTBAR'),
  'core_hvt_p': mos_fixture('PP', ['HVTP']),
  'io_tgox_n': mos_fixture('NP', ['TGOX']),
  'io_tgox_p': mos_fixture('PP', ['TGOX']),
  'dgo_only_n': mos_fixture('NP', ['DGOX']),
  'tgox_dgox_n': mos_fixture('NP', ['TGOX', 'DGOX']),
  'tgox_esdioe_n': mos_fixture('NP', ['TGOX', 'ESDIOE']),
  'poly_resistor': poly_resistor,
  'metal_resistor': metal_resistor,
  'diode_marker': diode_fixture,
  'esd_marker_only': esd_only_fixture,
  'pad_m1_m5_bar': pad_m1_m5 + mos_fixture('NP'),
  'pad_t4_bar': pad_t4 + mos_fixture('NP'),
  'bulk_alias': mos_fixture('NP')
}

fixtures.each do |name, shapes|
  layout = RBA::Layout.new
  layout.dbu = 0.001
  top = layout.create_cell('TOP')
  layer_indices = {}
  shapes.each do |shape|
    layer, kind, *geometry = shape
    layer_indices[layer] ||= layout.insert_layer(RBA::LayerInfo.new(*LAYERS.fetch(layer)))
    case kind
    when :box
      x1, y1, x2, y2 = geometry
      top.shapes(layer_indices[layer]).insert(RBA::Box.new((x1 * 1000).round, (y1 * 1000).round,
                                                         (x2 * 1000).round, (y2 * 1000).round))
    when :text
      text, x, y = geometry
      top.shapes(layer_indices[layer]).insert(RBA::Text.new(text, RBA::Trans.new((x * 1000).round,
                                                                                  (y * 1000).round)))
    else
      raise "unknown fixture shape: #{kind}"
    end
  end
  probe = layout.create_cell('LVS_LAYER_PROBES')
  probe_x = 10_000_000
  LAYERS.each do |layer, (layer_number, datatype)|
    next if layer_indices.key?(layer)

    layer_index = layout.insert_layer(RBA::LayerInfo.new(layer_number, datatype))
    probe.shapes(layer_index).insert(RBA::Box.new(probe_x, 10_000_000, probe_x + 1, 10_000_001))
    probe_x += 2_000
  end
  layout.write(File.join(OUT, "#{name}.gds"))
end

puts "#{fixtures.length} LVS extraction fixtures written to #{OUT}"
