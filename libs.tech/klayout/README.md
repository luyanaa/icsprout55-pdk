# ICsprout55 — KLayout integration (provisional)

## Contents

| File | Purpose |
|---|---|
| `tech/ics55.lyt` | Technology: dbu 0.001, layer map, reader options |
| `tech/ics55.lyp` | Layer properties (names, colors, patterns) |
| `tech/ics55.map` | GDS layer map (text, for `strm2* -l` or tech import) |
| `pcells/ics55_mos_analog.py` | Multi-finger analog/RF MOS + optional guard ring |
| `pcells/ics55_guard_ring.py` | Standalone guard ring (p+ for NMOS / n+ for PMOS) |
| `pcells/ics55_res_poly.py` | SAB P+ poly resistor (re_ppo_sab) |
| `pcells/ics55_mom.py` | Interdigitated MOM capacitor (M2..M5) |
| `pcells/ics55_pcell_demo.py` | Demo/smoke test: instantiates every PCell to GDS |

## Usage

- Load the technology: KLayout GUI → Tools → Manage Technologies → load
  `tech/ics55.lyt` (it references `ics55.lyp` next to it).
- PCells: Macro Development → open the `pcells/*.py` files → Run.
  Registers library **`ICsprout55`** with four PCells.
- Demo generation (headless):

```
klayout -b -r pcells/ics55_pcell_demo.py -z
# writes pcells/ics55_pcells.gds
```

- Import a GDS with the layer map:

```
klayout -b <file.gds> -l tech/ics55.map ...   (or use the technology)
```

## Layer map (GDS number → name)

Confirmed from std-cell + IO GDS analysis; `(prov)` = provisional name:

| GDS | Name | Note |
|---|---|---|
| 2/1 | ACT | active |
| 9/1 | NW | n-well (text `VNW` on 9/1, `VPW` on 261/12) |
| 17/1, 18/1 | LVTN, LVTP | LVT implant, n/p sides (prov) |
| 21/1, 22/1 | HVTN, HVTP | HVT implant, n/p sides (prov) |
| 28/1 | IOWELL | IO well/substrate region (prov) |
| 41/1 | POLY | gate poly, L=0.06um |
| 41/4 | PPO | poly-resistor marker (prov) |
| 52/1, 53/1 | NP, PP | N+/P+ implant |
| 55/1 | ESD | ESD diode active (prov) |
| 71/1 | IOACT | IO transistor active (prov) |
| 72/1 | CT | contact 0.09um |
| 81/1..85/1 | M1..M5 | metal 1..5 |
| 91/1..94/1 | V1..V4 | vias (0.09um) |
| 103/1 | TM2 | T4M2 thick top metal |
| 113/1 | TV2 | T4V2 via (0.36um) |
| 120/1 | PADM | pad metal/RDL strap (prov) |
| 121/1 | ALPAD | Al bond pad (55x55um) |
| 123/1 | PV | passivation opening (prov) |
| 191/12, 351/12 | BOUNDARY, CELLBOUND | cell boundaries |
| 261/12 | VPW | p-well text |
| 313/12, 354/12, 356/12, 357/12 | L313.. | reserved (prov) |

## Caveats

- PCell geometry is a **template** derived from std-cell GDS measurements
  (gate L 0.06um, poly pitch 0.25um, CT 0.09um). The foundry DRC is not
  released; verify all generated geometry against the foundry DRC before
  tapeout.
- `(prov)` layers are named by inference; they may differ from the
  foundry's official layer names.
