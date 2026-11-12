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
  different report caps and semantics. Antenna ratios are implemented in a
  separate KLayout deck, `libs.tech/drc/ics55_antenna.drc`, because they require
  netlist extraction.
- The source contains 461 active `RULECHECK` IDs plus 179 active block-style
  rule bodies (CT, implant, well, gate-oxide, silicide-block, resistor,
  voltage-class, dummy, and related families), 640 unique active IDs.
  A further 38 `RULECHECK` stubs are commented out in the source
  (CHIPEDGE_R_3, DNW_R_2, and the T1–T8/Y* MOM-marker macros) and are not
  counted as active rules.

## Static crosswalk summary

`drc_rule_comparison.json` is a legacy name/threshold inventory, not a
semantic-equivalence report. The current runner recomputes these values:

| Measure | Value | Meaning |
|---|---:|---|
| Source IDs | 640 | Unique active source rule names (461 `RULECHECK` + 179 block-style) |
| Crosswalk rows | 717 | Source rules plus 49 conditional/other-profile metal rows plus 28 expanded antenna rows |
| Legacy mapped rows | 481 | Name/threshold rows labeled `covered` |
| Unmapped rows | 236 | Rows labeled `missing` |
| Stale stored-value rows | 0 | Mapped rows whose stored values differ from the current JSON values |
| Semantic-equivalence passes | 0 | No rule-level equivalence credit is assigned |
| Calibre differential | BLOCKED | No matched Calibre run/report is available |

`covered` means only that a name/value mapping was recorded. It does not imply
equal geometry, qualifiers, exclusions, connectivity, windows, hierarchy, or
marker results.

Updated 2026-11-13. The crosswalk now includes the CT, NP/PP, AADUM/PODUM and
T4M2DUM block-style rows, the NW1 and DNW RULECHECK rows, the recent
CB / COVER / CHIPEDGE / ESD / DEUPAD / T4V2 additions, the ESD protection
device rows ESDN_1..ESDN_12 / ESDP_3 / ESDP_9, the seal-ring SRCK rows, the
complete TG/DG, SAB, HRP, ULLD, NVT1/NVT3/PVT1/PVT3, EFU_1b/1c/2b/2c, RDL, RV,
COVER_EN_1 and DGR_3 families, the 28 expanded antenna-ratio rows for the
frozen M=6/T=1/T4M2/T4V2 profile, and the approximation rows for ACT_S_4,
ACT_L_1/L_2, PO_L_1, NP/PP_S_6, NP/PP_EX_1, PP_R_3, DNW_S_3/S_4 and MOM_S_1.
All 640 active source rule IDs now have a crosswalk row. CHIPEDGE_R_3 and
DNW_R_2 are commented out in the supplied source and are not crosswalk rows.
ULLD_EX_3b's 0.12 µm far-poly branch is folded into the tighter EX_3a check and
remains `missing`. This inventory remains a source crosswalk, not a semantic
equivalence report.

| Family | Source behavior | KLayout state |
|---|---|---|
| ACT / POLY / NP / PP / CT | Source area, hole, width/space, coverage and topology rules | Direct area/hole predicates; ACT width/spacing/channel-width and NW/PW spacing plus edge-strip enclosures, 45-degree spacing (ACT_S_3), notch/hole spacing (ACT_S_4), NW_DNW spacing (ACT_S_7) and the thin-AA length checks ACT_L_1/L_2; NP/PP width/spacing, AA-enclosure, butted-AA overlap, butted-pickup gate space (NP_S_6/PP_S_6), the CMACRO gate extension/enclosure pair (NP_EX_1/PP_EX_1) and tap-area checks, plus the PP_R_3 unsilicided-butted-edge marker; POLY min-width, generic spacing, thin-poly contact/length limits (PO_L_1); CT width/bar/enclosure/coverage and CT_R_1/2/3/5. ABUT/SINGULAR, `NOT TOUCH EDGE`, connectivity and directional qualifiers remain omitted or approximated by edge/region selectors. |
| TG / DG / SAB / HRP / ULLD | Thick/thin gate-oxide markers, silicide block, high-resistance poly, ultra-low-leakage device marker | TG/DG_W/S/EN/EX/O on the source 0.47/0.32/0.25/0.47 µm thresholds and drawn-skew DGR_3; SAB_W/S/EX/A/R incl. the PO-interacting 0.44 µm space and ESDIOE GATE waivers; HRP poly-width, end-zone implant exclusion, SAB/CT fixed 0.21 µm and HPR/SAB alignment; ULLD W/S/EX/A/R with the far-poly EX_3b branch folded into the tighter EX_3a. ABUT<90/SINGULAR/OPPOSITE and 0-extent (`> 0`) qualifiers are not reproduced, so zero-distance contacts are flagged where the source allows them. |
| NVT1 / NVT3 / PVT1 / PVT3 | Voltage-class implant width/space, gate and AA spacing/extension, area/hole, and overlap prohibitions | One parameterised block emits W/S_1/S_2/S_3/EX_1/EX_2/A_1/A_2/R_1 for all four classes and S_4 for NVT1/NVT3/PVT3, with the SRAMALL waivers of NVT3/PVT3. R_1 combines the per-family PSUB, opposite-AA, opposite-voltage-class and DG/TG clauses. Gate-spacing and AA-extension selectors are rebuilt from poly edges inside AA. |
| Wells / DNW / NW1 | PW/NW/DNW area, width, spacing, enclosure, overlap and voltage-class rules | NW1_A_1/A_2, NW1_W_1, NW1_S_1 (LVNW0, NW resistor subtracted from markers), NW1_R_1, DNW_W_1/S_1/S_5, DNW_EN_1 (NW enclosure, coincident-edge and DNW-outside-NW coverage clauses), DNW_EN_2, DNW_R_3 and the derived-PW checks DNW_S_3/S_4 are emitted. DNW_S_3 measures the DNW-inside-PW bar to PW; DNW_S_4 adds the DG/TG-intersecting tpw/pw branches at 1.2 µm. NW1_S_2..S_5, DNW_S_2a (net classes), DNW_O_1 and DNW_R_1 remain omitted; DNW_R_2 is commented out in the source. `PW` is derived as the drawn extent outside NW/PSUB. |
| M1–M5 / T4M2 | Profile-selected area/hole, width/space, slots, dummy, density, exclusion and geometry rules | Area/hole, width, max-width, angle width/space, end-of-line and wide-space thresholds are emitted for M1–M5 and T4M2 with represented NODRC/SRAMALL/INDALL waivers; the T4M2 max-width marker keeps its DEUPAD/CB exclusion. Generic spacing does not preserve ABUT/SINGULAR qualifiers; M1_S_1_R and the min-density/max-density derivative rules remain omitted. |
| V1–V4 / T4V2 | Exact cut/bar geometry, spacing, directional enclosure, arrays, edge angle and source-specific waivers | V1–V4 use the ordinary/bar source union, baseline S1 spacing, separate lower/upper coverage, and 0.005um generic upper enclosure. T4V2 adds the exact 0.36um square fixed-width check (datatype-7 bar excluded as the GT4V2 group-dedup equivalent), the 45-degree rotation check, and the array-spacing check rebuilt from the source 0.28um closing / 0.855um opening sequence with a 0.5um in-array threshold. Conditional GOOD/directional rules T4V2_R_1_R/R_4_R remain omitted. |
| RV / RDL / COVER / CB | Fixed RV rectangle after fuse/GRID exclusions; qualified spacing/enclosure; direct outside-layer and coverage results | RV_W_1, the separate RV-outside-RDL result, RV_S_1/S_2, RV_EN_1_2 (T4M2 lower-metal enclosure plus outside markers), RV_EN_3_4, RV_R_1, RDL_W_1/S_1/S_2/S_3 (ALPA coverage and wide-wire spacing), RDL_EN_1/EN_2, and direct ALPA/ALPAD/COVER coverage predicates are represented. COVER_W_1/L_1/S_1 are emitted with SRBLK/SRINGBLK/NODRC waivers (L_1 uses anisotropic erosion for the 40x65 rectangle); COVER_S_2 rebuilds each pad plate from the metal interacting COVER with the source 21.499um opening and checks 2.5um plate spacing; COVER_EN_1 uses the source 1.5/1.498um INDALL split. CB_W_1/S_1/EN_1_EN_2 use the source INDALL threshold shift and an explicit outside-metal marker for the `OUTSIDE ALSO` clause. ABUT/SINGULAR qualifiers and the ALPA `WITH WIDTH` selector are approximated. |
| Density | 100×100 µm windows, 50 µm step, backup windows, per-layer dummy construction, global bounds, gradients, and NODRC/INDALL/GRID/SRINGBLK handling | Source-derived window/global checks are translated for ACT, POLY, M1–M5, and T4M2. Dummy regions and represented exclusions are retained. D_3 gradient outputs are omitted because the source omits `STEP` and the exact neighboring-window selection is not established. No cross-tool verification has been run. |
| Dummy / slot | Exact dummy-size masks, overlaps, and qualified layer-specific spacing rules | Active-profile ACT/POLY/M1–M5/T4M2 whitelists, AADUM/PODUM size-selector spacing and layer-pair spacing (S_1..S_13 / S_1..S_12), T4M2DUM spacing and direct dummy/CT and slot/CB overlaps plus slot spacing/rectangle-length are emitted. Non-abutted/`TOUCH`-qualified selections remain approximated. |
| MOM | MOM_R_1 via/MOM-marker prohibitions; MOM_R_2 text-qualified stack prohibitions and missing-label outputs; MOM_S_1 qualified spacing | MOM_R_1, active MOM_R_2 clauses and MOM_S_1 are translated. MOM_S_1 intersects the via outside MOMLVS1 with the metal/MOM-marker plates in a shielded separation check at 0.11 µm; the source ABUT<90 SINGULAR REGION qualifiers are not reproduced. Source Y12–Y78 required-marker bodies are commented out and are not treated as active checks. |
| Special | EFUSE marker Boolean rules, DEUPAD rules, ESD geometry/device rules, and latch-up checks | EFUSE predicates, DEUPAD_R_2/R_3/R_5/R_6/R_7, ESD_A_1/A_2/W_1/S_1, CHIPEDGE_EN_1/2/3 and the ESD protection-device rules ESDN_1_SEDP_1, ESDN_2_ESDP_2, ESDN_3, ESDN_4_ESDP_4, ESDN_5_ESDP_5, ESDN_6_ESDP_6, ESDN_7_ESDP_7, ESDN_8_ESDP_8, ESDN_9, ESDN_10, ESDN_11, ESDN_12, ESDP_3 and ESDP_9 are emitted. DEUPAD_R_3 checks the CB/COVER pad area against both top metals; R_7 uses the source 0.51um via-array clustering. CHIPEDGE checks run only when CHIPBLK is drawn, derive the design extent from the source drawn-layer list (CHIPBLK/SRINGBLK/SRBLK excluded), and add explicit outside markers for geometry KLayout's `enclosed()` does not report. ESD device classes are built from ESDIOE-scoped ACT/POLY/CT/SAB, with ENMOS/EPMOS recognised by active interacting the gate instead of Calibre ENCLOSE. ESDN_13_R / ESDP_10_R (net-area-ratio finger count) and the latch-up rules remain omitted rather than approximated. |
| Seal ring (SRCK) | DRC1_S seal window, per-metal inner/outer ring selection, bar/square contact and via classes, RDL/RV rings | SRCK_3..SRCK_6 are emitted for M1–M5 and T4M2 seal rings, SRCK_7_RDL..SRCK_10_RV for the RDL/RV rings, and the SRCK_11/13/14/15/16 bar/square width, size, enclosure and bar-to-square space checks for CT, V1–V4 and T4V2. The inner/outer ring split is a hole-containment proxy for the source TOUCH-on-holes selector; a lone ring is treated as the outer ring. ANGLED/ABUT/SINGULAR/OPPOSITE qualifiers, the SRCK_3 45-degree corner companion branch, and the SRCK_16b/16c 0.74 µm pre-filter are not reproduced. T2M1/T2M2/T4M1/T8M1/T8M2 ring variants are outside the frozen profile and remain unmapped. |
| Antenna | Separate `.ant` accumulated net-area ratios, diode credit, oxide classes, and process-stage connectivity | `ics55_antenna.drc` builds one KLayout netter per source stage for the shipped interconnect stack, then emits the 28 frozen-profile ratios per net: PO/GATE area (AR_1), PO side-wall/GATE (AR_2), CT/GATE (AR_3), cumulative metal/GATE (AR_5_10_M1..M5/T4M2), cumulative metal/GATE18 (AR18_5_10_*), single and cumulative via ratios (AR_4_*, AR_6_9_* for V1–V4/T4V2), RDV against GATE1825/GATE (AR_7_11_io/core) and RDL side-wall/GATE (AR_8_12). GATE is `(PO AND AA) INTERACT SD == 2`; diode credit is applied per µm² of SD area only. The source's fixed `!!AREA` diode constants and the 0-extent `> 0` diode threshold are omitted, which can only tighten results. Connectivity is rebuilt per source stage in CONNECT order, so a net that becomes clean only after later-stage connections still reports its earlier-stage violation. |

## Representative source values

| Rule | Source value | KLayout state | Known boundary |
|---|---:|---|---|
| ACT_A_1 | 0.0384 µm² | Same threshold; SRAMALL/NODRC waivers | KLayout execution only; no Calibre differential |
| ACT_W_1 / ACT_S_1 | 0.08 / 0.11 µm | Generic width (Manhattan proxy) and spacing thresholds | ABUT/SINGULAR qualifiers not reproduced |
| ACT_EN_1 / ACT_S_5 | 0.15 µm | Edge-strip NW enclosure of N+ AA and NW-to-N+ spacing in PW | Source NW1RES selector approximated by KLayout non-interaction |
| NW1_W_1 / NW1_S_1 | 0.47 / 0.47 µm | Generic width and LVNW0 spacing; the NW resistor is clipped from the marker polygons | ABUT/SINGULAR qualifiers not reproduced |
| DNW_W_1 / DNW_S_1 | 3.0 / 3.5 µm | Generic width and spacing thresholds | NODRC region waiver only |
| DNW_EN_1 / DNW_EN_2 | 1.0 / 0.55 µm | Edge-strip NW enclosure, coincident-edge clause and DNW-outside-NW coverage; edge-strip DNW enclosure of non-tap N+ AA | Source edge-level NODRC waiver approximated by region markers |
| PO_A_1 / PO_A_2 | 0.04 / 0.09 µm² | Same area/hole thresholds; PO_A_1 SRAMALL/NODRC and PO_A_2 NODRC waivers | Marker/report comparison not run against Calibre |
| NP_A_1 / PP_A_1 | 0.12 µm² each | Source area predicates with represented SRAMALL/NODRC waivers | EN/EX and `NOT TOUCH EDGE` implant rules remain omitted |
| NP_W_1 / NP_S_1 | 0.18 / 0.18 µm | Source width/spacing on the drawn implant layer | Single-point/OPPOSITE qualifiers not reproduced |
| NP_O_1 / PP_O_1 | 0.12 µm | Implant enclosure of AA measured by inside-edge strips | Source `INT` ABUT>0 SINGULAR reporting not reproduced |
| NP_A_3 / PP_A_3 | 0.04 µm² | Tap-area threshold with strict area semantics | `TOUCH` whole-polygon selection approximated by KLayout `interacting` |
| PP_R_1 | 0 | NP/PP overlap prohibition | Direct Boolean, no qualifiers |
| ACT_S_3 / ACT_S_4 | 0.18 / 0.18 µm | 45-degree edge spacing and U-shape notch / O-shape hole checks | EDGE-qualified source selectors approximated by notch_check and hole width |
| ACT_L_1 / ACT_L_2 | 25 / 0.5 µm | Thin-AA (width < 0.15 µm) contact-to-contact/end length and butted source/drain length | Calibre SIZE/STEP/opposite-edge selectors replaced by region coverage and bbox length |
| PO_L_1 | 25 µm | Thin-poly (width < 0.13 µm) contact-to-contact, contact-to-end and gate-contact reach | Coverage approximation with ESDIOE/NODRC region waivers |
| NP_S_6 / PP_S_6 | 0.30 µm | Butted opposite-type pickup to gate spacing | Butted-edge qualifier approximated by active/gate interaction |
| NP_EX_1 / PP_EX_1 | 0.30 / 0.16 µm | Implant extension beyond the gate in the S/D direction and enclosure of AA at the gate | CMACRO EXPAND EDGE bands replaced by inside-edge strips |
| PP_R_3 | 0 | NP/PP coincident gate edge on unsilicided AA/poly | COIN EDGE/INSIDE EDGE selector rebuilt from AA/PO-and-SAB geometry |
| DNW_S_3 / DNW_S_4 | 0.8 / 1.2 µm | DNW-to-derived-PW spacing and the DG/TG tpw/pw branches | Connectivity predicate replaced by DG/TG intersection |
| TG_W_1 / TG_S_1 / TG_S_2 | 0.47 / 0.47 / 0.25 µm | TG/DG generic width and spacing, MOS-AA space | ABUT/SINGULAR qualifiers not reproduced |
| TG_EN_1 / TG_EX_1 / TG_O_1 | 0.25 / 0.47 / 0.47 µm | AA/GATE enclosure, NW/PSUB extension and overlap width | Zero-extension contacts flagged by strict separation |
| SAB_W_1 / S_1 / S_3 | 0.42 / 0.42 / 0.21 µm | SAB width/spacing and SAB-to-AA, plus the PO-interacting 0.44 µm space | ABUT/SINGULAR and the 0.06 µm ESD overlap waiver approximated |
| HRP_W_2 / HRP_R_1 | 2.0 µm / 0.3 µm end zone | High-res poly width and NP/PP exclusion from the resistor middle | Width checked on every interacting poly; SDP coincident-edge exemption omitted |
| ULLD_EX_2 / EX_3a / S_5 | 0.18 / 0.15 / 0.18 µm | ULLD gate extension and AA-side extension along poly length | Poly/AA inside-edge selectors rebuilt from gate edges; far-poly EX_3b folded into EX_3a |
| NVT1_W_1 / S_1 / S_2 | 0.18 / 0.18 / 0.18 µm | Voltage-class width, spacing and gate spacing | SRAMALL and OPPOSITE qualifiers partially represented |
| EFU_1b_G .. EFU_2c_G | marker Booleans | FUSEALL/EFUSEALL/POEFUSEBLK interaction and coverage | Direct Booleans with NODRC waiver |
| RDL_W_1 / S_1 / S_2 / S_3 | 3–35 / 2.0 / 3.0 / 5.0 µm | RDL/ALPA width and wide-wire spacing | `WITH WIDTH` selector approximated by erosion; ABUT qualifiers omitted |
| RV_S_1 / EN_1_2 / EN_3_4 | 3.0 / 1.5 / 1.5 µm | RV spacing, lower-metal enclosure and RDL coverage/enclosure | LOGO/GRID/SRINGBLK/FUTR waivers approximated |
| DGR_3 | 45° ± 0.1 | Drawn ACT/POLY/CT/NP/PP edge angle | Edge-angle filter rebuilt in Ruby; INDDMY waiver |
| MOM_S_1 | 0.11 µm | Via outside MOMLVS1 to metal/MOM-marker plate spacing | ABUT<90 SINGULAR qualifiers not reproduced |
| COVER_EN_1 | 1.5 µm | COVER enclosure by ALPA | INDALL 1.5/1.498 split, ABUT/SINGULAR omitted |
| MET1_A_1 / MET1_A_2 | 0.042 / 0.18 µm² | Same strict area/hole thresholds with source NODRC and MET1 SRAMALL behavior | Other metal qualifiers omitted |
| M2–M5_A_1 / A_2 | 0.052 / 0.18 µm² | Same source area/hole thresholds and NODRC waiver | Other metal rules omitted |
| T4M2_A_1 / A_2 | 0.40 / 0.60 µm² | Same source area/hole thresholds with NODRC waiver | Profile-specific KLayout translation only |
| PO_W_1 / PO_S_1 | 0.06 / 0.12 µm | POLY width and generic spacing thresholds | PO_S_1 INDALL ABUT/SINGULAR qualifiers are not reproduced |
| CT_EN_2a | 0.015 µm active enclosure | CT/CTbar active-enclosure check | Generic enclosure operator does not preserve source ABUT/SINGULAR/OUTSIDE qualifiers |
| M1_S_1 / M2–M5_S_1 | 0.09 / 0.10 µm | Generic baseline spacing thresholds with represented NODRC/INDALL/SRAMALL masks | Source ABUT/SINGULAR and M1 INDALL branch differ |
| V1–V4_S_1 / EN_5 | 0.11 µm / 0.005 µm upper enclosure | Generic spacing, upper coverage, and all-side minimum enclosure | Conditional 0.02um opposite-side branch remains omitted |
| T4V2_S_1 / EN lower / EN upper | 0.34 / 0.01 / 0.02 µm | Generic spacing and lower/upper enclosure thresholds | Directional GOOD and source qualifiers remain omitted |
| T4V2_W_2 | 0.36 µm | Datatype-7 bar-width threshold; strict violation and exact-boundary fixtures | No source waiver |
| V1–V4_W_1 | 0.09×0.09 µm square | Ordinary/bar source-union square check with GRID/SRINGBLK/NODRC exclusions | Bar-width W_2 remains a separate marker-qualified rule |
| RV_W_1 | Exact 3×3 µm rectangle | Source fuse/GRID exclusions retained | Calibre rectangle selector not differentially verified |
| CB_W_1 / CB_S_1 | 3.0 / 5.0 µm | Width and spacing; INDALL branch keeps the source 0.001/0.002 shift | ABUT/SINGULAR qualifiers not reproduced |
| CB_EN_1_EN_2 | 1.5 µm | CB enclosure by T4M2 with an explicit outside-metal marker for `OUTSIDE ALSO` | T2/T8 metals are outside the frozen profile |
| COVER_W_1 / L_1 / S_1 | 40 / 65 / 5 µm | Width, 40x65 rectangle enclosure (anisotropic erosion), and spacing with SRBLK/SRINGBLK/NODRC waivers | ABUT/SINGULAR qualifiers not reproduced |
| COVER_S_2 | 2.5 µm | Metal pad plate rebuilt with the source 21.499 µm opening and checked against the same-metal lines | ABUT>0<90 and INDALL qualifiers not reproduced |
| CHIPEDGE_EN_1/2/3 | 0.37 / 6.0 / 1.5 µm | Design-extent, DNW, and seal-ring-metal enclosure checks, plus explicit outside markers for geometry `enclosed()` skips | ABUT<90/SINGULAR qualifiers not reproduced |
| DEUPAD_R_3 / R_7 | Two solid top metals; 0.51 µm via-array clustering | CB/COVER pad area checked against T4M2 and M5; array detection via the source 0.51 µm space search | Connectivity-derived via counting not reproduced |
| ESD_W_1 / S_1 | 0.47 / 0.47 µm | Generic width and spacing thresholds with NODRC waiver | ABUT/SINGULAR qualifiers not reproduced |
| T4V2_W_1 / S_2 | 0.36 µm square; 0.5 µm in-array | Exact rectangle filter on non-GT4V2 vias; array detection via 0.28/0.855 µm closing/opening sizing | SINGULAR/ABUT qualifiers and source `SIZE` semantics approximated |
| ESD_A_1 / A_2 | 0.6 µm² | ESD area/hole checks plus ESD_W_1/S_1 | Diode/connectivity rules remain omitted |
| ESDN_1_SEDP_1 / ESDN_2_ESDP_2 | 0.15 / 0.15 µm | Source CT enclosure by source active and CT-to-gate space on the ESDIOE device | ABUT<90/SINGULAR qualifiers not reproduced; ENC outside part emitted explicitly |
| ESDN_4_ESDP_4 / ESDN_5_ESDP_5 / ESDN_6_ESDP_6 | 0.05 / 1.29 / 0.21 µm | Drain-SAB overlap of the gate, SAB-hole-to-gate space and SAB-hole enclosure of drain CT, via the source ESAB/ESAB_HO classes | Hole extraction from the SAB polygon; OPPOSITE/qualifier semantics omitted |
| ESDN_7_ESDP_7 / ESDN_8_ESDP_8 | 0.21 / 1.0 µm | Drain-SAB enclosure of non-gate drain active and SAB-hole enclosure by drain active | Gate-coincident edge exemption modelled by growing the gate into the enclosure layer |
| ESDN_9 / ESDN_10 / ESDN_11 | 0.4 / 0.4 µm; overlap | ESD implant to gate space, implant enclosure by drain active, and direct implant/gate-poly overlap | ENMOS_DRAIN recognition approximated by ESDIOE-scoped active |
| ESDN_12 / ESDP_9 | < 30 or > 40 µm | Finger width from gate edges coincident with poly, checked per device type | INSIDE EDGE device filter approximated by edge-in-active selection |
| ESDN_3 / ESDP_3 | ≥ 0.5 µm; 0.4–0.5 µm | HV (TG, non-DG) ESD device gate length from gate/active coincident edges | COIN EDGE/GOOD edge-set selection rebuilt from edge intersections |
| SRCK_3_M..6_M / SRCK_3..6_T4M2 | 2 / 2 / 2 / 4 µm | Outer-ring edge space, inner/outer ring space, outer-ring width and inner-ring width against the DRC1_S window | Ring selection by hole containment; qualified corner/singular branches omitted |
| SRCK_7_RDL / 8_RDL / 9_RV / 10_RV | 4.5 / 5.5 / 6.5 / 3 µm | RDL/RV seal-ring edge space and width thresholds | Ring detection is the single-hole proxy; RV remains waived from RV_W_1 inside GRID |
| SRCK_11a / 13a / 14a / 15a / 16a | 0.09×0.27 µm bar; 0.09 µm square; 0.375 / 0.405 / 0.74 µm | CT seal-ring bar/square width and size, M1 enclosure, bar-to-square spacing | Bar/square classes from bbox thresholds; source ANGLED/SINGULAR qualifiers omitted |
| AR_1 / AR_2 / AR_3 | 250 / 500 (perim × 0.10) / 10 | PO area, PO side-wall and CT area ratios against GATE | Per-stage net ratio; no fixed diode term |
| AR_5_10_M1..M5 / T4M2 | 5000 (+500/µm² SD, +8000/µm² for T4M2) | Cumulative metal-to-GATE ratios with per-net diode credit | Source `ACCUMULATE` stages reproduced by one netter per CONNECT stage; fixed `!!AREA` constants omitted (tighter) |
| AR18_5_10_M1..M5 / T4M2 | 1000 (+500/µm² SD, +8000/µm² for T4M2) | Cumulative metal-to-GATE18 ratios | Same per-stage extraction and constant caveat as AR_5_10 |
| AR_4_VIA1..4 / T4V2; AR_6_9_* | 20 (+150/µm²); 50 (+250/µm²) | Single and cumulative via-to-GATE ratios | Cumulative fixture pairs necessarily co-fire the single-layer rule at the 0.01 µm² test gate |
| AR_7_11_io / core; AR_8_12 | 20 (+90/µm²) / 200 (+90/µm²); 1000 (+8000/µm²) | RDV-to-GATE1825/GATE and RDL side-wall (perimeter × 1.595) to GATE | GATE1825 = GATE AND (DGOX OR TGOX); diode credit applies only to SD-area nets |

Values and IDs are taken from the supplied source and
`libs.tech/drc/rule_decks/ics55_rules.json`. A matching threshold does not
close semantic gaps.

## Regression and evidence policy

- `drc_fixture_check.py` asserts exact KLayout category sets on deterministic
  fixtures. The suite now tests ACT/NP/PP width/spacing/overlap/tap-area, the
  45-degree/notch/hole ACT selectors and the thin-AA/thin-poly length rules,
  butted-pickup gate spacing and CMACRO implant extension, POLY width/spacing,
  CT active enclosure, M1–M5/T4M2 width and wide spacing,
  slot/dummy spacing, ordinary via spacing/upper enclosure, T4V2
  spacing/lower/upper enclosure, exact T4V2 square width and array spacing,
  CB width/space/enclosure, COVER width/length/space, COVER_EN_1 and
  pad-to-line spacing, RV width/space/enclosure/coverage, RDL width and
  wide-wire spacing, TG/DG/SAB/HRP/ULLD/NVT/PVT geometry, EFU marker
  predicates, DGR_3 drawn-skew edges, DNW_S_3/S_4 derived-PW spacing, MOM_S_1
  plate spacing, ESD width/space, DEUPAD top-metal and via-array coverage,
  CHIPEDGE design-extent/DNW/seal-ring enclosure, ESD protection-device
  CT/SAB/implant geometry, finger width and HV gate length under the special
  profile, and seal-ring SRCK ring geometry,
  width, RDL/RV rings and CT/V1–V4/T4V2 bar/square classes at strict violation
  and exact-boundary coordinates, in addition to area/hole, via-bar union,
  density, marker, MOM, and pad cases. These validate KLayout behavior only.
- `run_alignment.py --drc` runs the fixture suite and KLayout DRC on each
  selected GDS/top. It retains KLayout categories and hashes source decks,
  layer maps, profiles, modules, and fixture inputs. The cross-tool field remains
  `BLOCKED`.
- A Calibre differential PASS requires identical GDS hash, top cell, source
  deck/options/profile, report caps, and retained Calibre results. Compare rule
  IDs and marker geometry, not aggregate counts alone.
- No Calibre differential is available. The current status remains `BLOCKED`;
  static review and KLayout fixtures do not establish formal equivalence.
