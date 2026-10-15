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
`tables=advanced`. There is no antenna module or antenna switch.

## Ported and omitted source checks

The modules intentionally emit only predicates whose source geometry and
waivers can be represented. Unsupported Calibre qualifiers, connectivity, and
marker construction are omitted rather than replaced with generic width,
spacing, or enclosure checks.

- **FEOL:** direct area/hole checks for ACT, POLY, NP, and PP; CT coverage by M1
  and ACT-or-POLY. Width, spacing, directional enclosure, voltage/net classes,
  and other Calibre-specific checks are omitted.
- **BEOL metals:** source area and enclosed-hole checks for M1–M5 and T4M2,
  including source SRAMALL/NODRC waivers where applicable. Metal width/spacing
  checks with ABUT, SINGULAR, angle, array, or marker qualifiers are omitted.
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
- **Special:** source EFUSE marker Booleans; DEUPAD_R_2, R_5, and R_6; ESD_A_1
  and ESD_A_2. DEUPAD_R_3 is omitted because its Calibre ENCLOSE marker cannot
  be reproduced; ESD_W_1 and ESD_S_1 are omitted because their ABUT<90
  SINGULAR REGION qualifiers are not expressible by KLayout's width/space
  primitives. Device/connectivity rules are not approximated.
- **Grid/advanced:** optional LEF-derived manufacturing-grid and derived
  geometry diagnostics. They are not source-equivalence checks.

The JSON contains additional provenance for source rules that remain
unsupported; a recorded threshold or name match is not evidence that a rule is
implemented.

## Verification and equivalence status

`tests/regression/drc_fixture_check.py` generates deterministic layouts and
checks exact KLayout report-category sets for FEOL/BEOL/dummy/special, density,
and MOM profiles. Fixtures exercise strict area boundaries, exact/near-threshold
density windows, holes, marker waivers, via bars/rotation, backup windows,
small-layout padding, exclusions, dummy geometry, MOM labels, pad relationships,
and source-specific special markers.
This is KLayout execution evidence only.

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
