#!/usr/bin/env ruby
# ICS55 source-rule DRC fixtures (KLayout RBA).
#
# Writes one GDS per fixture (1 nm DBU, top cell TOP) into -rd out=<dir>.
# Geometry uses the official Calibre GDS layer map; numerical thresholds are
# loaded from the DRC source-value JSON where available.
#
# Usage:
#   klayout -b -r make_fixtures.rb -rd out=<dir>

require 'json'

ROOT = File.expand_path('../..', __dir__)
OUT = File.expand_path($out)
Dir.mkdir(OUT) unless Dir.exist?(OUT)
RULES = JSON.parse(File.read(File.join(ROOT, 'libs.tech/drc/rule_decks/ics55_rules.json')))['drc_rules']

LAYERS = {
  'ACT' => [2, 1], 'ACTDUM' => [2, 2], 'ACTDUMB' => [2, 3],
  'POLY' => [41, 1], 'POLYDUM' => [41, 2],
  'NP' => [52, 1], 'PP' => [53, 1], 'ESD' => [55, 1],
  'CT' => [72, 1], 'CTBAR' => [72, 7],
  'M1' => [81, 1], 'M1DUM' => [81, 2], 'M1DUMB' => [81, 3], 'M1SLOT' => [81, 8],
  'M2' => [82, 1], 'M2DUM' => [82, 2], 'M2DUMB' => [82, 3],
  'M3' => [83, 1], 'M3DUM' => [83, 2], 'M3DUMB' => [83, 3],
  'M4' => [84, 1], 'M4DUM' => [84, 2], 'M4DUMB' => [84, 3],
  'M5' => [85, 1], 'M5DUM' => [85, 2], 'M5DUMB' => [85, 3],
  'V1' => [91, 1], 'V1BAR' => [91, 7], 'V4BAR' => [94, 7],
  'T4M2' => [103, 1], 'T4M2DUM' => [103, 2], 'T4M2DUMB' => [103, 3], 'T4M2SLOT' => [103, 8],
  'TV2' => [113, 1], 'TV2BAR' => [113, 7],
  'RV' => [120, 1], 'CB' => [121, 1], 'ALPAD' => [122, 1], 'ALPADRES' => [122, 4],
  'RDL' => [123, 1], 'COVER' => [124, 1],
  'M1MOM' => [81, 10], 'M2MOM' => [82, 10], 'M3MOM' => [83, 10],
  'M4MOM' => [84, 10], 'M5MOM' => [85, 10], 'MOMLVS1' => [323, 12],
  'FUSEALL' => [292, 12], 'EFUSEALL' => [293, 12], 'POEFUSEBLK' => [294, 12],
  'GRBLK' => [353, 12], 'SRINGBLK_SRC' => [354, 13], 'NODRC' => [357, 12],
  'INDALL' => [302, 12],
  'CHIPBLK' => [351, 12], 'DEUPAD' => [381, 12],
}

def box(layer, x1, y1, x2, y2)
  [layer, :box, x1, y1, x2, y2]
end

def area_box(layer, min_area, width, fraction = 1.0)
  box(layer, 0, 0, width, min_area * fraction / width)
end

def ring(layer, width, height, hole_width, hole_height)
  hx = (width - hole_width) / 2.0
  hy = (height - hole_height) / 2.0
  [
    box(layer, 0, 0, width, hy),
    box(layer, 0, hy + hole_height, width, height),
    box(layer, 0, hy, hx, hy + hole_height),
    box(layer, hx + hole_width, hy, width, hy + hole_height),
  ]
end

def diamond(layer, cx, cy, radius)
  [layer, :polygon, [[cx, cy - radius], [cx + radius, cy], [cx, cy + radius], [cx - radius, cy]]]
end

def label(layer, text, x, y)
  [layer, :text, text, x, y]
end

def density_base(width, height, act: :half, omit_metal: nil, top_metal: :half, dummy: nil, nodrc: false)
  shapes = [box('CHIPBLK', 0, 0, width, height)]
  case act
  when :half
    shapes << box('ACT', 0, 0, width * 0.5, height)
  when :low
    shapes << box('ACT', 0, 0, width * 0.1, height)
  when :at_min
    shapes << box('ACT', 0, 0, width * 0.2, height)
  when :at_max
    shapes << box('ACT', 0, 0, width * 0.8, height)
  when :near_min
    shapes << box('ACT', 0, 0, width * 0.2 - 0.001, height)
  when :near_max
    shapes << box('ACT', 0, 0, width * 0.8 + 0.001, height)
  when :backup_only
    shapes.concat([
      box('ACT', 0, 0, 20, height), box('ACT', 40, 0, 60, height),
      box('ACT', 90, 0, 101, height),
    ])
  when :empty
    # Deliberately no active geometry.
  end

  x = 0.0
  while x < width
    shapes << box('POLY', x, 0, [x + 15, width].min, height)
    x += 50
  end
  (1..5).each do |number|
    name = "M#{number}"
    next if omit_metal == name
    x = 0.0
    while x < width
      shapes << box(name, x, 0, [x + 25, width].min, height)
      x += 50
    end
  end
  if top_metal == :half
    x = 0.0
    while x < width
      shapes << box('T4M2', x, 0, [x + 25, width].min, height)
      x += 50
    end
  end
  case dummy
  when :act then shapes << box('ACTDUMB', 0, 0, width, height)
  when :m1 then shapes << box('M1DUMB', 0, 0, width, height)
  when :top then shapes << box('T4M2DUMB', 0, 0, width, height)
  end
  shapes << box('NODRC', 0, 0, width, height) if nodrc
  shapes
end

def v1_pair(gap)
  second_x = 0.09 + gap
  right = second_x + 0.09
  [
    box('M1', -0.1, -0.1, right + 0.1, 0.2),
    box('M2', -0.1, -0.1, right + 0.1, 0.2),
    box('V1', 0, 0, 0.09, 0.09),
    box('V1', second_x, 0, right, 0.09),
  ]
end

def v1_upper_enclosure(enclosure)
  [
    box('M1', 0.05, 0.05, 0.5, 0.5),
    box('M2', 0.1 - enclosure, 0.1 - enclosure, 0.5, 0.5),
    box('V1', 0.1, 0.1, 0.19, 0.19),
  ]
end

def tv2_pair(gap)
  second_x = 0.2 + 0.36 + gap
  [
    box('M5', 0.1, 0.1, 2, 1.5),
    box('T4M2', 0.1, 0.1, 2, 1.5),
    box('TV2', 0.2, 0.2, 0.56, 0.56),
    box('TV2', second_x, 0.2, second_x + 0.36, 0.56),
  ]
end

def tv2_enclosure(lower, upper)
  [
    box('M5', 0.2 - lower, 0.2 - lower, 2, 1.5),
    box('T4M2', 0.2 - upper, 0.2 - upper, 2, 1.5),
    box('TV2', 0.2, 0.2, 0.56, 0.56),
  ]
end



FIXTURES = {
  # FEOL area predicates, inclusive threshold boundaries, and full/partial waivers.
  'clean' => [box('M1', 0, 0, 2, 1), box('M2', 0, 0, 2, 1), box('V1', 0.955, 0.455, 1.045, 0.545)],
  'act_area' => [area_box('ACT', RULES['act_area'], 0.16, 0.5)],
  'act_area_at_limit' => [area_box('ACT', RULES['act_area'], 0.16)],
  'act_area_nodrc_waived' => [area_box('ACT', RULES['act_area'], 0.16, 0.5), box('NODRC', 0, 0, 0.16, 0.12)],
  'poly_width_bad' => [box('POLY', 0, 0, 1, 0.05)],
  'poly_width_at_limit' => [box('POLY', 0, 0, 1, RULES['poly_width'])],
  'poly_spacing_bad' => [box('POLY', 0, 0, 1, 0.1), box('POLY', 0, 0.21, 1, 0.31)],
  'poly_spacing_at_limit' => [box('POLY', 0, 0, 1, 0.1), box('POLY', 0, 0.22, 1, 0.32)],
  'poly_area' => [area_box('POLY', RULES['poly_area'], 0.2, 0.5)],
  'poly_area_at_limit' => [area_box('POLY', RULES['poly_area'], 0.2)],

  'poly_area_nodrc_waived' => [area_box('POLY', RULES['poly_area'], 0.2, 0.5), box('NODRC', 0, 0, 0.2, 0.1)],
  'poly_area_partial_marker' => [area_box('POLY', RULES['poly_area'], 0.2, 0.5), box('NODRC', 0, 0, 0.1, 0.1)],
  'poly_hole' => ring('POLY', 1, 1, 0.2, 0.3),
  'poly_hole_at_limit' => ring('POLY', 1, 1, 0.3, 0.3),
  'np_area' => [area_box('NP', 0.12, 0.3, 0.5)],
  'np_area_at_limit' => [area_box('NP', 0.12, 0.3)],
  'pp_area' => [area_box('PP', 0.12, 0.3, 0.5)],
  'pp_area_at_limit' => [area_box('PP', 0.12, 0.3)],
  'ct_outside_required_layers' => [box('CT', 0, 0, 0.09, 0.09)],

  'ct_active_enclosure_bad' => [
    box('CTBAR', 0, 0, 0.09, 0.09), box('ACT', -(RULES['ct_drc_enc_act'] - 0.001), -(RULES['ct_drc_enc_act'] - 0.001), 1, 1),
    box('M1', -0.02, -0.02, 1, 1),
  ],
  'ct_active_enclosure_at_limit' => [
    box('CTBAR', 0, 0, 0.09, 0.09), box('ACT', -RULES['ct_drc_enc_act'], -RULES['ct_drc_enc_act'], 1, 1),
    box('M1', -0.02, -0.02, 1, 1),
  ],

  # BEOL area/hole rules, exact-area boundaries, and source-specific via qualifiers.
  'm1_area' => [area_box('M1', RULES['m1_area'], 0.21, 0.5)],
  'm1_area_at_limit' => [area_box('M1', RULES['m1_area'], 0.21)],
  'm1_area_nodrc_waived' => [area_box('M1', RULES['m1_area'], 0.21, 0.5), box('NODRC', 0, 0, 0.21, 0.1)],
  'm1_spacing_bad' => [box('M1', 0, 0, 0.3, 0.3), box('M1', 0.3 + RULES['m1_space'] - 0.01, 0, 0.6 + RULES['m1_space'] - 0.01, 0.3)],
  'm1_spacing_at_limit' => [box('M1', 0, 0, 0.3, 0.3), box('M1', 0.3 + RULES['m1_space'], 0, 0.6 + RULES['m1_space'], 0.3)],
  'm1_slot_spacing_ignored' => [
    box('M1', 0, 0, 0.3, 0.3), box('M1', 0.38, 0, 0.68, 0.3),
    box('M1SLOT', 0.38, 0, 0.68, 0.3),
  ],

  'm1_hole' => ring('M1', 1, 1, 0.3, 0.3),
  'm1_hole_at_limit' => ring('M1', 1, 1, 0.6, 0.3),
  't4m2_area' => [area_box('T4M2', RULES['tm2_area'], 0.4, 0.5)],
  't4m2_area_at_limit' => [area_box('T4M2', RULES['tm2_area'], 0.4)],
  't4m2_hole' => ring('T4M2', 2, 2, 0.5, 0.5),
  't4m2_hole_at_limit' => ring('T4M2', 2, 2, 0.6, 1.0),
  'v1_wrong_square' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), box('V1', 0.4, 0.4, 0.5, 0.5)],
  'v1_square_at_limit' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), box('V1', 0.455, 0.455, 0.545, 0.545)],
  'v1_bar_in_w1_union' => [box('V1BAR', 0, 0, 0.2, 0.2)],
  'v1_uncovered_lower_metal' => [box('M2', -0.1, -0.1, 0.2, 0.2), box('V1', 0, 0, 0.09, 0.09)],
  'v1_uncovered_nodrc_waived' => [box('V1', 0, 0, 0.09, 0.09), box('NODRC', 0, 0, 0.09, 0.09)],
  'v1_diagonal_edges' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), diamond('V1', 0.5, 0.5, 0.05)],
  'v1_spacing_bad' => v1_pair(RULES['v1_space'] - 0.01),
  'v1_spacing_at_limit' => v1_pair(RULES['v1_space']),
  'v1_upper_enclosure_bad' => v1_upper_enclosure(RULES['via_drc_enc_upper'] - 0.003),
  'v1_upper_enclosure_at_limit' => v1_upper_enclosure(RULES['via_drc_enc_upper']),
  't4v2_spacing_bad' => tv2_pair(RULES['tv2_space'] - 0.01),
  't4v2_spacing_at_limit' => tv2_pair(RULES['tv2_space']),
  't4v2_bar_width_bad' => [
    box('TV2BAR', 0, 0, RULES['tv2_bar_width'] - 0.05, 0.5),
    box('M5', -1, -1, 1, 1), box('T4M2', -1, -1, 1, 1),
  ],
  't4v2_bar_width_at_limit' => [
    box('TV2BAR', 0, 0, RULES['tv2_bar_width'], 0.5),
    box('M5', -1, -1, 1, 1), box('T4M2', -1, -1, 1, 1),
  ],
  't4v2_lower_enclosure_bad' => tv2_enclosure(RULES['tv2_drc_enc_m5'] - 0.005, 0.03),
  't4v2_lower_enclosure_at_limit' => tv2_enclosure(RULES['tv2_drc_enc_m5'], 0.03),
  't4v2_upper_enclosure_bad' => tv2_enclosure(0.03, RULES['tv2_drc_enc_tm2'] - 0.005),
  't4v2_upper_enclosure_at_limit' => tv2_enclosure(0.03, RULES['tv2_drc_enc_tm2']),

  'v1_diagonal_sringblk_waived' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), diamond('V1', 0.5, 0.5, 0.05), diamond('SRINGBLK_SRC', 0.5, 0.5, 0.05)],
  'v1_grid_exclusion' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), box('V1', 0.4, 0.4, 0.5, 0.6), box('GRBLK', 0.4, 0.4, 0.5, 0.6)],

  # Pad and redistribution-layer source predicates.
  'rv_wrong_rectangle' => [box('RV', 0, 0, 2, 2), box('RDL', 0, 0, 2, 2)],
  'rv_grid_exclusion' => [box('RV', 0, 0, 2, 2), box('RDL', 0, 0, 2, 2), box('GRBLK', 0, 0, 2, 2)],
  'rv_exact_rectangle' => [box('RV', 0, 0, 3, 3), box('RDL', 0, 0, 3, 3)],
  'rv_outside_rdl' => [box('RV', 0, 0, 3, 3)],
  'cover_outside_alpa' => [box('COVER', 0, 0, 1, 1)],
  'cb_outside_alpad' => [box('CB', 0, 0, 1, 1)],

  # Dummy geometry whitelist, marker overlap, and slot-to-pad relation.
  'act_dummy_valid' => [box('ACTDUM', 0, 0, RULES['act_dummy_3'], RULES['act_dummy_3'])],
  'act_dummy_invalid' => [box('ACTDUM', 0, 0, 2, 2)],
  'act_dummy_ct_overlap' => [box('ACTDUM', 0, 0, 3, 3), box('ACT', 0, 0, 3, 3), box('M1', 0, 0, 3, 3), box('CT', 0.2, 0.2, 0.29, 0.29)],
  'poly_dummy_valid' => [box('POLYDUM', 0, 0, RULES['poly_dummy_24'], RULES['poly_dummy_24'])],
  'poly_dummy_invalid' => [box('POLYDUM', 0, 0, 1, 2)],
  'm1_dummy_invalid' => [box('M1DUM', 0, 0, 1.2, 1.2)],
  't4m2_dummy_valid_rotated' => [box('T4M2DUM', 0, 0, 1.2, 0.6)],
  'slot_cb_overlap' => [box('M1SLOT', 0, 0, 1, 1), box('CB', 0, 0, 1, 1), box('ALPAD', 0, 0, 1, 1)],

  # Special source checks, marker geometry, exclusions, and exact area limits.
  'efu_fuse_without_efuse' => [box('FUSEALL', 0, 0, 1, 1)],
  'efu_efuse_uncovered_by_fuse' => [box('EFUSEALL', 0, 0, 1, 1)],
  'efu_po_block_uncovered' => [box('FUSEALL', 0, 0, 1, 1), box('EFUSEALL', 0, 0, 0.6, 1), box('POEFUSEBLK', 0, 0, 1, 1)],
  'efu_nodrc_waived' => [box('FUSEALL', 0, 0, 1, 1), box('NODRC', 0, 0, 1, 1)],
  'deupad_r2' => [box('DEUPAD', 0, 0, 1, 1), box('CB', 0.5, 0.2, 1.5, 0.8), box('ALPAD', 0.5, 0.2, 1.5, 0.8)],
  'deupad_r2_nodrc_waived' => [box('DEUPAD', 0, 0, 1, 1), box('CB', 0.5, 0.2, 1.5, 0.8), box('ALPAD', 0.5, 0.2, 1.5, 0.8), box('NODRC', 1, 0.2, 1.5, 0.8)],
  'deupad_r5' => [box('DEUPAD', 0, 0, 1, 1), box('CB', 0, 0, 1, 1), box('ALPAD', 0, 0, 1, 1), box('ALPADRES', 0.2, 0.2, 0.8, 0.8)],
  'deupad_r6_v4bar' => [box('DEUPAD', 0, 0, 1, 1), box('CB', 0, 0, 1, 1), box('ALPAD', 0, 0, 1, 1), box('M4', 0, 0, 1, 1), box('M5', 0, 0, 1, 1), box('V4BAR', 0.3, 0.3, 0.6, 0.6)],
  'esd_area' => [area_box('ESD', RULES['esd_area_min'], 0.5, 0.5)],
  'esd_area_at_limit' => [area_box('ESD', RULES['esd_area_min'], 0.6)],
  'esd_area_nodrc_waived' => [area_box('ESD', RULES['esd_area_min'], 0.5, 0.5), box('NODRC', 0, 0, 0.5, 0.6)],
  'esd_hole' => ring('ESD', 2, 2, 0.5, 0.5),
  'esd_hole_at_limit' => ring('ESD', 2, 2, 0.6, 1.0),

  # Density windows, strict boundaries, NODRC, backup edges, small layouts, and dummy halos.
  'density_act_low' => density_base(100, 100, act: :low),
  'density_act_exact_min' => density_base(100, 100, act: :at_min),
  'density_act_exact_max' => density_base(100, 100, act: :at_max),
  'density_act_near_min' => density_base(100, 100, act: :near_min),
  'density_act_near_max' => density_base(100, 100, act: :near_max),
  'density_backup_min' => density_base(160, 100, act: :backup_only),
  'density_act_small_low' => density_base(80, 80, act: :low),
  'density_nodrc_waived' => density_base(100, 100, act: :low, nodrc: true),
  'density_act_dummy_low' => density_base(150, 150, act: :empty, dummy: :act),
  'density_m1_dummy_low' => density_base(150, 150, omit_metal: 'M1', dummy: :m1),
  'density_t4m2_dummy_low' => density_base(150, 150, top_metal: :empty, dummy: :top),

  # MOM marker tests use source profile-only runs to separate the MOM family.
  'mom_v1_m1mom' => [box('V1', 0.4, 0.4, 0.49, 0.49), box('M1MOM', 0, 0, 1, 1)],
  'mom_v1bar_m1mom' => [box('V1BAR', 0.4, 0.4, 0.49, 0.49), box('M1MOM', 0, 0, 1, 1)],
  'mom_v1_nodrc_waived' => [box('V1', 0.4, 0.4, 0.49, 0.49), box('M1MOM', 0, 0, 1, 1), box('NODRC', 0, 0, 1, 1)],
  'mom_forbidden_m1_cap23' => [box('MOMLVS1', 0, 0, 1, 1), box('M1MOM', 0, 0, 1, 1), label('MOMLVS1', 'momcap23', 0.5, 0.5)],
  'mom_cap12_missing_label' => [box('MOMLVS1', 0, 0, 1, 1), box('M1MOM', 0, 0, 1, 1), box('M2MOM', 0, 0, 1, 1)],
  'mom_cap12_valid_label' => [box('MOMLVS1', 0, 0, 1, 1), box('M1MOM', 0, 0, 1, 1), box('M2MOM', 0, 0, 1, 1), label('MOMLVS1', 'momcap12', 0.5, 0.5)],
}

FIXTURES.each do |name, shapes|
  ly = RBA::Layout.new
  ly.dbu = 0.001
  top = ly.create_cell('TOP')
  layer_indices = {}
  shapes.each do |shape|
    layer, kind, *geometry = shape
    layer_indices[layer] ||= ly.insert_layer(RBA::LayerInfo.new(*LAYERS.fetch(layer)))
    case kind
    when :box
      x1, y1, x2, y2 = geometry
      top.shapes(layer_indices[layer]).insert(RBA::Box.new((x1 * 1000).round, (y1 * 1000).round,
                                                         (x2 * 1000).round, (y2 * 1000).round))
    when :polygon
      points = geometry.fetch(0).map { |x, y| RBA::Point.new((x * 1000).round, (y * 1000).round) }
      top.shapes(layer_indices[layer]).insert(RBA::Polygon.new(points))
    when :text
      text, x, y = geometry
      top.shapes(layer_indices[layer]).insert(RBA::Text.new(text, RBA::Trans.new((x * 1000).round, (y * 1000).round)))
    else
      raise "unknown fixture shape: #{kind}"
    end
  end
  ly.write(File.join(OUT, "#{name}.gds"))
end

puts "#{FIXTURES.length} source-rule fixtures written to #{OUT}"
