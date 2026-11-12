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
  'NW' => [9, 1], 'DNW' => [7, 1], 'DGOX' => [27, 1], 'TGOX' => [28, 1],
  'POLY' => [41, 1], 'POLYDUM' => [41, 2], 'POLYDUMB' => [41, 3],
  'NP' => [52, 1], 'PP' => [53, 1], 'ESD' => [55, 1], 'ESDIOE' => [232, 12],
  'NW1RES' => [9, 4], 'PSUB' => [261, 12], 'LDMOS' => [211, 12],
  'LVTN' => [17, 1], 'LVTP' => [18, 1], 'HVTN' => [21, 1], 'HVTP' => [22, 1],
  'HRP' => [54, 1], 'HPR' => [385, 12], 'ULLD' => [152, 12],
  'SAB' => [71, 1],
  'CT' => [72, 1], 'CTBAR' => [72, 7],
  'M1' => [81, 1], 'M1DUM' => [81, 2], 'M1DUMB' => [81, 3], 'M1SLOT' => [81, 8],
  'M2' => [82, 1], 'M2DUM' => [82, 2], 'M2DUMB' => [82, 3],
  'M3' => [83, 1], 'M3DUM' => [83, 2], 'M3DUMB' => [83, 3],
  'M4' => [84, 1], 'M4DUM' => [84, 2], 'M4DUMB' => [84, 3],
  'M5' => [85, 1], 'M5DUM' => [85, 2], 'M5DUMB' => [85, 3],
  'V1' => [91, 1], 'V1BAR' => [91, 7], 'V2' => [92, 1], 'V3' => [93, 1],
  'V4' => [94, 1], 'V4BAR' => [94, 7],
  'T4M2' => [103, 1], 'T4M2DUM' => [103, 2], 'T4M2DUMB' => [103, 3], 'T4M2SLOT' => [103, 8],
  'TV2' => [113, 1], 'TV2BAR' => [113, 7], 'T4V2' => [113, 1],
  'RV' => [120, 1], 'CB' => [121, 1], 'ALPAD' => [122, 1], 'ALPADRES' => [122, 4],
  'RDL' => [123, 1], 'COVER' => [124, 1],
  'M1MOM' => [81, 10], 'M2MOM' => [82, 10], 'M3MOM' => [83, 10],
  'M4MOM' => [84, 10], 'M5MOM' => [85, 10], 'MOMLVS1' => [323, 12],
  'FUSEALL' => [292, 12], 'EFUSEALL' => [293, 12], 'POEFUSEBLK' => [294, 12],
  'GRBLK' => [353, 12], 'SRINGBLK_SRC' => [354, 13], 'NODRC' => [357, 12],
  'INDALL' => [302, 12], 'SRAMALL' => [171, 12],
  'CHIPBLK' => [351, 12], 'DEUPAD' => [381, 12],
  'LOGO' => [355, 12], 'DMYBLK' => [359, 12], 'BMIM' => [140, 1],
  'INDDMY' => [301, 12],
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

def ring_at(layer, x, y, width, height, hole_width, hole_height)
  hx = (width - hole_width) / 2.0
  hy = (height - hole_height) / 2.0
  [
    box(layer, x, y, x + width, y + hy),
    box(layer, x, y + hy + hole_height, x + width, y + height),
    box(layer, x, y + hy, x + hx, y + hy + hole_height),
    box(layer, x + hx + hole_width, y + hy, x + width, y + hy + hole_height),
  ]
end

def diamond(layer, cx, cy, radius)
  [layer, :polygon, [[cx, cy - radius], [cx + radius, cy], [cx, cy + radius], [cx - radius, cy]]]
end

def label(layer, text, x, y)
  [layer, :text, text, x, y]
end

# SAB ring with an explicitly positioned hole (drawn as four abutting boxes).
def sab_ring(x1, y1, x2, y2, hx1, hy1, hx2, hy2)
  [
    box('SAB', x1, y1, x2, hy1),
    box('SAB', x1, hy2, x2, y2),
    box('SAB', x1, hy1, hx1, hy2),
    box('SAB', hx2, hy1, x2, hy2),
  ]
end

# ESD protection device. Active x=0..13, y=0..w; gate stripe at
# gate_left..gate_left+length; SAB ring over the drain with a hole whose left
# edge sits hole_gate um right of the gate; source/drain contacts, optional
# ESD implant and optional TGOX gate oxide for the HV ESDN_3/ESDP_3 checks.
def esd_device(w: 32.0, length: 0.5, gate_left: 2.5, implant: 'NP',
               ring_x1: nil, ring_x2: 13.21, hole_gate: 1.5, hole_w: 0.6,
               hole_cy: nil, hole_h: 0.8, ct_s_x: 1.25, ct_size: 0.18,
               imp_x1: nil, imp_x2: 12.6, imp_y1: 0.4, imp_y2: nil,
               tg: false)
  gate_right = gate_left + length
  ring_x1 ||= gate_right - 0.05
  hole_cy ||= w / 2.0
  hole_x1 = gate_right + hole_gate
  hole_x2 = hole_x1 + hole_w
  ct_cy = hole_cy
  imp_x1 ||= gate_right + 0.4
  imp_y2 ||= w - 0.4
  cy = w / 2.0
  shapes = [
    box('ACT', 0, 0, 13, w),
    box(implant, -0.2, -0.2, 13.2, w + 0.2),
    box('ESDIOE', -1, -1, 14, w + 1),
    box('POLY', gate_left, -0.5, gate_right, w + 0.5),
    *sab_ring(ring_x1, -0.21, ring_x2, w + 0.21,
              hole_x1, hole_cy - hole_h / 2.0, hole_x2, hole_cy + hole_h / 2.0),
    box('CT', ct_s_x - ct_size / 2.0, cy - ct_size / 2.0,
        ct_s_x + ct_size / 2.0, cy + ct_size / 2.0),
    box('CT', (hole_x1 + hole_x2 - ct_size) / 2.0, ct_cy - ct_size / 2.0,
        (hole_x1 + hole_x2 + ct_size) / 2.0, ct_cy + ct_size / 2.0),
    box('ESD', imp_x1, imp_y1, imp_x2, imp_y2),
  ]
  shapes << box('TGOX', gate_left - 0.05, -0.6, gate_right + 0.05, w + 0.6) if tg
  shapes
end

# Active with its mandatory NP coverage (ACT_R_1); other ACT-family fixtures
# keep the implant cover so only the rule under test can fire.
def act_np(x1, y1, x2, y2, margin = 0.15)
  [box('ACT', x1, y1, x2, y2), box('NP', x1 - margin, y1 - margin, x2 + margin, y2 + margin)]
end

def act_pp(x1, y1, x2, y2, margin = 0.15)
  [box('ACT', x1, y1, x2, y2), box('PP', x1 - margin, y1 - margin, x2 + margin, y2 + margin)]
end

# Native NMOS (PSUB) dog-bone: channel width = neck, channel length = length.
# The slot above the channel is open; the gate stripe sits inside it so the
# PO-coincident gate edges have length neck and the AA-coincident edges have
# length length. PSUB is the exact 0.285 um halo of the ACT, so the slot is
# also widened enough (0.9 um) that the halo notch stays above the 0.47 um
# PSUB spacing minimum. oxide adds DGOX (io1) or TGOX (io2).
def psub_native(neck, length, poly_end: nil, oxide: nil)
  top = neck + 0.4
  slot_x1 = 0.30
  slot_x2 = slot_x1 + length + 0.9
  x_right = slot_x2 + 0.5
  px1 = slot_x1 + 0.02
  px2 = px1 + length
  poly_top = poly_end ? neck + poly_end : top + 0.5
  act = [[0, 0], [x_right, 0], [x_right, top], [slot_x2, top],
         [slot_x2, neck], [slot_x1, neck], [slot_x1, top], [0, top]]
  psub = ['PSUB', :polygon, [
    [-0.285, -0.285], [x_right + 0.285, -0.285], [x_right + 0.285, top + 0.285],
    [slot_x2 - 0.285, top + 0.285], [slot_x2 - 0.285, neck + 0.285],
    [slot_x1 + 0.285, neck + 0.285], [slot_x1 + 0.285, top + 0.285],
    [-0.285, top + 0.285],
  ]]
  shapes = [
    ['ACT', :polygon, act],
    box('NP', -0.15, -0.15, x_right + 0.15, top + 0.15),
    box('POLY', px1, -0.5, px2, poly_top),
    box('CT', 0.05, 0.03, 0.14, 0.12),
    box('CT', x_right - 0.19, 0.03, x_right - 0.10, 0.12),
    box('M1', -0.05, -0.05, 0.20, 0.30),
    box('M1', x_right - 0.25, -0.05, x_right + 0.05, 0.30),
    psub,
  ]
  # 0.76 keeps the DG EN/EX checks quiet: PSUB extends 0.285 beyond the ACT
  # and the DG_EX_3 strip adds another 0.47 (0.755 < 0.76).
  shapes << box(oxide, -0.76, -0.76, x_right + 0.76, top + 0.76) if oxide
  shapes
end

# A tapped N+ pickup for well fixtures: ACT fully inside NW (>=0.15 um from the
# NW edge), implant cover, fixed 0.09 CT, and M1 over it. Keeps NW1_R_1 and the
# CT coverage/enclosure checks quiet while a well rule is exercised.
def nw_tap(x, y, w = 0.14, h = 0.3)
  [
    box('ACT', x, y, x + w, y + h),
    box('NP', x - 0.15, y - 0.15, x + w + 0.15, y + h + 0.15),
    box('CT', x + (w - 0.09) / 2.0, y + (h - 0.09) / 2.0,
        x + (w + 0.09) / 2.0, y + (h + 0.09) / 2.0),
    box('M1', x - 0.05, y - 0.05, x + w + 0.05, y + h + 0.05),
  ]
end

# Dog-bone active: a narrow channel of height +neck+ between two full-height
# arms, so the gate edge length (channel width) is independent of the arm size
# needed for CT landing. The gate stripe occupies the 0.30..0.36 slot of the
# 0.12-wide notch (>= ACT spacing, >= POLY width).
def channel_width(neck, top, oxide: nil, implant: 'NP')
  shapes = [
    ['ACT', :polygon, [[0, 0], [0.8, 0], [0.8, top], [0.42, top],
                       [0.42, neck], [0.30, neck], [0.30, top], [0, top]]],
    box(implant, -0.15, -0.15, 0.95, top + 0.15),
    box('POLY', 0.30, -0.5, 0.36, 0.5),
    box('CT', 0.05, 0.03, 0.14, 0.12),
    box('CT', 0.50, 0.03, 0.59, 0.12),
    box('M1', -0.05, -0.05, 0.85, 0.30),
  ]
  # 0.32 margin keeps the TG/DG EN_1/EN_2/EN_3 enclosure checks quiet while
  # the IO gate-oxide split still classifies the gate.
  shapes << box(oxide, -0.32, -0.32, 1.12, top + 0.32) if oxide
  shapes
end

def density_base(width, height, act: :half, omit_metal: nil, top_metal: :half, dummy: nil, nodrc: false)
  shapes = [box('CHIPBLK', 0, 0, width, height)]
  act_boxes = []
  case act
  when :half
    act_boxes << [0, 0, width * 0.5, height]
  when :low
    act_boxes << [0, 0, width * 0.1, height]
  when :at_min
    act_boxes << [0, 0, width * 0.2, height]
  when :at_max
    act_boxes << [0, 0, width * 0.8, height]
  when :near_min
    act_boxes << [0, 0, width * 0.2 - 0.001, height]
  when :near_max
    act_boxes << [0, 0, width * 0.8 + 0.001, height]
  when :backup_only
    act_boxes.concat([
      [0, 0, 20, height], [40, 0, 60, height],
      [90, 0, 101, height],
    ])
  when :empty
    # Deliberately no active geometry.
  end
  act_boxes.each do |x1, y1, x2, y2|
    shapes << box('ACT', x1, y1, x2, y2)
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
      # Fill stripes stay below the 12 um maximum-width rule; density values
      # asserted by these fixtures only involve the ACT and dummy layers.
      shapes << box(name, x, 0, [x + 10, width].min, height)
      x += 50
    end
  end
  if top_metal == :half
    x = 0.0
    while x < width
      shapes << box('T4M2', x, 0, [x + 10, width].min, height)
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

def via_grid(layer, x0, y0, count, size, gap)
  pitch = size + gap
  (0...count).flat_map do |row|
    (0...count).map do |col|
      x = x0 + col * pitch
      y = y0 + row * pitch
      box(layer, x, y, x + size, y + size)
    end
  end
end

# 45-degree bar with integer-nanometre vertices. A perpendicular width of
# wu*sqrt(2) is not representable exactly on the 1 nm grid, so callers choose
# the wu that lands on the intended side of a 0.19 um threshold.
def bar45(x_nm, y_nm, length_nm, wu_nm)
  [[x_nm, y_nm],
   [x_nm + length_nm, y_nm + length_nm],
   [x_nm + length_nm - wu_nm, y_nm + length_nm + wu_nm],
   [x_nm - wu_nm, y_nm + wu_nm]].map { |x, y| [x / 1000.0, y / 1000.0] }
end

def angle_pair(wu_nm, gap_nm)
  [['M1', :polygon, bar45(5000, 5000, 2000, wu_nm)],
   ['M1', :polygon, bar45(5000 - (wu_nm + gap_nm), 5000 + (wu_nm + gap_nm),
                          2000, wu_nm)]]
end

def metal_pair(layer, width, height, gap)
  [box(layer, 0, 0, width, height),
   box(layer, width + gap, 0, 2 * width + gap, height)]
end

def eol_lines(gap, width = 0.1)
  [box('M1', 0, 0, width, 2), box('M1', 0, 2 + gap, width, 4 + gap)]
end

# Design extent of 1500x1500 um (2.25e6 um^2 > the 2e6 um^2 huge-void limit),
# set by an inert GRBLK corner, with a narrow M1 strip inside.
def huge_void_fixture(strip_width)
  [box('M1', 100, 100, 100 + strip_width, 298),
   box('GRBLK', 1600, 1600, 1600.1, 1600.1)]
end

FIXTURES = {
  # FEOL area predicates, inclusive threshold boundaries, and full/partial waivers.
  'clean' => [box('M1', 0, 0, 2, 1), box('M2', 0, 0, 2, 1), box('V1', 0.955, 0.455, 1.045, 0.545)],
  'act_area' => act_np(0, 0, 0.16, RULES['act_area'] * 0.5 / 0.16),
  'act_area_at_limit' => act_np(0, 0, 0.16, RULES['act_area'] / 0.16),
  'act_area_nodrc_waived' => act_np(0, 0, 0.16, RULES['act_area'] * 0.5 / 0.16) +
                             [box('NODRC', 0, 0, 0.16, RULES['act_area'] * 0.5 / 0.16)],

  # ACT family: width, same-layer/TG spacing, NW-to-active spacing and
  # enclosure (including the edge-based ENC form), holes, implant coverage,
  # and gate channel width from the PO-coincident gate edges.
  'act_width_bad' => act_np(0, 0, RULES['act_width'] - 0.01, 0.6),
  'act_width_at_limit' => act_np(0, 0, RULES['act_width'], 0.6),
  'act_spacing_bad' => [
    *act_np(0, 0, 0.3, 0.6),
    *act_np(0.3 + RULES['act_space'] - 0.01, 0, 0.6 + RULES['act_space'] - 0.01, 0.6),
  ],
  'act_spacing_at_limit' => [
    *act_np(0, 0, 0.3, 0.6),
    *act_np(0.3 + RULES['act_space'], 0, 0.6 + RULES['act_space'], 0.6),
  ],
  'act_tg_spacing_bad' => [
    *act_np(0, 0, 0.3, 0.6), box('TGOX', -0.1, -0.1, 0.4, 0.7),
    *act_np(0.3 + RULES['act_space_tg'] - 0.01, 0, 0.6 + RULES['act_space_tg'] - 0.01, 0.6),
  ],
  'act_tg_spacing_at_limit' => [
    *act_np(0, 0, 0.3, 0.6), box('TGOX', -0.1, -0.1, 0.4, 0.7),
    *act_np(0.3 + RULES['act_space_tg'], 0, 0.6 + RULES['act_space_tg'], 0.6),
  ],
  # The bare NW blocks below are not tapped, so NW1_R_1 adds
  # well.nw.floating to every category set here.
  'act_nw_nact_space_bad' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_np(0.5 + RULES['act_nw_nact_pw_space'] - 0.01, 0, 0.7 + RULES['act_nw_nact_pw_space'] - 0.01, 0.65),
  ],
  'act_nw_nact_space_at_limit' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_np(0.5 + RULES['act_nw_nact_pw_space'], 0, 0.7 + RULES['act_nw_nact_pw_space'], 0.65),
  ],
  'act_nw_nact_tg_space_bad' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_np(0.5 + RULES['act_nw_nact_tg_space'] - 0.01, 0, 0.7 + RULES['act_nw_nact_tg_space'] - 0.01, 0.65),
    box('TGOX', 0.65, -0.1, 1.05, 0.75),
  ],
  'act_nw_nact_tg_space_at_limit' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_np(0.5 + RULES['act_nw_nact_tg_space'], 0, 0.7 + RULES['act_nw_nact_tg_space'], 0.65),
    box('TGOX', 0.66, -0.1, 1.06, 0.75),
  ],
  'act_nw_pact_space_bad' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_pp(0.5 + RULES['act_nw_pact_space'] - 0.01, 0, 0.7 + RULES['act_nw_pact_space'] - 0.01, 0.65),
  ],
  'act_nw_pact_space_at_limit' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_pp(0.5 + RULES['act_nw_pact_space'], 0, 0.7 + RULES['act_nw_pact_space'], 0.65),
  ],
  'act_nact_nw_enclosure_bad' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_np(0.15 - 0.01, 0.15, 0.35, 0.5),
  ],
  'act_nact_nw_enclosure_at_limit' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_np(0.15, 0.15, 0.35, 0.5),
  ],
  'act_pact_nw_enclosure_bad' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_pp(0.15 - 0.01, 0.15, 0.35, 0.5),
  ],
  'act_pact_nw_enclosure_at_limit' => [
    box('NW', 0, 0, 0.5, 0.65),
    *act_pp(0.15, 0.15, 0.35, 0.5),
  ],
  'act_pact_nw_tg_enclosure_bad' => [
    box('NW', 0, 0, 0.8, 0.65), box('TGOX', -0.1, -0.1, 0.9, 0.75),
    *act_pp(0.3, 0.15, 0.5, 0.5),
  ],
  'act_pact_nw_tg_enclosure_at_limit' => [
    box('NW', 0, -0.16, 0.82, 0.81), box('TGOX', -0.1, -0.2, 0.92, 0.85),
    *act_pp(0.31, 0.15, 0.51, 0.5),
  ],
  'act_hole' => ring('ACT', 1, 1, 0.2, 0.3) + [box('NP', -0.15, -0.15, 1.15, 1.15)],
  'act_hole_at_limit' => ring('ACT', 1, 1, 0.2, 0.4) + [box('NP', -0.15, -0.15, 1.15, 1.15)],
  'act_implant_coverage_bad' => [box('ACT', 0, 0, 0.5, 0.5)],
  'act_implant_coverage_nw1res_waived' => [
    box('ACT', 0, 0, 0.5, 0.5), box('NW1RES', 0, 0, 0.5, 0.5),
  ],
  'act_channel_width_bad' => channel_width(RULES['act_channel_width'] - 0.02, 0.16),
  'act_channel_width_at_limit' => channel_width(RULES['act_channel_width'], 0.17),
  'act_io_channel_width_bad' => channel_width(RULES['act_io_channel_width'] - 0.01, 0.26, oxide: 'DGOX'),
  'act_io_channel_width_at_limit' => channel_width(RULES['act_io_channel_width'], 0.27, oxide: 'DGOX'),

  # ACT_W_2/ACT_S_3: 45-degree AA width and space. The perpendicular width and
  # gap of a bar45 are wu_nm*sqrt(2), so 126 nm = 0.1782 um (flagged) and
  # 128 nm = 0.1810 um. 127 nm rounds to exactly 180 dbu on the integer grid.
  # The rectangular NP cover keeps NP_EN_1/NP_O_1 quiet.
  'act_angle_width_bad' => [
    ['ACT', :polygon, bar45(2000, 2000, 2000, 126)],
    box('NP', 1.72, 1.85, 4.15, 4.28),
  ],
  'act_angle_width_at_limit' => [
    ['ACT', :polygon, bar45(2000, 2000, 2000, 128)],
    box('NP', 1.72, 1.85, 4.15, 4.28),
  ],
  'act_angle_space_bad' => [
    ['ACT', :polygon, bar45(5000, 5000, 2000, 128)],
    ['ACT', :polygon, bar45(5000 - (128 + 126), 5000 + (128 + 126), 2000, 128)],
    box('NP', 4.40, 4.80, 7.20, 7.60),
  ],
  'act_angle_space_at_limit' => [
    ['ACT', :polygon, bar45(5000, 5000, 2000, 128)],
    ['ACT', :polygon, bar45(5000 - (128 + 128), 5000 + (128 + 128), 2000, 128)],
    box('NP', 4.40, 4.80, 7.20, 7.60),
  ],
  # ACT_S_2: wide-AA spacing (width > 0.2, run >= 0.3, gap >= 0.08). The gap
  # stays in [0.11, 0.125) so ACT_S_1 (0.11) is not violated; the 0.21 um AA
  # width is above the 0.2 um wide threshold.
  'act_wide_space_bad' => [
    *act_np(0, 0, 0.21, 0.6),
    *act_np(0.21 + 0.121, 0, 0.42 + 0.121, 0.6),
  ],
  'act_wide_space_at_limit' => [
    *act_np(0, 0, 0.21, 0.6),
    *act_np(0.21 + 0.125, 0, 0.42 + 0.125, 0.6),
  ],
  # ACT_S_7: N+ active outside a NW that encloses a DNW. The marker is outside
  # DNW, so the source's NOT DNW waiver does not apply.
  'act_nw_dnw_space_bad' => [
    box('NW', 0, 0, 6.2, 6.2), box('DNW', 1.1, 1.1, 4.1, 4.1), *nw_tap(2.0, 0.3),
    box('ACT', 6.4, 2.5, 6.6, 2.7), box('NP', 6.25, 2.35, 6.75, 2.85),
  ],
  'act_nw_dnw_space_at_limit' => [
    box('NW', 0, 0, 6.2, 6.2), box('DNW', 1.1, 1.1, 4.1, 4.1), *nw_tap(2.0, 0.3),
    box('ACT', 6.52, 2.5, 6.72, 2.7), box('NP', 6.37, 2.35, 6.87, 2.85),
  ],
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

  # NP/PP implant family: widths/spacings on the implant layer itself
  # (Calibre SDN = COPY NPi, SDP = COPY PPi), the source NP-O.1/PP-O.1
  # AA overlap margin, the butted-AA zero-space rules, NP/PP mutual
  # exclusion, and the butted-tap minimum area.
  'np_width_bad' => [box('NP', 0, 0, RULES['np_width'] - 0.01, 0.8)],
  'np_width_at_limit' => [box('NP', 0, 0, RULES['np_width'], 0.8)],
  'np_spacing_bad' => [
    box('NP', 0, 0, 0.3, 0.5),
    box('NP', 0.3 + RULES['np_space'] - 0.01, 0, 0.6 + RULES['np_space'] - 0.01, 0.5),
  ],
  'np_spacing_at_limit' => [
    box('NP', 0, 0, 0.3, 0.5),
    box('NP', 0.3 + RULES['np_space'], 0, 0.6 + RULES['np_space'], 0.5),
  ],
  'pp_width_bad' => [box('PP', 0, 0, RULES['pp_width'] - 0.01, 0.8)],
  'pp_width_at_limit' => [box('PP', 0, 0, RULES['pp_width'], 0.8)],
  'pp_spacing_bad' => [
    box('PP', 0, 0, 0.3, 0.5),
    box('PP', 0.3 + RULES['pp_space'] - 0.01, 0, 0.6 + RULES['pp_space'] - 0.01, 0.5),
  ],
  'pp_spacing_at_limit' => [
    box('PP', 0, 0, 0.3, 0.5),
    box('PP', 0.3 + RULES['pp_space'], 0, 0.6 + RULES['pp_space'], 0.5),
  ],
  'np_act_overlap_bad' => act_np(0, 0, 0.3, 0.3, RULES['np_act_overlap'] - 0.01),
  'np_act_overlap_at_limit' => act_np(0, 0, 0.3, 0.3, RULES['np_act_overlap']),
  'pp_act_overlap_bad' => act_pp(0, 0, 0.3, 0.3, RULES['pp_act_overlap'] - 0.01),
  'pp_act_overlap_at_limit' => act_pp(0, 0, 0.3, 0.3, RULES['pp_act_overlap']),
  # NP AND PACT is a zero-space rule; any overlap also violates PP_R_1 because
  # PACT is a subset of PP, so both categories fire as in the Calibre source.
  # The overlapping implants make the tap regions butt against the opposite
  # source/drain, so CT_R_5 fires without a CT; each fixture carries one legal
  # CT/M1 pair in the tap region to keep the expected set on the implant rule.
  'np_s4_bad' => [
    box('ACT', 0, 0, 0.4, 0.3), box('PP', -0.15, -0.15, 0.55, 0.45),
    box('NP', 0.2, -0.15, 0.7, 0.45),
    box('CT', 0.055, 0.105, 0.145, 0.195), box('M1', 0, 0, 0.4, 0.3),
  ],
  # NP_S_4 is waived inside SRAMALL, PP_R_1 carries no such waiver.
  'np_s4_sram_waived' => [
    box('ACT', 0, 0, 0.4, 0.3), box('PP', -0.15, -0.15, 0.55, 0.45),
    box('NP', 0.2, -0.15, 0.7, 0.45), box('SRAMALL', -0.5, -0.5, 1, 1),
    box('CT', 0.055, 0.105, 0.145, 0.195), box('M1', 0, 0, 0.4, 0.3),
  ],
  'pp_s4_bad' => [
    box('ACT', 0, 0, 0.4, 0.3), box('NP', -0.15, -0.15, 0.55, 0.45),
    box('PP', 0.2, -0.15, 0.7, 0.45),
    box('CT', 0.255, 0.105, 0.345, 0.195), box('M1', 0, 0, 0.4, 0.3),
  ],
  'pp_r1_bad' => [box('NP', 0, 0, 0.4, 0.4), box('PP', 0.3, 0, 0.7, 0.4)],
  'np_tap_area_bad' => [
    box('ACT', 0, 0, 0.6, 0.2), box('NW', -0.15, -0.15, 0.75, 0.35),
    box('NP', -0.15, -0.15, 0.18, 0.35), box('PP', 0.18, -0.15, 0.75, 0.35),
    box('CT', 0.045, 0.055, 0.135, 0.145), box('M1', 0, 0, 0.6, 0.2),
  ],
  'np_tap_area_at_limit' => [
    box('ACT', 0, 0, 0.6, 0.2), box('NW', -0.15, -0.15, 0.75, 0.35),
    box('NP', -0.15, -0.15, 0.2, 0.35), box('PP', 0.2, -0.15, 0.75, 0.35),
    box('CT', 0.055, 0.055, 0.145, 0.145), box('M1', 0, 0, 0.6, 0.2),
  ],
  'pp_tap_area_bad' => [
    box('ACT', 0, 0, 0.6, 0.2),
    box('PP', -0.15, -0.15, 0.18, 0.35), box('NP', 0.18, -0.15, 0.75, 0.35),
    box('CT', 0.045, 0.055, 0.135, 0.145), box('M1', 0, 0, 0.6, 0.2),
  ],
  'pp_tap_area_at_limit' => [
    box('ACT', 0, 0, 0.6, 0.2),
    box('PP', -0.15, -0.15, 0.2, 0.35), box('NP', 0.2, -0.15, 0.75, 0.35),
    box('CT', 0.055, 0.055, 0.145, 0.145), box('M1', 0, 0, 0.6, 0.2),
  ],

  # NP/PP to opposite-type AA spacings. Approaching within the opposite
  # implant's enclosure margin necessarily overlaps the opposite implant, so
  # the bad fixtures also report PP_R_1, as the source does.
  # NP_S_2: PMOS AA inside NW at 0.11/0.12 um; PP margin is 0.12 (PP_EN_2).
  'np_pact_space_bad' => [
    box('NW', 0, 0, 3, 3), *nw_tap(0.2, 0.2),
    *act_pp(1.0, 1.0, 1.4, 1.4, 0.12),
    box('NP', 1.51, 0.8, 2.0, 1.6),
  ],
  'np_pact_space_at_limit' => [
    box('NW', 0, 0, 3, 3), *nw_tap(0.2, 0.2),
    *act_pp(1.0, 1.0, 1.4, 1.4, 0.12),
    box('NP', 1.52, 0.8, 2.0, 1.6),
  ],
  # NP_S_3: P+ pickup in PW at 0.01/0.02 um; PP margin is 0.02 (PP_EN_1).
  'np_ptap_space_bad' => [
    *act_pp(1.0, 1.0, 1.4, 1.4, 0.02),
    box('NP', 1.41, 0.8, 1.9, 1.6),
  ],
  'np_ptap_space_at_limit' => [
    *act_pp(1.0, 1.0, 1.4, 1.4, 0.02),
    box('NP', 1.42, 0.8, 1.9, 1.6),
  ],
  # PP_S_2: NMOS AA in PW at 0.11/0.12 um; NP margin is 0.12 (NP_EN_2 limit).
  'pp_nact_space_bad' => [
    *act_np(1.0, 1.0, 1.4, 1.4, 0.12),
    box('PP', 1.51, 0.8, 2.0, 1.6),
  ],
  'pp_nact_space_at_limit' => [
    *act_np(1.0, 1.0, 1.4, 1.4, 0.12),
    box('PP', 1.52, 0.8, 2.0, 1.6),
  ],
  # PP_S_3: N+ pickup inside NW at 0.01/0.02 um; the NP margin is 0.15, so the
  # at-limit fixture still reports the implant overlap (PP_R_1) only.
  'pp_ntap_space_bad' => [
    box('NW', 0, 0, 3, 3), *nw_tap(0.2, 0.2),
    *act_np(1.0, 1.0, 1.4, 1.4),
    box('PP', 1.41, 0.8, 1.9, 1.6),
  ],
  'pp_ntap_space_at_limit' => [
    box('NW', 0, 0, 3, 3), *nw_tap(0.2, 0.2),
    *act_np(1.0, 1.0, 1.4, 1.4),
    box('PP', 1.42, 0.8, 1.9, 1.6),
  ],
  # NP_S_5/PP_S_5: opposite-type gate 0.15/0.30 um away. The gate poly crosses
  # the AA and the implant is placed over field above the PP/NP cover, touching
  # the cover edge but not overlapping it. The implant side margin to the poly
  # is 0.15, so NP_EN_3/PP_EN_3 stay quiet.
  # The PMOS gate is the source-derived GATE (a transistor gate whose two
  # source/drain regions are contacted), so the fixture is a complete PMOS
  # with a CT/M1 pad on each side.
  'np_gate_space_bad' => [
    box('NW', 0, 0, 4, 3), *nw_tap(0.2, 0.2),
    box('ACT', 1.0, 1.0, 2.2, 1.6), box('PP', 0.85, 0.85, 2.35, 1.75),
    box('POLY', 1.55, 0.5, 1.65, 2.5),
    box('CT', 1.15, 1.25, 1.24, 1.34), box('CT', 1.96, 1.25, 2.05, 1.34),
    box('M1', 1.05, 1.15, 1.34, 1.44), box('M1', 1.86, 1.15, 2.15, 1.44),
    box('NP', 1.35, 1.75, 1.85, 2.05),
  ],
  'np_gate_space_at_limit' => [
    box('NW', 0, 0, 4, 3), *nw_tap(0.2, 0.2),
    box('ACT', 1.0, 1.0, 2.2, 1.6), box('PP', 0.85, 0.85, 2.35, 1.75),
    box('POLY', 1.55, 0.5, 1.65, 2.5),
    box('CT', 1.15, 1.25, 1.24, 1.34), box('CT', 1.96, 1.25, 2.05, 1.34),
    box('M1', 1.05, 1.15, 1.34, 1.44), box('M1', 1.86, 1.15, 2.15, 1.44),
    box('NP', 1.35, 1.90, 1.85, 2.20),
  ],
  'pp_gate_space_bad' => [
    box('ACT', 1.0, 1.0, 1.6, 1.6),
    box('NP', 0.85, 0.85, 1.75, 1.75),
    box('POLY', 1.25, 0.5, 1.35, 2.5),
    box('PP', 1.05, 1.75, 1.55, 2.05),
  ],
  'pp_gate_space_at_limit' => [
    box('ACT', 1.0, 1.0, 1.6, 1.6),
    box('NP', 0.85, 0.85, 1.75, 1.75),
    box('POLY', 1.25, 0.5, 1.35, 2.5),
    box('PP', 1.05, 1.90, 1.55, 2.20),
  ],
  # NP_EN_1/PP_EN_1: AA enclosure by the same-type implant at 0.01/0.02 um.
  # The 0.01 um margin also violates the 0.12 um NP_O_1/PP_O_1 overlap margin.
  # N+ active is placed inside NW so NP_EN_2 (the 0.12 um inside-PW form)
  # does not co-fire; the 0.4 um AA keeps NP_A_1 quiet.
  'np_aa_enclosure_bad' => [
    box('NW', 0, 0, 3, 3), *nw_tap(0.2, 0.2),
    *act_np(1.2, 1.2, 1.6, 1.6, 0.01),
  ],
  'np_aa_enclosure_at_limit' => [
    box('NW', 0, 0, 3, 3), *nw_tap(0.2, 0.2),
    *act_np(1.2, 1.2, 1.6, 1.6, 0.02),
  ],
  'pp_ptap_enclosure_bad' => act_pp(0, 0, 0.4, 0.4, 0.01),
  'pp_ptap_enclosure_at_limit' => act_pp(0, 0, 0.4, 0.4, 0.02),
  # NP_EN_2/PP_EN_2: active inside PW/NW enclosure by the implant at 0.11/0.12
  # um; the 0.11 um case also violates the 0.12 um implant overlap margin.
  'np_nact_pw_enclosure_bad' => act_np(0, 0, 0.3, 0.3, 0.11),
  'np_nact_pw_enclosure_at_limit' => act_np(0, 0, 0.3, 0.3, 0.12),
  'pp_pact_nw_enclosure_bad' => [
    box('NW', 0, 0, 2.5, 2.5), *nw_tap(0.2, 0.2),
    *act_pp(1.0, 1.0, 1.4, 1.4, 0.11),
  ],
  'pp_pact_nw_enclosure_at_limit' => [
    box('NW', 0, 0, 2.5, 2.5), *nw_tap(0.2, 0.2),
    *act_pp(1.0, 1.0, 1.4, 1.4, 0.12),
  ],
  # NP_EN_3/PP_EN_3: field-poly end enclosure by the implant at 0.149/0.15 um.
  'np_po_enclosure_bad' => [box('POLY', 0, 0, 0.1, 0.5), box('NP', -0.2, 0.3, 0.3, 0.649)],
  'np_po_enclosure_at_limit' => [box('POLY', 0, 0, 0.1, 0.5), box('NP', -0.2, 0.3, 0.3, 0.65)],
  'pp_po_enclosure_bad' => [box('POLY', 0, 0, 0.1, 0.5), box('PP', -0.2, 0.3, 0.3, 0.649)],
  'pp_po_enclosure_at_limit' => [box('POLY', 0, 0, 0.1, 0.5), box('PP', -0.2, 0.3, 0.3, 0.65)],

  # PSUB native NMOS blocked implant. PSUB_EN_1 is an exact-shape halo XOR, so
  # every transistor fixture draws PSUB as the exact 0.285 um ACT halo.
  'psub_area_bad' => [box('PSUB', 0, 0, 0.75, 0.799)],
  'psub_area_at_limit' => [box('PSUB', 0, 0, 0.75, 0.8)],
  'psub_area_nodrc_waived' => [box('PSUB', 0, 0, 0.75, 0.799), box('NODRC', 0, 0, 0.75, 0.799)],
  'psub_hole_area_bad' => ring('PSUB', 2, 2, 0.7, 0.7),
  'psub_hole_area_at_limit' => ring('PSUB', 2, 2, 0.75, 0.8),
  'psub_width_bad' => [box('PSUB', 0, 0, 0.46, 1.4)],
  'psub_width_at_limit' => [box('PSUB', 0, 0, 0.47, 1.3)],
  'psub_space_bad' => [box('PSUB', 0, 0, 0.75, 0.8), box('PSUB', 1.21, 0, 1.96, 0.8)],
  'psub_space_at_limit' => [box('PSUB', 0, 0, 0.75, 0.8), box('PSUB', 1.22, 0, 1.97, 0.8)],
  'psub_nw_space_bad' => [box('PSUB', 0, 0, 1.2, 0.5), box('NW', 2.34, 0, 6, 4)],
  'psub_nw_space_at_limit' => [box('PSUB', 0, 0, 1.2, 0.5), box('NW', 2.35, 0, 6, 4)],
  'psub_mos_space_bad' => [box('PSUB', 0, 0, 0.75, 0.8), *act_np(1.10, 0.2, 1.30, 0.4)],
  'psub_mos_space_at_limit' => [box('PSUB', 0, 0, 0.75, 0.8), *act_np(1.11, 0.2, 1.31, 0.4)],
  'psub_channel_width_bad' => psub_native(0.4, 0.2),
  'psub_channel_width_at_limit' => psub_native(0.5, 0.2),
  'psub_channel_width_max_bad' => psub_native(100.5, 0.2),
  'psub_core_length_bad' => psub_native(1.0, 0.19),
  'psub_core_length_at_limit' => psub_native(1.0, 0.2),
  'psub_core_length_max_bad' => psub_native(1.0, 100.5),
  'psub_io1_length_bad' => psub_native(1.0, 0.79, oxide: 'DGOX'),
  'psub_io1_length_at_limit' => psub_native(1.0, 0.8, oxide: 'DGOX'),
  'psub_io1_length_max_bad' => psub_native(1.0, 20.5, oxide: 'DGOX'),
  'psub_io2_length_bad' => psub_native(1.0, 0.99, oxide: 'TGOX'),
  'psub_io2_length_at_limit' => psub_native(1.0, 1.0, oxide: 'TGOX'),
  'psub_gate_ext_bad' => psub_native(1.0, 0.3, poly_end: 0.31),
  'psub_gate_ext_at_limit' => psub_native(1.0, 0.3, poly_end: 0.32),
  'psub_dnw_overlap_bad' => [
    box('NW', 0, 0, 6.5, 6.5), box('DNW', 2, 2, 5.1, 5.1), *nw_tap(0.2, 0.2),
    box('PSUB', 1.6, 2.1, 2.8, 3.1),
  ],
  'psub_dnw_coincident_bad' => [
    box('NW', 0, 0, 6.5, 6.5), box('DNW', 2, 2, 5.1, 5.1), *nw_tap(0.2, 0.2),
    box('PSUB', 0.5, 2.0, 2.0, 2.8),
  ],
  'psub_multi_aa_bad' => [
    box('PSUB', 0.015, 0.015, 1.485, 0.885),
    *act_np(0.3, 0.3, 0.6, 0.6), *act_np(0.9, 0.3, 1.2, 0.6),
  ],
  'psub_multi_aa_indall_waived' => [
    box('PSUB', 0.015, 0.015, 1.485, 0.885),
    *act_np(0.3, 0.3, 0.6, 0.6), *act_np(0.9, 0.3, 1.2, 0.6),
    box('INDALL', 0.8, 0.2, 1.3, 0.7),
  ],
  'psub_pp_gate_overlap_bad' => psub_native(1.0, 0.3) +
    [box('PP', 0.0, 1.56, 1.0, 1.74)],
  'ct_outside_required_layers' => [box('CT', 0, 0, 0.09, 0.09)],

  'ct_active_enclosure_bad' => [
    box('CTBAR', 0, 0, 0.09, 0.09),
    *act_np(-(RULES['ct_drc_enc_act'] - 0.001), -(RULES['ct_drc_enc_act'] - 0.001), 1, 1),
    box('M1', -0.1, -0.1, 1, 1),
  ],
  'ct_active_enclosure_at_limit' => [
    box('CTBAR', 0, 0, 0.09, 0.09),
    *act_np(-RULES['ct_en2_dir'], -RULES['ct_drc_enc_act'], 1, 1),
    box('M1', -0.1, -0.1, 1, 1),
  ],
  'ct_active_enclosure_dir_ok' => [
    box('CT', 0, 0, 0.09, 0.09),
    *act_np(-RULES['ct_en2_dir'], -0.02, 1, 1),
    box('M1', -0.1, -0.1, 1, 1),
  ],
  'ct_active_enclosure_dir_bad' => [
    box('CT', 0, 0, 0.09, 0.09),
    *act_np(-0.02, -0.02, 1, 1),
    box('M1', -0.1, -0.1, 1, 1),
  ],

  # Source CT width/spacing/coverage predicates.
  'ct_width_bad' => [
    box('CT', 0.2, 0.2, 0.29, 0.32), *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_width_at_limit' => [
    box('CT', 0.2, 0.2, 0.29, 0.29), *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_width_efuse_bad' => [
    box('CT', 0.2, 0.2, 0.32, 0.32), box('EFUSEALL', 0, 0, 1, 1),
    box('FUSEALL', 0, 0, 1, 1), box('POEFUSEBLK', 0, 0, 1, 1),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_width_sram_bad' => [
    box('CT', 0.2, 0.2, 0.32, 0.32), box('SRAMALL', 0, 0, 1, 1),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_width_grid_bad' => [
    box('CT', 0.2, 0.2, 0.29, 0.32), box('GRBLK', 0, 0, 1, 1),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_width_grid_ring_waived' => [
    box('CT', 0.2, 0.2, 0.4, 0.4), box('SRINGBLK_SRC', 0, 0, 1, 1),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_bar_width_bad' => [
    box('CTBAR', 0.2, 0.2, 0.28, 0.5), *act_np(-0.1, -0.1, 1, 1), box('M1', -0.1, -0.1, 1, 1),
  ],
  'ct_bar_at_limit' => [
    box('CTBAR', 0.2, 0.2, 0.29, 0.29), *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_spacing_bad' => [
    box('CT', 0.2, 0.2, 0.29, 0.29), box('CT', 0.39, 0.2, 0.48, 0.29),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_spacing_at_limit' => [
    box('CT', 0.2, 0.2, 0.29, 0.29), box('CT', 0.4, 0.2, 0.49, 0.29),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  # CT_S_1a: 3x3 contact array at a 0.13 (bad) / 0.14 (limit) um pitch. The
  # pitch passes the 0.11 um CT_S_1 minimum, so only the dense-array limit
  # reports the bad case.
  'ct_s1a_bad' => [
    *[0.2, 0.42, 0.64].product([0.2, 0.42, 0.64]).map { |x, y| box('CT', x, y, x + 0.09, y + 0.09) },
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_s1a_at_limit' => [
    *[0.2, 0.43, 0.66].product([0.2, 0.43, 0.66]).map { |x, y| box('CT', x, y, x + 0.09, y + 0.09) },
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  # CT_EN_4d: the 1.2 um wide M1 is caught by WITH WIDTH > 1; the y-direction
  # enclosure is above 0.04, so only the x-side distance drives the bad case.
  'ct_en4d_bad' => [
    box('CT', 0.03, 0.2, 0.12, 0.29), *act_np(-0.05, 0.1, 0.5, 0.4),
    box('M1', 0, 0, 1.2, 1.2),
  ],
  'ct_en4d_at_limit' => [
    box('CT', 0.04, 0.2, 0.13, 0.29), *act_np(-0.05, 0.1, 0.5, 0.4),
    box('M1', 0, 0, 1.2, 1.2),
  ],
  'ct_poly_active_space_bad' => [
    box('CT', 0, 0, 0.09, 0.09), box('POLY', -0.2, -0.2, 0.14, 0.14),
    *act_np(0.154, -0.1, 1, 1), box('M1', -0.1, -0.1, 1, 1),
  ],
  'ct_poly_active_space_at_limit' => [
    box('CT', 0, 0, 0.09, 0.09), box('POLY', -0.2, -0.2, 0.14, 0.14),
    *act_np(0.155, -0.1, 1, 1), box('M1', -0.1, -0.1, 1, 1),
  ],
  'ct_core_gate_space_bad' => [
    *act_np(0, 0, 2, 1), box('POLY', 0.5, -0.2, 0.6, 1.2),
    box('CT', 0.405, 0.2, 0.495, 0.29), box('CT', 1.0, 0.2, 1.09, 0.29),
    box('M1', 0, 0, 2, 1),
  ],
  'ct_core_gate_space_at_limit' => [
    *act_np(0, 0, 2, 1), box('POLY', 0.5, -0.2, 0.6, 1.2),
    box('CT', 0.355, 0.2, 0.445, 0.29), box('CT', 1.0, 0.2, 1.09, 0.29),
    box('M1', 0, 0, 2, 1),
  ],
  'ct_io_gate_space_bad' => [
    *act_np(0, 0, 2, 1), box('POLY', 0.5, -0.2, 0.6, 1.2),
    box('DGOX', -0.32, -0.32, 2.32, 1.32),
    box('CT', 0.405, 0.2, 0.495, 0.29), box('CT', 1.0, 0.2, 1.09, 0.29),
    box('M1', 0, 0, 2, 1),
  ],
  'ct_io_gate_space_at_limit' => [
    *act_np(0, 0, 2, 1), box('POLY', 0.5, -0.2, 0.6, 1.2),
    box('DGOX', -0.32, -0.32, 2.32, 1.32),
    box('CT', 0.32, 0.2, 0.41, 0.29), box('CT', 1.0, 0.2, 1.09, 0.29),
    box('M1', 0, 0, 2, 1),
  ],
  'ct_active_coverage_bad' => [
    box('CT', 0, 0, 0.09, 0.09), *act_np(0.05, -0.1, 1, 1),
    box('NODRC', -0.1, -0.1, 0.2, 0.2),
  ],
  'ct_poly_coverage_bad' => [
    box('CT', 0, 0, 0.09, 0.09), box('POLY', 0.045, -0.1, 1, 1),
    box('NODRC', -0.1, -0.1, 0.2, 0.2),
  ],
  'ct_poly_enclosure_bad' => [
    box('POLY', 0, -0.5, 0.1, 0.1), box('CT', 0.005, 0.005, 0.095, 0.095),
    box('M1', -0.1, -0.6, 0.2, 0.2),
  ],
  'ct_poly_enclosure_at_limit' => [
    box('POLY', -RULES['ct_en3_all'], -RULES['ct_en3_all'], 0.5, 0.09 + RULES['ct_en3_all']),
    box('CT', 0, 0, 0.09, 0.09), box('M1', -0.1, -0.1, 0.6, 0.2),
  ],
  'ct_poly_enclosure_directional_ok' => [
    box('POLY', -RULES['ct_en3_dir'], -0.5, 0.09 + RULES['ct_en3_dir'], 0.09 + RULES['ct_en3_min']),
    box('CT', 0, 0, 0.09, 0.09), box('M1', -0.1, -0.6, 0.2, 0.2),
  ],
  'ct_poly_enclosure_all_bad' => [
    box('POLY', -0.03, -0.5, 0.12, 0.11),
    box('CT', 0, 0, 0.09, 0.09), box('M1', -0.1, -0.6, 0.2, 0.2),
  ],
  'ct_m1_enclosure_directional_ok' => [
    box('CT', 0, 0, 0.09, 0.09), *act_np(-0.1, -0.1, 0.2, 0.2),
    box('M1', -RULES['ct_en4_dir'], -0.01, 0.09 + RULES['ct_en4_dir'], 1),
  ],
  'ct_m1_enclosure_all_bad' => [
    box('CT', 0, 0, 0.09, 0.09), *act_np(-0.1, -0.1, 0.2, 0.2),
    box('M1', -0.03, -0.5, 0.12, 0.11),
  ],
  'ct_m1_coverage_bad' => [
    box('CT', 0, 0, 0.09, 0.09), box('M1', 0.05, -0.1, 1, 1),
  ],
  'ct_m1_not_interacting' => [
    box('CT', 0, 0, 0.09, 0.09), box('SRAMALL', -0.1, -0.1, 0.2, 0.2),
  ],
  'ct_on_gate' => [
    *act_np(0, 0, 1, 1), box('POLY', 0.35, -0.1, 0.55, 1.1),
    box('CT', 0.39, 0.4, 0.48, 0.49),
    box('CT', 0.15, 0.2, 0.24, 0.29), box('CT', 0.7, 0.2, 0.79, 0.29),
    box('M1', 0, 0, 1, 1),
  ],
  'ct_sab' => [
    box('CT', 0.2, 0.2, 0.29, 0.29), box('SAB', 0.25, 0.25, 0.35, 0.35),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_rotated' => [
    diamond('CT', 0.5, 0.5, 0.2), *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  'ct_rotated_sring_waived' => [
    diamond('CT', 0.5, 0.5, 0.2), box('SRINGBLK_SRC', 0, 0, 1, 1),
    *act_np(0, 0, 1, 1), box('M1', 0, 0, 1, 1),
  ],
  # The butted tap crosses the NW boundary, so the generic ACT_S_5 space check
  # sees a zero gap between NW and the N+ active in PW; SRAMALL waives that
  # (approximated) rule while CT_R_5 has no SRAMALL waiver and still fires.
  # The waiver is whole-shape, so SRAMALL must fully cover the NW shape.
  'ct_tap_bad' => [
    box('ACT', 0, 0, 1, 1), box('NP', -0.15, -0.15, 1.15, 1.15), box('NW', 0.5, -0.15, 1.15, 1.15),
    box('SRAMALL', -0.5, -0.5, 1.5, 1.5),
  ],
  'ct_tap_with_ct' => [
    box('ACT', 0, 0, 1, 1), box('NP', -0.15, -0.15, 1.15, 1.15), box('NW', 0.5, -0.15, 1.15, 1.15),
    box('CT', 0.455, 0.455, 0.545, 0.545), box('M1', 0, 0, 1, 1),
    box('SRAMALL', -0.5, -0.5, 1.5, 1.5),
  ],

  # Wells: NW1 area/hole/width/spacing/floating and DNW width/space/N+ SD
  # spacing/enclosure/coverage/TPW. Every NW carries a legal N+ pickup (CT and
  # M1) so NW1_R_1 stays quiet; DNW fixtures keep the deep well inside NW with
  # the 1.0 um margin unless the enclosure or coverage clause is under test.
  'nw_area' => [box('NW', 0, 0, 0.5, 0.59), *nw_tap(0.18, 0.15, 0.14, 0.29)],
  'nw_area_at_limit' => [box('NW', 0, 0, 0.5, 0.6), *nw_tap(0.18, 0.15)],
  'nw_hole' => [*ring('NW', 1.7, 1.7, 0.5, 0.5), *nw_tap(0.2, 0.2)],
  'nw_hole_at_limit' => [*ring('NW', 1.7, 1.7, 0.5, 0.6), *nw_tap(0.2, 0.2)],
  'nw_width_bad' => [box('NW', 0, 0, 0.45, 0.7), *nw_tap(0.155, 0.15)],
  'nw_width_at_limit' => [box('NW', 0, 0, RULES['nw_width'], 0.7), *nw_tap(0.165, 0.15)],
  'nw_space_bad' => [
    box('NW', 0, 0, 0.5, 0.62), *nw_tap(0.18, 0.15),
    box('NW', 0.96, 0, 1.46, 0.62), *nw_tap(1.14, 0.15),
  ],
  'nw_space_at_limit' => [
    box('NW', 0, 0, 0.5, 0.62), *nw_tap(0.18, 0.15),
    box('NW', RULES['nw_width'] + 0.5, 0, RULES['nw_width'] + 1.0, 0.62),
    *nw_tap(RULES['nw_width'] + 0.68, 0.15),
  ],
  'nw_floating' => [box('NW', 0, 0, 0.5, 0.62)],
  'nw_floating_tapped' => [box('NW', 0, 0, 0.5, 0.62), *nw_tap(0.18, 0.15)],

  'dnw_clean' => [
    box('NW', 0, 0, 5.4, 5.4), box('DNW', 1.1, 1.1, 4.3, 4.3), *nw_tap(2.0, 0.3),
  ],
  'dnw_width_bad' => [
    box('NW', 0, 0, 5.1, 5.4), box('DNW', 1.1, 1.1, 4.0, 4.3), *nw_tap(2.0, 0.3),
  ],
  'dnw_width_at_limit' => [
    box('NW', 0, 0, 5.2, 5.4), box('DNW', 1.1, 1.1, 4.1, 4.3), *nw_tap(2.0, 0.3),
  ],
  'dnw_space_bad' => [
    box('NW', 0, 0, 12, 5.4), box('DNW', 1.1, 1.1, 4.3, 4.3),
    box('DNW', 7.7, 1.1, 10.9, 4.3), *nw_tap(5.0, 0.3),
  ],
  'dnw_space_at_limit' => [
    box('NW', 0, 0, 12.1, 5.4), box('DNW', 1.1, 1.1, 4.3, 4.3),
    box('DNW', 7.8, 1.1, 11.0, 4.3), *nw_tap(5.0, 0.3),
  ],
  'dnw_nsdi_space_bad' => [
    box('NW', 0, 0, 5.4, 5.4), box('DNW', 1.1, 1.1, 4.3, 4.3), *nw_tap(2.0, 0.3),
    box('ACT', 5.89, 2.5, 6.09, 2.7), box('NP', 5.74, 2.35, 6.24, 2.85),
  ],
  'dnw_nsdi_space_at_limit' => [
    box('NW', 0, 0, 5.4, 5.4), box('DNW', 1.1, 1.1, 4.3, 4.3), *nw_tap(2.0, 0.3),
    box('ACT', 5.9, 2.5, 6.1, 2.7), box('NP', 5.75, 2.35, 6.25, 2.85),
  ],
  'dnw_nw_enclosure_bad' => [
    box('NW', 0, 0, 5.2, 5.4), box('DNW', 0.9, 1.1, 4.1, 4.3), *nw_tap(2.0, 0.3),
  ],
  'dnw_nw_enclosure_at_limit' => [
    box('NW', 0, 0, 5.2, 5.4), box('DNW', 1.0, 1.1, 4.1, 4.3), *nw_tap(2.0, 0.3),
  ],
  # DNW edge exactly on the NW boundary: zero enclosure, reported by the
  # source's COINCIDENT EDGE clause instead of the enclosure strip.
  'dnw_nw_coincident_bad' => [
    box('NW', 0, 0, 5.0, 5.4), box('DNW', 0, 1.1, 3.2, 4.1), *nw_tap(2.0, 0.3),
  ],
  # DNW outside NW: TPW = PW inside DNW. A P+ pickup inside TPW suppresses
  # DNW_R_3; the coverage clause of DNW_EN_1 reports the DNW outside NW.
  'dnw_nw_coverage_bad' => [
    box('NW', -1.1, -1.1, 3.0, 3.0), box('DNW', 0, 0, 3.5, 3.5), *nw_tap(0.5, -0.6),
    box('ACT', 3.2, 1.0, 3.4, 1.24), box('PP', 3.05, 0.85, 3.55, 1.39),
    box('CT', 3.255, 1.075, 3.345, 1.165), box('M1', 3.15, 0.95, 3.45, 1.29),
  ],
  # NODRC waives the coverage output (the source DNW_R_3 has no NODRC waiver),
  # isolating the floating-TPW report.
  'dnw_tpw_floating' => [
    box('NW', -1.1, -1.1, 3.0, 3.0), box('DNW', 0, 0, 3.5, 3.5), *nw_tap(0.5, -0.6),
    box('NODRC', -2, -2, 5, 5),
  ],
  # Gate-covered non-tap N+ AA inside the DNW edge: DNW_EN_2 fires at 0.54 um
  # enclosure while the full gate keeps NSDi empty, so DNW_S_5 cannot fire.
  'dnw_nact_enclosure_bad' => [
    box('NW', -1.1, -1.1, 3.0, 3.0), box('DNW', 0, 0, 4.1, 4.1), *nw_tap(0.5, -0.6),
    box('ACT', 3.3, 1.0, 3.56, 1.26), box('NP', 3.15, 0.85, 3.71, 1.41),
    box('POLY', 3.2, 0.8, 3.7, 1.5),
    box('ACT', 3.16, 1.6, 3.36, 1.84), box('PP', 3.01, 1.45, 3.51, 1.99),
    box('CT', 3.215, 1.675, 3.305, 1.765), box('M1', 3.11, 1.55, 3.41, 1.89),
  ],
  'dnw_nact_enclosure_at_limit' => [
    box('NW', -1.1, -1.1, 3.0, 3.0), box('DNW', 0, 0, 4.1, 4.1), *nw_tap(0.5, -0.6),
    box('ACT', 3.3, 1.0, 3.55, 1.26), box('NP', 3.15, 0.85, 3.7, 1.41),
    box('POLY', 3.2, 0.8, 3.7, 1.5),
    box('ACT', 3.16, 1.6, 3.36, 1.84), box('PP', 3.01, 1.45, 3.51, 1.99),
    box('CT', 3.215, 1.675, 3.305, 1.765), box('M1', 3.11, 1.55, 3.41, 1.89),
  ],

  # DNW_O_1: NW/DNW overlap sliver. A P+ pickup inside the TPW suppresses
  # DNW_R_3; the DNW outside NW still trips the coverage clause of DNW_EN_1.
  'dnw_o1_bad' => [
    box('NW', -1.1, -1.1, 3.0, 3.0), box('DNW', 2.7, 0.2, 5.7, 3.4), *nw_tap(0.5, -0.6),
    box('ACT', 4.2, 1.0, 4.4, 1.24), box('PP', 4.05, 0.85, 4.55, 1.39),
    box('CT', 4.255, 1.075, 4.345, 1.165), box('M1', 4.15, 0.95, 4.45, 1.29),
  ],
  'dnw_o1_at_limit' => [
    box('NW', -1.1, -1.1, 3.0, 3.0), box('DNW', 2.6, 0.2, 5.6, 3.4), *nw_tap(0.5, -0.6),
    box('ACT', 4.2, 1.0, 4.4, 1.24), box('PP', 4.05, 0.85, 4.55, 1.39),
    box('CT', 4.255, 1.075, 4.345, 1.165), box('M1', 4.15, 0.95, 4.45, 1.29),
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

  # Metal width, maximum width, 45-degree, wide-metal, dense line-end and
  # huge-void rules. Geometry is chosen to keep every other metal category quiet.
  'm1_width_bad' => [box('M1', 0, 0, RULES['m1_width'] - 0.01, 0.6)],
  'm1_width_at_limit' => [box('M1', 0, 0, RULES['m1_width'], 0.6)],
  'm1_max_width_bad' => [box('M1', 0, 0, RULES['m1_max_width'] + 0.002, 14)],
  'm1_max_width_at_limit' => [box('M1', 0, 0, RULES['m1_max_width'], 14)],
  # Perpendicular widths: 133 nm*sqrt(2)=0.188 um (bad), 134 nm*sqrt(2)=0.1895 um
  # (nearest legal grid point below the flagged 0.19 um threshold).
  'm1_angle_width_bad' => [['M1', :polygon, bar45(3000, 3000, 2000, 133)]],
  'm1_angle_width_at_limit' => [['M1', :polygon, bar45(3000, 3000, 2000, 134)]],
  # 45-degree gaps: 85 nm*sqrt(2)=0.120 um (bad, above the 0.11 dense-EOL
  # limit), 135 nm*sqrt(2)=0.191 um (nearest legal grid point above 0.19).
  'm1_angle_space_bad' => angle_pair(135, 85),
  'm1_angle_space_at_limit' => angle_pair(135, 135),
  'm1_wide_space_bad' => metal_pair('M1', 0.5, 2, RULES['metal_wide_space'] - 0.01),
  'm1_wide_space_at_limit' => metal_pair('M1', 0.5, 2, RULES['metal_wide_space']),
  'm1_wide_space_short_run' => [
    box('M1', 0, 0, 0.5, 2),
    box('M1', 0.64, 1.7, 1.14, 4),
  ],
  'm1_wide_space_narrow' => metal_pair('M1', RULES['metal_wide_width'] - 0.12, 2,
                                       RULES['metal_wide_space'] - 0.01),
  'm1_wider_space_bad' => metal_pair(
    'M1', RULES['metal_wider_width'] + 0.1, 3,
    (RULES['metal_wide_space'] + RULES['metal_wider_space']) / 2.0),
  'm1_wider_space_at_limit' => metal_pair('M1', RULES['metal_wider_width'] + 0.1, 3,
                                          RULES['metal_wider_space']),
  'm1_wider_space_narrow' => metal_pair('M1', RULES['metal_wider_width'] - 0.1, 3,
                                        (RULES['metal_wide_space'] + RULES['metal_wider_space']) / 2.0),
  'm1_eol_space_bad' => eol_lines(RULES['m1_dense_eol_space'] - 0.01),
  'm1_eol_space_at_limit' => eol_lines(RULES['m1_dense_eol_space']),
  'm1_eol_jog_exempt' => [box('M1', 0, 0, 0.1, 2), box('M1', 0.2, 1.92, 2.0, 2.01)],
  'm1_void_width_bad' => huge_void_fixture(RULES['metal_void_width'] - 0.15),
  'm1_void_width_at_limit' => huge_void_fixture(RULES['metal_void_width']),

  'm2_width_bad' => [box('M2', 0, 0, RULES['m2_width'] - 0.01, 0.6)],
  'm2_width_at_limit' => [box('M2', 0, 0, RULES['m2_width'], 0.6)],
  't4m2_width_bad' => [box('T4M2', 0, 0, RULES['tm2_width'] - 0.01, 2)],
  't4m2_width_at_limit' => [box('T4M2', 0, 0, RULES['tm2_width'], 2)],
  't4m2_max_width_bad' => [box('T4M2', 0, 0, RULES['tm2_max_width'] + 0.002, 25)],
  't4m2_max_width_at_limit' => [box('T4M2', 0, 0, RULES['tm2_max_width'], 25)],
  't4m2_spacing_bad' => metal_pair('T4M2', 0.5, 2, RULES['tm2_space'] - 0.01),
  't4m2_spacing_at_limit' => metal_pair('T4M2', 0.5, 2, RULES['tm2_space']),
  't4m2_wide_space_bad' => metal_pair('T4M2', 2.5, 3, RULES['tm2_wide_space'] - 0.05),
  't4m2_wide_space_at_limit' => metal_pair('T4M2', 2.5, 3, RULES['tm2_wide_space']),
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
  't4v2_width_bad' => [
    box('M5', 0.17, 0.17, 2, 1.5), box('T4M2', 0.17, 0.17, 2, 1.5),
    box('TV2', 0.2, 0.2, 0.2 + RULES['tv2_width'] - 0.01, 0.2 + RULES['tv2_width'] - 0.01),
  ],
  't4v2_width_at_limit' => tv2_enclosure(0.03, 0.03),
  't4v2_s2_array_bad' => [
    box('M5', 2.5, 2.5, 7.5, 7.5), box('T4M2', 2.5, 2.5, 7.5, 7.5),
    *via_grid('TV2', 3.0, 3.0, 3, 0.36, RULES['tv2_s2_space'] - 0.01),
  ],
  't4v2_s2_array_at_limit' => [
    box('M5', 2.5, 2.5, 7.5, 7.5), box('T4M2', 2.5, 2.5, 7.5, 7.5),
    *via_grid('TV2', 3.0, 3.0, 3, 0.36, RULES['tv2_s2_space']),
  ],

  'v1_diagonal_sringblk_waived' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), diamond('V1', 0.5, 0.5, 0.05), diamond('SRINGBLK_SRC', 0.5, 0.5, 0.05)],
  'v1_grid_exclusion' => [box('M1', 0, 0, 1, 1), box('M2', 0, 0, 1, 1), box('V1', 0.4, 0.4, 0.5, 0.6), box('GRBLK', 0.4, 0.4, 0.5, 0.6)],

  # Pad and redistribution-layer source predicates. RDL/T4M2 plates enclose
  # each RV by 1.5um and carry two vias so the source RV_R_1 single-via check
  # stays quiet unless a fixture targets it.
  'rv_wrong_rectangle' => [
    box('RV', 0, 0, 2, 2), box('RV', 6, 0, 8, 2),
    box('RDL', -1.5, -1.5, 9.5, 3.5), box('T4M2', -1.5, -1.5, 9.5, 3.5),
  ],
  'rv_grid_exclusion' => [
    box('RV', 0, 0, 2, 2), box('GRBLK', 0, 0, 2, 2),
    box('RV', 6, 0, 8, 2), box('GRBLK', 6, 0, 8, 2),
    box('RDL', -1.5, -1.5, 9.5, 3.5), box('T4M2', -1.5, -1.5, 9.5, 3.5),
  ],
  'rv_exact_rectangle' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -1.5, -1.5, 10.5, 4.5),
  ],
  'rv_outside_rdl' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('T4M2', -1.5, -1.5, 10.5, 4.5),
  ],
  'rv_space_bad' => [
    box('RV', 0, 0, 3, 3), box('RV', 5.99, 0, 8.99, 3),
    box('RDL', -1.5, -1.5, 10.49, 4.5), box('T4M2', -1.5, -1.5, 10.49, 4.5),
  ],
  'rv_space_at_limit' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -1.5, -1.5, 10.5, 4.5),
  ],
  'rv_cb_space_bad' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -1.5, -1.5, 16.5, 7.5),
    box('CB', 12, 0, 15, 6), box('ALPAD', 11, -1, 16, 7),
  ],
  'rv_cb_space_at_limit' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -1.5, -1.5, 21, 7.5),
    box('CB', 15, 0, 18, 6), box('ALPAD', 14, -1, 19, 7),
  ],
  'rv_enc_metal_bad' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -0.5, -0.5, 9.5, 3.5),
  ],
  'rv_enc_metal_at_limit' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -1.5, -1.5, 10.5, 4.5),
  ],
  'rv_enc_rdl_bad' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1, -1, 10, 4), box('T4M2', -1.5, -1.5, 10.5, 4.5),
  ],
  'rv_enc_rdl_at_limit' => [
    box('RV', 0, 0, 3, 3), box('RV', 6, 0, 9, 3),
    box('RDL', -1.5, -1.5, 10.5, 4.5), box('T4M2', -1.5, -1.5, 10.5, 4.5),
  ],
  'rv_single_bad' => [
    box('RV', 0, 0, 3, 3), box('RDL', -1.5, -1.5, 4.5, 4.5),
    box('T4M2', -1.5, -1.5, 4.5, 4.5),
  ],
  'cover_outside_alpa' => [box('COVER', 0, 0, 1, 1)],
  'cb_outside_alpad' => [box('CB', 0, 0, 1, 1)],

  # RDL: 3.0 width window, 35.0 maximum width, 2.0/3.0/5.0 spacing selected by
  # the ALPA width thresholds (10/35). The wider-spacing bad fixture also trips
  # the 35um maximum width, since only a >35um polygon selects RDL_S_3.
  'rdl_width_bad' => [box('RDL', 0, 0, 2, 10)],
  'rdl_width_at_limit' => [box('RDL', 0, 0, 3, 10)],
  'rdl_width_max_bad' => [box('RDL', 0, 0, 35.5, 36)],
  'rdl_width_max_at_limit' => [box('RDL', 0, 0, 35, 36)],
  'rdl_space_bad' => [box('RDL', 0, 0, 3, 5), box('RDL', 4.99, 0, 7.99, 5)],
  'rdl_space_at_limit' => [box('RDL', 0, 0, 3, 5), box('RDL', 5, 0, 8, 5)],
  'rdl_wide_space_bad' => [box('RDL', 0, 0, 11, 11), box('RDL', 13.49, 5, 16.49, 10)],
  'rdl_wide_space_at_limit' => [box('RDL', 0, 0, 11, 11), box('RDL', 14, 5, 17, 10)],
  'rdl_wider_space_bad' => [box('RDL', 0, 0, 36, 36), box('RDL', 40, 5, 43, 10)],
  'rdl_wider_space_at_limit' => [box('RDL', 0, 0, 36, 36), box('RDL', 41, 5, 44, 10)],

  # CB (passivation opening): 3.0 width, 5.0 spacing, 1.5 T4M2 enclosure.
  # Each CB is covered by its T4M2 plate and by ALPAD (CB_EN_1_EN_2 and
  # RDL_EN_2 stay quiet unless the fixture targets them).
  'cb_width_bad' => [
    box('CB', 2, 2, 4.99, 8), box('T4M2', 0.5, 0.5, 6.49, 9.5), box('ALPAD', 1, 1, 6, 9),
  ],
  'cb_width_at_limit' => [
    box('CB', 2, 2, 5, 8), box('T4M2', 0.5, 0.5, 6.5, 9.5), box('ALPAD', 1, 1, 6, 9),
  ],
  'cb_space_bad' => [
    box('CB', 0, 0, 3, 6), box('CB', 7.99, 0, 10.99, 6),
    box('T4M2', -1.5, -1.5, 4.5, 7.5), box('T4M2', 6.49, -1.5, 12.49, 7.5),
    box('ALPAD', -0.5, -0.5, 11.49, 6.5),
  ],
  'cb_space_at_limit' => [
    box('CB', 0, 0, 3, 6), box('CB', 8, 0, 11, 6),
    box('T4M2', -1.5, -1.5, 4.5, 7.5), box('T4M2', 6.5, -1.5, 12.5, 7.5),
    box('ALPAD', -0.5, -0.5, 11.5, 6.5),
  ],
  'cb_enc_bad' => [
    box('CB', 2, 2, 5, 8), box('T4M2', 0.51, 0.51, 6.49, 9.49), box('ALPAD', 1, 1, 6, 9),
  ],
  'cb_enc_at_limit' => [
    box('CB', 2, 2, 5, 8), box('T4M2', 0.5, 0.5, 6.5, 9.5), box('ALPAD', 1, 1, 6, 9),
  ],

  # COVER (RDLPA2): 40x65 minimum opening, 5.0 spacing, 1.5 ALPA enclosure,
  # and 2.5 pad-plate spacing from the 21.499um UNDEROVER plate reconstruction.
  'cover_width_bad' => [box('COVER', 0, 0, 39.99, 65), box('ALPAD', -1.5, -1.5, 41.49, 66.5)],
  'cover_width_at_limit' => [box('COVER', 0, 0, 40, 65), box('ALPAD', -1.5, -1.5, 41.5, 66.5)],
  'cover_length_bad' => [box('COVER', 0, 0, 40, 64.99), box('ALPAD', -1.5, -1.5, 41.5, 66.49)],
  'cover_length_at_limit' => [box('COVER', 0, 0, 40, 65), box('ALPAD', -1.5, -1.5, 41.5, 66.5)],
  'cover_space_bad' => [
    box('COVER', 0, 0, 40, 65), box('COVER', 44.99, 0, 84.99, 65),
    box('ALPAD', -1.5, -1.5, 86.49, 66.5),
  ],
  'cover_space_at_limit' => [
    box('COVER', 0, 0, 40, 65), box('COVER', 45, 0, 85, 65),
    box('ALPAD', -1.5, -1.5, 86.5, 66.5),
  ],
  'cover_enc_alpa_bad' => [
    box('COVER', 0, 0, 40, 65), box('ALPAD', -1, -1, 41, 66),
  ],
  'cover_enc_alpa_at_limit' => [
    box('COVER', 0, 0, 40, 65), box('ALPAD', -1.5, -1.5, 41.5, 66.5),
  ],
  # The CB in the pad keeps the T4M2 maximum-width rule quiet (PA exemption)
  # and gives the reconstructed pad plate a passivation opening.
  'cover_pad_space_bad' => [
    box('T4M2', 0, 0, 50, 65), box('COVER', 5, 0, 45, 65), box('CB', 20, 20, 26, 26),
    box('ALPAD', -1.5, -1.5, 51.5, 66.5), box('T4M2', 52.49, 0, 62.49, 10),
  ],
  'cover_pad_space_at_limit' => [
    box('T4M2', 0, 0, 50, 65), box('COVER', 5, 0, 45, 65), box('CB', 20, 20, 26, 26),
    box('ALPAD', -1.5, -1.5, 51.5, 66.5), box('T4M2', 52.5, 0, 62.5, 10),
  ],

  # Dummy geometry whitelist, marker overlap, and slot-to-pad relation.
  'act_dummy_valid' => [box('ACTDUM', 0, 0, RULES['act_dummy_3'], RULES['act_dummy_3'])],
  'act_dummy_invalid' => [box('ACTDUM', 0, 0, 2, 2)],
  'act_dummy_ct_overlap' => [box('ACTDUM', 0, 0, 3, 3), *act_np(0, 0, 3, 3), box('M1', 0, 0, 3, 3), box('CT', 0.2, 0.2, 0.29, 0.29)],
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
  # padarea = DEUPAD AND (CB OR COVER). A 3x3 T4V2 array at the 0.5um
  # within-array spacing satisfies DEUPAD_R_7 and T4V2_S_2 at once.
  'deupad_r3_bad' => [
    box('DEUPAD', 0, 0, 60, 60), box('CB', 2, 2, 8, 8),
    box('T4M2', 0.5, 0.5, 9.5, 9.5), box('M5', 0.5, 0.5, 9.5, 7.0),
    box('ALPAD', 1, 1, 9, 9), *via_grid('TV2', 3.0, 3.0, 3, 0.36, 0.5),
  ],
  'deupad_r3_at_limit' => [
    box('DEUPAD', 0, 0, 60, 60), box('CB', 2, 2, 8, 8),
    box('T4M2', 0.5, 0.5, 9.5, 9.5), box('M5', 0.5, 0.5, 9.5, 9.5),
    box('ALPAD', 1, 1, 9, 9), *via_grid('TV2', 3.0, 3.0, 3, 0.36, 0.5),
  ],
  'deupad_r7_bad' => [
    box('DEUPAD', 0, 0, 60, 60), box('CB', 2, 2, 8, 8),
    box('T4M2', 0.5, 0.5, 9.5, 9.5), box('M5', 0.5, 0.5, 9.5, 9.5),
    box('ALPAD', 1, 1, 9, 9),
  ],
  'deupad_r7_at_limit' => [
    box('DEUPAD', 0, 0, 60, 60), box('CB', 2, 2, 8, 8),
    box('T4M2', 0.5, 0.5, 9.5, 9.5), box('M5', 0.5, 0.5, 9.5, 9.5),
    box('ALPAD', 1, 1, 9, 9), *via_grid('TV2', 3.0, 3.0, 2, 0.36, 0.5),
  ],
  'esd_area' => [area_box('ESD', RULES['esd_area_min'], 0.5, 0.5)],
  'esd_area_at_limit' => [area_box('ESD', RULES['esd_area_min'], 0.6)],
  'esd_area_nodrc_waived' => [area_box('ESD', RULES['esd_area_min'], 0.5, 0.5), box('NODRC', 0, 0, 0.5, 0.6)],
  'esd_hole' => ring('ESD', 2, 2, 0.5, 0.5),
  'esd_hole_at_limit' => ring('ESD', 2, 2, 0.6, 1.0),
  'esd_width_bad' => [box('ESD', 0, 0, RULES['esd_width'] - 0.01, 2)],
  'esd_width_at_limit' => [box('ESD', 0, 0, RULES['esd_width'], 2)],
  'esd_space_bad' => [
    box('ESD', 0, 0, 0.6, 2), box('ESD', 0.6 + RULES['esd_space'] - 0.01, 0, 1.2 + RULES['esd_space'] - 0.01, 2),
  ],
  'esd_space_at_limit' => [
    box('ESD', 0, 0, 0.6, 2), box('ESD', 0.6 + RULES['esd_space'], 0, 1.2 + RULES['esd_space'], 2),
  ],
  'esd_nmos_clean' => esd_device,
  'esd_nmos_ct_act_enc_bad' => esd_device(ct_s_x: 0.14),
  'esd_nmos_ct_act_enc_at_limit' => esd_device(ct_s_x: 0.24),
  'esd_nmos_ct_gate_space_bad' => esd_device(ct_s_x: 2.34),
  'esd_nmos_ct_gate_space_at_limit' => esd_device(ct_s_x: 2.26),
  'esd_nmos_sab_gate_ovl_bad' => esd_device(ring_x1: 2.97),
  'esd_nmos_sab_hole_gate_space_bad' => esd_device(hole_gate: 1.2),
  'esd_nmos_sab_hole_gate_space_at_limit' => esd_device(hole_gate: 1.29),
  'esd_nmos_sab_hole_ct_enc_bad' => esd_device(ct_size: 0.22),
  'esd_nmos_sab_act_space_bad' => esd_device(ring_x2: 13.1),
  'esd_nmos_sab_hole_drain_enc_bad' => esd_device(hole_gate: 8.5),
  'esd_nmos_sab_hole_drain_enc_at_limit' => esd_device(hole_gate: 8.4),
  'esd_nmos_implant_gate_space_bad' => esd_device(imp_x1: 3.2),
  'esd_nmos_implant_act_enc_bad' => esd_device(imp_x2: 13.2),
  'esd_nmos_implant_gate_overlap_bad' => esd_device(imp_x1: 2.7),
  'esd_nmos_finger_width_bad' => esd_device(w: 29.0),
  'esd_nmos_finger_width_min_at_limit' => esd_device(w: 30.0),
  'esd_nmos_finger_width_max_bad' => esd_device(w: 41.0),
  'esd_nmos_finger_width_max_at_limit' => esd_device(w: 40.0),
  'esd_pmos_finger_width_bad' => esd_device(w: 29.0, implant: 'PP'),
  'esd_hv_nmos_length_bad' => esd_device(length: 0.3, tg: true),
  'esd_hv_nmos_length_at_limit' => esd_device(length: 0.5, tg: true),
  'esd_hv_pmos_length_low_bad' => esd_device(length: 0.3, implant: 'PP', tg: true),
  'esd_hv_pmos_length_high_bad' => esd_device(length: 0.55, implant: 'PP', tg: true),
  'esd_hv_pmos_length_at_limit' => esd_device(length: 0.4, implant: 'PP', tg: true),
  'esd_hv_pmos_length_max_at_limit' => esd_device(length: 0.5, implant: 'PP', tg: true),

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

  # AADUM size-class spacing, cross-layer spacing/overlap, and boundary enclosure.
  'aadum_s1_bad' => [box('ACTDUM', 0, 0, 3, 3), box('ACTDUM', 4.9, 0, 7.9, 3)],
  'aadum_s1_at_limit' => [box('ACTDUM', 0, 0, 3, 3), box('ACTDUM', 5.0, 0, 8.0, 3)],
  'aadum_s2_bad' => [box('ACTDUM', 0, 0, 1, 1), box('ACTDUM', 1.5, 0, 2.5, 1)],
  'aadum_s2_at_limit' => [box('ACTDUM', 0, 0, 1, 1), box('ACTDUM', 1.6, 0, 2.6, 1)],
  'aadum_s3_bad' => [box('ACTDUM', 0, 0, 0.467, 0.467), box('ACTDUM', 0.737, 0, 1.204, 0.467)],
  'aadum_s3_at_limit' => [box('ACTDUM', 0, 0, 0.467, 0.467), box('ACTDUM', 0.747, 0, 1.214, 0.467)],
  'aadum_s4_bad' => [
    *act_np(0, 0, 1, 1), box('ACTDUM', 2.5, 0, 5.5, 3),
    *act_np(20, 0, 21, 1), box('ACTDUM', 20.5, 0.5, 23.5, 3.5),
  ],
  'aadum_s4_at_limit' => [*act_np(0, 0, 1, 1), box('ACTDUM', 2.6, 0, 5.6, 3)],
  'aadum_s5_bad' => [
    box('POLY', 0, 0, 1, 0.3), box('ACTDUM', 2.5, 0, 5.5, 3),
    box('POLY', 20, 0, 21, 0.3), box('ACTDUM', 20.5, -1, 23.5, 2),
  ],
  'aadum_s5_at_limit' => [box('POLY', 0, 0, 1, 0.3), box('ACTDUM', 2.6, 0, 5.6, 3)],
  'aadum_s6_bad' => [
    box('NW', 0, 0, 3, 3), box('ACTDUM', 0.2, 0.2, 1.2, 1.2),
    box('ACTDUM', 3.2, 0.2, 4.2, 1.2),
  ],
  'aadum_s6_at_limit' => [
    box('NW', 0, 0, 3, 3), box('ACTDUM', 0.3, 0.3, 1.3, 1.3),
    box('ACTDUM', 3.3, 0.3, 4.3, 1.3),
  ],
  'aadum_s7_bad' => [box('ACTDUM', 2.1, 0, 3.1, 1), box('FUSEALL', 5, 0, 7, 2)],
  'aadum_s7_at_limit' => [box('ACTDUM', 2.0, 0, 3.0, 1), box('FUSEALL', 5, 0, 7, 2)],
  'aadum_s8_bad' => [box('ACTDUM', 3.5, 0, 4.5, 1), box('NW1RES', 5, 0, 6, 0.3)],
  'aadum_s8_at_limit' => [box('ACTDUM', 3.4, 0, 4.4, 1), box('NW1RES', 5, 0, 6, 0.3)],
  'aadum_s9_bad' => [box('ACTDUM', 3.91, 0, 4.91, 1), box('LOGO', 5, 0, 7, 2)],
  'aadum_s9_at_limit' => [box('ACTDUM', 3.9, 0, 4.9, 1), box('LOGO', 5, 0, 7, 2)],
  'aadum_s10_bad' => [box('ACTDUM', 2.1, 0, 3.1, 1), box('INDALL', 5, 0, 7, 2)],
  'aadum_s10_at_limit' => [box('ACTDUM', 2.0, 0, 3.0, 1), box('INDALL', 5, 0, 7, 2)],
  'aadum_s11_bad' => [
    box('CHIPBLK', 0, 0, 6, 6), box('ACTDUM', 0.5, 2.5, 1.5, 3.5),
    box('ACTDUM', 6.5, 2.5, 7.5, 3.5),
  ],
  'aadum_s11_at_limit' => [
    box('CHIPBLK', 0, 0, 6, 6), box('ACTDUM', 0.6, 2.5, 1.6, 3.5),
    box('ACTDUM', 6.6, 2.5, 7.6, 3.5),
  ],
  'aadum_s12_bad' => [box('ACTDUM', 2.1, 0, 3.1, 1), box('ACTDUMB', 5, 0, 6, 1)],
  'aadum_s12_at_limit' => [box('ACTDUM', 2.0, 0, 3.0, 1), box('ACTDUMB', 5, 0, 6, 1)],
  'aadum_s13_bad' => [box('ACTDUM', 2.1, 0, 3.1, 1), box('DMYBLK', 5, 0, 7, 2)],
  'aadum_s13_at_limit' => [box('ACTDUM', 2.0, 0, 3.0, 1), box('DMYBLK', 5, 0, 7, 2)],

  # PODUM size-class spacing, cross-layer spacing/overlap, and boundary enclosure.
  'podum_s1_bad' => [box('POLYDUM', 0, 0, 2.4, 2.4), box('POLYDUM', 4.9, 0, 7.3, 2.4)],
  'podum_s1_at_limit' => [box('POLYDUM', 0, 0, 2.4, 2.4), box('POLYDUM', 5.0, 0, 7.4, 2.4)],
  'podum_s2_bad' => [box('POLYDUM', 0, 0, 0.92, 0.92), box('POLYDUM', 1.59, 0, 2.51, 0.92)],
  'podum_s2_at_limit' => [box('POLYDUM', 0, 0, 0.92, 0.92), box('POLYDUM', 1.6, 0, 2.52, 0.92)],
  'podum_s3_bad' => [box('POLYDUM', 0, 0, 0.381, 0.381), box('POLYDUM', 0.731, 0, 1.112, 0.381)],
  'podum_s3_at_limit' => [box('POLYDUM', 0, 0, 0.381, 0.381), box('POLYDUM', 0.741, 0, 1.122, 0.381)],
  'podum_s4_bad' => [
    *act_np(0, 0, 1, 1), box('POLYDUM', 1.79, 0, 2.71, 0.92),
    *act_np(20, 0, 21, 1), box('POLYDUM', 20.1, 0.1, 21.02, 1.02),
  ],
  'podum_s4_at_limit' => [*act_np(0, 0, 1, 1), box('POLYDUM', 1.8, 0, 2.72, 0.92)],
  'podum_s5_bad' => [
    box('POLY', 0, 0, 1, 0.3), box('POLYDUM', 1.79, 0, 2.71, 0.92),
    box('POLY', 20, 0, 21, 0.3), box('POLYDUM', 20.2, -0.2, 21.12, 0.72),
  ],
  'podum_s5_at_limit' => [box('POLY', 0, 0, 1, 0.3), box('POLYDUM', 1.8, 0, 2.72, 0.92)],
  'podum_s6_bad' => [
    box('NW', 0, 0, 3, 3), box('POLYDUM', 0.2, 0.2, 1.12, 1.12),
    box('POLYDUM', 3.2, 0.2, 4.12, 1.12),
  ],
  'podum_s6_at_limit' => [
    box('NW', 0, 0, 3, 3), box('POLYDUM', 0.3, 0.3, 1.22, 1.22),
    box('POLYDUM', 3.3, 0.3, 4.22, 1.22),
  ],
  'podum_s7_bad' => [box('POLYDUM', 3.58, 0, 4.5, 0.92), box('NW1RES', 5, 0, 6, 0.3)],
  'podum_s7_at_limit' => [box('POLYDUM', 3.48, 0, 4.4, 0.92), box('NW1RES', 5, 0, 6, 0.3)],
  'podum_s8_bad' => [box('POLYDUM', 3.99, 0, 4.91, 0.92), box('LOGO', 5, 0, 7, 2)],
  'podum_s8_at_limit' => [box('POLYDUM', 3.98, 0, 4.9, 0.92), box('LOGO', 5, 0, 7, 2)],
  'podum_s9_bad' => [box('POLYDUM', 2.18, 0, 3.1, 0.92), box('INDALL', 5, 0, 7, 2)],
  'podum_s9_at_limit' => [box('POLYDUM', 2.08, 0, 3.0, 0.92), box('INDALL', 5, 0, 7, 2)],
  'podum_s10_bad' => [
    box('CHIPBLK', 0, 0, 6, 6), box('POLYDUM', 0.2, 2.5, 1.12, 3.42),
    box('POLYDUM', 6.5, 2.5, 7.42, 3.42),
  ],
  'podum_s10_at_limit' => [
    box('CHIPBLK', 0, 0, 6, 6), box('POLYDUM', 0.3, 2.5, 1.22, 3.42),
    box('POLYDUM', 6.6, 2.5, 7.52, 3.42),
  ],
  'podum_s11_bad' => [box('POLYDUM', 2.18, 0, 3.1, 0.92), box('POLYDUMB', 5, 0, 5.92, 0.92)],
  'podum_s11_at_limit' => [box('POLYDUM', 2.08, 0, 3.0, 0.92), box('POLYDUMB', 5, 0, 5.92, 0.92)],
  'podum_s12_bad' => [box('POLYDUM', 2.18, 0, 3.1, 0.92), box('DMYBLK', 5, 0, 7, 2)],
  'podum_s12_at_limit' => [box('POLYDUM', 2.08, 0, 3.0, 0.92), box('DMYBLK', 5, 0, 7, 2)],

  # T4M2DUM size-class spacing, wide-run macro, angle, and boundary rules.
  't4m2dum_s1_bad' => [box('T4M2DUM', 0, 0, 2, 2), box('T4M2DUM', 2.7, 0, 4.7, 2)],
  't4m2dum_s1_at_limit' => [box('T4M2DUM', 0, 0, 2, 2), box('T4M2DUM', 2.8, 0, 4.8, 2)],
  't4m2dum_s2_bad' => [box('T4M2DUM', -6.9, 0, -4.9, 2), box('T4M2', 5, 0, 6, 1)],
  't4m2dum_s2_at_limit' => [box('T4M2DUM', -7.0, 0, -5.0, 2), box('T4M2', 5, 0, 6, 1)],
  't4m2dum_s3_bad' => [box('T4M2DUM', 0, 0, 1, 1), box('T4M2DUM', 1.3, 0, 2.3, 1)],
  't4m2dum_s3_at_limit' => [box('T4M2DUM', 0, 0, 1, 1), box('T4M2DUM', 1.4, 0, 2.4, 1)],
  't4m2dum_s4_bad' => [box('T4M2DUM', 3.5, 0, 4.5, 1), box('T4M2', 5, 0, 6, 1)],
  't4m2dum_s4_at_limit' => [box('T4M2DUM', 3.4, 0, 4.4, 1), box('T4M2', 5, 0, 6, 1)],
  't4m2dum_s5_bad' => [box('T4M2DUM', 0, 0, 0.6, 1.2), box('T4M2DUM', 0.9, 0, 1.5, 1.2)],
  't4m2dum_s5_at_limit' => [box('T4M2DUM', 0, 0, 0.6, 1.2), box('T4M2DUM', 1.0, 0, 1.6, 1.2)],
  't4m2dum_s6_bad' => [box('T4M2DUM', 3.9, 0, 4.5, 1.2), box('T4M2', 5, 0, 6, 1)],
  't4m2dum_s6_at_limit' => [box('T4M2DUM', 3.8, 0, 4.4, 1.2), box('T4M2', 5, 0, 6, 1)],
  't4m2dum_s7_bad' => [box('T4M2', 0, 0, 2, 2), box('T4M2DUM', 2.5, 0, 4.5, 2)],
  't4m2dum_s7_at_limit' => [box('T4M2', 0, 0, 2, 2), box('T4M2DUM', 2.6, 0, 4.6, 2)],
  't4m2dum_s8_bad' => [diamond('T4M2', 1, 1, 0.5), box('T4M2DUM', 1.5, 1.5, 2.5, 2.5)],
  't4m2dum_s8_at_limit' => [diamond('T4M2', 1, 1, 0.5), box('T4M2DUM', 1.533, 1.533, 2.533, 2.533)],
  't4m2dum_s9_bad' => [box('T4M2DUM', 1.1, 0, 2.1, 1), box('FUSEALL', 5, 0, 8, 3)],
  't4m2dum_s9_at_limit' => [box('T4M2DUM', 1.0, 0, 2.0, 1), box('FUSEALL', 5, 0, 8, 3)],
  't4m2dum_s10_bad' => [box('BMIM', 0, 0, 6, 6), box('T4M2DUM', 1.9, 1.9, 2.9, 2.9)],
  't4m2dum_s10_at_limit' => [box('BMIM', 0, 0, 6, 6), box('T4M2DUM', 2.0, 2.0, 3.0, 3.0)],
  't4m2dum_s11_bad' => [box('T4M2DUM', 3.91, 0, 4.91, 1), box('LOGO', 5, 0, 7, 2)],
  't4m2dum_s11_at_limit' => [box('T4M2DUM', 3.9, 0, 4.9, 1), box('LOGO', 5, 0, 7, 2)],
  't4m2dum_s12_bad' => [box('INDALL', 0, 0, 8, 8), box('T4M2DUM', 2.9, 2.9, 3.9, 3.9)],
  't4m2dum_s12_at_limit' => [box('INDALL', 0, 0, 8, 8), box('T4M2DUM', 3.0, 3.0, 4.0, 4.0)],
  't4m2dum_s13_bad' => [box('CHIPBLK', 0, 0, 7, 7), box('T4M2DUM', 2.4, 2.4, 3.4, 3.4)],
  't4m2dum_s13_at_limit' => [box('CHIPBLK', 0, 0, 7, 7), box('T4M2DUM', 2.5, 2.5, 3.5, 3.5)],

  # CHIPEDGE: design extent 0.37um inside the border, DNW 6.0um inside,
  # seal-ring metal 1.5um inside. CHIPBLK itself is ignored by the extent.
  'chipedge_en1_bad' => [box('CHIPBLK', 0, 0, 6, 6), box('M1', 1, 1, 5.8, 3)],
  'chipedge_en1_at_limit' => [box('CHIPBLK', 0, 0, 6, 6), box('M1', 1, 1, 5.63, 3)],
  'chipedge_en2_bad' => [
    box('CHIPBLK', 0, 0, 20, 20), box('NW', 4.9, 5.4, 10.3, 10.8),
    box('DNW', 5.9, 6.5, 9.1, 9.7), *nw_tap(6.9, 5.7),
  ],
  'chipedge_en2_at_limit' => [
    box('CHIPBLK', 0, 0, 20, 20), box('NW', 5.0, 5.4, 10.4, 10.8),
    box('DNW', 6.0, 6.5, 9.2, 9.7), *nw_tap(7.0, 5.7),
  ],
  'chipedge_en3_bad' => [
    box('CHIPBLK', 0, 0, 10, 10), box('SRINGBLK_SRC', 1.29, 1.39, 8.71, 2.09),
    box('T4M2', 1.49, 1.49, 8.51, 1.99),
  ],
  'chipedge_en3_at_limit' => [
    box('CHIPBLK', 0, 0, 10, 10), box('SRINGBLK_SRC', 1.3, 1.4, 8.7, 2.1),
    box('T4M2', 1.5, 1.5, 8.5, 2.0),
  ],
  't4m2dum_s14_bad' => [box('T4M2DUM', 2.1, 0, 3.1, 1), box('T4M2DUMB', 5, 0, 6, 1)],
  't4m2dum_s14_at_limit' => [box('T4M2DUM', 2.0, 0, 3.0, 1), box('T4M2DUMB', 5, 0, 6, 1)],
  't4m2dum_s15_bad' => [box('T4M2DUM', 2.1, 0, 3.1, 1), box('DMYBLK', 5, 0, 7, 2)],
  't4m2dum_s15_at_limit' => [box('T4M2DUM', 2.0, 0, 3.0, 1), box('DMYBLK', 5, 0, 7, 2)],

  # Metal-slot spacing and the size/orientation predicate.
  'sl_s_1_bad' => [box('M1SLOT', 0, 0, 2, 4.5), box('M1SLOT', 4, 0, 6, 4.5)],
  'sl_s_1_at_limit' => [box('M1SLOT', 0, 0, 2, 4.5), box('M1SLOT', 5, 0, 7, 4.5)],
  'sl_w_1_l_1_bad' => [
    box('M1SLOT', 0, 0, 1.9, 4.5),
    ['M1SLOT', :polygon, [[10, 0], [12, 0], [12, 2], [11, 2], [11, 4.5], [10, 4.5]]],
  ],
  'sl_w_1_l_1_at_limit' => [box('M1SLOT', 0, 0, 2, 4.5)],

  # Seal-ring rules (SRCK): 40x40 um SRINGBLK window; outer rings are 2 um
  # wide with 2 um edge/ring space, inner rings 4 um wide, at the limits.
  # *_bad variants shrink those margins below the thresholds.
  'srck_m1_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
  ],
  'srck_m1_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 1, 1, 38, 38, 35, 35), *ring_at('M1', 4, 4, 32, 32, 28, 28),
  ],
  'srck_t4m2_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('T4M2', 2, 2, 36, 36, 32, 32), *ring_at('T4M2', 6, 6, 28, 28, 20, 20),
  ],
  'srck_t4m2_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('T4M2', 1, 1, 38, 38, 35, 35), *ring_at('T4M2', 4, 4, 32, 32, 28, 28),
  ],
  'srck_rdl_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40), *ring_at('RDL', 4.5, 4.5, 31, 31, 20, 20),
  ],
  'srck_rdl_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('RDL', 4, 4, 32, 32, 20, 20), *ring_at('RDL', 12, 12, 16, 16, 8, 8),
  ],
  'srck_rv_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40), box('RV', 6.5, 6.5, 9.5, 9.5),
    box('RDL', 5, 5, 11, 11),
  ],
  'srck_rv_edge_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40), box('RV', 6, 6, 9, 9),
    box('RDL', 4.5, 4.5, 10.5, 10.5),
  ],
  'srck_rv_width_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40), box('RV', 6.5, 6.5, 9, 9.5),
    box('RDL', 5, 5, 11, 11),
  ],
  'srck_ct_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    box('CT', 3.535, 5, 3.625, 5.27), box('CT', 3.505, 6.01, 3.595, 6.10),
  ],
  'srck_ct_bar_enc_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    box('CT', 3.6, 5, 3.69, 5.27), box('CT', 3.505, 6.2, 3.595, 6.29),
  ],
  'srck_ct_square_enc_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    box('CT', 3.535, 5, 3.625, 5.27), box('CT', 3.7, 6.2, 3.79, 6.29),
  ],
  'srck_ct_space_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    box('CT', 3.535, 5, 3.625, 5.27), box('CT', 3.505, 5.77, 3.595, 5.86),
  ],
  'srck_ct_square_size_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    box('CT', 3.535, 5, 3.625, 5.27), box('CT', 3.3, 6.2, 3.5, 6.4),
  ],
  'srck_ct_bar_width_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    ['CT', :polygon, [[3.3, 10.0], [3.57, 10.0], [3.57, 10.09], [3.38, 10.09],
                      [3.38, 10.27], [3.3, 10.27]]],
  ],
  'srck_v1_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    *ring_at('M2', 2, 2, 36, 36, 32, 32), *ring_at('M2', 6, 6, 28, 28, 20, 20),
    box('V1', 3.535, 5, 3.625, 5.27), box('V1', 3.505, 5.87, 3.595, 5.96),
  ],
  'srck_v1_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    *ring_at('M2', 2, 2, 36, 36, 32, 32), *ring_at('M2', 6, 6, 28, 28, 20, 20),
    box('V1', 3.6, 5, 3.69, 5.27), box('V1', 3.6, 5.5, 3.72, 5.62),
  ],
  'srck_v1_bar_width_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M1', 2, 2, 36, 36, 32, 32), *ring_at('M1', 6, 6, 28, 28, 20, 20),
    *ring_at('M2', 2, 2, 36, 36, 32, 32), *ring_at('M2', 6, 6, 28, 28, 20, 20),
    ['V1', :polygon, [[3.3, 10.0], [3.57, 10.0], [3.57, 10.09], [3.38, 10.09],
                      [3.38, 10.27], [3.3, 10.27]]],
  ],
  'srck_v2_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M2', 2, 2, 36, 36, 32, 32), *ring_at('M2', 6, 6, 28, 28, 20, 20),
    *ring_at('M3', 2, 2, 36, 36, 32, 32), *ring_at('M3', 6, 6, 28, 28, 20, 20),
    box('V2', 3.46, 5, 3.55, 5.27), box('V2', 3.46, 5.97, 3.55, 6.06),
  ],
  'srck_tv2_at_limit' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M5', 2, 2, 36, 36, 32, 32), *ring_at('M5', 6, 6, 28, 28, 20, 20),
    *ring_at('T4M2', 2, 2, 36, 36, 32, 32), *ring_at('T4M2', 6, 6, 28, 28, 20, 20),
    box('TV2', 3.20, 5, 3.56, 6.08), box('TV2', 3.40, 6.68, 3.76, 7.04),
  ],
  'srck_tv2_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M5', 2, 2, 36, 36, 32, 32), *ring_at('M5', 6, 6, 28, 28, 20, 20),
    *ring_at('T4M2', 2, 2, 36, 36, 32, 32), *ring_at('T4M2', 6, 6, 28, 28, 20, 20),
    box('TV2', 3.6, 5, 3.96, 6.08), box('TV2', 3.54, 6.48, 3.84, 6.78),
  ],
  'srck_tv2_bar_width_bad' => [
    box('SRINGBLK_SRC', 0, 0, 40, 40),
    *ring_at('M5', 2, 2, 36, 36, 32, 32), *ring_at('M5', 6, 6, 28, 28, 20, 20),
    *ring_at('T4M2', 2, 2, 36, 36, 32, 32), *ring_at('T4M2', 6, 6, 28, 28, 20, 20),
    ['TV2', :polygon, [[3.2, 5.0], [3.56, 5.0], [3.56, 6.08], [3.5, 6.08],
                       [3.5, 6.38], [3.2, 6.38]]],
  ],
}

# --- Batch 9 FEOL fixtures: TG/DG, SAB, HRP, ULLD, voltage implants, DGR_3 ---

# Two contacted source/drain regions so the derived GATE layer (POLY
# interacting at least two contacted AA4 regions) is non-empty.
def mos_device(poly_y1 = -0.2, poly_y2 = 1.2, length: 2.0, implant: 'NP')
  [
    *(implant == 'PP' ? act_pp(0, 0, length, 1.0) : act_np(0, 0, length, 1.0)),
    box('POLY', 0.5, poly_y1, 0.6, poly_y2),
    box('CT', 0.10, 0.40, 0.19, 0.49),
    box('CT', length - 0.20, 0.40, length - 0.11, 0.49),
    box('M1', 0.03, 0.33, 0.25, 0.55),
    box('M1', length - 0.25, 0.33, length - 0.03, 0.55),
  ]
end

# MOS entirely covered by the gate-oxide marker. EN_1 (MOS AA) and EN_2
# (GATE) share the 0.25 threshold and GATE is inside MOS, so a 0.24 margin
# always reports both; 0.25 is the inclusive boundary.
def tg_dg_aa_device(oxide, margin)
  mos_device + [box(oxide, -margin, -margin, 2.0 + margin, 1.0 + margin)]
end

# Isolation device for EN_3 without contacts: LDMOS is the deck's second
# GATE source (GATE0 AND LDMOS). The gate ends 0.06 um inside the ACT edge,
# so the EN_3 strip needs 0.32 beyond the gate => 0.26 beyond the ACT.
def tg_dg_isolation_device(oxide, margin)
  [
    box('ACT', 0, 0, 0.42, 0.6),
    box('NP', -0.15, -0.15, 0.57, 0.75),
    box('POLY', 0.30, -0.2, 0.36, 0.8),
    box('LDMOS', -0.2, -0.2, 1.0, 0.8),
    box(oxide, -0.25, -0.25, 0.42 + margin, 0.85),
  ]
end

# A ULLD marker must interact both HVTN and HVTP (the source has two
# NOT INTERACT statements), so every ULLD fixture carries both covers.
def ulld_cover(x1, y1, x2, y2, margin = 0.5)
  [box('HVTN', x1 - margin, y1 - margin, x2 + margin, y2 + margin),
   box('HVTP', x1 - margin, y1 - margin, x2 + margin, y2 + margin)]
end

# Resistor stack: POLY and HRP coincide; HPR and SAB coincide and sit 0.30
# inside the POLY so the HRP EN_1/EX_1 and SAB enclosure checks stay quiet.
def hrp_base(poly_w = 2.5, poly_h = 2.5, sab_x1 = 0.3, sab_y1 = 0.3,
             sab_x2 = nil, sab_y2 = nil)
  sab_x2 ||= poly_w - 0.3
  sab_y2 ||= poly_h - 0.3
  [
    box('POLY', 0, 0, poly_w, poly_h),
    box('HRP', 0, 0, poly_w, poly_h),
    box('HPR', sab_x1, sab_y1, sab_x2, sab_y2),
    box('SAB', sab_x1, sab_y1, sab_x2, sab_y2),
  ]
end

[['tg', 'TGOX'], ['dg', 'DGOX']].each do |prefix, oxide|
  FIXTURES["#{prefix}_width_bad"] = [box(oxide, 0, 0, 0.46, 1.2)]
  FIXTURES["#{prefix}_width_at_limit"] = [box(oxide, 0, 0, 0.47, 1.2)]
  FIXTURES["#{prefix}_space_bad"] = [
    box(oxide, 0, 0, 0.5, 1.2), box(oxide, 0.96, 0, 1.46, 1.2),
  ]
  FIXTURES["#{prefix}_space_at_limit"] = [
    box(oxide, 0, 0, 0.5, 1.2), box(oxide, 0.97, 0, 1.47, 1.2),
  ]
  FIXTURES["#{prefix}_mos_space_bad"] = [
    *act_np(0, 0, 1, 1), box(oxide, 1.24, 0, 1.94, 1.2),
  ]
  FIXTURES["#{prefix}_mos_space_at_limit"] = [
    *act_np(0, 0, 1, 1), box(oxide, 1.25, 0, 1.95, 1.2),
  ]
  FIXTURES["#{prefix}_gate_space_bad"] = mos_device + [
    box(oxide, 0.3, 1.31, 1.7, 2.51),
  ]
  FIXTURES["#{prefix}_gate_space_at_limit"] = mos_device + [
    box(oxide, 0.3, 1.32, 1.7, 2.52),
  ]
  FIXTURES["#{prefix}_aa_enc_bad"] = tg_dg_aa_device(oxide, 0.24)
  FIXTURES["#{prefix}_aa_enc_at_limit"] = tg_dg_aa_device(oxide, 0.25)
  FIXTURES["#{prefix}_aa_gate_enc_bad"] = tg_dg_isolation_device(oxide, 0.25)
  FIXTURES["#{prefix}_aa_gate_enc_at_limit"] = tg_dg_isolation_device(oxide, 0.26)
  FIXTURES["#{prefix}_nw_space_bad"] = [
    box('NW', 0, 0, 2, 1), *nw_tap(0.2, 0.2), box(oxide, 2.46, 0, 3.2, 1.2),
  ]
  FIXTURES["#{prefix}_nw_space_at_limit"] = [
    box('NW', 0, 0, 2, 1), *nw_tap(0.2, 0.2), box(oxide, 2.47, 0, 3.21, 1.2),
  ]
  FIXTURES["#{prefix}_psub_space_bad"] = [
    box('PSUB', 0, 0, 1, 1), box(oxide, 1.46, 0, 2.2, 1.2),
  ]
  FIXTURES["#{prefix}_psub_space_at_limit"] = [
    box('PSUB', 0, 0, 1, 1), box(oxide, 1.47, 0, 2.21, 1.2),
  ]
  FIXTURES["#{prefix}_nw_ext_bad"] = [
    box('NW', 0, 0, 1.6, 1), *nw_tap(1.3, 0.3), box(oxide, 0.1, 0.1, 0.9, 0.9),
  ]
  FIXTURES["#{prefix}_nw_ext_at_limit"] = [
    box('NW', 0, 0, 2, 1.88), *nw_tap(1.7, 0.5), box(oxide, 0.47, 0.47, 1.41, 1.41),
  ]
  FIXTURES["#{prefix}_nw_ext2_bad"] = [
    box('NW', 0, 0, 2, 1), *nw_tap(0.2, 0.3), box(oxide, 1.5, -0.5, 2.4, 1.5),
  ]
  FIXTURES["#{prefix}_nw_ext2_at_limit"] = [
    box('NW', 0, 0, 2, 1), *nw_tap(0.2, 0.3), box(oxide, 1.5, -0.5, 2.47, 1.5),
  ]
  FIXTURES["#{prefix}_psub_ext_bad"] = [
    box('PSUB', 0, 0, 1, 1), box(oxide, -0.46, -0.46, 1.46, 1.46),
  ]
  FIXTURES["#{prefix}_psub_ext_at_limit"] = [
    box('PSUB', 0, 0, 1, 1), box(oxide, -0.47, -0.47, 1.47, 1.47),
  ]
  FIXTURES["#{prefix}_nw_overlap_bad"] = [
    box('NW', 0, 0, 2, 1), *nw_tap(0.15, 0.3), box(oxide, 1.8, -0.5, 2.6, 1.5),
  ]
  FIXTURES["#{prefix}_nw_overlap_at_limit"] = [
    box('NW', 0, 0, 2, 1), *nw_tap(0.15, 0.3), box(oxide, 1.53, -0.5, 2.6, 1.5),
  ]
  FIXTURES["#{prefix}_psub_overlap_bad"] = [
    box('PSUB', 0, 0, 2, 1), box(oxide, 1.8, -0.5, 3.0, 1.5),
  ]
  FIXTURES["#{prefix}_psub_overlap_at_limit"] = [
    box('PSUB', 0, 0, 2, 1), box(oxide, 1.53, -0.5, 3.0, 1.5),
  ]
end
FIXTURES['tg_dg_space_bad'] = [box('TGOX', 0, 0, 1, 1), box('DGOX', 1.46, 0, 2.46, 1)]
FIXTURES['tg_dg_space_at_limit'] = [box('TGOX', 0, 0, 1, 1), box('DGOX', 1.47, 0, 2.47, 1)]
FIXTURES['tg_dg_overlap'] = [box('TGOX', 0, 0, 1.2, 1.2), box('DGOX', 0.8, 0.8, 2, 2)]

# SAB family. The 0.44 um spacing with PO in the space region is kept inside
# ESDIOE so the field-PO spacing rule does not fire on the marker PO.
FIXTURES['sab_width_bad'] = [box('SAB', 0, 0, 0.41, 2.0)]
FIXTURES['sab_width_at_limit'] = [box('SAB', 0, 0, 0.42, 2.0)]
FIXTURES['sab_space_bad'] = [box('SAB', 0, 0, 0.5, 2.0), box('SAB', 0.91, 0, 1.41, 2.0)]
FIXTURES['sab_space_at_limit'] = [box('SAB', 0, 0, 0.5, 2.0), box('SAB', 0.92, 0, 1.42, 2.0)]
FIXTURES['sab_po_space_bad'] = [
  box('SAB', 0, 0, 1.4, 1.6), box('POLY', 0.4, 0.4, 1.0, 1.2),
  box('SAB', 1.83, 0.3, 2.9, 1.7), box('POLY', 1.50, 0.5, 1.56, 1.5),
  box('ESDIOE', 0, 0, 3, 2),
]
FIXTURES['sab_po_space_at_limit'] = [
  box('SAB', 0, 0, 1.4, 1.6), box('POLY', 0.4, 0.4, 1.0, 1.2),
  box('SAB', 1.84, 0.3, 2.9, 1.7), box('POLY', 1.50, 0.5, 1.56, 1.5),
  box('ESDIOE', 0, 0, 3, 2),
]
FIXTURES['sab_aa_space_bad'] = [
  *act_np(0, 0, 1, 1), box('SAB', 1.20, 0, 2.0, 2.0),
]
FIXTURES['sab_aa_space_at_limit'] = [
  *act_np(0, 0, 1, 1), box('SAB', 1.21, 0, 2.01, 2.0),
]
FIXTURES['sab_gate_space_bad'] = mos_device(length: 3.0) + [
  box('SAB', 0.95, 0.21, 2.58, 0.79),
]
FIXTURES['sab_gate_space_at_limit'] = mos_device(length: 3.0) + [
  box('SAB', 0.96, 0.21, 2.58, 0.79),
]
# Poly ends exactly on the ACT boundary here so there is no field poly and
# SAB_S_5 cannot couple; the SAB crosses the gate to trip only the SAB_S_4
# overlap clause.
FIXTURES['sab_gate_overlap_bad'] = mos_device(0.0, 1.0, length: 3.0) + [
  box('SAB', 0.41, 0.21, 2.58, 0.79),
]
FIXTURES['sab_aa_ext_bad'] = [
  *act_np(0, 0, 2, 2), box('SAB', 0.20, 0.20, 1.80, 1.80),
]
FIXTURES['sab_aa_ext_at_limit'] = [
  *act_np(0, 0, 2, 2), box('SAB', 0.21, 0.21, 1.79, 1.79),
]
FIXTURES['sab_aa_ext_outside_bad'] = [
  *act_np(0, 0, 1, 1), box('SAB', -0.2, -0.2, 1.2, 1.2),
]
FIXTURES['sab_aa_ext_outside_at_limit'] = [
  *act_np(0, 0, 1, 1), box('SAB', -0.21, -0.21, 1.21, 1.21),
]
FIXTURES['sab_field_poly_space_bad'] = [
  box('POLY', 0, 0, 0.5, 1), box('SAB', 0.79, 0, 1.6, 2),
]
FIXTURES['sab_field_poly_space_at_limit'] = [
  box('POLY', 0, 0, 0.5, 1), box('SAB', 0.80, 0, 1.61, 2),
]
FIXTURES['sab_field_poly_ext_bad'] = [
  box('POLY', 0, 0, 1, 1), box('SAB', -0.2, -0.2, 1.2, 1.2),
]
FIXTURES['sab_field_poly_ext_at_limit'] = [
  box('POLY', 0, 0, 1, 1), box('SAB', -0.21, -0.21, 1.21, 1.21),
]
FIXTURES['sab_ct_space_bad'] = [
  *act_np(0, 0, 2, 2), box('CT', 0.2, 0.2, 0.29, 0.29),
  box('M1', 0, 0, 2, 2), box('SAB', 0.49, 0.21, 1.5, 1.5),
]
FIXTURES['sab_ct_space_at_limit'] = [
  *act_np(0, 0, 2, 2), box('CT', 0.2, 0.2, 0.29, 0.29),
  box('M1', 0, 0, 2, 2), box('SAB', 0.50, 0.21, 1.5, 1.5),
]
FIXTURES['sab_area_bad'] = [box('SAB', 0, 0, 0.6, 0.6)]
FIXTURES['sab_area_at_limit'] = [box('SAB', 0, 0, 0.9, 0.9)]
FIXTURES['sab_hole_bad'] = ring('SAB', 2, 2, 0.8, 0.8)
FIXTURES['sab_hole_at_limit'] = ring('SAB', 2, 2, 0.9, 0.9)
FIXTURES['sab_coincident_poly_bad'] = [
  box('POLY', 0, 0, 1, 1), box('SAB', 1, 0, 2, 1),
]
FIXTURES['sab_coincident_aa_bad'] = [
  *act_np(0, 0, 1, 1), box('SAB', 1, 0, 2, 1),
]

# HRP family around the clean resistor stack.
FIXTURES['hrp_width_bad'] = [box('HRP', 0, 0, 0.20, 1.0)]
FIXTURES['hrp_width_at_limit'] = [box('HRP', 0, 0, 0.21, 1.0)]
FIXTURES['hrp_space_bad'] = [box('HRP', 0, 0, 0.5, 1), box('HRP', 0.70, 0, 1.2, 1)]
FIXTURES['hrp_space_at_limit'] = [box('HRP', 0, 0, 0.5, 1), box('HRP', 0.71, 0, 1.21, 1)]
FIXTURES['hrp_poly_width_bad'] = hrp_base(1.9, 2.5)
FIXTURES['hrp_poly_width_at_limit'] = hrp_base(2.0, 2.5)
FIXTURES['hrp_po_space_bad'] = mos_device + [
  box('HRP', 0.75, -0.5, 1.5, 1.5),
]
FIXTURES['hrp_po_space_at_limit'] = mos_device + [
  box('HRP', 0.76, -0.5, 1.5, 1.5),
]
# HRP_S_3 is the fixed 0.21 um SAB-to-CT spacing: the CT expanded by 0.21
# must still touch the SAB inside the resistor. The CT sits on the POLY end
# cap outside the SAB, fully inside POLY so the CT enclosure rules stay quiet.
FIXTURES['hrp_sab_ct_space_bad'] = [
  box('POLY', 0, 0, 3.2, 2.5), box('HRP', 0, 0, 3.2, 2.5),
  box('HPR', 0.3, 0.3, 2.5, 2.2), box('SAB', 0.3, 0.3, 2.5, 2.2),
  box('CT', 2.75, 1.0, 2.84, 1.09), box('M1', 2.67, 0.93, 2.89, 1.15),
]
FIXTURES['hrp_sab_ct_space_at_limit'] = [
  box('POLY', 0, 0, 3.2, 2.5), box('HRP', 0, 0, 3.2, 2.5),
  box('HPR', 0.3, 0.3, 2.5, 2.2), box('SAB', 0.3, 0.3, 2.5, 2.2),
  box('CT', 2.71, 1.0, 2.80, 1.09), box('M1', 2.63, 0.93, 2.85, 1.15),
]
FIXTURES['hrp_pp_sab_ovl_bad'] = hrp_base + [box('PP', 0.8, 0.29, 1.3, 0.55)]
FIXTURES['hrp_pp_sab_ovl_at_limit'] = hrp_base + [box('PP', 0.8, 0.29, 1.3, 0.6)]
FIXTURES['hrp_po_enc_bad'] = hrp_base(2.5, 2.5, 0.19, 0.19, 2.31, 2.31)
FIXTURES['hrp_po_enc_at_limit'] = hrp_base(2.5, 2.5, 0.2, 0.2, 2.3, 2.3)
FIXTURES['hrp_sab_ext_bad'] = [
  box('POLY', 0, 0, 2.5, 2.5), box('HRP', -0.5, -0.5, 4.0, 4.0),
  box('HPR', 0.20, 0.20, 2.70, 2.70), box('SAB', 0.20, 0.20, 2.70, 2.70),
]
FIXTURES['hrp_sab_ext_at_limit'] = [
  box('POLY', 0, 0, 2.5, 2.5), box('HRP', -0.5, -0.5, 4.0, 4.0),
  box('HPR', 0.22, 0.22, 2.72, 2.72), box('SAB', 0.22, 0.22, 2.72, 2.72),
]
FIXTURES['hrp_np_mid_bad'] = hrp_base(2.5, 2.5, 0.3, 0.5, 2.2, 2.0) +
  [box('NP', 0.8, 1.0, 1.3, 1.5)]
FIXTURES['hrp_sab_align_bad'] = hrp_base(2.5, 2.5) + [
  box('SAB', 0.3, 2.2, 2.2, 2.3),
]

# ULLD family. P-type ACT keeps both HVTN and HVTP covers legal (PTAP = PACT
# without NW), and the N+ spacing fixture ties the ACT into a tapped NW so
# neither cover overlaps opposite-type source/drain AA.
FIXTURES['ulld_width_bad'] = [box('ULLD', 0, 0, 0.17, 2.0)] + ulld_cover(0, 0, 0.17, 2.0)
FIXTURES['ulld_width_at_limit'] = [box('ULLD', 0, 0, 0.18, 2.0)] + ulld_cover(0, 0, 0.18, 2.0)
FIXTURES['ulld_space_bad'] = [
  box('ULLD', 0, 0, 0.5, 2.0), box('ULLD', 0.67, 0, 1.17, 2.0),
  *ulld_cover(0, 0, 1.17, 2.0),
]
FIXTURES['ulld_space_at_limit'] = [
  box('ULLD', 0, 0, 0.5, 2.0), box('ULLD', 0.68, 0, 1.18, 2.0),
  *ulld_cover(0, 0, 1.18, 2.0),
]
FIXTURES['ulld_aa_space_bad'] = [
  *act_pp(0, 0, 1, 1), box('ULLD', 1.01, 0, 2.0, 1.0),
  *ulld_cover(1.01, 0, 2.0, 1.0),
]
FIXTURES['ulld_aa_space_at_limit'] = [
  *act_pp(0, 0, 1, 1), box('ULLD', 1.15, 0, 2.14, 1.0),
  *ulld_cover(1.15, 0, 2.14, 1.0),
]
FIXTURES['ulld_nact_space_bad'] = [
  box('ACT', 0, 0, 1, 1), box('NP', -0.15, -0.15, 1.15, 1.15),
  box('NW', -0.2, -0.2, 1.2, 1.2),
  box('CT', 0.2, 0.2, 0.29, 0.29), box('M1', 0.1, 0.1, 0.4, 0.4),
  box('ULLD', 1.04, 0, 2.0, 1.0), *ulld_cover(1.04, 0, 2.0, 1.0),
]
FIXTURES['ulld_nact_space_at_limit'] = [
  box('ACT', 0, 0, 1, 1), box('NP', -0.15, -0.15, 1.15, 1.15),
  box('NW', -0.2, -0.2, 1.2, 1.2),
  box('CT', 0.2, 0.2, 0.29, 0.29), box('M1', 0.1, 0.1, 0.4, 0.4),
  box('ULLD', 1.15, 0, 2.11, 1.0), *ulld_cover(1.15, 0, 2.11, 1.0),
]
FIXTURES['ulld_gate_space_bad'] = channel_width(0.4, 0.6, implant: 'PP') + [
  box('ULLD', 0.53, -0.1, 0.95, 0.4), *ulld_cover(0.53, -0.1, 0.95, 0.4),
]
FIXTURES['ulld_gate_space_at_limit'] = channel_width(0.4, 0.6, implant: 'PP') + [
  box('ULLD', 0.54, -0.1, 0.96, 0.4), *ulld_cover(0.54, -0.1, 0.96, 0.4),
]
FIXTURES['ulld_ex1_bad'] = act_pp(0, 0, 1, 1) + [
  box('ULLD', 0.3, 0.3, 1.4, 1.01), *ulld_cover(0.3, 0.3, 1.4, 1.01),
]
FIXTURES['ulld_ex1_at_limit'] = act_pp(0, 0, 1, 1) + [
  box('ULLD', 0.3, 0.3, 1.4, 1.02), *ulld_cover(0.3, 0.3, 1.4, 1.02),
]
FIXTURES['ulld_ex2_bad'] = channel_width(0.4, 0.6, implant: 'PP') + [
  box('ULLD', 0.13, -0.2, 0.60, 0.62), *ulld_cover(0.13, -0.2, 0.60, 0.62),
]
FIXTURES['ulld_ex2_at_limit'] = channel_width(0.4, 0.6, implant: 'PP') + [
  box('ULLD', 0.12, -0.2, 0.60, 0.62), *ulld_cover(0.12, -0.2, 0.60, 0.62),
]
FIXTURES['ulld_ex3a_bad'] = channel_width(0.4, 0.6, implant: 'PP') + [
  box('ULLD', -0.2, -0.1, 0.9, 0.58), *ulld_cover(-0.2, -0.1, 0.9, 0.58),
]
FIXTURES['ulld_ex3a_at_limit'] = channel_width(0.4, 0.6, implant: 'PP') + [
  box('ULLD', -0.2, -0.2, 0.9, 0.58), *ulld_cover(-0.2, -0.2, 0.9, 0.58),
]
FIXTURES['ulld_area_bad'] = [box('ULLD', 0, 0, 0.4, 0.4)] + ulld_cover(0, 0, 0.4, 0.4)
FIXTURES['ulld_area_at_limit'] = [box('ULLD', 0, 0, 0.45, 0.4)] + ulld_cover(0, 0, 0.45, 0.4)
FIXTURES['ulld_hole_bad'] = ring('ULLD', 1, 1, 0.4, 0.4) + ulld_cover(0, 0, 1, 1)
FIXTURES['ulld_hole_at_limit'] = ring('ULLD', 1, 1, 0.45, 0.4) + ulld_cover(0, 0, 1, 1)
FIXTURES['ulld_r2_bad'] = [box('ULLD', 1, 1, 2, 2)]
FIXTURES['ulld_psub_overlap_bad'] = [
  box('PSUB', 0, 0, 1.2, 1.2), box('ULLD', 0.8, 0.2, 1.6, 1.4),
  box('HVTN', 1.3, 0.2, 1.6, 1.4), box('HVTP', 1.3, 0.2, 1.6, 1.4),
]

# Voltage-class implants. NVT1 carries the full boundary pair set; the other
# families exercise each rule's bad case.
[['nvt1', 'LVTN', 'NP', true], ['nvt3', 'HVTN', 'NP', true],
 ['pvt1', 'LVTP', 'NP', false], ['pvt3', 'HVTP', 'PP', true]].each do |fam, vt, implant, sab_rule|
  FIXTURES["#{fam}_width_bad"] = [box(vt, 0, 0, 0.17, 2.0)]
  FIXTURES["#{fam}_space_bad"] = [box(vt, 0, 0, 0.5, 2.0), box(vt, 0.67, 0, 1.17, 2.0)]
  FIXTURES["#{fam}_aa_space_bad"] = [
    *(implant == 'PP' ? act_pp(0, 0, 0.5, 1.0) : act_np(0, 0, 0.5, 1.0)),
    box(vt, 0.64, 0, 1.2, 0.5),
  ]
  FIXTURES["#{fam}_gate_space_bad"] = channel_width(0.4, 0.6, implant: implant) +
    [box(vt, 0.53, -0.1, 0.95, 0.4)]
  FIXTURES["#{fam}_gate_ext_bad"] = channel_width(0.4, 0.6, implant: implant) +
    [box(vt, 0.13, -0.2, 0.54, 0.58)]
  FIXTURES["#{fam}_aa_gate_ext_bad"] = mos_device(implant: implant) + [
    box(vt, -0.2, -0.2, 0.6, 0.8),
  ]
  FIXTURES["#{fam}_area_bad"] = [box(vt, 0, 0, 0.4, 0.4)]
  FIXTURES["#{fam}_hole_bad"] = ring(vt, 1, 1, 0.4, 0.4)
  FIXTURES["#{fam}_psub_overlap_bad"] = [box('PSUB', 0, 0, 2, 2), box(vt, 0.5, 0.5, 1.5, 1.5)]
  if sab_rule
    FIXTURES["#{fam}_sab_aa_space_bad"] = [
      *(implant == 'PP' ? act_pp(0, 0, 2, 2) : act_np(0, 0, 2, 2)),
      box('SAB', 0.21, 0.21, 0.80, 1.79),
      box(vt, 1.00, 0.21, 1.80, 1.79),
    ]
    FIXTURES["#{fam}_sab_aa_space_at_limit"] = [
      *(implant == 'PP' ? act_pp(0, 0, 2, 2) : act_np(0, 0, 2, 2)),
      box('SAB', 0.21, 0.21, 0.80, 1.79),
      box(vt, 1.01, 0.21, 1.81, 1.79),
    ]
  end
end
FIXTURES['nvt1_aa_space_at_limit'] = [*act_np(0, 0, 0.5, 1.0), box('LVTN', 0.65, 0, 1.21, 0.5)]
FIXTURES['nvt1_gate_space_at_limit'] = channel_width(0.4, 0.6) + [box('LVTN', 0.54, -0.1, 0.96, 0.4)]
FIXTURES['nvt1_gate_ext_at_limit'] = channel_width(0.4, 0.6) + [box('LVTN', 0.12, -0.2, 0.54, 0.58)]
FIXTURES['nvt1_aa_gate_ext_at_limit'] = mos_device + [
  box('LVTN', -0.2, -0.2, 0.78, 0.8),
]
FIXTURES['nvt1_area_at_limit'] = [box('LVTN', 0, 0, 0.45, 0.4)]
FIXTURES['nvt1_hole_at_limit'] = ring('LVTN', 1, 1, 0.45, 0.4)
FIXTURES['nvt1_width_at_limit'] = [box('LVTN', 0, 0, 0.18, 2.0)]
FIXTURES['nvt1_space_at_limit'] = [box('LVTN', 0, 0, 0.5, 2.0), box('LVTN', 0.68, 0, 1.18, 2.0)]

# DGR_3: non-orthogonal, non-45-degree base-layer edges. The 33.7-degree
# chamfer keeps every interior angle obtuse so ACT width stays quiet.
FIXTURES['dgr_3_bad'] = [
  ['ACT', :polygon, [[0, 0], [3, 0], [3, 1], [1.5, 2], [0, 2]]],
  box('NP', -0.15, -0.15, 3.15, 2.15),
]
FIXTURES['dgr_3_inddmy_waived'] = [
  ['ACT', :polygon, [[0, 0], [3, 0], [3, 1], [1.5, 2], [0, 2]]],
  box('NP', -0.15, -0.15, 3.15, 2.15), box('INDDMY', -0.5, -0.5, 3.5, 2.5),
]
FIXTURES['dgr_3_45_ok'] = [
  diamond('ACT', 1.5, 1.5, 1.0), box('NP', 0.2, 0.2, 2.8, 2.8),
]

# --- Batch 9: Calibre-only geometry approximations (ACT/PO length, implant
# --- boundary, PP_R_3, DNW_S_3/S_4, MOM_S_1) ---

# A 0.09 CT with the M1 landing pad used by the FEOL contact fixtures.
def ct_pad(x, y)
  [box('CT', x, y, x + 0.09, y + 0.09),
   box('M1', x - 0.065, y - 0.065, x + 0.155, y + 0.155)]
end

# ACT_S_4 U-shape: a 0.12 um wide notch opening upward (>= 0.11 so ACT_S_1
# does not co-fire), gap-wide.
def act_u_shape(gap)
  outer = 0.2 + gap
  [['ACT', :polygon, [[0, 0], [outer, 0], [outer, 0.2], [0.1 + gap, 0.2],
                      [0.1 + gap, 0.1], [0.1, 0.1], [0.1, 0.2], [0, 0.2]]],
   box('NP', -0.2, -0.2, outer + 0.2, 0.4)]
end
FIXTURES['act_u_shape_bad'] = act_u_shape(0.12)
FIXTURES['act_u_shape_at_limit'] = act_u_shape(0.18)

# ACT_S_4 O-shape: enclosed hole 0.9 um tall. The 0.13/0.18 hole widths stay
# >= act_wide_space (0.125) and >= act_space (0.11). KLayout's notch check also
# sees the facing hole edges, so a violation is reported under both the U- and
# O-shape categories of the same source rule.
def act_o_shape(hole_w)
  ring('ACT', 2, 2, hole_w, 0.9) + [box('NP', -0.2, -0.2, 2.2, 2.2)]
end
FIXTURES['act_o_shape_bad'] = act_o_shape(0.13)
FIXTURES['act_o_shape_at_limit'] = act_o_shape(0.18)

# ACT_L_1: 0.14 um thin AA (no gate, so no GATE derivation) with landing CTs.
def thin_aa_ct(gap)
  len = 0.69 + gap
  [box('ACT', 0, 0, len, 0.14),
   box('NP', -0.2, -0.2, len + 0.2, 0.34),
   *ct_pad(0.3, 0.025), *ct_pad(0.39 + gap, 0.025)]
end
FIXTURES['act_l1_ct_bad'] = thin_aa_ct(25.1)
FIXTURES['act_l1_ct_at_limit'] = thin_aa_ct(25.0)

# ACT_L_1 end clause: one CT with a long AA tail.
def thin_aa_end(end_len)
  len = 0.39 + end_len
  [box('ACT', 0, 0, len, 0.14),
   box('NP', -0.2, -0.2, len + 0.2, 0.34),
   *ct_pad(0.3, 0.025)]
end
FIXTURES['act_l1_end_bad'] = thin_aa_end(25.1)
FIXTURES['act_l1_end_at_limit'] = thin_aa_end(25.0)

# ACT_L_2: thin N+ source/drain butted to a P+ pickup (no NW), without a CT.
def thin_sd_tap(sd_len)
  gate_left = 1.0 - sd_len - 0.3
  [box('ACT', 0, 0, 2.0, 0.14),
   box('NP', -0.2, -0.2, 1.0, 0.34),
   box('PP', 1.0, -0.2, 2.2, 0.34),
   box('POLY', gate_left, -0.2, gate_left + 0.3, 0.34),
   *ct_pad(1.5, 0.025)]
end
FIXTURES['act_l2_bad'] = thin_sd_tap(0.55)
FIXTURES['act_l2_at_limit'] = thin_sd_tap(0.5)

# PO_L_1: 0.12 um thin PO with wide landing pads at the CTs.
def thin_po_ct(gap)
  len = 0.69 + gap
  [box('POLY', 0, 0, len, 0.12),
   box('POLY', 0, 0, 0.45, 0.42),
   box('POLY', len - 0.45, 0, len, 0.42),
   *ct_pad(0.3, 0.15), *ct_pad(0.39 + gap, 0.15)]
end
FIXTURES['po_l1_ct_bad'] = thin_po_ct(25.1)
FIXTURES['po_l1_ct_at_limit'] = thin_po_ct(25.0)

def thin_po_end(end_len)
  len = 0.39 + end_len
  [box('POLY', 0, 0, len, 0.12),
   box('POLY', 0, 0, 0.45, 0.42),
   box('POLY', len - 0.45, 0, len, 0.42),
   *ct_pad(0.3, 0.15)]
end
FIXTURES['po_l1_end_bad'] = thin_po_end(25.1)
FIXTURES['po_l1_end_at_limit'] = thin_po_end(25.0)

# PO_L_1 gate clause: thin-channel gate (0.12 um wide) whose nearest CT is
# 25 um from the far channel edge. The two AA contacts (one per source/drain)
# are required for the deck GATE derivation; their 25 um halos top out at
# 1.09 + 25 = 26.09 um, so the gate edge itself is the limit.
def thin_gate(act_h)
  [box('ACT', 0, 0, 2.0, act_h),
   box('NP', -0.2, -0.2, 2.2, act_h + 0.2),
   box('POLY', 0.8, -2.0, 0.92, act_h),
   box('POLY', 0.65, -2.0, 1.07, -1.7),
   *ct_pad(0.815, -1.9),
   *ct_pad(0.2, 1.0), *ct_pad(1.5, 1.0)]
end
FIXTURES['po_l1_gate_bad'] = thin_gate(26.1)
FIXTURES['po_l1_gate_at_limit'] = thin_gate(26.09)

# NP_S_6/PP_S_6: opposite-type butted pickup with a gate in the adjoining
# source/drain; 0.25 um gate-to-pickup gap fires, 0.30 um is exact.
def butted_pickup_n(gate_right)
  [box('ACT', 0, 0, 2.1, 0.5),
   box('NP', -0.2, -0.2, 1.05, 0.7),
   box('PP', 1.05, -0.2, 2.3, 0.7),
   box('POLY', gate_right - 0.15, -0.2, gate_right, 0.7),
   *ct_pad(1.5, 0.2)]
end
FIXTURES['np_s6_bad'] = butted_pickup_n(0.8)
FIXTURES['np_s6_at_limit'] = butted_pickup_n(0.75)

def butted_pickup_p(gate_right)
  [box('ACT', 0, 0, 2.1, 0.5),
   box('PP', -0.2, -0.2, 1.05, 0.7),
   box('NP', 1.05, -0.2, 2.3, 0.7),
   box('NW', -0.3, -0.3, 2.3, 0.8),
   box('POLY', gate_right - 0.15, -0.2, gate_right, 0.7),
   *ct_pad(0.2, 0.2), *ct_pad(1.6, 0.2)]
end
FIXTURES['pp_s6_bad'] = butted_pickup_p(0.8)
FIXTURES['pp_s6_at_limit'] = butted_pickup_p(0.75)

# NP_EX_1/PP_EX_1: implant margin around the AA at the gate.
def np_gate_margin(margin)
  [box('ACT', 0, 0, 2.0, 1.0),
   box('NP', -margin, -margin, 2.0 + margin, 1.0 + margin),
   box('POLY', 0.8, -0.2, 0.95, 1.2)]
end
FIXTURES['np_ex1_bad'] = np_gate_margin(0.13)
FIXTURES['np_ex1_at_limit'] = np_gate_margin(0.16)

def pp_gate_margin(margin)
  [box('ACT', 0, 0, 2.0, 1.0),
   box('PP', -margin, -margin, 2.0 + margin, 1.0 + margin),
   box('POLY', 0.8, -0.2, 0.95, 1.2)]
end
FIXTURES['pp_ex1_bad'] = pp_gate_margin(0.13)
FIXTURES['pp_ex1_at_limit'] = pp_gate_margin(0.16)

# NP_EX_1a/PP_EX_1a: implant extension beyond the gate along the source/drain
# direction. The AA ends 0.16 um inside the implant so NP_EX_1 stays quiet.
def np_gate_ext(act_right, np_right)
  [box('ACT', 0, 0, act_right, 1.0),
   box('NP', -0.2, -0.2, np_right, 1.2),
   box('POLY', 1.3, -0.2, 1.45, 1.2)]
end
FIXTURES['np_ex1a_bad'] = np_gate_ext(1.54, 1.70)
FIXTURES['np_ex1a_at_limit'] = np_gate_ext(1.59, 1.75)

def pp_gate_ext(act_right, pp_right)
  [box('ACT', 0, 0, act_right, 1.0),
   box('PP', -0.2, -0.2, pp_right, 1.2),
   box('POLY', 1.3, -0.2, 1.45, 1.2)]
end
FIXTURES['pp_ex1a_bad'] = pp_gate_ext(1.54, 1.70)
FIXTURES['pp_ex1a_at_limit'] = pp_gate_ext(1.59, 1.75)

# PP_R_3: NP/PP coincident edge covered by SAB (unsilicided AA).
FIXTURES['pp_r3_bad'] = [
  box('ACT', 0, 0, 2.0, 1.2), box('NP', -0.2, -0.2, 1.0, 1.4),
  box('PP', 1.0, -0.2, 2.2, 1.4), box('SAB', 0.25, 0.21, 1.75, 0.79),
  *ct_pad(1.6, 1.03),
]
FIXTURES['pp_r3_at_limit'] = [
  box('ACT', 0, 0, 2.0, 1.2), box('NP', -0.2, -0.2, 1.0, 1.4),
  box('PP', 1.0, -0.2, 2.2, 1.4), *ct_pad(1.6, 1.03),
]

# DNW_S_3/S_4: PW islands split by full-height NW bars; TPW = PW inside DNW.
# The bar width is the TPW-to-PW gap (0.5 violates, 0.8 is exact). Taps keep
# NW1_R_1 quiet; the TPW islands still have no P+ tap CT (DNW_R_3 fires).
def dnw_pw_split(bar)
  [box('NW', 0, 0, 2, 6),
   box('NW', 4.5, 0, 4.5 + bar, 6),
   box('NW', 8, 0, 10, 6),
   box('DNW', 3.5, 1, 6.5, 5),
   *nw_tap(0.93, 2.0), *nw_tap(4.5 + (bar - 0.14) / 2.0, 2.0),
   *nw_tap(8.93, 2.0)]
end
FIXTURES['dnw_s3_bad'] = dnw_pw_split(0.5)
FIXTURES['dnw_s3_at_limit'] = dnw_pw_split(0.8)

# DNW_S_4: TGOX over the left PW/TPW island. Its right edge is 0.47 um from
# the middle NW bar (TG_S_4 exact); the far TPW island is bar + 0.47 away.
def dnw_tpw_dgtg(bar)
  dnw_pw_split(bar) + [box('TGOX', 2.8, 1.5, 4.03, 4.5)]
end
FIXTURES['dnw_s4_bad'] = dnw_tpw_dgtg(0.5)
FIXTURES['dnw_s4_at_limit'] = dnw_tpw_dgtg(0.8)

# MOM_S_1: a via outside MOMLVS1 keeps 0.11 um to MOM-marker metal inside it.
FIXTURES['mom_s1_bad'] = [
  box('M1', 0, 0, 1, 1), box('M1MOM', 0, 0, 1, 1), box('MOMLVS1', 0, 0, 1, 1),
  box('V1', 1.05, 0.4, 1.14, 0.49),
]
FIXTURES['mom_s1_at_limit'] = [
  box('M1', 0, 0, 1, 1), box('M1MOM', 0, 0, 1, 1), box('MOMLVS1', 0, 0, 1, 1),
  box('V1', 1.11, 0.4, 1.20, 0.49),
]

# Antenna fixtures (ics55_antenna.drc). GATE is 0.1 x 0.1 = 0.01 um^2 with
# two SD_1 sides, so the source INTERACT SD_1 == 2 gate derivation qualifies.
def ant_gate
  [box('ACT', 0, 0, 0.5, 0.1),
   box('NP', -0.1, -0.1, 0.6, 0.2),
   box('POLY', 0.2, -0.1, 0.3, 0.2),
   box('POLY', -0.75, 0.19, 1.25, 0.45)]
end

def ant_ct(shapes = ant_gate)
  shapes + [box('CT', 0.2, 0.25, 0.3, 0.35)]
end

# Metal pad of the requested area: 2 um wide from x=-0.75, bottom at y=0.19.
def ant_pad(layer, area, width = 2.0)
  box(layer, -0.75, 0.19, -0.75 + width, 0.19 + area / width)
end

def ant_stack(pads, vias, extra = [])
  shapes = ant_ct + extra
  pads.each { |layer, area| shapes << ant_pad(layer, area) }
  vias.each { |layer, x1, y1, x2, y2| shapes << box(layer, x1, y1, x2, y2) }
  shapes
end

FIXTURES['ant_clean'] = ant_gate

# AR_1: PO area / GATE area > 250, with AR_2 kept quiet by a blocky extension.
def ant_po_area(block_h)
  [box('ACT', 0, 0, 0.5, 0.1),
   box('NP', -0.1, -0.1, 0.6, 0.2),
   box('POLY', 0.2, -0.1, 0.3, 0.2),
   box('POLY', -0.75, 0.2, 1.25, 0.2 + block_h)]
end
FIXTURES['ant_ar1_bad'] = ant_po_area(1.24)       # PO = 2.51, ratio 251
FIXTURES['ant_ar1_at_limit'] = ant_po_area(1.235) # PO = 2.50, ratio 250

# AR_2: PERIMETER(PO) * 0.10 / GATE > 500 on a 0.06 um runner.
def ant_po_runner(len)
  [box('ACT', 0, 0, 0.5, 0.1),
   box('NP', -0.1, -0.1, 0.6, 0.2),
   box('POLY', 0.2, -0.1, 0.26, 0.2 + len)]
end
FIXTURES['ant_ar2_bad'] = ant_po_runner(15.0)       # 30.72*0.1/0.006 = 512
FIXTURES['ant_ar2_at_limit'] = ant_po_runner(14.6)  # 29.92*0.1/0.006 = 498.7

# AR_3: CT1 area / GATE area > 10 on poly-only contacts.
def ant_ct_count(count)
  coords = [[-0.7, 0.2], [-0.4, 0.2], [-0.1, 0.2], [0.2, 0.2], [0.5, 0.2], [0.8, 0.2],
            [-0.55, 0.33], [-0.25, 0.33], [0.05, 0.33], [0.35, 0.33], [0.65, 0.33]]
  ant_gate + coords.first(count).map { |x, y| box('CT', x, y, x + 0.1, y + 0.1) }
end
FIXTURES['ant_ar3_bad'] = ant_ct_count(11)
FIXTURES['ant_ar3_at_limit'] = ant_ct_count(10)

# Small vertical via used inside the stack fixtures.
def ant_small_via(layer, x1 = 0.3, y1 = 0.3, size = 0.09)
  box(layer, x1, y1, x1 + size, y1 + size)
end

# AR_5_10_M1 / AR18_5_10_M1: M1-only gate net.
FIXTURES['ant_m1_bad'] = ant_ct + [ant_pad('M1', 51)]
FIXTURES['ant_m1_at_limit'] = ant_ct + [ant_pad('M1', 50)]
FIXTURES['ant_m1_18_bad'] = ant_ct([box('DGOX', 0.15, -0.05, 0.35, 0.15)] + ant_gate) +
  [ant_pad('M1', 21)]
FIXTURES['ant_m1_18_at_limit'] = ant_ct([box('DGOX', 0.15, -0.05, 0.35, 0.15)] + ant_gate) +
  [ant_pad('M1', 10)]

# Cumulative metal checks: the current layer pushes the net over the limit.
FIXTURES['ant_m2_bad'] = ant_stack([['M1', 30], ['M2', 21]],
                                   [['V1', 0.3, 0.4, 0.39, 0.49]])
FIXTURES['ant_m2_at_limit'] = ant_stack([['M1', 30], ['M2', 20]],
                                        [['V1', 0.3, 0.4, 0.39, 0.49]])
FIXTURES['ant_m2_18_bad'] = ant_stack(
  [['M1', 5], ['M2', 5.1]], [['V1', 0.3, 0.4, 0.39, 0.49]],
  [box('DGOX', 0.15, -0.05, 0.35, 0.15)])
FIXTURES['ant_m2_18_at_limit'] = ant_stack(
  [['M1', 5], ['M2', 5]], [['V1', 0.3, 0.4, 0.39, 0.49]],
  [box('DGOX', 0.15, -0.05, 0.35, 0.15)])
FIXTURES['ant_m3_bad'] = ant_stack(
  [['M1', 10], ['M2', 10], ['M3', 31]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49]])
FIXTURES['ant_m3_18_bad'] = ant_stack(
  [['M1', 4], ['M2', 4], ['M3', 2.1]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49]],
  [box('DGOX', 0.15, -0.05, 0.35, 0.15)])
FIXTURES['ant_m4_bad'] = ant_stack(
  [['M1', 10], ['M2', 10], ['M3', 10], ['M4', 21]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49]])
FIXTURES['ant_m4_18_bad'] = ant_stack(
  [['M1', 3], ['M2', 3], ['M3', 3], ['M4', 1.1]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49]],
  [box('DGOX', 0.15, -0.05, 0.35, 0.15)])
FIXTURES['ant_m5_bad'] = ant_stack(
  [['M1', 10], ['M2', 10], ['M3', 10], ['M4', 10], ['M5', 11]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49]])
FIXTURES['ant_m5_18_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2], ['M5', 2.1]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49]],
  [box('DGOX', 0.15, -0.05, 0.35, 0.15)])
FIXTURES['ant_t4m2_bad'] = ant_stack(
  [['M1', 10], ['M2', 10], ['M3', 10], ['M4', 10], ['M5', 9], ['T4M2', 2]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49],
   ['T4V2', 0.3, 0.4, 0.39, 0.49]])
FIXTURES['ant_t4m2_18_bad'] = ant_stack(
  [['M1', 1], ['M2', 1], ['M3', 1], ['M4', 1], ['M5', 1], ['T4M2', 5.1]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49],
   ['T4V2', 0.3, 0.4, 0.39, 0.49]],
  [box('DGOX', 0.15, -0.05, 0.35, 0.15)])

# Single-via checks.
FIXTURES['ant_via1_bad'] = ant_stack([['M1', 2]], [['V1', 0.3, 0.3, 0.6, 1.0]])
FIXTURES['ant_via1_at_limit'] = ant_stack([['M1', 2]], [['V1', 0.3, 0.3, 0.7, 0.8]])
FIXTURES['ant_via1_cum_bad'] = ant_stack([['M1', 3]], [['V1', 0.3, 0.3, 0.9, 1.15]])
FIXTURES['ant_via2_bad'] = ant_stack(
  [['M1', 2], ['M2', 2]], [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.3, 0.7, 0.825]])
FIXTURES['ant_via2_cum_bad'] = ant_stack(
  [['M1', 2], ['M2', 2]], [['V1', 0.3, 0.3, 0.8, 1.0], ['V2', 0.3, 0.3, 0.7, 0.7]])
FIXTURES['ant_via3_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.3, 0.7, 0.825]])
FIXTURES['ant_via3_cum_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2]],
  [['V1', 0.3, 0.3, 0.68, 0.8], ['V2', 0.3, 0.3, 0.68, 0.8],
   ['V3', 0.3, 0.3, 0.56, 0.8]])
FIXTURES['ant_via4_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2]],
  [['V1', 0.3, 0.3, 0.4, 0.8], ['V2', 0.3, 0.3, 0.4, 0.8],
   ['V3', 0.3, 0.3, 0.4, 0.8], ['V4', 0.3, 0.3, 0.8, 0.72]])
FIXTURES['ant_via4_cum_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2]],
  [['V1', 0.3, 0.3, 0.62, 0.8], ['V2', 0.3, 0.3, 0.62, 0.8],
   ['V3', 0.3, 0.3, 0.64, 0.8], ['V4', 0.3, 0.3, 0.4, 0.5]])
FIXTURES['ant_t4v2_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2], ['M5', 2], ['T4M2', 2]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49],
   ['T4V2', 0.3, 0.3, 0.6, 1.0]])
FIXTURES['ant_t4v2_at_limit'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2], ['M5', 2], ['T4M2', 2]],
  [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
   ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49],
   ['T4V2', 0.3, 0.3, 0.7, 0.8]])
FIXTURES['ant_t4v2_cum_bad'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2], ['M5', 2], ['T4M2', 2]],
  [['V1', 0.3, 0.3, 0.6, 0.6], ['V2', 0.3, 0.3, 0.6, 0.6],
   ['V3', 0.3, 0.3, 0.6, 0.6], ['V4', 0.3, 0.3, 0.6, 0.6],
   ['T4V2', 0.3, 0.3, 0.8, 0.6]])
FIXTURES['ant_t4v2_cum_at_limit'] = ant_stack(
  [['M1', 2], ['M2', 2], ['M3', 2], ['M4', 2], ['M5', 2], ['T4M2', 2]],
  [['V1', 0.3, 0.3, 0.6, 0.6], ['V2', 0.3, 0.3, 0.6, 0.6],
   ['V3', 0.3, 0.3, 0.6, 0.6], ['V4', 0.3, 0.3, 0.6, 0.6],
   ['T4V2', 0.3, 0.3, 0.7, 0.65]])

# RDV / RDL checks on the full stack.
ANT_FULL_PADS = [['M1', 1], ['M2', 1], ['M3', 1], ['M4', 1], ['M5', 1], ['T4M2', 1]]
ANT_FULL_VIAS = [['V1', 0.3, 0.4, 0.39, 0.49], ['V2', 0.3, 0.4, 0.39, 0.49],
                 ['V3', 0.3, 0.4, 0.39, 0.49], ['V4', 0.3, 0.4, 0.39, 0.49],
                 ['T4V2', 0.3, 0.4, 0.39, 0.49]]
FIXTURES['ant_rdv_io_bad'] = ant_stack(
  ANT_FULL_PADS, ANT_FULL_VIAS,
  [box('DGOX', 0.15, -0.05, 0.35, 0.15), box('RV', 0, 0.2, 0.3, 0.9)])
FIXTURES['ant_rdv_io_at_limit'] = ant_stack(
  ANT_FULL_PADS, ANT_FULL_VIAS,
  [box('DGOX', 0.15, -0.05, 0.35, 0.15), box('RV', 0, 0.2, 0.4, 0.7)])
FIXTURES['ant_rdv_core_bad'] = ant_stack(
  ANT_FULL_PADS, ANT_FULL_VIAS, [box('RV', 0, 0.2, 1.4, 1.7)])
FIXTURES['ant_rdv_core_at_limit'] = ant_stack(
  ANT_FULL_PADS, ANT_FULL_VIAS, [box('RV', 0, 0.2, 1.0, 2.2)])
FIXTURES['ant_rdl_bad'] = ant_stack(
  ANT_FULL_PADS, ANT_FULL_VIAS,
  [box('RV', 0, 0.2, 0.3, 0.9), box('RDL', 0, 0.2, 2.0, 1.4)])
FIXTURES['ant_rdl_at_limit'] = ant_stack(
  ANT_FULL_PADS, ANT_FULL_VIAS,
  [box('RV', 0, 0.2, 0.3, 0.9), box('RDL', 0, 0.2, 2.0, 1.33)])

# Conservative diode credit: the SD area on the gate net adds 500 um^-2 to the
# metal limit but the source's fixed !AREA term is omitted.
def ant_diode(m1_area)
  [box('ACT', 0, 0, 0.5, 0.1),
   box('NP', -0.1, -0.1, 0.6, 0.2),
   box('POLY', 0.2, -0.1, 0.3, 0.2),
   box('POLY', -0.75, 0.19, 1.25, 0.45),
   box('CT', 0.2, 0.25, 0.3, 0.35),
   box('ACT', 2.0, 0.0, 2.5, 1.0),
   box('NP', 1.9, -0.1, 2.6, 1.1),
   box('CT', 2.2, 0.4, 2.3, 0.5),
   box('M1', -0.75, 0.19, 4.25, 0.19 + m1_area / 5.0)]
end
FIXTURES['ant_m1_diode_waived'] = ant_diode(51)
FIXTURES['ant_m1_diode_boundary'] = ant_diode(53)

# Stage-wise connectivity: two gate nets merge only through the shared M3 bar.
# Gate A (0.01 um^2) carries 60 um^2 of M1 on its own and must fire at the M1
# and M2 stages; the merged M3 net is clean (~3150), so a full-net model would
# dilute the violation away.
FIXTURES['ant_stage_split'] = [
  box('ACT', -0.9, 0.0, -0.4, 0.1),
  box('NP', -1.0, -0.1, -0.3, 0.2),
  box('POLY', -0.7, -0.1, -0.6, 0.2),
  box('CT', -0.68, 0.12, -0.62, 0.18),
  box('M1', -0.8, 0.1, 1.2, 30.1),
  box('V1', 0.0, 29.0, 0.3, 29.3),
  box('M2', -0.2, 28.8, 0.5, 29.5),
  box('V2', 0.05, 28.95, 0.35, 29.25),
  box('ACT', 9.0, 0.0, 9.7, 0.1),
  box('NP', 8.9, -0.1, 9.8, 0.2),
  box('POLY', 9.2, -0.1, 9.5, 0.2),
  box('CT', 9.3, 0.12, 9.36, 0.18),
  box('M1', 9.1, 0.1, 11.1, 30.1),
  box('V1', 10.0, 29.0, 10.3, 29.3),
  box('M2', 9.8, 28.8, 10.5, 29.5),
  box('V2', 10.05, 28.95, 10.35, 29.25),
  box('M3', 0.0, 28.9, 10.4, 29.4),
]

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
