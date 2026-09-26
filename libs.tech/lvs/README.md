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

- Connectivity: NSD/PSD/POLY -> CT -> M1 -> V1 -> ... -> M5 -> TV2 -> TM2.
  The raw ACT regions are intentionally NOT connected (they span gate +
  source + drain; connecting them would short the terminals).
- Bulk: p-substrate (ACT outside NW) is globally tied to VSS, NW to VDD
  (std-cell convention: the CDL declares bulk = VDD/VSS and the released
  cells contain no in-cell well taps).  Disable with `-rd no_well_ties=true`
  for analog blocks with isolated wells.
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
compared exactly, W with a 5% relative tolerance (tight MOS width check).
Cell-internal nets are matched by connectivity, not names.  `max_res(1e9)` /
`min_caps(1e-18)` eliminate open resistors / tiny caps.  The compare depth
is unlimited (`max_depth(0)`): the default 500-step backtracking limit fails
on some feedback-latch cells (e.g. SDFFNRX2H7R, DFFRQX0P5H7R) whose
netlists are provably equivalent.

## Known limitations

- MOM capacitors are not extracted (documented above).
- The IO library (P65_1233_*) extracts 213+ devices per cell including
  wide multi-finger transistors (e.g. W=160U ESD devices); comparison against
  the IO CDL needs multi-finger combining and ESD-diode equivalence tuning
  (`--combine-devices` is a start) — in progress.
- Cells with floating well regions need `-rd no_well_ties=true` and manual
  bulk handling.
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
