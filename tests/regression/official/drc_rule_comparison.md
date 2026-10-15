# Calibre DRC ↔ KLayout semantic comparison

## Source and frozen profile

- Calibre sources: `pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc` and
  `pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.ant`.
- Frozen released profile: `total_metal=6`, `top_metal=1`, T4V2/T4M2 selected,
  `OPEN_RECOMMENDED_ON=NO`. Active metal rules select M1–M5 and T4M2.
  `Density_rules`, `LATCH_UP_CHECK`, `DUP_CHECK`, `Metal_Slot_CHECK`,
  `MOM_CHECK`, `ESD_CHECK`, and `Poly_EFuse_CHECK` are enabled by source
  `#DEFINE` values; nearby comments for ESD/poly-EFuse are contradictory.
- The main `.drc` uses `DRC MAXIMUM RESULTS ALL`; the separate `.ant` deck has
  different report caps and semantics. The KLayout port does not include an
  antenna module.
- There are 466 unique `RULECHECK` IDs in the source, including conditional
  top-stack variants and recommended rules. This total is not the active-rule
  count for the frozen profile.

## Static crosswalk summary

`drc_rule_comparison.json` is a legacy name/threshold inventory, not a
semantic-equivalence report. The current runner recomputes these values:

| Measure | Value | Meaning |
|---|---:|---|
| Source IDs | 466 | Unique source `RULECHECK` names |
| Legacy mapped rows | 85 | Name/threshold rows labeled `covered` |
| Unmapped rows | 381 | Rows labeled `missing` |
| Stale stored-value rows | 26 | Mapped rows whose stored values differ from the current JSON values |
| Semantic-equivalence passes | 0 | No rule-level equivalence credit is assigned |
| Calibre differential | BLOCKED | No matched Calibre run/report is available |

`covered` means only that a name/value mapping was recorded. It does not imply
equal geometry, qualifiers, exclusions, connectivity, windows, hierarchy, or
marker results.

## Source behavior and KLayout state

| Family | Source behavior | KLayout state |
|---|---|---|
| ACT / POLY / NP / PP / CT | Source-specific area, hole, coverage, width/space, voltage, topology, and marker rules | Direct area/hole checks and CT coverage predicate are emitted with represented waivers. Width/space, directional enclosure, voltage, and connectivity semantics are omitted. |
| M1–M5 / T4M2 | Profile-selected area/hole, width/space, slots, dummy, density, exclusion, and geometry rules | Area/hole predicates use source thresholds and represented SRAMALL/NODRC waivers. Width/space selectors with ABUT/SINGULAR/angle/array semantics are omitted. Density and geometry checks are separate KLayout translations. |
| V1–V4 / T4V2 | Exact cut/bar geometry, directional enclosure, array/neighborhood, edge angle, and source-specific waivers | V1–V4 square checks use the source via layer; top T4V2 rules use interior-cut plus bar geometry. Representable 45-degree and separate lower-metal OUTLAYER checks are emitted. Directional enclosure and array/neighborhood rules are omitted. |
| RV / RDL / COVER / CB | Fixed RV rectangle after fuse/GRID exclusions; qualified spacing/enclosure; direct outside-layer and coverage results | RV_W_1, the separate RV-outside-RDL result, and direct RDL/ALPAD/COVER coverage predicates are represented. Qualified enclosure/spacing rules are omitted. |
| Density | 100×100 µm windows, 50 µm step, backup windows, per-layer dummy construction, global bounds, gradients, and NODRC/INDALL/GRID/SRINGBLK handling | Source-derived window/global checks are translated for ACT, POLY, M1–M5, and T4M2. Dummy regions and represented exclusions are retained. D_3 gradient outputs are omitted because the source omits `STEP` and the exact neighboring-window selection is not established. No cross-tool verification has been run. |
| Dummy / slot | Exact dummy-size masks, overlaps, and qualified layer-specific spacing rules | Active-profile ACT/POLY/M1–M5/T4M2 whitelists and direct dummy/CT and slot/CB overlaps are emitted. Qualified spacing rules are omitted. |
| MOM | MOM_R_1 via/MOM-marker prohibitions; MOM_R_2 text-qualified stack prohibitions and missing-label outputs; MOM_S_1 qualified spacing | MOM_R_1 and active MOM_R_2 clauses are translated. MOM_S_1 is omitted due ABUT<90 SINGULAR REGION semantics. Source Y12–Y78 required-marker bodies are commented out and are not treated as active checks. |
| Special | EFUSE marker Boolean rules, DEUPAD rules, ESD geometry/device rules, and latch-up checks | EFUSE predicates, DEUPAD_R_2/R_5/R_6, and ESD_A_1/A_2 are emitted. DEUPAD_R_3 is omitted because its ENCLOSE marker differs; ESD_W_1/S_1 and device/connectivity/latch-up rules are omitted rather than approximated. |
| Antenna | Separate `.ant` accumulated net-area ratios, diode credit, oxide classes, and process-stage connectivity | Not implemented. No antenna diagnostic or fallback is emitted. |

## Representative source values

| Rule | Source value | KLayout state | Known boundary |
|---|---:|---|---|
| ACT_A_1 | 0.0384 µm² | Same threshold; SRAMALL/NODRC waivers | KLayout execution only; no Calibre differential |
| PO_A_1 / PO_A_2 | 0.04 / 0.09 µm² | Same area/hole thresholds; PO_A_1 SRAMALL/NODRC and PO_A_2 NODRC waivers | Marker/report comparison not run against Calibre |
| NP_A_1 / PP_A_1 | 0.12 µm² each | Source area predicates with represented SRAMALL/NODRC waivers | Other implant rules omitted |
| MET1_A_1 / MET1_A_2 | 0.042 / 0.18 µm² | Same strict area/hole thresholds with source NODRC and MET1 SRAMALL behavior | Other metal qualifiers omitted |
| M2–M5_A_1 / A_2 | 0.052 / 0.18 µm² | Same source area/hole thresholds and NODRC waiver | Other metal rules omitted |
| T4M2_A_1 / A_2 | 0.40 / 0.60 µm² | Same source area/hole thresholds with NODRC waiver | Profile-specific KLayout translation only |
| V1–V4_W_1 | Exact 0.09×0.09 µm rectangle | Exact-square check on source via geometry; GRID/SRINGBLK/NODRC waiver | Vn bar-width rules are separate and omitted |
| RV_W_1 | Exact 3×3 µm rectangle | Source fuse/GRID exclusions retained | Calibre rectangle selector not differentially verified |
| ESD_A_1 / A_2 | 0.6 µm² | ESD polygon/hole area checks with NODRC waiver | ESD width/space qualifiers and devices omitted |

Values and IDs are taken from the supplied source and
`libs.tech/drc/rule_decks/ics55_rules.json`. A matching threshold does not
close semantic gaps.

## Regression and evidence policy

- `drc_fixture_check.py` asserts exact KLayout report-category sets on
  deterministic source-behavior fixtures for FEOL/BEOL/dummy/special, density,
  and MOM profiles. Fixtures include strict/near-threshold density boundaries,
  hole areas, marker waivers, via-bar/orientation behavior, backup windows,
  small-layout padding, dummy halos, MOM labels, and pad/special relationships.
  They verify the KLayout implementation only.
- `run_alignment.py --drc` runs the fixture suite and KLayout DRC on each
  selected GDS/top. It retains KLayout categories and hashes source decks,
  layer maps, profiles, modules, and fixture inputs. The cross-tool field remains
  `BLOCKED`.
- A Calibre differential PASS requires identical GDS hash, top cell, source
  deck/options/profile, report caps, and retained Calibre results. Compare rule
  IDs and marker geometry, not aggregate counts alone.
- No Calibre differential is available. The current status remains `BLOCKED`;
  static review and KLayout fixtures do not establish formal equivalence.
