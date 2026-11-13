# Calibre DRC ↔ KLayout semantic comparison

## Source and frozen profile

- Calibre sources: `pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc` and
  `pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.ant`.
- Frozen released profile: `total_metal=6`, `top_metal=1`, T4V2/T4M2 selected,
  `OPEN_RECOMMENDED_ON=NO`. Active metal rules select M1–M5 and T4M2.
  `Density_rules`, `LATCH_UP_CHECK`, `DUP_CHECK`, `Metal_Slot_CHECK`,
  `MOM_CHECK`, `ESD_CHECK`, and `Poly_EFuse_CHECK` are enabled by source
  `#DEFINE` values; nearby comments for ESD/poly-EFuse are contradictory.
- The vendor `<Choice 2>` stack is implemented with `-rd total_metal=N`,
  `-rd top_metal=N` and the six `T2V1_T2M1`…`T8V2_T8M2` switches. Defaults keep
  the released profile, so the M6–M8, T2/T4M1/T8, V5–V7 and alternate-dummy
  rules are present in the decks but inactive unless a profile is requested.
- Vendor `OPEN_RECOMMENDED_ON=NO` maps to `recommended=warn`: recommended rules
  are evaluated and reported in the KLayout log as warnings, without adding
  report categories. `recommended=error` emits them as report categories and
  `recommended=off` skips them.
- Vendor IO option: the released libraries use IO 1833; `-rd IO=1825` (or
  `-rd io_1825=true`) compiles in the IO-1825-only PSUB_W_3c and PO_W_2c/2e/2f
  rules.
- The main `.drc` uses `DRC MAXIMUM RESULTS ALL`; the separate `.ant` deck has
  different report caps and semantics. Antenna ratios are implemented in a
  separate KLayout deck, `libs.tech/drc/ics55_antenna.drc`, because they require
  netlist extraction.
- The supplied `.drc` exposes 999 unique rule IDs to the static comparator:
  771 `RULECHECK` IDs (including the profile-gated and loop-expanded metal, via,
  dummy, ESD and seal-ring families) plus 228 active block-style rule bodies
  (CT, implant, well, gate-oxide, silicide-block, resistor, voltage-class,
  dummy, and related families). A further 38 `RULECHECK` stubs are commented out
  in the source (CHIPEDGE_R_3, DNW_R_2, and the T1–T8/Y* MOM-marker macros) and
  are not counted as active rules.

## Static crosswalk summary

`drc_rule_comparison.json` is a legacy name/threshold inventory, not a
semantic-equivalence report. The current runner recomputes these values:

| Measure | Value | Meaning |
|---|---:|---|
| Source IDs | 999 | Unique vendor `.drc` rule IDs visible to `compare_current.py` |
| Crosswalk rows | 1045 | 999 source IDs plus 28 expanded antenna rows, 14 Tcl-`for` via rows and 4 seal-ring loop-template rows |
| Mapped rows | 1042 | Rows labeled `covered` |
| Unmapped rows | 3 | `PSUB_W_3c` (compiled only under IO 1825) and `PO_S_7`/`PO_S_7a_R` (vendor references `AA_LS`, never defined) |
| Stale stored-value rows | 0 | Mapped rows whose stored values differ from the current JSON values |
| Semantic-equivalence passes | 0 | No rule-level equivalence credit is assigned |
| Calibre differential | BLOCKED | No matched Calibre run/report is available |

`covered` means the mapped KLayout category or rule literal is emitted by deck
code. `compare_current.py` strips Ruby comments, collects literal `.output`
categories, rule-ID strings and templates, and machine-checks every covered row;
comments and dead code do not count. It does not imply equal geometry,
qualifiers, exclusions, connectivity, windows, hierarchy, or marker results.

Updated 2026-11-13. All 999 vendor rule IDs now have a crosswalk row; 1042 of
1045 rows are `covered`. The three `missing` rows are PSUB_W_3c, which the
supplied source compiles only under `#IFDEF IO 1825` (the released profile is
IO 1833), and PO_S_7/PO_S_7a_R, whose source predicates reference `AA_LS`, a
layer the supplied deck never defines. Every POLY-family `covered` row maps to
its actually emitted `poly.po.*` category (or recommended rule-ID literal), not
to a generic base category. The former invisible gaps are closed, including NW1_S_2..S_5,
DNW_S_2a, DNW_O_1 and DNW_R_1; MET1_S_1_R and M2–M8_S_1_R; the per-profile
D_1_min/D_1_max/D_2/D_3 density rows; T4V2_R_1_R/R_4_R and Vn_R_3/R_4_R;
ESDN_13_R/ESDP_10_R and the latch-up LU_* family; the AA, NW, NW-STI and poly
resistor families; the T2/T4M1/T8 thick-metal, dummy and seal-ring variants;
and ULLD_EX_3b. The crosswalk also includes the CT, NP/PP, AADUM/PODUM and
T4M2DUM block-style rows, the NW1 and DNW RULECHECK rows, the
CB / COVER / CHIPEDGE / ESD / DEUPAD / T4V2 additions, the ESD protection
device rows ESDN_1..ESDN_12 / ESDP_3 / ESDP_9, the seal-ring SRCK rows, the
complete TG/DG, SAB, HRP, ULLD, NVT1/NVT3/PVT1/PVT3, EFU_1b/1c/2b/2c, RDL, RV,
COVER_EN_1 and DGR_3 families, the 28 expanded antenna-ratio rows for the
frozen M=6/T=1/T4M2/T4V2 profile, and the approximation rows for ACT_S_4,
ACT_L_1/L_2, PO_L_1, NP/PP_S_6, NP/PP_EX_1, PP_R_3, DNW_S_3/S_4 and MOM_S_1.
CHIPEDGE_R_3 and DNW_R_2 are commented out in the supplied source and are not
crosswalk rows. This inventory remains a source crosswalk, not a semantic
equivalence report.

| Family | Source behavior | KLayout state |
|---|---|---|
| ACT / POLY / NP / PP / CT | Source area, hole, width/space, coverage and topology rules | Direct area/hole predicates; ACT width/spacing/channel-width and NW/PW spacing plus edge-strip enclosures, 45-degree spacing (ACT_S_3), notch/hole spacing (ACT_S_4), NW_DNW spacing (ACT_S_7) and the thin-AA length checks ACT_L_1/L_2; NP/PP width/spacing, AA-enclosure, butted-AA overlap, butted-pickup gate space (NP_S_6/PP_S_6), the CMACRO gate extension/enclosure pair (NP_EX_1/PP_EX_1) and tap-area checks, plus the PP_R_3 unsilicided-butted-edge marker; POLY min-width, generic spacing, thin-poly contact/length limits (PO_L_1); CT width/bar/enclosure/coverage and CT_R_1/2/3/5, plus CT_S_2 diff-net spacing and CT_R_4. Recommended ACT_R_3/ACT_W_3a_R/ACT_S_1_R/ACT_S_2a_R, CT_S_4_R/CT_EN_2_R/CT_EN_3_R/CT_EN_4a_R_4b_R and the PO_S/EN/EX/L/A recommended rules emit through the recommended helper (log warnings by default). ABUT/SINGULAR, `NOT TOUCH EDGE`, connectivity and directional qualifiers remain omitted or approximated by edge/region selectors. |
| TG / DG / SAB / HRP / ULLD | Thick/thin gate-oxide markers, silicide block, high-resistance poly, ultra-low-leakage device marker | TG/DG_W/S/EN/EX/O on the source 0.47/0.32/0.25/0.47 µm thresholds and drawn-skew DGR_3; SAB_W/S/EX/A/R incl. the PO-interacting 0.44 µm space and ESDIOE GATE waivers; HRP poly-width, end-zone implant exclusion, SAB/CT fixed 0.21 µm and HPR/SAB alignment; ULLD W/S/EX/A/R with the far-poly EX_3b branch approximated from the AA long edges outside a 0.20 µm gate halo. ABUT<90/SINGULAR/OPPOSITE and 0-extent (`> 0`) qualifiers are not reproduced, so zero-distance contacts are flagged where the source allows them. |
| Resistors (AA / NW / NW-STI / POLY) | AARES/NWR/POLYres marker bodies: width, SAB/CT spacing, implant enclosure/extension/coverage, NW/PP/tap interactions, dogbone/rect, silicide-block and resistor-count rules | `resistor.aa.*`, `resistor.nw.*`, `resistor.nw_sti.*` and `resistor.poly.*` emit the width/spacing/marker/enclosure/coverage families with NODRC waivers and the per-family S_1 ESD/HRP/NP/NVT1/PVT1 splits. SAB/CT interaction and implant selectors are rebuilt from the drawn markers; Calibre ENCLOSE/COIN-EDGE qualifiers are approximated by enclosure and edge-strip operators. |
| NVT1 / NVT3 / PVT1 / PVT3 | Voltage-class implant width/space, gate and AA spacing/extension, area/hole, and overlap prohibitions | One parameterised block emits W/S_1/S_2/S_3/EX_1/EX_2/A_1/A_2/R_1 for all four classes and S_4 for NVT1/NVT3/PVT3, with the SRAMALL waivers of NVT3/PVT3. R_1 combines the per-family PSUB, opposite-AA, opposite-voltage-class and DG/TG clauses. Gate-spacing and AA-extension selectors are rebuilt from poly edges inside AA. |
| Wells / DNW / NW1 | PW/NW/DNW area, width, spacing, enclosure, overlap and voltage-class rules | NW1_A_1/A_2, NW1_W_1, NW1_S_1 (LVNW0, NW resistor subtracted from markers), NW1_R_1, DNW_W_1/S_1/S_5, DNW_EN_1 (NW enclosure, coincident-edge and DNW-outside-NW coverage clauses), DNW_EN_2, DNW_R_3 and the derived-PW checks DNW_S_3/S_4 are emitted. DNW_S_3 measures the DNW-inside-PW bar to PW; DNW_S_4 adds the DG/TG-intersecting tpw/pw branches at 1.2 µm. NW1_S_2..S_5 (LV, LV/HV, HV and diff-net spacing), DNW_S_2a (net-class spacing), DNW_O_1 and DNW_R_1 are also emitted. DNW_R_2 is commented out in the source. `PW` is derived as the drawn extent outside NW/PSUB; ABUT/SINGULAR qualifiers are not reproduced. |
| M1–M5 / T4M2 | Profile-selected area/hole, width/space, slots, dummy, density, exclusion and geometry rules | Area/hole, width, max-width, angle width/space, end-of-line and wide-space thresholds are emitted for M1–M5 and T4M2 with represented NODRC/SRAMALL/INDALL waivers; the T4M2 max-width marker keeps its DEUPAD/CB exclusion. Generic spacing does not preserve ABUT/SINGULAR qualifiers. MET1_S_1_R and M2–M8_S_1_R are evaluated as recommended log-warning rules; the per-profile D_1_min/D_1_max/D_2/D_3 density rows are emitted in `density.drc`. |
| Thick metal / off-profile stack | T2M1/T2M2/T4M1/T8M1/T8M2 metal and via families, alternate dummy and density checks | `11_thick_metal.drc` emits `T*_W_1/W_2/W_3/S_1..S_5/R_1..R_4/EN_*`, the `T*DUM_W_1/S_*` families and the T2/T8 seal-ring variants, all gated by the vendor profile switches. The released T4M2 rules share the M1–M5/T4M2 path; T2/T4M1/T8 rules are inactive by default and only smoke-tested. |
| V1–V7 / T4V2 | Exact cut/bar geometry, spacing, directional enclosure, arrays, edge angle and source-specific waivers | V1–V4 use the ordinary/bar source union, baseline S1 spacing, separate lower/upper coverage, and 0.005um generic upper enclosure. T4V2 adds the exact 0.36um square fixed-width check (datatype-7 bar excluded as the GT4V2 group-dedup equivalent), the 45-degree rotation check, and the array-spacing check rebuilt from the source 0.28um closing / 0.855um opening sequence with a 0.5um in-array threshold. V5–V7 emit the same width/bar/spacing/coverage families behind the M6–M8 switches; `via.vN.hbar` implements the Vn_R_3 horizontal-bar check, and the Vn_R_4_R, Vn_2a_R_2b_R and Vn_R_2a_2b recommended rules plus T4V2_R_1_R/R_4_R emit as log warnings by default. Source GOOD/directional qualifiers on the recommended rules remain approximated. |
| RV / RDL / COVER / CB | Fixed RV rectangle after fuse/GRID exclusions; qualified spacing/enclosure; direct outside-layer and coverage results | RV_W_1, the separate RV-outside-RDL result, RV_S_1/S_2, RV_EN_1_2 (T4M2 lower-metal enclosure plus outside markers), RV_EN_3_4, RV_R_1, RDL_W_1/S_1/S_2/S_3 (ALPA coverage and wide-wire spacing), RDL_EN_1/EN_2, and direct ALPA/ALPAD/COVER coverage predicates are represented. COVER_W_1/L_1/S_1 are emitted with SRBLK/SRINGBLK/NODRC waivers (L_1 uses anisotropic erosion for the 40x65 rectangle); COVER_S_2 rebuilds each pad plate from the metal interacting COVER with the source 21.499um opening and checks 2.5um plate spacing; COVER_EN_1 uses the source 1.5/1.498um INDALL split. CB_W_1/S_1/EN_1_EN_2 use the source INDALL threshold shift and an explicit outside-metal marker for the `OUTSIDE ALSO` clause. ABUT/SINGULAR qualifiers and the ALPA `WITH WIDTH` selector are approximated. |
| Density | 100×100 µm windows, 50 µm step, backup windows, per-layer dummy construction, global bounds, gradients, and NODRC/INDALL/GRID/SRINGBLK handling | Source-derived window/global checks are translated for ACT, POLY, M1–M5, and T4M2, and the T2/T4M1/T8 variants emit behind the profile switches. Dummy regions and represented exclusions are retained. D_3 gradient outputs use the source 100 µm gradient window (the source omits `STEP`, so step equals window). No cross-tool verification has been run. |
| Dummy / slot | Exact dummy-size masks, overlaps, and qualified layer-specific spacing rules | Active-profile ACT/POLY/M1–M5/T4M2 whitelists, AADUM/PODUM size-selector spacing and layer-pair spacing (S_1..S_13 / S_1..S_12), T4M2DUM spacing and direct dummy/CT and slot/CB overlaps plus slot spacing/rectangle-length are emitted. The `T2M1DUM`/`T2M2DUM`/`T4M1DUM`/`T8M1DUM`/`T8M2DUM` W/S families and the T* metal dummy spacing pair are emitted behind the profile switches. Non-abutted/`TOUCH`-qualified selections remain approximated. |
| MOM | MOM_R_1 via/MOM-marker prohibitions; MOM_R_2 text-qualified stack prohibitions, missing-marker and missing-label outputs; MOM_S_1 qualified spacing | MOM_R_1, the MOM_R_2 forbidden-stack, missing-marker (source Y12–Y78) and missing-label (source Z12–Z78) clauses, and MOM_S_1 are translated. MOM_S_1 intersects the via outside MOMLVS1 with the metal/MOM-marker plates in a shielded separation check at 0.11 µm; the source ABUT<90 SINGULAR REGION qualifiers are not reproduced. KLayout has no polygon-with-text selection, so a MOMLVS1 label is approximated as MOMLVS1 interacting with its text anchor. |
| Special | EFUSE marker Boolean rules, DEUPAD rules, ESD geometry/device rules, and latch-up checks | EFUSE predicates, DEUPAD_R_2/R_3/R_5/R_6/R_7, ESD_A_1/A_2/W_1/S_1, CHIPEDGE_EN_1/2/3 and the ESD protection-device rules ESDN_1_SEDP_1, ESDN_2_ESDP_2, ESDN_3, ESDN_4_ESDP_4, ESDN_5_ESDP_5, ESDN_6_ESDP_6, ESDN_7_ESDP_7, ESDN_8_ESDP_8, ESDN_9, ESDN_10, ESDN_11, ESDN_12, ESDP_3 and ESDP_9 are emitted. DEUPAD_R_3 checks the CB/COVER pad area against both top metals; R_7 uses the source 0.51um via-array clustering. CHIPEDGE checks run only when CHIPBLK is drawn, derive the design extent from the source drawn-layer list (CHIPBLK/SRINGBLK/SRBLK excluded), and add explicit outside markers for geometry KLayout's `enclosed()` does not report. ESD device classes are built from ESDIOE-scoped ACT/POLY/CT/SAB, with ENMOS/EPMOS recognised by active interacting the gate instead of Calibre ENCLOSE. ESDN_13_R / ESDP_10_R (total channel width per drain connection) use a merged-POLY grouping proxy and emit as recommended warnings. The latch-up rules emit `latchup.guard_ring`, `latchup.guard_width`, `latchup.s1a..s1d` and `latchup.s2_ntap/s2_ptap` with the source LATCHUP/SRINGBLK/NODRC waivers. |
| Seal ring (SRCK) | DRC1_S seal window, per-metal inner/outer ring selection, bar/square contact and via classes, RDL/RV rings | SRCK_3..SRCK_6 are emitted for M1–M5 and T4M2 seal rings, SRCK_7_RDL..SRCK_10_RV for the RDL/RV rings, and the SRCK_11/13/14/15/16 bar/square width, size, enclosure and bar-to-square space checks for CT, V1–V4 and T4V2. The inner/outer ring split is a hole-containment proxy for the source TOUCH-on-holes selector; a lone ring is treated as the outer ring. ANGLED/ABUT/SINGULAR/OPPOSITE qualifiers, the SRCK_3 45-degree corner companion branch, and the SRCK_16b/16c 0.74 µm pre-filter are not reproduced. T2M1/T2M2/T4M1/T8M1/T8M2 ring variants are emitted behind the profile switches and inactive in the released profile. |
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
| NP_A_1 / PP_A_1 | 0.12 µm² each | Source area predicates with represented SRAMALL/NODRC waivers | EN/EX qualifiers and `NOT TOUCH EDGE` implant selectors approximated |
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
| ULLD_EX_2 / EX_3a / S_5 | 0.18 / 0.15 / 0.18 µm | ULLD gate extension and AA-side extension along poly length | Poly/AA inside-edge selectors rebuilt from gate edges; far-poly EX_3b approximated from AA long edges outside a 0.20 µm gate halo |
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
| ESD_A_1 / A_2 | 0.6 µm² | ESD area/hole checks plus ESD_W_1/S_1 | Diode-connectivity rules beyond ESDN_13_R/ESDP_10_R remain omitted |
| ESDN_1_SEDP_1 / ESDN_2_ESDP_2 | 0.15 / 0.15 µm | Source CT enclosure by source active and CT-to-gate space on the ESDIOE device | ABUT<90/SINGULAR qualifiers not reproduced; ENC outside part emitted explicitly |
| ESDN_4_ESDP_4 / ESDN_5_ESDP_5 / ESDN_6_ESDP_6 | 0.05 / 1.29 / 0.21 µm | Drain-SAB overlap of the gate, SAB-hole-to-gate space and SAB-hole enclosure of drain CT, via the source ESAB/ESAB_HO classes | Hole extraction from the SAB polygon; OPPOSITE/qualifier semantics omitted |
| ESDN_7_ESDP_7 / ESDN_8_ESDP_8 | 0.21 / 1.0 µm | Drain-SAB enclosure of non-gate drain active and SAB-hole enclosure by drain active | Gate-coincident edge exemption modelled by growing the gate into the enclosure layer |
| ESDN_9 / ESDN_10 / ESDN_11 | 0.4 / 0.4 µm; overlap | ESD implant to gate space, implant enclosure by drain active, and direct implant/gate-poly overlap | ENMOS_DRAIN recognition approximated by ESDIOE-scoped active |
| ESDN_12 / ESDP_9 | < 30 or > 40 µm | Finger width from gate edges coincident with poly, checked per device type | INSIDE EDGE device filter approximated by edge-in-active selection |
| ESDN_13_R / ESDP_10_R | 30–40 µm channel-width window | Total channel width per ESD drain connection via a merged-POLY grouping proxy | Recommended log warning by default; grouping can merge adjacent fingers |
| LU_W_1 / LU_S_1a..d / LU_S_2 | 0.12 µm guard width; 2.0–5.0 µm N/PMOS spaces | latchup.guard_ring / guard_width / s1a..s1d / s2_ntap / s2_ptap | LATCHUP/SRINGBLK/NODRC waivers; source connectivity not rebuilt |
| ACT_R_3 / ACT_W_3a_R / ACT_S_1_R / MET1_S_1_R | Recommended predicates | recommended_output log warnings (default `warn`) | Vendor default is silent; `recommended=error` re-enables report categories |
| Resistor widths / SAB-CT | 0.4 (AA, POLY), 1.8 (NW, NW-STI), 0.21–0.28 µm | resistor.aa/nw/nw_sti/poly width and SAB-CT spacing | Marker-based selectors; Calibre ENCLOSE/COIN-EDGE operators approximated |
| T4M2DUM / T*DUM | 0.6×1.2 µm dummy; 0.4/0.6/0.8 µm spaces | T4M2DUM and T2/T4M1/T8 dummy W/S families | Off-profile T* families inactive by default |
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
  density, marker, MOM, and pad cases. Batch 10 adds AA-resistor width,
  latch-up guard width, the V1 H-bar via rule, a T4M1 width fixture under the
  off-profile switch, and an `ACT_S_1_R` fixture in `recommended=error` mode.
  Recommended rules are exercised in the default `warn` mode; the `off` mode
  and the six profile switch combinations are smoke-tested, not
  fixture-scored. These validate KLayout behavior only.
- `compare_current.py` machine-checks the crosswalk: every `covered` mapping
  must still be emitted by deck code and every vendor ID must have a row, so a
  commented-out or deleted rule cannot stay nominally covered. The released
  profile stays the default; the off-profile metal/via/dummy/density/seal-ring
  rules are emitted in code but evaluate only when their vendor switch is set.
- `run_alignment.py --drc` runs the fixture suite and KLayout DRC on each
  selected GDS/top. It retains KLayout categories and hashes source decks,
  layer maps, profiles, modules, and fixture inputs. The cross-tool field remains
  `BLOCKED`.
- A Calibre differential PASS requires identical GDS hash, top cell, source
  deck/options/profile, report caps, and retained Calibre results. Compare rule
  IDs and marker geometry, not aggregate counts alone.
- No Calibre differential is available. The current status remains `BLOCKED`;
  static review and KLayout fixtures do not establish formal equivalence.
