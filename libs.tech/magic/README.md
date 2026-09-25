# Magic technology file (libs.tech/magic)

Clean-room Magic (magic-vlsi 8.3.x) support for the ICsprout55 55nm LLULP
1P6M1TM process (1.2V core + 3.3V IO).  Scope: **interconnect RC parasite
extraction** (`extract all` + `ext2spice`) as an alternative to the Python
RCX (`libs.tech/pex/rcx.py`).  DRC is intentionally NOT covered - the
ICsprout55 DRC runs in KLayout (`libs.tech/drc/ics55_drc.drc`).

## Usage

```sh
MAGIC=/nix/store/d08kw4xlbyf2c8ncs635hlbnvp8hwwhn-magic-vlsi-8.3.660/bin/magic
$MAGIC -noconsole -dnull -rcfile /dev/null -T libs.tech/magic/ics55.tech <<'EOF'
gds read <lib.gds>
load <topcell>
extract all
ext2spice cthresh 0 rthresh 0
ext2spice -o out.spice
quit
EOF
```

The extracted SPICE netlist contains the MOS devices with the official CDL
model names and terminal order (D G S B), plus the lumped node-to-substrate
capacitances.  The `.ext` file also carries the full per-node capacitance
data (readable with `ext2sim` / the standalone `ext2spice`).

## Extraction values and provenance

| Quantity | Value | Source |
|---|---|---|
| M1 sheet resistance | 0.1122 ohm/sq | N551P6M.lef `RPERSQ` |
| M2-M5 sheet resistance | 0.0914 ohm/sq | N551P6M.lef `RPERSQ` |
| TM2 (top metal) sheet | 0.0239 ohm/sq | N551P6M.lef `RPERSQ` |
| Via resistance (V1-V4, TV2) | 2.5 ohm/via | N551P6M.lef `VIA RESISTANCE` |
| M1 area cap | 0.0007630 pF/um2 | N551P6M_ecos.lef `CAPACITANCE` |
| M2-M4 area cap | 0.0011069 pF/um2 | N551P6M_ecos.lef |
| M5 area cap | 0.0006259 pF/um2 | N551P6M_ecos.lef |
| TM2 area cap | 0.0001299 pF/um2 | N551P6M_ecos.lef |
| Edge (fringe) caps | 0.0000339-0.0000409 pF/um | N551P6M_ecos.lef `EDGECAPACITANCE` |

All values are the released LEF seeds; the same numbers drive
`libs.tech/pex/rc_seed.py`.  Magic tech-file values are integer aF/um2
(area), aF/um (perimeter) and mOhm/sq (sheet).

## Device extraction

The `device mosfet` lines emit the official CDL model names:

- `nm1p2_svt_lp` / `pm1p2_svt_lp` - core 1.2V regular Vt (H7CR cells)
- `nm1p2_lvt_lp` / `pm1p2_lvt_lp` - low Vt (H7CL cells, NVT1/PVT1 17/1 18/1)
- `nm1p2_hvt_lp` / `pm1p2_hvt_lp` - high Vt (H7CH cells, NVT3/PVT3 21/1 22/1)
- `nm3p3_lp` / `pm3p3_lp` - 3.3V IO devices (ACT under TGOX 28/1)

The threshold/IO split is done with the `compose` section (diff types per
implant/oxide).  Bulk terminals: NMOS -> substrate (`pwell,space/w`), PMOS ->
the nwell node.  The extracted W/L are the drawn geometry (W in the 100nm
`scale` units, e.g. W=210 = 0.21um).

## Known limitations

- **Gate-oxide capacitance (Cox) and MOS overlap caps are NOT released** -
  the device lines carry no cap terms (placeholder).  The MOS models in
  `libs.tech/spice/models/mos_core.l` are structural stubs only.
- **Poly/diff sheet resistance NOT released** - the poly is an ideal
  conductor (resist 0) in the extraction.
- **No layer-to-layer overlap capacitance and no lateral (wire-to-wire)
  coupling model** - the LEF contains only to-reference capacitance seeds.
  `rcx.py` is fail-closed on coupling for the same reason.
- **Width-dependent sheet resistance not modeled** - Magic uses a fixed rho
  per layer; the ECoS RCX binary's `RPSQ_VS_WIDTH` tables (recovered in
  `libs.tech/pex/ics55_static.py`) have no Magic tech-file equivalent.
  The recovered THICKNESS/RPSQ/ETCH corner multipliers and the FNV-1a
  variation scheme apply to the Python RCX only.
- **DRC section is a dummy** (one width rule) - the real DRC is KLayout.
- **Not cross-checked against `rcx.py` yet** - a netlist-level diff of the
  Magic output vs the Python RCX is pending.

## Bring-up notes (gotchas)

- The `cifinput` GDS mapping is `calma <CIFNAME> <gdsnum> <gdstype>` - the
  CIF layer name comes FIRST (a bare `calma <n> <t>` is a parse error).
- **The nwell (9/1) must be mapped in `cifinput`** - if missing, the PMOS
  bulk extraction fails with "Device pfet does not have a compatible
  substrate node" (the nwell is never painted).
- Tech section order: `contact` -> `compose` -> `connect` -> `extract`
  (compose needs contact; extract needs connect).
- The `.ext` file records the tech **name** (`ics55`); the in-process
  `ext2spice` then matches the loaded technology.
- `units microns` in the extract section puts all values in aF/um2, aF/um,
  mOhm/sq.

## Validation

Validated with magic-vlsi 8.3.660 on the released libraries:

- INVX1H7R: 2 devices (W=210/270, L=60), correct models and bulks.
- AND2X8H7R: 8 devices with per-finger widths (120-310).
- SDFFNRX2H7R: 38 devices + 129 parasitic caps.
- IO P65_1233_VSS1A: 29 devices, all `nm3p3_lp`.
