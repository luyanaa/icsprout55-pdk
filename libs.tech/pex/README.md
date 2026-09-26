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

## Config generator (`config_gen.py`)

`config_gen.py` is the single clean-room value source (released LEF seeds +
user-approved estimates) and emits all extraction configs, so a future silicon
calibration touches one file:

    python config_gen.py --palace --magic-snippet --openrcx --layers-rc

- `--palace`      -> `palace/ics55_stackup.xml` (verified with the gds2palace reader)
- `--magic-snippet` -> the magic .tech extract values (resist/areacap/perimc)
- `--openrcx`     -> `libs.tech/librelane/<scl>/rcx.rules` (OpenRCX format)
- `--layers-rc`   -> `libs.tech/librelane/<scl>/layers_rc.tcl` (librelane
                     LAYERS_RC/VIAS_R, corner-keyed)

Validated with the LibreLane nix-shell (2026-09-25) on a 4-bit counter:
synthesis -> PnR -> STA (3 corners) -> OpenRCX (our rcx.rules -> counter.nom.spef)
-> IR-drop (LAYERS_RC/VIAS_R) all PASS; the Magic GDS stream-out starts but
reads the large IO library slowly (30-min timeout).  Working example:
libs.tech/librelane/examples/counter/ (run with
`librelane --manual-pdk --pdk-root <parent> -p ics55 config.yaml`).

Notes from the bring-up:
- The pinned OpenROAD 2026-02-17 requires the LEGACY rules header
  ("Extraction Rules for rcx" + Version + Corners); the newer
  "Extraction Rules for OpenRCX" header segfaults calcMinMaxRC.  The full
  RESOVER/OVER/UNDER/DIAGUNDER/OVERUNDER block matrix (LayerCount 7) is
  required - a reduced table also segfaults.
- LAYERS_RC/VIAS_R must be YAML dicts (the tcl env cannot carry dicts),
  keyed {corner: {layer: {res, cap}}} / {corner: {via: {res}}} with the
  released LEF names (MET1.., VIA1..).

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

## 3D quasi-static R/L/M: FastHenry (`fasthenry/`)

For 3D inductors and test structures in the quasi-static regime (dimensions
~ lambda/10), `fasthenry/ext2fasthenry.py` converts the same routed-layout
JSON used by `rcx.py` + the palace stackup into a FastHenry2 `.inp` deck:
segments at their layer's z (metal thickness from the stackup, sigma =
1/(Rsh*h) = stackup Conductivity / 1e6 in 1/(um*ohm)), vias as short vertical
segments (LEF cut sizes), a `g1` lossy-silicon ground plane, ports as
`.external` nodes.  FastHenry directly yields R(f), L(f), M(f) - the regime
the full-wave Palace handles less efficiently.  Build the solver from
github.com/ediloren/FastHenry2 when needed.

## Calibration

- **R: no calibration needed** - the sheet resistance is the released LEF
  RPERSQ (sigma*h = 1/Rsh by construction, so the DC R is foundry-consistent).
- **C: calibrate against the released LEF capacitance seeds** - the palace
  stackup's eps/thickness are estimates; tune them until the simulated
  per-layer C reproduces the LEF `CAPACITANCE`/`EDGECAPACITANCE` values.
- **L/M(f) and thermal: need silicon data** - the metal thickness inference
  and the substrate resistivity (10 ohm*cm) drive the eddy-current loss and
  Q(f); the thermal conductivities drive the temperature.  Calibrate against
  foundry test structures / measured inductors and thermal resistance when
  released (currently not available).

## RCX provenance limit (2026-09-25)

The upstream LibreLane flow repository (https://github.com/ckdur/icsprout55-openpdk)
publishes ICsprout55 RC extraction data under `hacking/decrypted_output/`
(StarRC-format `kItf*.txt`/`kCaptab*.txt`, all corners) and OpenRCX generation
scripts.  **Those values are NOT clean-room and are deliberately NOT used
here**: they were obtained by XOR-decrypting the proprietary ECOS iRCX library
(`libircx_ics55.so`, openecos-projects/ecc-tools); the upstream's own
`hacking/NOTES.md` documents the decryption.  The released ICS55 PDK contains
no absolute thicknesses, permittivities or capacitance tables - the only
clean-room RC sources are the released LEFs (RPSQ, via resistance,
capacitance seeds), which is what this directory and the palace stackup use.

**Anyone who wants the foundry-accurate RC values may use the upstream's
decrypted values instead of our clean-room estimates** - at their own
discretion regarding the provenance/legal status of that data.  The upstream
values (e.g. M1 RPSQ 0.0827 RCbest, M1 thickness 0.198um, IMD eps 3/5/7) are
also the natural silicon-calibration target if the provenance concern is
resolved.

## Limitations

- **DEVSIM (TCAD device simulation) is NOT possible**: DEVSIM solves the
  semiconductor device equations and requires a TCAD model (doping profiles,
  device physics parameters, mesh, contacts), which the foundry has not
  released.  This PDK ships layout/parasitic extraction and circuit-level
  simulation only; device-level simulation would need the foundry TCAD data.
  (Marked 2026-09-25.)

## Notes

- The layer map for extraction = `../klayout/tech/ics55.lyp`.
- DC current limits (LEF DCCURRENTDENSITY): M1 1.5, M2-5 1.7, T4M2 8.1,
  CT 0.29, VIA1-4 0.135, T4V2 3.2 mA/µm — usable for IR/EM budgeting.
