# ICsprout55 LVS (KLayout)

Transistor-level layout-vs-schematic for the released ICS55 libraries,
implemented as a KLayout LVS deck (port of the iLVS device-recognition table,
`lvs/README.md` history, to the KLayout LVS engine).  Deck structure follows
the IHP SG13G2 (130 nm) runset; device recognition follows the FreePDK45
well/implant split (nact/pact, ngate/pgate, nsd/psd).

## Status

**Provisional KLayout port** — deterministic source-behavior fixtures and
selected released-CDL checks are local evidence only. No same-input Calibre
differential is available; this is not an LVS signoff result.

## Devices

| Device | CDL model / class | Recognition |
|---|---|---|
| core NMOS/PMOS 1.2V | `nm1p2_{svt,lvt,hvt}_lp` / `pm1p2_{svt,lvt,hvt}_lp` | POLY × ACT in NP/PP; source-specific SVT/LVT/HVT selectors |
| IO NMOS/PMOS 3.3V | `nm3p3_lp` / `pm3p3_lp` | POLY × TGOX IO active in NP/PP |
| PPO/SAB poly resistor | `re_ppo_sab_2t` | POLY/PPO/SAB selector, with CT terminal straps; Calibre `rsh_rppo=10.252 Ω/□` |
| Metal resistors | `RE_M1..RE_M5_{2T,3T}` or `RE_TM1/TM2_{2T,3T}` | Stack-selected resistor marker and conductor; source sheet resistances |
| ALPAD/RDL resistors | `RE_ALPA_{2T,3T}` | RDL/ALPAD resistor markers with AP terminals |
| 3.3V P+/NW diode | `dio_3p3_pp_nw_lp` | P+ junction with DIODE marker (191/12) and TGOX in NW; ESD marker (55/1) is unrelated |
| MOM capacitor | — | not extracted |

LVT uses markers 17/18; HVT uses 21/22. Core MOS selectors exclude both TGOX
and DGOX. TGOX IO selectors retain the source-defined ESDIOE exception.

## How it works

- Connectivity: source/drain, CT-qualified tap regions and POLY feed the
  conductor stack. `metal_stack=auto` selects M1-M5 or M4-T4M1-T4M2 from the
  top hierarchy; `--metal-stack` can force either stack. Raw ACT is not
  connected because it spans gate, source and drain regions.
- Resistor bodies are extracted as resistor path layers with CT/AP terminal
  conductors; they are not shorted into the ordinary connectivity graph.
- Ports follow Calibre `PORT DEPTH 0`: only direct top-cell text on selected
  conductors becomes a pin. Child-cell labels remain internal nets.
- Bulk: standard-cell mode globally ties PSUB/NW to the top CDL ground/power
  pins (falling back to VSS/VDD). `--no-well-ties` instead uses CT-qualified
  physical taps and preserves isolated well islands; use this for macros with
  physical body ties.
- The released CDL is preprocessed before reading: repeated definitions are
  deduplicated, `X <nets> / <subckt>` calls are converted to plain SPICE, and
  symbolic parameters are declared for instances.
- The default comparison flattens the schematic (the released standard-cell
  GDS is flat). Opt-in `strict_hierarchy=true` keeps the schematic hierarchical
  and requires exact one-to-one circuit-name and named-boundary-pin sets across
  the extracted GDS and reference netlists.

## Usage

```sh
# Standard cell: standard-cell bulk rails are globally tied.
python3 run_lvs.py --layout <lib>.gds --top ADDFX1H7R --netlist <lib>.cdl

# Macro with physical taps and isolated wells:
python3 run_lvs.py --layout macro.gds --top MACRO --netlist macro.cdl \
    --no-well-ties --metal-stack auto

# Direct KLayout invocation
klayout -b -r ics55.lvs -rd input=<lib>.gds -rd top=ADDFX1H7R \
    -rd schematic=<lib>.cdl -rd report=addf.lvsdb \
    -rd target_netlist=addf_extracted.cir -rd metal_stack=auto -z

# Strict hierarchy comparison (also requires strict_topology=true and deep extraction)
klayout -b -r ics55.lvs -rd input=macro.gds -rd top=MACRO \
    -rd schematic=macro.cdl -rd no_well_ties=true \
    -rd strict_topology=true -rd strict_hierarchy=true -z
```

`run_lvs.py` resolves relative paths from the caller's working directory,
creates output directories, and removes prior report/netlist outputs before
running KLayout. It returns 0 only when KLayout exits successfully, writes
both outputs, and emits an explicit compare-pass marker; 1 means an explicit
mismatch; 2 means a missing tool/input/output, colliding paths, or absent
compare verdict. KLayout tool errors retain their nonzero status. Direct
KLayout invocation prints the `ICS55_LVS_COMPARE=PASS|FAIL` marker but does
not use this wrapper's exit-code handling.

Compare is topology-based. MOS L and non-geometric parameters compare exactly;
MOS W uses the official 10% relative tolerance (`mos_err 0.1`). W deviations
over 5% warn; deviations over 10% fail. KLayout uppercases parsed SPICE root
names, so the deck normalizes only a case-equivalent root spelling; it does
not rewrite net, pin, or device labels. Default simplification includes
KLayout's built-in electrical reductions. `--combine-devices` requests an
additional explicit combine stage; it never authorizes joining distinct nets.

`max_res(1e9)` / `min_caps(1e-18)` filter high-value resistors and tiny caps.
The compare search is bounded at `max_depth(8)` and
`max_branch_complexity(1024)`. A smaller 50-unit branch limit reported
`needs at least 992` for the 2RW macro, so limit-exhausted reports are not proof
of a topology mismatch.

The OpenRAM runner requests `-rd strict_topology=true` for generated macros.
This mode disables simplification/purge that can remove unused declared pins,
combines only electrically parallel MOS, uses 1e-9 um absolute and zero relative
W/L tolerance, and requires identical case-insensitive declared top-pin names.
Every shared boundary net is a mandatory native comparison correspondence;
no physical nets are joined. The native `LayoutVsSchematic` database records
the comparison, and the extracted SPICE is saved before the search begins.
Default released-standard-cell comparison retains the 10% width convention
above. Flat strict comparison remains the default and is selected with
`strict_hierarchy=false` (or by omitting that switch).

`strict_hierarchy=true` is an opt-in no-flatten path, not a name-guessing
heuristic. It requires deep layout extraction, an exact case-insensitive
one-to-one set of all extracted/reference circuit names, and an exact set of
named pins on every paired circuit. Every such pin pair is passed as a
mandatory `same_nets(..., true)` correspondence; duplicate/unnamed circuits
or pins, divergent duplicate CDL definitions, missing circuits, and mismatched
boundaries fail closed as an error or `INCONCLUSIVE`.
No hierarchy comparison is attempted for these inputs.

The normal `align` step is deliberately skipped: KLayout documents that it
flattens circuits when it cannot find a correspondence. The explicit mapping
is instead supplied to `NetlistComparer` without that flattening step.
If circuit names and pin boundaries match, KLayout's
native comparison checks the full paired hierarchy and devices with the same
strict MOS model/W/L settings as flat mode. No circuit renaming, pin deletion,
power aliasing, net joining, or tolerance change is performed. Different but
functionally equivalent partitions are intentionally unsupported by this
mode; use the strict flat fallback instead. A timeout remains inconclusive,
and no full-macro runtime improvement is claimed until a full run completes.

`openram_strict_capability.json` is the source-controlled OpenRAM macro
capability contract. It pins the strict comparison settings, adjacent PDK
revision, KLayout version, and the frozen SHA-256 manifest for this deck and
its included rule modules. The OpenRAM runner validates this file before a
strict macro LVS launch; generic standard-cell LVS does not consume it.


## Known limitations

- MOM capacitors, 2.5V/native MOS families, BJTs, and additional diode classes
  are not extracted.
- The IO library (P65_1233_*) comparison is not validated. Its wide
  multi-finger/ESD devices need further model and topology checks;
  `--combine-devices` is optional and is not a proven equivalence fix.
- For macros with physical body taps, use `--no-well-ties`. Body islands then
  connect only through CT-qualified taps; uncontacted regions remain floating
  and must be represented in the source netlist.
- The official Calibre LVS source is released under `pv/LVS`, but this
  KLayout translation has no same-input Calibre differential in this
  environment. It is not foundry signoff.
- MOS finger reduction uses KLayout's physical-parallel rule: identical
  gate, bulk, channel length and unordered source/drain net pair, with summed
  width. Uncontacted diffusion islands remain separate even if the reference
  CDL has a single device with their total width.
- The removed CDL-guided reduction joined distinct S/D nets. Its direct
  top-cell ACT lookup also returned no component for hierarchical macros,
  grouping unrelated devices together. On an OpenRAM 2RW macro this produced
  a synthetic `gnd|vdd` net; the same frozen GDS/reference passed after
  replacing that pass with physical-parallel reduction. Never restore
  reference-width-based net joining to make an LVS result pass.
- NMOS and PMOS body annotations use separate virtual layers connected only
  to PSUB and NW respectively; an annotation layer must not bridge the two.
- Foundry data inconsistencies (drawn widths deviate from the CDL; the deck
  reports the geometry truthfully, the compare passes the 5-10% band with a
  WARNING and fails beyond the official 10%):
  - INVX16H7L/H7R/H7H: NMOS drawn 3.04um vs CDL 2.4um, PMOS 2.4um vs
    3.04um (widths swapped, +27%).
  - OAI33X0P5H7L/H7R/H7H: fingers drawn 200nm vs CDL 150nm (+33%).
  - INVX7H7L/H7R/H7H: NMOS 1.2um vs CDL 1.05um, PMOS 1.52um vs 1.33um
    (+14%).
  - TBUFX8H7L/H7R/H7H: TG output-pass NMOS drawn 460nm vs CDL 500nm
    (-8%) - passes at the official 10% tolerance with a WARNING;
    structure verified isomorphic (tristate function identical).
  - NAND3BBX0P7H7L/H7R/H7H: PMOS drawn 190nm vs CDL 222nm (-14%) on top of
    the stack-order issue below.
- NAND3BBX0P5H7* / NAND3BBX0P7H7* (all three libs) draw the NMOS series stack
  reversed vs the released CDL (layout VSS-A1N-A2N-C-Y, CDL Y-A1N-A2N-C-VSS).
  The logic is identical (a series AND is commutative) but the extracted and
  reference netlists are not topologically equivalent, so the compare
  truthfully reports a mismatch; matching requires corrected foundry data.
