# ICsprout55 KLayout DRC

The DRC deck is a source-driven, partial translation of the supplied Calibre
`.drc` file for the released process profile. It is not foundry signoff and is
not formally Calibre-equivalent. Calibre license availability is not a
prerequisite for using this deck, but no Calibre differential can be claimed
without retained Calibre and KLayout reports for the same GDS, top cell, and
profile.

Rule values and provenance are recorded in `rule_decks/ics55_rules.json`:

- `official`: threshold/pattern transcribed from the Calibre source; this does
  not by itself preserve the source's qualifiers or reporting semantics.
- `lef`: routing constraint from the technology LEF, not automatically a DRC
  rule.
- `gds`: measurement from released library geometry, not foundry rule data.
- `derived`: a non-source diagnostic or placeholder; not foundry rule data.

## Active profile and run switches

The source profile is frozen at `total_metal=6`, `top_metal=1`, with T4V2/T4M2
selected and `OPEN_RECOMMENDED_ON=NO`. It selects M1–M5 and T4M2 for active
metal rules. The source/manual layer-map difference is retained deliberately:
Calibre maps SRINGBLK to 354/13 and derives GRID from GRBLK OR SRINGBLK;
the manual stream map lists SRINGBLK 354/12 and GRID 179/40. Source-derived
checks use the `_SRC` aliases, not the manual aliases.

```sh
klayout -b -r ics55_drc.drc -rd input=<layout.gds> \
  [-rd top=<topcell>] [-rd report=<out.lyrdb>] \
  [-rd no_feol=true] [-rd no_beol=true] \
  [-rd no_density=true] [-rd no_mom=true] \
  [-rd tables=main|feol|beol|dummy_slot|density|mom|special|grid|advanced] \
  [-rd check_grid=true] [-rd advanced=true] [-rd run_mode=deep|flat|tiling] [-z]
```

`tables=main` is the default and enables FEOL, BEOL, dummy/slot, density, MOM,
and special rules. `tables=<family>` selects only the named family. Density and
MOM can be disabled in the main profile with `no_density=true` and
`no_mom=true`. Manufacturing-grid and empirical advanced diagnostics are
opt-in with `check_grid=true` or `tables=grid`, and `advanced=true` or
`tables=advanced`.

Antenna rules require netlist extraction and live in a separate deck:

```sh
klayout -b -r ics55_antenna.drc -rd input=<layout.gds> \
  [-rd top=<topcell>] [-rd report=<out.lyrdb>]
```

It emits `antenna.<SOURCE_ID>` categories for the 28 frozen-profile antenna
ratios. The source `.ant` deck is a separate signoff run; the KLayout deck is a
source port and has not been matched against a Calibre antenna report.

## Ported and omitted source checks

The modules intentionally emit only predicates whose source geometry and
waivers can be represented. Unsupported Calibre qualifiers, connectivity, and
marker construction are omitted rather than replaced with generic width,
spacing, or enclosure checks.

- **FEOL:** direct area/hole checks for ACT, POLY, NP, and PP. ACT adds
  ACT_W_1 width (Manhattan proxy via `angle_limit(45)`), ACT_W_3a/3b channel
  width, ACT_S_1/ACT_S_1a spacing, ACT_S_5/S_6 NW-to-N+ spacing, ACT_S_8
  NW-to-P+ pickup spacing, edge-strip ACT_EN_1/2/2a enclosures, and ACT_R_1
  implant coverage. NP/PP add NP_W_1/PP_W_1 width, NP_S_1/PP_S_1 spacing,
  NP_O_1/PP_O_1 implant enclosure of AA (the source `INT` measured from the AA
  edges inside the implant), NP_S_4/PP_S_4 butted-AA overlap, PP_R_1 NP/PP
  overlap, and NP_A_3/PP_A_3 tap area. The source ABUT<90, SINGULAR REGION, and
  OPPOSITE edge qualifiers are not reproduced, so width/spacing checks use the
  generic KLayout metric. Omitted ACT checks: ACT_W_2, ACT_S_2/3/4/7, ACT_L_1/2,
  ACT_R_3. Omitted NP/PP checks: NP_S_2/3/5/6, PP_S_2/3/5/6, NP_EN_1..3,
  PP_EN_1..3, NP_EX_1/1a, PP_EX_1/1a (CMACRO), and PP_R_3 (COIN EDGE).
  CT/CTbar implements the fixed-square and bar-width checks (CT_W_1, CT_W_2,
  including the source GRID/SRAMALL/EFUSEALL/RCT waivers), CT_S_1 spacing,
  CT_S_3/4/5 poly-to-contact spacing, AA/POLY/M1 coverage (CT_EN_1, EN_2b, EN_3c,
  EN_4a/4b/4c), and CT_R_1/2/3/5. The source `RECTANGLE ENC ... GOOD` clauses
  are OR-alternatives and are evaluated by eroding the enclosing layer:
  CT_EN_2b adds a 0.03 um opposite-pair requirement to the CT_EN_2a 0.015 um
  minimum; CT_EN_3 accepts (0.01 um all sides + 0.04 um on one opposite pair)
  or 0.025 um on all sides; CT_EN_4 accepts 0.04 um on one opposite pair or
  0.025 um on all sides, applied to CTs strictly inside M1 (the source
  `(CT NOT TOUCH M1)` domain). CT_S_1a (SIZE OVERUNDER neighborhood), CT_S_2
  (NOT CONNECTED), CT_S_6 (edge-layer enclosure), the remaining directional
  output/COIN EDGE clauses, and CT_EN_4d (WITH WIDTH selector) are omitted.
  Wells implement NW1_A_1/A_2, NW1_W_1, NW1_S_1 (low-voltage LVNW0 spacing,
  with the NW resistor subtracted from the markers), and NW1_R_1 (floating NW
  via NTAP enclosing CT), plus DNW_W_1, DNW_S_1, DNW_S_5 (DNW to N+ SD),
  DNW_EN_1 (NW enclosure of DNW plus the coincident-edge and DNW-outside-NW
  coverage clauses), DNW_EN_2 (DNW enclosure of non-tap N+ AA), and DNW_R_3
  (floating TPW). The
  source ABUT<90/SINGULAR qualifiers are not reproduced, and the derived PW is
  the drawn extent outside NW/PSUB. Omitted well checks: NW1_S_2..S_5 (net
  classes), DNW_S_2a/S_4 (connectivity), DNW_S_3 (whole-polygon PW-inside-DNW
  island construction), DNW_O_1 (INT margin semantics), and DNW_R_1
  (recommended edge output narrowed by DNW_EN_1 and the coverage clause).
  Remaining FEOL checks (voltage/net classes, well resistors, and other
  Calibre-specific constructs) are not yet implemented.

  Observed on the released H7 core cells: core-gate POLY is drawn 0.05 um from
  CT on AA (CT_S_4 requires 0.055 um; the DRM figure measures the same
  gate-side dimension), so CT_S_4 reports contacts on every H7 cell tested
  (INVX8H7L, NAND2X1H7L, AND2X1H7L, BUFX2H7L, DFFX1H7L, AOI22X1H7L).
  BUFX2H7L also has a CT with 0.01 um M1 enclosure (CT_EN_4a_4b_4c). These are
  library drawing results, not deck approximations.
- **BEOL metals:** source area and enclosed-hole checks for M1–M5 and T4M2,
  including source SRAMALL/NODRC waivers where applicable. Baseline M1–M5
  spacing uses generic KLayout space checks. Metal width checks with ABUT,
  SINGULAR, angle, array, or marker qualifiers are omitted.
- **BEOL vias and pads:** exact V1–V4 square checks, source 45-degree-edge checks,
  and separate unqualified via-outside-lower-metal clauses; T4V2 uses its
  interior-cut plus bar geometry. RV exact-rectangle, RV-outside-RDL, and direct
  RDL/ALPAD/COVER coverage predicates are present. Directional enclosure and
  array/neighborhood rules are omitted.
- **Dummy/slot:** source-size whitelists for ACT, POLY, M1–M5, and T4M2 dummy
  shapes; dummy/CT overlap and slot/CB overlap checks. Spacing rules with
  Calibre-specific selectors are omitted.
- **Density:** source-derived window/global checks for ACT, POLY, M1–M5, and
  T4M2 under the selected profile, with dummy layers, source-sized dummy
  regions, window backup, and mapped NODRC/GRID/SRINGBLK/INDALL exclusions.
  Gradient D_3 rules are omitted because the source omits `STEP` and the exact
  neighboring-window selection is not established. These are KLayout
  translations, not Calibre-verified results.
- **MOM:** MOM_R_1 via/MOM-marker intersections and the active MOM_R_2 forbidden
  stack assignments / missing-label checks. MOM_S_1 is omitted because its
  ABUT<90 SINGULAR REGION spacing qualifier is not represented. The source's
  complementary required-marker Y12–Y78 bodies are commented out and are not
  emitted.
- **Special:** source EFUSE marker Booleans; DEUPAD_R_2/R_3/R_5/R_6/R_7;
  ESD_A_1/A_2/W_1/S_1; CHIPEDGE_EN_1/2/3; and the ESD protection-device rules
  ESDN_1_SEDP_1, ESDN_2_ESDP_2, ESDN_3, ESDN_4_ESDP_4, ESDN_5_ESDP_5,
  ESDN_6_ESDP_6, ESDN_7_ESDP_7, ESDN_8_ESDP_8, ESDN_9, ESDN_10, ESDN_11,
  ESDN_12, ESDP_3, and ESDP_9. ABUT/SINGULAR/OPPOSITE qualifiers are not
  reproduced; ESD device classes are ESDIOE-scoped and ENMOS/EPMOS are
  recognised by interaction instead of Calibre ENCLOSE. ESDN_13_R/ESDP_10_R
  and the latch-up rules are not approximated.
- **Antenna:** `ics55_antenna.drc` builds one KLayout netter per source stage
  and evaluates the source accumulated net-area ratios in the source's
  incremental CONNECT order (PO/GATE, CT1, M1, V1, M2, …, T4M2, RDV, RDL):
  AR_1/AR_2/AR_3 (PO area, PO side wall, CT area), AR_5_10 and AR18_5_10
  cumulative metal (M1–M5, T4M2), AR_4 and AR_6_9 single/cumulative vias
  (V1–V4, T4V2), AR_7_11_io/core (RDV), and AR_8_12 (RDL side wall).
  `GATE = (PO AND AA) INTERACT SD == 2`, with `GATE18 = GATE AND DGOX` and
  `GATE1825 = GATE AND (DGOX OR TGOX)`. Per-stage extraction matters: a net
  that is clean once later-stage connections merge it can still violate an
  earlier-layer ratio, and the source reports it. Diode credit is applied per
  µm² of SD area to the stage net that carries it; the source's fixed
  `!!AREA` constants and zero-extent diode filter are omitted, which only
  tightens the reported limits.
- **Grid/advanced:** optional LEF-derived manufacturing-grid and derived
  geometry diagnostics. They are not source-equivalence checks.

The JSON contains additional provenance for source rules that remain
unsupported; a recorded threshold or name match is not evidence that a rule is
implemented.

## Verification and equivalence status

`tests/regression/drc_fixture_check.py` generates deterministic layouts and
checks exact KLayout report-category sets for FEOL/BEOL/dummy/special, density,
and MOM profiles, plus the separate antenna deck (`ant_*` fixtures with the
`antenna` profile). Fixtures exercise strict area boundaries, exact/near-threshold
density windows, holes, marker waivers, via bars/rotation, antenna ratio
boundaries and diode credit, backup windows, small-layout padding, exclusions,
dummy geometry, MOM labels, pad relationships, and source-specific special
markers. This is KLayout execution evidence only.

`tests/regression/run_alignment.py --drc` runs the fixture suite and the DRC on
selected GDS/top inputs. It records source/profile/module/layer-map/fixture
hashes. The cross-tool differential remains `BLOCKED` until a matched Calibre
report is available. A valid differential must compare rule IDs and marker
geometry, not aggregate counts alone.

## Hierarchy and cell-exclusion mode

With `-rd cell_exclusion=true -rd top=<topcell>`, the deck subtracts the
interior of each instance bounding box, shrunk by `cell_excl_margin` (default
0.1 µm), from checked input layers. The remaining frame band retains shapes at
cell boundaries but can create artificial fragments. This screening mode
excludes all child instances, not only standard cells; leave it off for
per-cell checks, macro internals, and full-hierarchy signoff-style runs.

## Separate analog review

These design-review items are not implemented by the DRC deck: gate-orientation
uniformity, SA/SB matching with dummy poly, well-proximity matching, tap/guard
ring distance, contact completeness, and deep-N-well isolation. They require
separate layout review or dedicated validated checks.
