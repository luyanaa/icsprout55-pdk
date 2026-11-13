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
| Varactor 1.2V/2.5V | `var1p2_npd_nw_lp` / `var2p5_npd_nw_lp` | N+ gate over NW with VARAM (193/12); DGOX selects 2.5V; POS = gate, NEG = contacted NW tap |
| DNW varactor | `var1p2_npd_nw_dnw_lp` / `var2p5_npd_nw_dnw_lp` | Same core inside DNW; DNW is tied to the NW terminal |
| RF NMOS 5T/6T | `ics55_rf_nmos_{svt,lvt,hvt}_{5t,6t}` | DNW-qualified NMOS with P-well tap; terminals D G S B DNW (6T adds PSUB) |
| RF PMOS 5T | `ics55_rf_pmos_{svt,lvt,hvt}_5t` | DNW-qualified PMOS with N-well tap; terminals D G S B SUB |
| 1TM+ALPA1 inductor | `ics55_ind` | INDALL (302/12) keep-out and RV (120/1) terminal pads; TM2/RDL spiral body cut from the conductor graph |
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
- RF model wrappers and `ics55_ind` are read as primitive devices by a
  `NetlistSpiceReader` delegate, so the five- and six-terminal RF devices and
  the two-terminal inductor compare directly against the layout extractors
  instead of being flattened into unrelated internals. MOS source/drain (and
  inductor PLUS/MINUS) are declared equivalent terminals.
- Varactors use the official `npoGate AND NW AND VARAM` core split by
  DGOX/TGOX and SAB. DNW variants are separated by `interacting(DNW)`; the
  DNW is connected to NW where the two N regions overlap.
- RF MOS 5T/6T are DNW-qualified core MOS devices with contacted body taps.
  A P+ tap outside DNW adjacent to the triple well selects the 6T NMOS or the
  5T PMOS substrate terminal; the 5T NMOS stops at the P-well/DNW terminals.
- The inductor PCell draws INDALL over the whole footprint and RV pads at
  both terminals. The deck cuts TM2 inside INDALL except in the RV pad
  halos, so the spiral body is the device rather than a short between the
  two terminal nets. On the schematic side instantiate it as
  `X<name> PLUS MINUS ics55_ind`.
- Comparison normally flattens the schematic. For `strict_topology=true`
  without `strict_hierarchy=true`, physical extraction also defaults to flat,
  unless `run_mode` is explicitly supplied. Generic and `net_only=true`
  extraction retain the deep default. Opt-in `strict_hierarchy=true` requires
  deep extraction, preserves the schematic hierarchy, and requires exact
  one-to-one circuit-name and named-boundary-pin sets on both sides.
- ERC runs on the pre-reduction extracted netlist after top-level labels
  become pins, unless `--no-erc` / `-rd no_erc=true` is given. It ports the
  official `ERC SELECT CHECK` set: `erc_pTap_to_power`,
  `erc_nTap_to_ground`, `erc_mp2pg`, `erc_mn2pg`, `erc_mn2pghvt`,
  `erc_mp2pghvt`, `erc_ptap_outside_dnw_non_ground`, `erc_pathcheck_bad`,
  `erc_nWell_not_to_power`, `erc_pWell_not_to_ground`. The bare PATHCHK
  statements (ground-without-power, power-without-ground, unlabeled nets)
  are not in any `ERC SELECT CHECK` list in the official profile, so they
  are reported as diagnostics and never change `ICS55_ERC`. Power/ground
  names follow `LVS POWER NAME "?VDD?" "?POWER?"` / `LVS GROUND NAME
  "?VSS?" "?GND?"` plus the bulk-tie overrides.

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

# Strict flat macro comparison: both physical and reference sides default flat.
klayout -b -r ics55.lvs -rd input=macro.gds -rd top=MACRO \
    -rd schematic=macro.cdl -rd no_well_ties=true -rd strict_topology=true -z

# Strict hierarchy comparison (also requires strict_topology=true and deep extraction)
klayout -b -r ics55.lvs -rd input=macro.gds -rd top=MACRO \
    -rd schematic=macro.cdl -rd no_well_ties=true \
    -rd strict_topology=true -rd strict_hierarchy=true -z

# Skip ERC (only for fixtures/diagnostics; signoff runs keep it enabled)
python3 run_lvs.py --layout <lib>.gds --top ADDFX1H7R --netlist <lib>.cdl \
    --no-erc
```

`run_lvs.py` resolves relative paths from the caller's working directory,
creates output directories, and removes prior report/netlist outputs before
running KLayout. It returns 0 only when KLayout exits successfully, writes
both outputs, and emits explicit compare-pass and ERC-pass markers; 1 means
a compare mismatch or ERC violations; 2 means a missing tool/input/output,
colliding paths, or an absent compare/ERC verdict. KLayout tool errors retain
their nonzero status. Direct KLayout invocation prints the
`ICS55_LVS_COMPARE=PASS|FAIL` and `ICS55_ERC=PASS|FAIL` markers but does not
use this wrapper's exit-code handling.

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
above. Strict flat comparison is selected with `strict_hierarchy=false` (or
by omitting that switch), and an omitted `run_mode` selects flat physical
extraction. Explicit `run_mode=deep` remains available for diagnostics; a
deep-layout/flat-reference hierarchy mismatch is not a passing comparison.

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
  are not extracted. The released 1.2V antenna-diode cells (ANT2*, ANT4*)
  reference one of these unsupported diode flavors and therefore report a
  false mismatch against the ported extraction.
- RF MOS 5T/6T recognition is DNW-based (the PDK has no RF device marker).
  The layout must provide the contacted P-well/DNW taps; the 6T NMOS and 5T
  PMOS additionally need a P+ substrate tap outside DNW within 3 um of the
  triple well. Multi-finger source/drain regions are assigned alternately by
  x-order; S/D are equivalent terminals, so a swapped assignment is accepted
  but an irregular finger topology may need manual review.
- The RF wrapper models are compared as primitive devices with topology only;
  W/L and the wrapper's internal resistors/capacitors are not checked. The
  varactor extractor covers the two-terminal flavours; RF 3T varactor
  variants are not extracted.
- Inductor extraction requires an RV terminal pad group at both ends of the
  spiral (the PCell now draws them). Terminal nets are paired as the farthest
  RV pads, and the TM2/RDL spiral inside INDALL is the device body. INDALL
  must not enclose unrelated TM2 routing, which would be cut as body metal.
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
- The official deck sets `LVS REDUCE SPLIT GATES YES`; the port does not.
  Series stacks drawn as two parallel diffusion fingers (each reference
  transistor split into e.g. 0.36/0.24 um halves with private midpoint nets)
  are not folded by `combine_devices`, which requires identical source/drain
  nets. These cells report a false topology mismatch although the extracted
  circuit is equivalent and the widths sum to the reference. This is stricter
  than Calibre, not looser; it affects released AND2/AND3, AOI*/OAI*,
  NAND2B/NAND4BB and TBUFX2 families (see the LVS comparison report).
- NMOS and PMOS body annotations use separate virtual layers connected only
  to PSUB and NW respectively; an annotation layer must not bridge the two.
- Foundry data inconsistencies (drawn widths deviate from the CDL; the deck
  reports the geometry truthfully, the compare passes the 5-10% band with a
  WARNING and fails beyond the official 10%):
  - INVX16H7L/H7R/H7H: NMOS drawn 3.04um vs CDL 2.4um, PMOS 2.4um vs
    3.04um (widths swapped, +27%).
  - OAI33X0P5H7L/H7R/H7H: fingers drawn 200nm (NMOS) / 280nm (PMOS) vs CDL
    150nm / 190nm (+33% / +47%).
  - INVX7H7L/H7R/H7H: NMOS 1.2um vs CDL 1.05um, PMOS 1.52um vs 1.33um
    (+14%).
  - TBUFX8H7L/H7R/H7H: TG output-pass NMOS drawn 460nm vs CDL 500nm
    (-8%) - passes at the official 10% tolerance with a WARNING;
    structure verified isomorphic (tristate function identical).
- NAND3BBX0P5H7* / NAND3BBX0P7H7* (all three libs) draw the NMOS series stack
  reversed vs the released CDL (layout VSS-A1N-A2N-C-Y, CDL Y-A1N-A2N-C-VSS).
  Extracted widths match the CDL multiset (150/175/190/222 nm); the logic is
  identical (a series AND is commutative) but the extracted and reference
  netlists are not topologically equivalent, so the compare truthfully reports
  a mismatch; matching requires corrected foundry data.
- ERC covers the ten selected official checks, not the full Calibre rule
  set. `erc_gate_floating` and `erc_nWell_floating` are off in the vendor
  profile and `DFM_ERC_CHECK FALSE` disables the DFM group; they are not
  evaluated. The three unselected PATHCHK statements are diagnostics only.
  Differences from Calibre, all stricter or equal: `erc_pathcheck_bad` omits
  the `nw_para_diode_all` exclusion (unsupported device), so a surviving
  unlabeled/floating island near such a diode can report where Calibre would
  not; standard-cell global well ties make `erc_nWell_not_to_power` and
  `erc_pWell_not_to_ground` pass by construction unless `--no-well-ties`
  is used; tap/well checks probe the contacted conductor first, so a tap
  merged into an unnamed soft-connected well island may be reported where
  Calibre resolves a label. PATHCHK edges follow MOS source/drain and
  resistor A/B terminals only; gates, MOS bulk, diode terminals and MOM
  capacitors are not conducting paths, matching Calibre's `PATHCHK` device
  connectivity. ERC results are still not a foundry signoff.
