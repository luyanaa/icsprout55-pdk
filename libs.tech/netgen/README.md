# Netgen LVS (libs.tech/netgen)

Netgen LVS for the ICsprout55 55nm LLULP 1P6M1TM process.  The layout side is
extracted with Magic (`libs.tech/magic/ics55.tech`); the reference side is the
released CDL under `libs.ref/*/cdl`.  The independent KLayout deck
(`libs.tech/lvs/ics55.lvs`) remains the cross-check and the documented
reference for expected foundry deviations.  Neither flow is foundry signoff.

Scope: MOS standard cells, MOS-only macros, the IO junction diodes the
Magic tech derives from the `DIODE` marker (1.2V lvt p+/n+ and 3.3V p+),
and the silicide-blocked p+ poly resistor (`re_ppo_sab_2t`), which Magic
extracts as folded series segments.  Other resistor flavors are not modeled;
use the KLayout deck for cells that need them (see Known limitations).

## Files

| File | Purpose |
|---|---|
| `ics55.tcl` | Netgen setup: device classes, property tolerance/merging, `cells1`/`cells2`.  Also loaded by LibreLane through `NETGEN_SETUP`. |
| `run_lvs.py` | Standalone end-to-end runner: Magic extraction, SPICE post-processing, netgen compare, JSON summary. |

## Flow

1. **Magic** reads the GDS, loads the top cell, runs `extract do local` +
   `extract all`, and writes `ext2spice lvs` output.
2. **Post-processing** (`run_lvs.py`) injects the CDL port order into the
   `.subckt` line and converts Magic's micrometre W/L to SI metres.  Magic
   also emits `ad/as` in um^2 and `pd/ps` in um; those are converted too (the
   netgen setup deletes them, so they never influence the compare).  Diode
   `area` (um^2) and `pj` (um) are converted to m^2/m the same way.
   Resistor-subcircuit calls (`X... re_*`) are rewritten to primitive `R`
   devices with `w`/`l` in metres; netgen then combines the folded series
   segments into the CDL's single W/L.
3. **netgen** compares the prepared layout netlist with the released CDL using
   `ics55.tcl`.
4. The runner classifies the result and writes a JSON summary next to the
   report.

`ext2spice lvs` deliberately emits `.subckt <cell>` without ports, and the
released CDL is in SI units.  Using `port makeall` or `ext2spice scale on`
instead was evaluated and rejected: the first depends on Magic's port
numbering, the second produces inconsistent units in the device lines.
Post-processing keeps the comparison explicit and auditable.

### Well ties

The released standard-cell GDS has no well/substrate taps, so a standalone
standard-cell extraction would leave every device bulk on an isolated node.
`--mode stdcell` (default) rewrites the PMOS bulk terminal to `VDD` and the
NMOS bulk to `VSS`, the same global tie the KLayout deck applies in its
standard-cell mode.

`--mode macro` (or `--no-well-ties`) keeps the extracted body connections.
Use it for a macro that has physical taps: the promoted Magic tech connects an
n+ tap to `nwell` and a p+ tap to the substrate node, so body islands are real
layout connectivity rather than an assumption.

### Hierarchical macros

`ext2spice lvs` keeps hierarchy: the child `.subckt` lines are preserved and
only the subckt whose name equals `--top` gets the injected ports.  netgen
then descends into the child, but only if the reference netlist contains that
child's `.SUBCKT`.  A top-only reference therefore fails with
`Circuit 1 contains 2 devices, Circuit 2 contains 1`.

Merge the cell libraries into the reference with `--library` (repeatable):

```sh
python3 libs.tech/netgen/run_lvs.py \
    --layout macro.gds --top MACRO --mode macro \
    --netlist macro_top.cdl \
    --library libs.ref/ics55_LLSC_H7CR/cdl/ics55_LLSC_H7CR.cdl
```

The runner writes `<workdir>/reference.cdl` (main netlist + each library,
with a single `.END`) and leaves the inputs untouched; the JSON summary
records `libraries` and `reference`.  `.SUBCKT` port lists still come from
`--netlist`, so the top-level CDL must declare the macro top.

The top-level pins must be labelled in the layout: `esMakePorts` propagates
a label into the child only when the net is named at the top.  `readspice` on
a top-level CDL is the fallback when the layout has no labels.

A standard-cell child needs `--mode stdcell`: the released standard-cell GDS
has no physical taps, so its bulk terminals are only resolvable through the
global VDD/VSS tie, which is what the released CDL assumes.  `--mode macro`
is for cells whose bodies are actually tapped (IO and custom macros).

## Setup details (`ics55.tcl`)

- Device classes: `nm1p2_svt_lp`/`pm1p2_svt_lp` (H7CR), `nm1p2_lvt_lp`/
  `pm1p2_lvt_lp` (H7CL), `nm1p2_hvt_lp`/`pm1p2_hvt_lp` (H7CH), and
  `nm3p3_lp`/`pm3p3_lp` (3.3V IO).
- `property parallel enable` for the MOS classes.  A multi-finger layout then
  merges devices that share drain, gate, source and bulk, and compares against
  the single-device CDL entry (e.g. INVX16).  Devices with different source or
  drain nets never merge.
- `tolerance {w 0.10} {l 0.01}` matches the KLayout deck: L is effectively
  exact, W uses the released 10% relative tolerance.
- `delete ad as pd ps`: diffusion area/perimeter exist only in the extraction.
- **Diodes** (`dio_1p2_pp_nw_lvt_lp`, `dio_1p2_np_pw_lvt_lp`,
  `dio_3p3_pp_nw_lp`): `parallel enable` merges the parallel junction
  fingers Magic extracts.  The CDL carries a per-instance `AREA`/`PJ` plus an
  `M` multiplier; `merge {area add} {pj add}` makes netgen multiply the
  additive values by `M` while combining the parallel devices (see
  `netcmp.c`, `mult > 1`), so the CDL total (`M x AREA`) compares against the
  merged layout total.  `tolerance {area 0.10} {pj 0.10}` mirrors the Calibre
  deck's `VARIABLE dio_err 0.1` (netgen tolerances are relative).
- **Resistors** (`re_ppo_sab_2t`): the layout emits one `rsubcircuit` per
  straight poly segment, and `run_lvs.py` rewrites both sides' `X` calls to
  primitive `R`.  The reference's empty `.SUBCKT re_ppo_sab_2t` placeholder is
  dropped at the same time, otherwise netgen sees two classes with the same
  name and different pins and flattens the reference resistors away.
  `property default` already marks resistor `w` as series-critical and `l`
  as series-add, so netgen merges the four series segments into the CDL's
  folded `W=1u L=14.56u` (or `11.64u`).  A wide resistor is drawn as two
  parallel halves; netgen's default parallel width rule is the harmonic
  resistor formula, so the setup overrides it to `parallel {w add}`
  (4u || 4u = 8u) and enables resistor parallel merging.

`cells1`/`cells2` are mandatory: LibreLane's
`librelane/scripts/netgen/setup.tcl` sources this file and then uses the lists
to equate cell-name prefixes and to implement `LVS_FLATTEN_CELLS` /
`LVS_IGNORE_CELLS`.  Omitting them breaks the LibreLane step before netgen
starts.

## Usage

```sh
# standard cell (reference CDL located automatically under libs.ref)
python3 libs.tech/netgen/run_lvs.py \
    --layout libs.ref/ics55_LLSC_H7CR/gds/ics55_LLSC_H7CR.gds \
    --top NAND2X1H7R

# MOS-only macro with physical taps, no global well tie
python3 libs.tech/netgen/run_lvs.py \
    --layout <macro.gds> --top <MACRO> --mode macro \
    --report /tmp/MACRO.lvs.rpt
```

Options: `--netlist`, `--library`, `--report`, `--json`, `--magicrc`,
`--setup`, `--workdir`, `--keep-work`, `-v`.  The default scratch directory
is `/tmp/opencode`.

Exit status:

| Code | Meaning |
|---|---|
| 0 | Circuits match uniquely, no property errors. |
| 1 | Topology matches uniquely, but property (W/L) errors were found. |
| 2 | Topology mismatch, missing input, or a tool failure. |

The JSON summary carries `verdict`, `topology_match`, `property_errors`,
device counts, input paths, and the report path.

## LibreLane

`libs.tech/librelane/config.tcl` already sets:

```tcl
set ::env(MAGICRC)    .../libs.tech/magic/ics55.magicrc
set ::env(MAGIC_TECH) .../libs.tech/magic/ics55.tech
set ::env(NETGEN_SETUP) .../libs.tech/netgen/ics55.tcl
```

`Netgen.LVS` consumes the Magic SPICE netlist and the powered Verilog netlist.
KLayout remains `PRIMARY_GDSII_STREAMOUT_TOOL`; the Magic tech exists for
extraction and LVS, not for DRC or stream-out.

## Validation

Run on 2026-11-14 with magic 8.3.685 and netgen 1.5.325:

| Library | Cell | Result |
|---|---|---|
| H7CR | INVX1H7R | match |
| H7CR | NAND2X1H7R | match |
| H7CR | AND2X1H7R | match |
| H7CR | SDFFNRX2H7R | match |
| H7CL | NAND2X1H7L | match |
| H7CH | NAND2X1H7H | match |
| H7CR | OAI33X0P5H7R | topology match, property errors (drawn W +33%/+47%) |
| H7CR | INVX16H7R | topology match, property errors (NMOS/PMOS widths swapped) |
| IO | MAGIC_PDIO fixture | match (p+ junction, area=10 um^2, pj=14 um) |
| IO | MAGIC_NDIO fixture | match (n+ junction, area=10 um^2, pj=13 um) |
| IO | SNAKE resistor fixture | match (4 series segments -> 1 folded R) |
| IO | P65_1233_VSS1 | match (44 diode fingers, 3 nets after ground equating) |
| IO | P65_1233_CUT | match (32 x 3.3V diode fingers -> 8 devices, M=4 folded) |
| IO | P65_1233_VDD1A | match (40 IO nMOS + 20 diodes + 16 R segments -> 8 devices) |
| IO | P65_1233_VDD1 | match (18 IO pMOS + 20 IO nMOS + 10 diodes + 8 R segments -> 6 devices) |
| IO | P65_1233_PAR | match (18 IO pMOS + 20 IO nMOS + 10 diodes + 10 R segments -> 6 devices) |

The two property-error cells are the same foundry deviations documented in
`libs.tech/lvs/README.md`; they are reported truthfully, not hidden by a wider
tolerance.  That README also lists INVX7 (+14%), TBUFX8 (5-10%, warning only)
and NAND3BB (reversed series stack, a genuine topology mismatch).

For INVX16 the layout merges 13 NMOS / 7 PMOS fingers into one netgen device
whose `M` counts the fingers; netgen compares the per-finger `W` against the
single CDL device, so the printed delta is larger than the +27% total-width
deviation documented for the KLayout deck.  The verdict is the same: expected
property error, topology match.

### Diode calibration on P65_1233_VSS1

The released cell is diode-only.  Magic extracts 44 fingers:
22 `dio_1p2_pp_nw_lvt_lp` and 22 `dio_1p2_np_pw_lvt_lp`, and no `dio_3p3`
or other device.  The per-finger values multiply back to exactly the CDL
`M x AREA` / `M x PJ` totals:

| Group | Fingers | Layout total (um^2 / um) | CDL M x AREA / PJ |
|---|---|---|---|
| DD1 | 11 | 376.20 / 420.20 | 10 x 37.62p / 42.02u |
| DD2 | 11 | 226.60 / 270.60 | 10 x 22.66p / 27.06u |
| DD3 | 11 | 546.48 / 590.48 | 10 x 54.648p / 59.048u |
| DD0 | 11 | 350.79 / 394.79 | 10 x 35.079p / 39.479u |

The end-to-end runner (`--ground-prefix VSS`, the Calibre deck's
`LVS GROUND NAME "?VSS?"` convention) reports `Circuits match uniquely` with
zero property errors.  The two p+ substrate taps make VSS1 and VSSIO one
physical ground, so the two p diodes merge on both sides (layout 22 -> 1,
reference 20 -> 1); the four device totals above still match exactly.

`tests/regression/magic_lvs_check.py` reruns this matrix together with the
Magic connectivity/stack, capacitance-calibration, diode-fixture and
resistor and hierarchical-macro checks (26 checks, ~110 s).

## Known limitations

- The compare is only as good as the released CDL.  Foundry cells whose drawn
  geometry differs from the CDL remain property errors.
- Magic extracts the drawn W/L; it has no model for width-dependent sheet
  resistance or for coupling capacitance.
- No Cox or overlap capacitance is available in the released data, so the
  extracted device lines carry no intrinsic capacitance.
- **Only the `re_ppo_sab_2t` resistor is modeled.**  The IO CDL also defines
  n+ poly, diffusion and non-SAB resistors (`re_ndif_*`, `re_pdif_*`,
  `re_nwaa_*`, `re_ppo_2t`, ...).  A cell that uses one of those cannot pass
  LVS until the matching `rppo`-style body and device rule is added.
- **Ground-domain nets are equated (`--ground-prefix VSS`).**  The promoted
  tech ties every p+ diffusion to the p-substrate (`pdiff -> pwell,space/w`),
  which is what makes a standalone p+ tap a substrate tap.  In an IO cell
  both `VSS1` and `VSSIO` have p+ taps, so a flat extraction physically
  merges them (`.ext` reports `equiv "VSS1" "VSSIO"`).  The Calibre deck
  handles this with `LVS GROUND NAME "?VSS?" "?GND?"`; `run_lvs.py` now does
  the same: every net starting with `VSS` is renamed to `VSS` in both the
  layout and reference netlists before the compare.  This is why
  `P65_1233_VSS1` passes.  Power nets are not equated (an nwell tie does not
  cross the substrate).  Use `--ground-prefix ''` to disable.
- **Hierarchical references with ground-split child ports** would need the
  same ground equating applied consistently at every level; the current
  rewrite renames device nets but leaves `.SUBCKT` port lists intact, which
  is correct for flat cells and for standard-cell children (VDD/VSS only).
  It has not been exercised on a hierarchical IO macro.
- **The 3.3V `dio_3p3_pp_nw_lp` rule is calibrated on `P65_1233_CUT`**, the
  diode-only 3.3V clamp: 32 fingers of `ACT & PP & NW & TGOX & DIODE - POLY`
  (minus PVT1/PVT3) give 29.5875 um^2 / 42.45 um each, exactly the CDL
  `M=4` values, and netgen matches 8 devices / 7 nets.
- Hierarchical macro LVS needs the child `.SUBCKT` definitions in the
  reference (`--library`) and top-level pin labels in the layout.  A child
  subckt that is absent from the reference cannot be matched; netgen can only
  flatten a child that both sides declare.  The runner does not implement an
  automatic flattening step.
- A full 51 MB IO library read is CPU-heavy (minutes) and the IO cells are
  large flat layouts; run such extractions alone rather than in parallel with
  other Magic jobs.
