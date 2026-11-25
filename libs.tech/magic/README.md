# Magic technology file (libs.tech/magic)

Clean-room Magic (magic-vlsi 8.3.685) support for the ICsprout55 55nm LLULP
1P6M1TM process (1.2V core + 3.3V IO).  Scope: **LVS netlist extraction** and
**interconnect RC extraction** (`extract all` + `ext2spice`).  DRC is
intentionally NOT covered - the ICsprout55 DRC runs in KLayout
(`libs.tech/drc/ics55_drc.drc`).

The technology is the promoted former work copy; the exact-stack, tap, and
capacitance regressions in `tests/regression/magic_lvs_check.py` gate it.

## Usage

```sh
magic -noconsole -dnull -rcfile libs.tech/magic/ics55.magicrc <<'EOF'
gds read <lib.gds>
load <topcell>
extract do local
extract all
ext2spice lvs
ext2spice -o out.spice
quit
EOF
```

For LVS use the standalone runner, which also injects ports, converts units
and invokes netgen:

```sh
python3 libs.tech/netgen/run_lvs.py --layout <lib.gds> --top <CELL>
```

The extracted SPICE netlist contains the MOS devices with the official CDL
model names and terminal order (D G S B); the `.ext` file also carries the
per-node capacitance data.  `ext2spice lvs` intentionally emits no ports on
the `.subckt` line and uses micrometre W/L; the LVS runner fixes both (see
`libs.tech/netgen/README.md`).

## Connectivity (LVS)

The `connect` section qualifies every contact by the layers it touches
(`ct/a`, `ct/m1`, `v1/a`, ...) instead of connecting bare layer names.  A
contact then joins only the two planes it really sits between; without this,
Magic merges every contact at one coordinate and fragments poly/diffusion
nets.  The contact section sets `stackable`, which is required when a contact
and a via share exactly the same centre (CT + V1): otherwise Magic drops the
lower contact.

The tap rules are part of the connectivity:

- `nwell,ndiff -> nwell,ndiff` (plus the lvt/hvt/IO n-diff variants): an n+
  tap is the nwell contact.
- `substrate pdiff,lvtpdiff,hvtpdiff,iopdiff,pwell,space/w $SUB`: a p+ tap is
  a substrate contact.

An n+ tap therefore extracts as an `nw` node, a p+ tap as the `substrate`
node, and an untapped nwell island stays separate.  This makes physical taps
in a macro real body connections; standalone standard cells (which have no
taps) use the global well tie in `libs.tech/netgen/run_lvs.py` instead.

## GDS layer mapping (`cifinput`)

The input section maps both the drawn geometry and the datatype-6 text
layers.  Three rules matter:

- **Metal labels are read with their conductor.**  `layer m1 CM1,M1LBL`
  maps 81/1 (geometry) and 81/6 (text) to the same Magic type, and
  `labels M1LBL` attaches the text to it.  The same pattern covers m2-m5
  (82-85/6) and tm2 (103/6).  Without it every pin label lands on an
  "unknown layer" and Magic relocates it (`Moving label "Y" from space to
  metal1`), which can attach a pin to the wrong net.
- **`options ignore-unknown-layer-labels`** discards labels on unmapped
  layers instead of relocating them.
- **Markers are `templayer`s.**  PPO 41/4, ESD 55/1, SAB 71/1, MET1DUM
  81/2, RV 120/1, CB 121/1, RDL 123/1 and RDLLBL 123/6 are read as CIF
  templayers: the geometry is available for boolean derivation but is
  never painted, so it cannot create connectivity.

`DIODE` 191/12 is the one exception.  A cifinput `templayer` plane is
discarded before the layer list is evaluated, so `and DIODE` against one
returns nothing - it cannot be used as a boolean operand.  `DIODE` is
therefore a plain `layer` painting the inert `diode` type, listed first so
that act/np/pp paint over the marker tile.

The derived diode junctions (`pdio1p2lvt`, `ndio1p2lvt`, `pdio3p3`) live on
their own `diodeactive` extraction plane.  A device region on the active
plane is split by every contact cut; keeping the junction on a separate plane
leaves the diffusion, contacts and metals unchanged, and a `connect` rule
joins the junction to `pdiff`/`ndiff` and the contact image.  This is the
same pattern the ETRI050 tech uses (`pdiode_active`/`diodeactive`).  The
`cifinput` `layer` syntax accepts at most three fields: every boolean must be
its own continuation line (`layer X A`, then `and B`, `and-not C`, ...); an
inline `layer X A and B` is rejected and silently leaves an empty layer.

Derived layers must come **after** their source layers: a `layer ... and X`
entry only sees read layers defined above it, so keep every derived layer
at the end of `cifinput`.  Painting a derived layer onto `poly` over
ACT+PP silently composes into `pfet`, which makes `cif write` show nothing;
probe derived geometry on a fresh type or on `m1`.

### Layers that cannot be read

Magic's Calma reader caps layer and datatype at `CALMA_LAYER_MAX` = 255
(`calma/calmaInt.h`).  GDS layers 261/12, 313/12, 351/12, 354/12, 356/12
and 357/12 therefore cannot be mapped or ignored, and `gds read` keeps
reporting them.  On the IO GDS this is 114 errors spread over 22-23 cells;
they are administrative markers (boundary, cell-name, substrate-marker
planes) with no device meaning.  Mapping everything else takes the same
read from 324 unknown-layer errors and 902 "Moving label" events to 114
and 0.  The extracted device list is unchanged; the only difference in the
standard-cell netlist is that the pins are now named (`Y`, `A`, `VDD`,
`VSS`) instead of Magic's auto-generated node names, because the labels
attach to the metal rather than being relocated.

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
`libs.tech/pex/rc_seed.py`.

### Capacitance units (important)

The extraction grid is 10 nm, so 1 um^2 = 10000 grid squares.  Magic stores

- `areacap` in aF per grid square: stored value x 1e4 = aF/um^2, i.e.
  stored value = 0.1 x (LEF pF/um^2);
- `perimc` in aF per grid edge: stored value x 100 = aF/um, i.e. stored value
  = 10 x (LEF pF/um).

The LEF-derived values are therefore `areacap m1 0.0763` and
`perimc m1 space 0.339`, not the 4x/2x smaller numbers that a 5 nm grid would
imply.  A 10x10 um plate must extract 77.656 fF on M1, 112.254 fF on M2 and
14.462 fF on TM2 (area + perimeter).  The regression checks these to 0.5%;
the current tech matches them exactly.

## Device extraction

The `device mosfet` lines emit the official CDL model names:

- `nm1p2_svt_lp` / `pm1p2_svt_lp` - core 1.2V regular Vt (H7CR cells)
- `nm1p2_lvt_lp` / `pm1p2_lvt_lp` - low Vt (H7CL cells, NVT1/PVT1 17/1 18/1)
- `nm1p2_hvt_lp` / `pm1p2_hvt_lp` - high Vt (H7CH cells, NVT3/PVT3 21/1 22/1)
- `nm3p3_lp` / `pm3p3_lp` - 3.3V IO devices (ACT under TGOX 28/1)

The threshold/IO split is done with the `compose` section (diff types per
implant/oxide), so the contact rules must cover every composed diffusion type:
`ct lvtndiff/lvtpdiff/hvtndiff/hvtpdiff/iondiff/iopdiff m1`.  Bulk terminals:
NMOS -> substrate (`pwell,space/w`), PMOS -> the nwell node.  Extracted W/L are
the drawn geometry in micrometres (e.g. W=0.21).

The `device pdiode`/`ndiode` lines add the junction diodes, also with the
official CDL model names:

- `dio_1p2_pp_nw_lvt_lp` - p+ in nwell, PVT1 lvt: `ACT & PP & NW & DIODE & PVT1 - POLY`
- `dio_1p2_np_pw_lvt_lp` - n+ in p-substrate, NVT1 lvt: `ACT & NP & NVT1 & DIODE - NW - POLY`
- `dio_3p3_pp_nw_lp` - p+ in nwell under thick oxide: `ACT & PP & NW & TGOX & DIODE - POLY`

These follow the Calibre deck's `pJunc`/`pDioJunc` derivation and the
`dio_1p2_*`/`dio_3p3_*` device split.  `a=area` and `p=pj` are written in
um^2 / um; `libs.tech/netgen/run_lvs.py` converts them to the CDL's SI units.
On `P65_1233_VSS1` the 44 extracted fingers multiply back to exactly the CDL
`M x AREA`/`M x PJ` totals, and the 32 3.3V fingers on `P65_1233_CUT` do the
same (see `libs.tech/netgen/README.md`).

The `device rsubcircuit re_ppo_sab_2t rppo poly l=l w=w` line adds the
silicide-blocked p+ poly resistor:

- body `rppo = POLY & PP & SAB(71/1) & PPO(41/4) - ...`; `SAB` and `PPO` are
  painted as real layers because a `templayer` plane is not visible to a
  later `layer` boolean.  `PPO` 41/4 is the Calibre deck's `POLYres` marker,
  `SAB` 71/1 its silicide block.
- Each straight segment is one resistor (`w` x `l` from the drawn geometry);
  `run_lvs.py` rewrites the calls to primitive `R` and netgen's series
  combination folds the four segments into the CDL's `W=1u L=14.56u`/`11.64u`.
  The `resist rppo 725700` value mirrors the Calibre `rsh_rpposab` 725.7
  ohm/sq seed.

## Known limitations

- **Poly resistors are not extracted.**  The released IO/macro CDL also
  contains poly resistors (`re_*`); they have no Magic device definition, so
  cells that use them cannot pass netgen LVS with this tech.  Use the
  KLayout deck (`libs.tech/lvs/ics55.lvs`) for those.
- **The 3.3V p+ diode rule is implemented but uncalibrated** (`ACT & PP & NW &
  TGOX & DIODE - POLY`); only the 1.2V lvt p+/n+ junctions were calibrated on
  `P65_1233_VSS1`.
- **A flat extraction merges the ground nets through the p-substrate.**  The
  global `pdiff -> pwell,space/w` connect rule (needed so a standalone p+ tap
  is a substrate tap) connects every p+ tap, so a cell that taps two grounds
  (e.g. `VSS1` and `VSSIO` in `P65_1233_VSS1`) extracts them as one node.
  This is physically what the p-substrate does.  The LVS runner applies the
  Calibre deck's convention (`LVS GROUND NAME "?VSS?"`): every `VSS*` net is
  renamed to `VSS` in both netlists before the compare
  (`run_lvs.py --ground-prefix`, default `VSS`).  Power nets stay separate.
  The junction geometry itself is exact.
- **GDS layers above 255 stay unreadable.**  Magic's Calma reader cannot
  represent them, so the six administrative planes in the IO library keep
  producing `gds read` errors.  They carry no device semantics.
- **Gate-oxide capacitance (Cox) and MOS overlap caps are NOT in the released LEF** -
  the extracted device lines carry no cap terms. Use the vendor BSIM4 cards
  under `libs.tech/spice/foundry/` for device-level simulation.
- **Poly/diff sheet resistance NOT released** - the poly is an ideal conductor
  (`resist 0`) in the extraction.
- **No layer-to-layer overlap capacitance and no lateral (wire-to-wire)
  coupling model** - the LEF contains only to-reference capacitance seeds.
  `rcx.py` is fail-closed on coupling for the same reason.
- **Width-dependent sheet resistance not modeled** - Magic uses a fixed rho
  per layer; the ECoS RCX binary's `RPSQ_VS_WIDTH` tables (recovered in
  `libs.tech/pex/ics55_static.py`) have no Magic tech-file equivalent.
- **DRC section is a dummy** (one width rule) - the real DRC is KLayout.
- **Extraction cost grows with bbox area and node count** - a 10x10 um plate
  extracts in ~5 s, two separated plates on one layer in ~45 s.  Large macros
  are minutes, not seconds.

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
- `ext2spice lvs` writes `.subckt <cell>` with no ports and W/L in um; this
  is expected, not an extraction failure.  Use `libs.tech/netgen/run_lvs.py`
  for the netgen comparison.

## Validation

`python3 tests/regression/magic_lvs_check.py` (magic 8.3.685, netgen 1.5.325,
klayout; 26 checks, ~110 s):

- exact-centre CT/V1, V1/V2, V2/V3, V3/V4, V4/TV2 stacks each collapse to one
  node (`stackable`);
- n+ tap -> `nw`, p+ tap -> `substrate`, untapped nwell stays separate;
- 10x10 um M1/M2/TM2 plates match the LEF area + edge capacitance exactly;
- `MAGIC_PDIO` / `MAGIC_NDIO` extract exactly one 1.2V lvt diode each with
  area=10 um^2 and pj=14/13 um, while a plain contacted tap cell extracts
  zero diodes (the shared-contact regression);
- the `SNAKE` resistor fixture extracts four `re_ppo_sab_2t` segments
  (l=3.64 um, w=1 um each) and netgen folds them into one W=1u/L=14.56u
  device with zero property errors;
- the IO matrix passes with `--mode macro`: `P65_1233_VSS1` (44 x 1.2V
  diode fingers), `P65_1233_CUT` (32 x 3.3V diode fingers -> 8 devices),
  `P65_1233_VDD1A` (40 IO nMOS + 20 diodes + 16 folded R segments ->
  8 devices), `P65_1233_VDD1` (18 IO pMOS + 20 IO nMOS + 10 diodes +
  8 R segments -> 6 devices) and `P65_1233_PAR` (18 IO pMOS + 20 IO nMOS +
  10 diodes + 10 R segments -> 6 devices), all with zero property errors;
- a `MAGIC_HIER` cell instancing `INVX1H7R` passes netgen LVS both with the
  child subckts inline in the reference CDL and with a top-only CDL plus
  `--library` (the merged reference contains both `.SUBCKT INVX1H7R` and
  `.SUBCKT MAGIC_HIER`);
- INVX1H7R, NAND2X1H7R, AND2X1H7R, SDFFNRX2H7R, NAND2X1H7L, NAND2X1H7H pass
  netgen LVS;
- OAI33X0P5H7R and INVX16H7R report property errors (documented foundry
  width deviations), with topology still matching.

The IO library read is a separate manual check (51 MB, minutes): `gds read`
+ `load P65_1233_VSS1` reports 114 unknown-layer errors, all from the six
above-255 administrative planes, and 0 unknown-label or "Moving label"
events.  Extracting `P65_1233_VSS1` yields 44 diode fingers whose merged
totals equal the CDL `M x AREA`/`M x PJ` exactly (see the netgen README);
the netgen compare still fails on VSS1/VSSIO pin topology because the p+
taps of both grounds merge through the substrate (a documented limitation).

Earlier bring-up (8.3.660) confirmed the device split on INVX1H7R,
AND2X8H7R, SDFFNRX2H7R and the IO cell `P65_1233_VSS1A`.
