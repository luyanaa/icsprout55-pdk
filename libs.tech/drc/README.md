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
  [-rd tables=main|feol|beol|dummy_slot|density|mom|special] \
  [-rd run_mode=deep|flat|tiling] \
  [-rd total_metal=6] [-rd top_metal=1] \
  [-rd T4V2_T4M2=true] [-rd recommended=warn|error|off] [-rd IO=1833|1825] [-z]
```

Process-profile switches mirror the vendor deck. The released profile is
`total_metal=6`, `top_metal=1`, `T4V2_T4M2=1`; it enables M1–M5 and T4M2 (with
V1–V4 and T4V2). The other top-metal families — T2M1/T2V1, T2M2/T2V2,
T4M1/T4V1, T8M1/T8V1, T8M2/T8V2 and M6–M8/V5–V7 — are implemented in
`11_thick_metal.drc`, `06_metal.drc`, `07_via.drc`, `dummy_slot.drc` and
`density.drc`, but stay disabled unless their `T*` / `total_metal` /
`top_metal` switches are set. `IO=1825` adds the IO-1825-only channel-length
rules; the released libraries use IO 1833.

Recommended rules (vendor `OPEN_RECOMMENDED_ON=NO`) are evaluated in every run
and reported as KLayout log warnings by default. `-rd recommended=error` turns
them into report categories (used by the `recommended` fixture profile), and
`-rd recommended=off` skips them.

`tables=main` is the default and enables FEOL, BEOL, dummy/slot, density, MOM,
and special rules. `tables=<family>` selects only the named family. Density and
MOM can be disabled in the main profile with `no_density=true` and
`no_mom=true`.

Antenna rules require netlist extraction and live in a separate deck:

```sh
klayout -b -r ics55_antenna.drc -rd input=<layout.gds> \
  [-rd top=<topcell>] [-rd report=<out.lyrdb>]
```

It emits `antenna.<SOURCE_ID>` categories for the 28 frozen-profile antenna
ratios. The source `.ant` deck is a separate signoff run; the KLayout deck is a
source port and has not been matched against a Calibre antenna report.

## Ported and omitted source checks

`tests/regression/official/drc_rule_comparison.json` maps every rule ID in the
supplied Calibre deck to the KLayout category that implements it. All active
rules are evaluated by the released profile except:

- **PSUB_W_3c** is compiled only for the `IO=1825` option; the released
  libraries use IO 1833.
- **PO_S_7 / PO_S_7a_R** select L-shape regions with `AA_LS`, which the
  supplied Calibre deck references but never defines. The rule cannot be
  evaluated as written and is not emitted.

Calibre qualifiers that KLayout cannot reproduce (`ABUT<90`, `SINGULAR` /
`OPPOSITE` / `COIN EDGE` reporting, `NOT CONNECTED` net classes, `NET AREA
RATIO` connectivity, directional `GOOD` branches) are replaced by the
documented stricter form or omitted from an otherwise-emitted rule. Generic
KLayout width/space/separation metrics can therefore report coincident-edge or
same-net markers the source would waive: the port may be slightly tighter,
never looser, for those clauses. Per-rule notes are in `ics55_rules.json` and
the comparison JSON.

- **ACT/NP/PP/PSUB:** area and hole checks, Manhattan width proxy, channel
  width, spacing (including TG, NW-to-N+/P+, pickup and DNW classes), edge
  strip enclosures, 45-degree width/space, max-length rules, NP/PP overlap and
  butted-AA checks, gate-AA enclosure/extension, tap area, and the native-NMOS
  PSUB channel width/length/enclosure rules. The source `ABUT<90`, `SINGULAR
  REGION` and `NOT TOUCH EDGE SDP` selectors are not reproduced, so some
  predicates are evaluated with the stricter generic metric.
- **CT:** fixed-square and datatype-7 bar width, S_1/S_2/S_3 spacing (S_2
  reduces to the general spacing after the cluster selection; S_3 applies the
  different-net threshold to all pairs, tighter), S_4 gate spacing, S_5
  same-AA/TG spacing, AA/POLY/M1 enclosures and coverage, rotation, tap and
  single-contact recommendations. CT_S_6 (edge-layer enclosure with
  `COIN`/`INSIDE EDGE`) has no faithful KLayout primitive and is not emitted;
  the directional/`COIN EDGE` output clauses of EN_3/EN_4a_4b_4c are not
  reproduced, while their directional configurations are evaluated as erosion
  alternatives.
- **POLY:** area/hole, width, spacing, and the PO_S/PO_W/PO_EX/PO_L family:
  thin-poly contact reach, core/DG/TG channel lengths, 45-degree field poly,
  wide spacing, AA spacing, line end, STI/AA extension, endcap, bent poly,
  implant coverage and the large-PO density rule. PO_S_1's separate `ABUT<89`
  clause inside INDALL is omitted. The recommended PO rules are reported as
  log warnings.
- **Wells:** NW1 area, width, S_1–S_5 spacing, floating NW, and DNW width,
  DNW–NW spacing, DNW–PW/DG/TG spacing, DNW–NSD spacing, NW/DNW enclosure and
  floating TPW. Same-net (`CONNECTED`) source statements are evaluated with
  their stricter different-net thresholds because KLayout has no net classes.
- **TG/DG/SAB/HRP/ULLD/voltage implants:** source thresholds with the
  documented approximations (inside-edge strips, long-edge enclosure, SAB
  wide-run erosion, ULLD long-edge predicates). Source `ABUT`/`SINGULAR`/
  `OPPOSITE` qualifiers are not reproduced.
- **Resistors:** the 54 GAAres/GNWresAA/GNWresSTI/GPOLYres rules, measured on
  whole polygons. The AAres_R_3 dog-bone selector is approximated by a
  non-rectangle test and NWresAA_EN_3 by the directly expressible enclosure
  and coverage terms.
- **Latch-up:** LU_R_2, LU_W_1, LU_S_1a–d and LU_S_2_NTAP/PTAP. There is no
  net tracing, so I/O-pad devices are approximated as active under TGOX or
  DGOX; devices connected to a pad net through core gate oxide are not
  identified. LU_S_2 uses the source 5 + 30 = 35 um tap reach as a halo
  intersected with the checked well.
- **BEOL metals:** M1–M8 and T4M2 area/hole/width/max-width/spacing,
  wide-metal spacing classes (erosion approximation), 45-degree width/space,
  line-end/void and dummy-adjacency rules. The source `ABUT`/`SINGULAR` and
  marker-specific qualifiers are not reproduced; M6–M8 are gated by
  `CHECK_M`.
- **Vias:** V1–V7 and T4V2 square/bar width, S_1/S_2/S_3 spacing, 45-degree
  rotation, metal coverage and enclosure, H-bar single-via and array spacing,
  and the recommended redundancy rules. V1–V4 array/`OPPOSITE`/`NOT
  CONNECTED` variants are evaluated as all-pairs spacing (tighter); V5–V7 are
  gated by `CHECK_V`.
- **Pads/RDL/cover/seal ring:** RV/RDL/CB/COVER geometry and relationship
  predicates; SRCK_3–SRCK_16 ring checks with the inner/outer-ring selector
  approximated by hole containment.
- **Thick top metals:** T2M1/T2V1, T2M2/T2V2, T4M1/T4V1, T8M1/T8V1 and
  T8M2/T8V2 width/space/enclosure and dummy rules are implemented but
  disabled in the released profile.
- **Dummy/slot, density, MOM:** source dummy/slot size and spacing rules;
  density window/global checks including the numeric D_3 gradient (the source
  omits `STEP`, so step = window); MOM_R_1, MOM_R_2 (forbidden-stack,
  missing-marker and missing-label clauses) and MOM_S_1.
- **Special:** EFUSE marker Booleans, DEUPAD_R_2/R_3/R_5/R_6/R_7, ESD geometry
  (ESD_A_1/A_2/W_1/S_1), CHIPEDGE_EN_1/2/3, the ESD device rules
  (ESDN_1_SEDP_1 through ESDP_9), and recommended ESDN_13_R/ESDP_10_R with a
  merged-POLY finger-group proxy instead of `NET AREA RATIO` connectivity.
  ESD device classes are ESDIOE-scoped and ENMOS/EPMOS are recognised by
  interaction instead of Calibre `ENCLOSE`.
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

Observed on the released H7 core cells: core-gate POLY is drawn 0.05 um from
CT on AA (CT_S_4 requires 0.055 um; the DRM figure measures the same
gate-side dimension), so CT_S_4 reports contacts on every H7 cell tested
(INVX8H7L, NAND2X1H7L, AND2X1H7L, BUFX2H7L, DFFX1H7L, AOI22X1H7L).
BUFX2H7L also has a CT with 0.01 um M1 enclosure (CT_EN_4a_4b_4c). These are
library drawing results, not deck approximations.

The JSON contains additional provenance for source rules that remain
approximated; a recorded threshold or name match is not evidence of semantic
equivalence.

## Verification and equivalence status

`tests/regression/drc_fixture_check.py` generates 784 deterministic layouts
and checks exact KLayout report-category sets for the main, beol, t4m1,
recommended, density, mom and special profiles, plus the separate antenna deck
(`ant_*` fixtures with the `antenna` profile). Fixtures exercise strict area
boundaries, exact/near-threshold density windows, holes, marker waivers, via
bars/rotation, antenna ratio boundaries and diode credit, backup windows,
small-layout padding, exclusions, dummy geometry, MOM labels, pad
relationships, and source-specific special markers. This is KLayout execution
evidence only.

`tests/regression/official/compare_current.py` checks that every "covered"
crosswalk row still names a category emitted by the deck, and
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
