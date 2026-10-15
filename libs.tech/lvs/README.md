# ICsprout55 LVS (KLayout)

Transistor-level layout-vs-schematic for the released ICS55 libraries,
implemented as a KLayout LVS deck (port of the iLVS device-recognition table,
`lvs/README.md` history, to the KLayout LVS engine).  Deck structure follows
the IHP SG13G2 (130 nm) runset; device recognition follows the FreePDK45
well/implant split (nact/pact, ngate/pgate, nsd/psd).

## Status

**Working** — verified LVS-clean on a random sample of std cells across
H7CR / H7CL / H7CH (INV, NAND2, ADDF, DFF, XOR, ...) against the released CDL.

## Devices

| Device | CDL model | Recognition |
|---|---|---|
| core NMOS 1.2V | `nm1p2_{svt,lvt,hvt}_lp` | POLY x ACT in NP; bulk = p-substrate (VSS) |
| core PMOS 1.2V | `pm1p2_{svt,lvt,hvt}_lp` | POLY x ACT in PP inside NW; bulk = NW (VDD) |
| IO NMOS 3.3V | `nm3p3_lp` | POLY x IOACT in NP |
| IO PMOS 3.3V | `pm3p3_lp` | POLY x IOACT in PP inside NW |
| poly resistor | `re_ppo_sab_2t` | POLY with PPO marker (41/4), CT straps (Rsq 850, derived) |
| ESD diode | `dio_3p3_pp_nw_lp` | ESD region (55/1) inside NW, P+ anode |
| MOM cap | — | **not extracted yet** (interdigitated M2..M5; needs a custom extractor) |

Vt flavors: LVT via 17/18, HVT via 21/22 (SVT = no marker).

## How it works

- Connectivity: source/drain, contact-qualified tap regions and POLY -> CT -> M1
  -> V1 -> ... -> M5 -> TV2 -> TM2.
  The raw ACT regions are intentionally NOT connected (they span gate +
  source + drain; connecting them would short the terminals).
- Bulk: default standard-cell mode globally ties PSUB to VSS and NW to VDD.
  `-rd no_well_ties=true` instead connects MOS bodies through CT-qualified
  physical taps and keeps separate n-well islands distinct.
- The released CDL is preprocessed before reading: duplicate leaf subckts
  (e.g. TG) are dropped, the `X <nets> / <subckt>` call syntax is converted
  to plain SPICE, and symbolic `W=nw` parameters get `.PARAM` declarations so
  instance parameters propagate during flattening.
- The schematic is flattened before comparison (the CDL is hierarchical, the
  library GDS is flat).

## Usage

```sh
# CLI wrapper
python3 run_lvs.py --layout <lib>.gds --top ADDFX1H7R --netlist <lib>.cdl

# or directly
klayout -b -r ics55.lvs -rd input=<lib>.gds -rd top=ADDFX1H7R \
    -rd schematic=<lib>.cdl -rd report=addf.lvsdb \
    -rd target_netlist=addf_extracted.cir -z
```

Compare is topology-based; L and all non-geometric device parameters are
compared exactly, W with the official 10% relative tolerance (`mos_err 0.1`).
W deviations over 5% warn; deviations over 10% fail.
KLayout uppercases parsed SPICE root circuit names; the deck normalizes only a
case-equivalent top-circuit spelling to the GDS primary name. No net, pin, or
device labels are rewritten by that normalization.
`max_res(1e9)` / `min_caps(1e-18)` filter high-value resistors and tiny caps.
The compare search is bounded at `max_depth(8)` and
`max_branch_complexity(1024)`. A smaller 50-unit branch limit reported
`needs at least 992` for the 2RW macro, so limit-exhausted reports are not proof
of a topology mismatch.

## Known limitations

- MOM capacitors are not extracted (documented above).
- The IO library (P65_1233_*) extracts 213+ devices per cell including
  wide multi-finger transistors (e.g. W=160U ESD devices); comparison against
  the IO CDL needs multi-finger combining and ESD-diode equivalence tuning
  (`--combine-devices` is a start) — in progress.
- Use `-rd no_well_ties=true` for isolated-well macros. Body islands connect
  only through CT-qualified physical taps; uncontacted regions remain floating
  and must be modeled explicitly in the source netlist.
- Not signoff-quality: no foundry LVS rule deck is released; device
  recognition is derived from the released GDS/CDL.
- The released std cells draw multi-finger transistors (e.g. W=300n = 2x150n
  fingers) where some fingers' outer source/drain island is floating (a
  diffusion island without any contact), and large-drive cells (e.g.
  AND2X8H7R) split the series node of a gate chain across several floating
  islands.  The CDL lists one device per gate signal with the summed width,
  so `rule_decks/combine_fingers.lvs` combines the extracted fingers into one
  device and merges the split series-node parts.  The combining is
  CDL-guided: only groups whose summed width matches a single reference
  device of the same class (same gate net for labeled nets, width-based for
  internal nodes) are combined, so cells that legitimately split a signal
  into several devices (e.g. OAI32X3H7L's B1 = 190n + 380n) are left
  untouched.
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
