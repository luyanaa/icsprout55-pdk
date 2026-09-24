# ICsprout55 PEX (reserved)

**Status: reserved.** Parasitic extraction tech files are not released.
This directory is allocated for:

- `openrcx/` — OpenRCX (OpenROAD) extraction technology + layer config
- `qrc/`, `star/` — foundry QRC/StarRC tech files (when released)
- `extracted/` — sample extracted netlists

## Starting data (from the released tech LEF, `N551P6M_ecos.lef`)

These values are the seed for the PEX setup and are already used by
`../drc/` and `../spice/models/`:

| Layer | Rsheet Ω/sq | Area cap pF/µm² | Edge cap pF/µm |
|---|---|---|---|
| M1 | 0.1122 | 0.7630e-3 | 0.0339e-3 |
| M2 | 0.0914 | 1.1069e-3 | 0.0391e-3 |
| M3 | 0.0914 | 1.1069e-3 | 0.0409e-3 |
| M4 | 0.0914 | 1.1069e-3 | 0.0409e-3 |
| M5 | 0.0914 | 0.6259e-3 | 0.0344e-3 |
| T4M2 | 0.0239 | 0.1299e-3 | 0.0368e-3 |
| RDL | 0.0151 | 0.0574e-3 | 0.0281e-3 |

Via resistance: 2.5 Ω per via (VIA1-4, T4V2, RV).

**Known gap:** the LEF carries no coupling-capacitance model — lateral
coupling dominates at 65nm-class nodes and must come from the foundry RC
deck or from field-solver calibration on test structures.

## Notes

- The layer map for extraction = `../klayout/tech/ics55.lyp`.
- DC current limits (LEF DCCURRENTDENSITY): M1 1.5, M2-5 1.7, T4M2 8.1,
  CT 0.29, VIA1-4 0.135, T4V2 3.2 mA/µm — usable for IR/EM budgeting.
