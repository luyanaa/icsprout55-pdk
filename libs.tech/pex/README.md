# ICsprout55 PEX

**Status: clean-room seeds + vendor-data calibration study.** The released
PDK ships no parasitic-extraction tech files. This directory contains:

- the clean-room RC stack generated from the released LEF
  (`config_gen.py` → `palace/ics55_stackup.xml`, OpenRCX rules,
  LibreLane `LAYERS_RC`/`VIAS_R`),
- the routed-geometry RCX/SPEF extractor `rcx.py`,
- `starrc/` — the vendor StarRC ITF/CAPTAB files (decrypted upstream, see the
  provenance warning below), and
- `starrc_calib.py` + `starrc/CALIBRATION.json` — the comparison between the
  clean-room stack and those vendor files.

## Starting data (from the released tech LEF, `N551P6M_ecos.lef`)

These values are the seed for the PEX setup and are used by `config_gen.py`
and `rcx.py`:

| Layer | Rsheet Ω/sq | Area cap pF/µm² | Edge cap pF/µm |
|---|---|---|---|
| M1 | 0.1122 | 0.7630e-3 | 0.0339e-3 |
| M2 | 0.0914 | 1.1069e-3 | 0.0391e-3 |
| M3 | 0.0914 | 1.1069e-3 | 0.0409e-3 |
| M4 | 0.0914 | 1.1069e-3 | 0.0409e-3 |
| M5 | 0.0914 | 0.6259e-3 | 0.0344e-3 |
| T4M2 | 0.0239 | 0.1299e-3 | 0.0368e-3 |
| RDL | 0.0151 | 0.0574e-3 | 0.0281e-3 |

Via resistance: 2.5 Ω per routing via (VIA1-4, T4V2) in the LEF; the vendor
ITF states 2 Ω for V1-V4, 0.25 Ω for TV and 0.08 Ω for RV.

**Known gap:** the LEF carries no coupling-capacitance model — lateral
coupling dominates at 65nm-class nodes and must come from the foundry RC
deck or from field-solver calibration on test structures. The vendor CAPTAB
provides exactly that width-resolved self/coupling table and is the reference
in `starrc/CALIBRATION.json`.

## StarRC vendor-data calibration (`starrc/`, `starrc_calib.py`)

The files under `starrc/` are **vendor (ICsprout) StarRC data**, not released
PDK collateral: upstream XOR-decrypted them out of the proprietary ECOS iRCX
library (`libircx_ics55.so`) and published them under `hacking/decrypted_output/`.
They are imported here **byte-identically apart from a provenance banner**,
with SHA-256 recorded in `starrc/ORIGIN.json`, and are used **only** as an
offline comparison target. They are **not** Apache-2.0 and must not be
redistributed or treated as signoff data.

```sh
python3 libs.tech/pex/import_starrc.py        # (re)download + banner + hashes
python3 libs.tech/pex/starrc_calib.py --output libs.tech/pex/starrc/CALIBRATION.json
```

Measured findings (`starrc/CALIBRATION.json`):

| Check | Result |
|---|---|
| R: ITF `RPSQ` vs LEF `RPERSQ`, all 7 routing layers | **exact match** — the LEF resistance seeds *are* the vendor values, so no R calibration is needed |
| R: LEF vs `config_gen.py` thickness inference | the bulk-Cu inference (`1.72e-8 Ω·m`) is **10–21% too thin**; effective ρ from `RPSQ × ITF thickness` is 1.92e-8…2.19e-8 Ω·m, i.e. 1.12–1.27× bulk Cu as expected from surface/grain scattering |
| C: LEF `CPERSQDIST`+`EDGECAPACITANCE` vs CAPTAB self-cap | the CAPTAB `A <layer> OVER SUBSTRATE` table fits `C/L = a·W + b` to ~4% rms, but its absolute `a` sits ~45× below the LEF `CPERSQDIST`; the CAPTAB tables are per-environment (layer over/under specific neighbours) and are not directly comparable to the in-context LEF density |
| C: coupling | LEF has no coupling model at all; CAPTAB carries a per-width coupling column for every over/under stack |
| vias | LEF 2.5 Ω vs ITF 2.0 Ω (V1-V4), 0.25 Ω (TV), 0.08 Ω (RV) |
| contacts | absent from the LEF; ITF gives CT_NP 30 Ω, CT_PP 29 Ω, CT_ND 37 Ω, CT_PD 36 Ω |
| dielectrics | ITF `ER` values are 3/4/5/7 by layer; `config_gen.py`'s single `EPS_IMD = 3.3` is not one of them (the series-mean over the real IMD stack is 3.61) |
| geometry | ITF states metal `THICKNESS`/`WMIN`/`SMIN` directly (M1 0.18 µm, M2-M5 0.21 µm, TM 0.9 µm, RDL 1.45 µm) |

## Vendor override in `config_gen.py`

`config_gen.py` keeps the clean-room BASE data verbatim (released LEF seeds +
user-approved estimates) and layers the vendor data on top:

```sh
# BASE only - reproduces the pre-override artifacts byte for byte
python3 libs.tech/pex/config_gen.py --palace --openrcx --corner typ --source lef

# vendor override (default) - one corner
python3 libs.tech/pex/config_gen.py --palace --openrcx --corner rcworst

# vendor override - every corner, plus the flow-corner manifest
python3 libs.tech/pex/config_gen.py --palace --openrcx --layers-rc --manifest --all-corners
```

What the override changes, and what it deliberately does not:

| Quantity | Source | Rationale |
|---|---|---|
| metal THICKNESS | ITF | replaces the 10–21% thin bulk-Cu inference; also fixes `sigma = 1/(RPSQ·t)` |
| RPSQ | ITF | identical to the LEF at Typ, so only non-Typ corners change |
| dielectric `eps` | ITF, collapsed with the series rule `Σt / Σ(t/ε)` | one effective value per group; Typ IMD becomes 3.61 (not 3.3) |
| via + contact R | ITF | adds CT_NP/PP/ND/PD, which the LEF does not carry at all |
| layer capacitance | LEF base **× CAPTAB corner ratio** | ratio-only on purpose: the CAPTAB absolute scale is undocumented and ~45× off the LEF, but the corner ratios are unit-independent |
| inter-metal spacing | unchanged (BASE estimate) | the ITF dielectric ordering/`MEASURED_FROM` semantics need the gds2palace reader re-run before the geometry can be rebuilt from them |

## Corner handling

The vendor set decomposes into two independent axes. Measured from the ITF:

| corner | conductor t | RPSQ | dielectrics |
|---|---|---|---|
| `typ` | 1.00 | 1.00 | 1.00 (baseline) |
| `rcbest` | ×1.10 | ×0.63–0.78 | all ×1.10 |
| `rcworst` | ×0.90 | ×1.26–1.36 | all ×0.90 |
| `cbest` | ×0.90 | ×1.26–1.36 | shaped (+0.25 IMD7b2, +0.049 IMDn b1, −0.022 IMD1b) |
| `cworst` | ×1.10 | ×0.63–0.78 | shaped (mirror of cbest) |

So **rcbest/rcworst scale R and C together**, while **cbest/cworst move only the
C axis and pair with the opposite R**. The vendor pairs them fixed because that
is how the process varies; `--rc-corner`/`--c-corner` mix the axes explicitly
when a flow wants worst-R × worst-C.

Generated outputs, by container type:

| Artifact | Shape | Corners |
|---|---|---|
| `LAYERS_RC`/`VIAS_R` (`layers_rc.tcl`) | corner-keyed dict — **one file holds them all** | 5 vendor names + the 3 flow/Liberty names |
| OpenRCX `rcx*.rules` | one rules file per extraction run | `rcx.rules` (= typ, canonical) + `rcx_<corner>.rules` for each |
| Palace stackup | geometry differs per corner | `ics55_stackup.xml` (= typ, canonical) + `ics55_stackup_<corner>.xml` for each |
| `RC_CORNER_MANIFEST.json` | machine-readable record of every corner, with the Liberty mapping | all |

The flow/Liberty corner names the released libraries were characterized at are
mapped in `LIBERTY_CORNER_MAP` and emitted as extra keys, so STA and extraction
agree by name:

| flow corner | R axis | C axis |
|---|---|---|
| `nom_tt_025C_1v20` | typ | typ |
| `nom_ss_125C_1v08` | rcworst | cworst |
| `nom_ff_n40C_1v32` | rcbest | cbest |

Note that `cbest`/`cworst` here are the *dielectric-shaped, R-crossed* corners
as the vendor ships them, which is why the `ss` corner pairs rcworst with
cworst rather than with cbest.

## Config generator (`config_gen.py`)

`config_gen.py` is the single value source for all extraction configs.  It
carries the clean-room BASE (released LEF seeds + user-approved estimates)
verbatim and applies the StarRC vendor override on top (see above), so a
future silicon calibration touches one file:

    python config_gen.py --palace --magic-snippet --openrcx --layers-rc --manifest --all-corners

- `--palace`      -> `palace/ics55_stackup[_<corner>].xml` (verified with the
                     gds2palace reader; XML declaration is first, then the
                     licence comment, so the file is well-formed)
- `--magic-snippet` -> the magic .tech extract values (resist/areacap/perimc),
                     printed per corner; contact resistances as comments
- `--openrcx`     -> `libs.tech/librelane/<scl>/rcx.rules` (= typ) plus
                     `rcx_<corner>.rules` for every corner
- `--layers-rc`   -> `libs.tech/librelane/<scl>/layers_rc.tcl` (librelane
                     LAYERS_RC/VIAS_R; one corner-keyed dict with all corners)
- `--manifest`    -> `RC_CORNER_MANIFEST.json` (every corner's resolved
                     values plus the Liberty corner mapping)

Flags: `--source {starrc,lef}` selects the override (default `starrc`);
`--corner`, `--rc-corner`, `--c-corner` select/mix corners; `--all-corners`
emits every vendor corner.

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

## RCX provenance limit

The upstream LibreLane flow repository (https://github.com/ckdur/icsprout55-openpdk)
publishes ICsprout55 RC extraction data under `hacking/decrypted_output/`
(StarRC-format `kItf*.txt`/`kCaptab*.txt`, all corners).  Those values are
**NOT clean-room**: they were obtained by XOR-decrypting the proprietary ECOS
iRCX library (`libircx_ics55.so`, openecos-projects/ecc-tools); the upstream's
own `hacking/NOTES.md` documents the decryption.

They are imported into `starrc/` **as a comparison target only**, with the
provenance banner and SHA-256 manifest described above.  Consequences:

- the shipped extraction configs (`config_gen.py` → Palace stackup, OpenRCX
  rules, `LAYERS_RC`/`VIAS_R`) remain **LEF-seeded clean-room** and do not
  embed any vendor value;
- `starrc_calib.py` reports how far the clean-room stack is from the vendor
  data, so a future calibration decision has measured numbers behind it;
- the files are not Apache-2.0, are not released PDK collateral, and must not
  be redistributed or used as signoff data;
- the previously-noted vendor values (M1 0.198 µm RCbest thickness, IMD eps
  3/5/7, etc.) are now measured in `starrc/CALIBRATION.json` rather than
  quoted from memory.

Adopting any reported number into `config_gen.py` remains a separate,
deliberate change with its own review.

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
