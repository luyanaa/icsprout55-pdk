#!/usr/bin/env ruby
# Deterministic LVS extraction fixtures built with KLayout RBA.
#
# Usage: klayout -b -r make_lvs_fixtures.rb -rd out=<directory>

require 'fileutils'

OUT = File.expand_path($out)
FileUtils.mkdir_p(OUT)
LAYERS = {
'ACT' => [2, 1], 'ACTDUM' => [2, 2], 'ACTDUMB' => [2, 3], 'ACTRES' => [2, 4],
  'DNW' => [7, 1], 'NW' => [9, 1],
  'ULLD' => [152, 12], 'UD' => [153, 12], 'OD' => [154, 12],
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
  'COVER' => [124, 1], 'DIODE' => [191, 12],
  'INDALL' => [302, 12], 'INDDMY' => [301, 12], 'INDVIA' => [303, 12],
  'MOMLVS1' => [323, 12], 'MOMTER' => [282, 12],
  'MET1MOM' => [81, 10], 'MET2MOM' => [82, 10], 'MET3MOM' => [83, 10],
  'MET4MOM' => [84, 10], 'MET5MOM' => [85, 10]
}

def box(layer, x1, y1, x2, y2, kind = :box)
  [layer, kind, x1, y1, x2, y2]
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

def varactor_fixture(dnw: false, dgox: false)
  shapes = [
    box('NW', 0, 0, 1.5, 0.6),
    box('ACT', 0, 0, 1.0, 0.6),
    box('NP', 0, 0, 1.0, 0.6),
    box('POLY', 0.45, -0.1, 0.55, 0.7),
    box('VARAM', 0, 0, 1.0, 0.6),
    box('CT', 0.46, 0.62, 0.54, 0.70),
    box('M1', 0.44, 0.60, 0.56, 0.72),
    box('ACT', 1.15, 0.2, 1.45, 0.45),
    box('NP', 1.15, 0.2, 1.45, 0.45),
    box('CT', 1.24, 0.27, 1.36, 0.38),
    box('M1', 1.20, 0.22, 1.40, 0.43)
  ]
  shapes << box('DGOX', 0, 0, 1.0, 0.6) if dgox
  shapes << box('DNW', 0, -0.2, 1.5, 0.8) if dnw
  shapes
end

def rf_nmos_fixture(six_t: false)
  shapes = [
    box('DNW', -0.5, -0.2, 1.6, 0.8),
    box('ACT', 0, 0, 1.0, 0.6),
    box('POLY', 0.45, -0.1, 0.55, 0.7),
    box('NP', 0, 0, 1.0, 0.6),
    box('CT', 0.10, 0.20, 0.25, 0.40),
    box('CT', 0.75, 0.20, 0.90, 0.40),
    box('M1', 0.08, 0.18, 0.27, 0.42),
    box('M1', 0.73, 0.18, 0.92, 0.42),
    box('CT', 0.46, 0.62, 0.54, 0.70),
    box('M1', 0.44, 0.60, 0.56, 0.72),
    box('ACT', 1.15, 0.2, 1.45, 0.45),
    box('PP', 1.15, 0.2, 1.45, 0.45),
    box('CT', 1.24, 0.27, 1.36, 0.38),
    box('M1', 1.20, 0.22, 1.40, 0.43),
    box('ACT', -0.35, 0.2, -0.1, 0.45),
    box('NP', -0.35, 0.2, -0.1, 0.45),
    box('CT', -0.26, 0.27, -0.14, 0.38),
    box('M1', -0.30, 0.22, -0.10, 0.43)
  ]
  if six_t
    shapes += [
      box('ACT', -1.2, 0.2, -0.9, 0.45),
      box('PP', -1.2, 0.2, -0.9, 0.45),
      box('CT', -1.11, 0.27, -0.99, 0.38),
      box('M1', -1.15, 0.22, -0.95, 0.43)
    ]
  end
  shapes
end

rf_pmos_fixture = [
  box('DNW', -0.5, -0.2, 1.6, 0.8),
  box('NW', 0, 0, 1.5, 0.6),
  box('ACT', 0, 0, 1.0, 0.6),
  box('POLY', 0.45, -0.1, 0.55, 0.7),
  box('PP', 0, 0, 1.0, 0.6),
  box('CT', 0.10, 0.20, 0.25, 0.40),
  box('CT', 0.75, 0.20, 0.90, 0.40),
  box('M1', 0.08, 0.18, 0.27, 0.42),
  box('M1', 0.73, 0.18, 0.92, 0.42),
  box('CT', 0.46, -0.32, 0.54, -0.24),
  box('M1', 0.44, -0.34, 0.56, -0.22),
  box('ACT', 1.15, 0.2, 1.45, 0.45),
  box('NP', 1.15, 0.2, 1.45, 0.45),
  box('CT', 1.24, 0.27, 1.36, 0.38),
  box('M1', 1.20, 0.22, 1.40, 0.43),
  box('ACT', -1.2, 0.2, -0.9, 0.45),
  box('PP', -1.2, 0.2, -0.9, 0.45),
  box('CT', -1.11, 0.27, -0.99, 0.38),
  box('M1', -1.15, 0.22, -0.95, 0.43)
]

# Four-terminal RF MOS drawn without DNW: the layout is the plain core MOS, so
# the RF 4T schematic wrapper must compare against NM1P2_SVT_LP.  All four nets
# are labelled so the wrapper pins are exercised end to end.
rf_nmos_4t_fixture = [
  box('ACT', 0, 0, 1.0, 0.6),
  box('POLY', 0.45, -0.1, 0.55, 0.7),
  box('NP', 0, 0, 1.0, 0.6),
  box('CT', 0.10, 0.20, 0.25, 0.40),
  box('CT', 0.75, 0.20, 0.90, 0.40),
  box('M1', 0.08, 0.18, 0.27, 0.42),
  box('M1', 0.73, 0.18, 0.92, 0.42),
  label('M1LBL', 'S', 0.17, 0.30),
  label('M1LBL', 'D', 0.82, 0.30),
  box('CT', 0.46, 0.62, 0.54, 0.70),
  box('M1', 0.44, 0.60, 0.56, 0.72),
  label('M1LBL', 'G', 0.50, 0.66),
  box('ACT', 1.15, 0.2, 1.45, 0.45),
  box('PP', 1.15, 0.2, 1.45, 0.45),
  box('CT', 1.24, 0.27, 1.36, 0.38),
  box('M1', 1.20, 0.22, 1.40, 0.43),
  label('M1LBL', 'B', 1.30, 0.32)
]

# Two-terminal inductor modeled like the ics55_ind PCell: TM2 pad A feeds a
# spiral lead into a tap pad, an RV-connected RDL underpass crosses to pad B,
# and one INDVIA marker covers each RV terminal group.  The TM2 bar is cut by
# INDALL except around the RV pads, so the two terminals are separate nets.
# `open` cuts the TM2 lead between pad A and the tap; `short` straps the two
# RDL pad nets together.
def inductor_fixture(open: false, short: false)
  lead_end = open ? 10 : 22
  shapes = [
    box('INDALL', 0, 0, 40, 20),
    # pad A (outer terminal) and its RV transition vias
    box('T4M2', 0, 7, 12, 13), box('RDL', 0, 7, 12, 13),
    box('RV', 0, 8.5, 3, 11.5), box('RV', 9, 8.5, 12, 11.5),
    # TM2 lead and tap pad (inner end)
    box('T4M2', 0, 9, lead_end, 11), box('T4M2', 18, 4, 24, 16),
    box('RV', 19.5, 7, 22.5, 10), box('RV', 19.5, 13, 22.5, 16),
    # RDL underpass from the tap to pad B (crosses under the lead in 2D only)
    box('RDL', 18, 7, 34, 13),
    # pad B (inner terminal) and its RV transition vias
    box('T4M2', 28, 7, 40, 13), box('RDL', 28, 7, 40, 13),
    box('RV', 28, 8.5, 31, 11.5), box('RV', 37, 8.5, 40, 11.5),
    # explicit LVS terminal markers
    box('INDVIA', 0, 7, 12, 13), box('INDVIA', 28, 7, 40, 13),
    label('T4M2LBL', 'PLUS', 6, 10), label('T4M2LBL', 'MINUS', 34, 10)
  ]
  shapes << box('RDL', 0, 12, 40, 14) if short
  shapes
end

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

# A child-cell MOS whose source and body meet through a real wrapper tap.
# Top-level D/G/S text and the physical tap require no global well aliases.
strict_flat_parent = mos_fixture('NP') + [
  box('POLY', 0.45, -0.4, 0.55, -0.05),
  box('CT', 0.46, -0.32, 0.54, -0.24),
  box('M1', 0.44, -0.34, 0.56, -0.22),
  box('ACT', -0.65, 0.2, -0.4, 0.45, :top_box),
  box('PP', -0.65, 0.2, -0.4, 0.45, :top_box),
  box('CT', -0.6, 0.25, -0.45, 0.4, :top_box),
  box('M1', -0.63, 0.22, -0.42, 0.43, :top_box),
  box('M1', -0.52, 0.28, 0.17, 0.34, :top_box),
  label('M1LBL', 'D', 0.82, 0.3), label('M1LBL', 'S', 0.17, 0.3),
  label('M1LBL', 'G', 0.5, -0.28)
]

# ERC smoke fixtures: one labeled CMOS inverter and single-device rail cases.
gate_tap = [
  box('POLY', 0.45, -0.4, 0.55, -0.05),
  box('CT', 0.46, -0.32, 0.54, -0.24),
  box('M1', 0.44, -0.34, 0.56, -0.22),
  label('M1LBL', 'IN', 0.5, -0.28)
]

erc_pmos = [
  box('ACT', 2.0, 0, 3.0, 0.6), box('POLY', 2.45, -0.1, 2.55, 0.7),
  box('PP', 2.0, 0, 3.0, 0.6), box('NW', 2.0, 0, 3.6, 0.6),
  box('CT', 2.10, 0.20, 2.25, 0.40), box('CT', 2.75, 0.20, 2.90, 0.40),
  box('M1', 2.08, 0.18, 2.27, 0.42), box('M1', 2.73, 0.18, 2.92, 0.42),
  box('M1', 0.73, 0.18, 2.27, 0.42),
  box('POLY', 2.45, -0.4, 2.55, -0.05),
  box('CT', 2.46, -0.32, 2.54, -0.24),
  box('M1', 0.44, -0.34, 2.56, -0.22)
]

# Contacted n-well tie strapped to the PMOS source rail.
erc_well_tie = [
  box('ACT', 3.1, 0.2, 3.45, 0.45), box('NP', 3.1, 0.2, 3.45, 0.45),
  box('CT', 3.2, 0.27, 3.35, 0.38), box('M1', 3.16, 0.22, 3.39, 0.43),
  box('M1', 2.73, 0.18, 3.39, 0.42)
]

erc_inverter = mos_fixture('NP') + erc_pmos + erc_well_tie + gate_tap + [
  label('M1LBL', 'VSS', 0.17, 0.3), label('M1LBL', 'VDD', 2.82, 0.3),
  label('M1LBL', 'OUT', 1.5, 0.3)
]

erc_bad_ptap = [
  box('ACT', 4.0, 0.2, 4.35, 0.45), box('PP', 4.0, 0.2, 4.35, 0.45),
  box('CT', 4.1, 0.27, 4.25, 0.38), box('M1', 4.06, 0.22, 4.29, 0.43),
  box('M1', 3.16, 0.18, 4.29, 0.42)
]

erc_bad_ntap = [
  box('NW', -0.7, 0, -0.15, 0.6), box('ACT', -0.55, 0.2, -0.2, 0.45),
  box('NP', -0.55, 0.2, -0.2, 0.45),
  box('CT', -0.45, 0.27, -0.3, 0.38), box('M1', -0.49, 0.22, -0.26, 0.43),
  box('M1', -0.49, 0.18, 0.27, 0.42),
  # A correct p-tap keeps the P substrate on VSS while the n-tap is on VSS.
  box('ACT', -1.6, 0.2, -1.25, 0.45), box('PP', -1.6, 0.2, -1.25, 0.45),
  box('CT', -1.5, 0.27, -1.35, 0.38), box('M1', -1.54, 0.22, -1.31, 0.43),
  box('M1', -1.54, 0.18, 0.27, 0.42)
]

# Interdigitated MOM stack built like the ics55_mom PCell: three fingers per
# polarity on M2/M3/M4, vias on the two buses, MOMLVS1/momcap24 and METxMOM
# markers.  `open` cuts the PLUS bus (a floating half must not count as a
# comb); `short` straps a PLUS and a MINUS finger together on M2.
def mom_fixture(three_terminal: false, open: false, short: false)
  n = 3
  length = 2.0
  pitch = 0.2
  wire = 0.1
  space = 0.1
  x0 = -n * pitch
  y0 = -length / 2.0
  tot = 2 * n * pitch
  bus = [x0 - 0.2, x0 + tot + 0.2]
  shapes = []
  %w[M2 M3 M4].each_with_index do |metal, level|
    n.times do |f|
      xp = x0 + 2 * f * pitch
      xm = x0 + (2 * f + 1) * pitch
      shapes << box(metal, xp - wire / 2, y0, xp + wire / 2, y0 + length - space)
      shapes << box(metal, xm - wire / 2, y0 + space, xm + wire / 2, y0 + length)
    end
    if open
      shapes << box(metal, bus[0], y0 - 0.3, 0.05, y0)
      shapes << box(metal, 0.15, y0 - 0.3, bus[1], y0)
    else
      shapes << box(metal, bus[0], y0 - 0.3, bus[1], y0)
    end
    shapes << box(metal, bus[0], y0 + length, bus[1], y0 + length + 0.3)
    next if level.zero?

    via = level == 1 ? 'V2' : 'V3'
    n.times do |f|
      xp = x0 + 2 * f * pitch
      xm = x0 + (2 * f + 1) * pitch
      shapes << box(via, xp - 0.045, y0 - 0.2, xp + 0.045, y0 - 0.11)
      shapes << box(via, xm - 0.045, y0 + length + 0.11, xm + 0.045, y0 + length + 0.2)
    end
  end
  shapes << box('M2', -0.65, 0.2, -0.35, 0.25) if short
  if three_terminal
    shapes << box('M1', x0 - 0.3, y0 - 0.4, x0 + tot + 0.3, y0 + length + 0.4)
    shapes << box('MOMTER', x0 - 0.3, y0 - 0.4, x0 + tot + 0.3, y0 + length + 0.4)
    shapes << label('M1LBL', 'B', 0.7, 0.5)
  end
  shapes << box('MOMLVS1', x0 - 0.3, y0 - 0.4, x0 + tot + 0.3, y0 + length + 0.4)
  shapes << label('MOMLVS1', 'momcap24', 0, 0)
  %w[MET2MOM MET3MOM MET4MOM].each do |marker|
    shapes << box(marker, bus[0], y0, bus[1], y0 + length)
  end
  shapes << label('M2LBL', 'PLUS', 0, y0 - 0.15)
  shapes << label('M2LBL', 'MINUS', 0, y0 + length + 0.15)
  shapes
end

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
  'varactor_1p2': varactor_fixture,
  'varactor_2p5': varactor_fixture(dgox: true),
  'varactor_dnw_1p2': varactor_fixture(dnw: true),
  'varactor_dnw_2p5': varactor_fixture(dnw: true, dgox: true),
  'rf_nmos_5t': rf_nmos_fixture,
  'rf_nmos_6t': rf_nmos_fixture(six_t: true),
  'rf_pmos_5t': rf_pmos_fixture,
  'rf_nmos_4t': rf_nmos_4t_fixture,
  'inductor_1tm_alpa': inductor_fixture,
  'inductor_1tm_alpa_open': inductor_fixture(open: true),
  'inductor_1tm_alpa_short': inductor_fixture(short: true),
  'mom_2t': mom_fixture,
  'mom_3t': mom_fixture(three_terminal: true),
  'mom_2t_open': mom_fixture(open: true),
  'mom_2t_short': mom_fixture(short: true),
  'pad_m1_m5_bar': pad_m1_m5 + mos_fixture('NP'),
  'pad_t4_bar': pad_t4 + mos_fixture('NP'),
  'bulk_alias': mos_fixture('NP'),
  'strict_flat_parent': strict_flat_parent,
  'erc_clean': erc_inverter,
  'erc_mn2pg': mos_fixture('NP') + gate_tap + [
    label('M1LBL', 'VSS', 0.17, 0.3), label('M1LBL', 'VDD', 0.82, 0.3)
  ],
  'erc_pathchk_ground': mos_fixture('NP') + gate_tap + [
    label('M1LBL', 'VSS', 0.17, 0.3), label('M1LBL', 'OUT', 0.82, 0.3)
  ],
  'erc_pathchk_power': mos_fixture('PP') + gate_tap + [
    label('M1LBL', 'VDD', 0.82, 0.3), label('M1LBL', 'OUT', 0.17, 0.3)
  ],
  'erc_bad_ptap': erc_inverter + erc_bad_ptap,
  'erc_bad_ntap': erc_inverter + erc_bad_ntap
}

fixtures.each do |name, shapes|
  layout = RBA::Layout.new
  layout.dbu = 0.001
  top = layout.create_cell('TOP')
  geometry_cell = name == :strict_flat_parent ? layout.create_cell('MOS_LEAF') : top
  if geometry_cell != top
    top.insert(RBA::CellInstArray.new(geometry_cell.cell_index, RBA::Trans.new))
  end
  layer_indices = {}
  shapes.each do |shape|
    layer, kind, *geometry = shape
    layer_indices[layer] ||= layout.insert_layer(RBA::LayerInfo.new(*LAYERS.fetch(layer)))
    case kind
    when :box, :top_box
      x1, y1, x2, y2 = geometry
      cell = kind == :top_box ? top : geometry_cell
      cell.shapes(layer_indices[layer]).insert(RBA::Box.new((x1 * 1000).round, (y1 * 1000).round,
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
