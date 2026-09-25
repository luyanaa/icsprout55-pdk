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

## 3D / RLC extension: gds2palace + AWS Palace (`palace/`)

The 2D seed-based `rcx.py` is extended to 3D / frequency-dependent RLC by the
gds2palace + Palace FEM workflow (the current replacement for the legacy
Magic ext2fastcap/ext2fasthenry, which are not part of Magic 8.3):

- `palace/ics55_stackup.xml` - technology stackup for the AWS Palace FEM
  solver (schemaVersion 2.0): metal conductivities from the LEF RPERSQ +
  bulk-Cu thickness inference (all ~5.81e7 S/m), via conductivities from the
  LEF 2.5 ohm via resistance and the LEF via cut sizes, dielectric eps/thickness
  = typical 55nm-node estimates.  Verified with the gds2palace 0.6.0 stackup
  reader (every metal/via zmin lands in its intended dielectric).
- `palace/run_model.py` - model script: GDSII + stackup -> gmsh mesh +
  Palace config.json (1 GHz default, fine mesh); `--thermal` switches to the
  Elmer steady-state thermal flow (heatsources + const-temp boundaries, the
  stackup carries the thermal conductivities/densities).  Requires
  `pip install gds2palace` (gdspy, gmsh, numpy, shapely); the Palace solver
  itself is installed separately (apptainer/spack, see the gds2palace docs).

All stackup values are estimates (no absolute thicknesses or permittivities
in the released data) and are overridable in the XML.

## Notes

- The layer map for extraction = `../klayout/tech/ics55.lyp`.
- DC current limits (LEF DCCURRENTDENSITY): M1 1.5, M2-5 1.7, T4M2 8.1,
  CT 0.29, VIA1-4 0.135, T4V2 3.2 mA/µm — usable for IR/EM budgeting.
