# Rule-to-rule comparison: official Calibre DRC vs KLayout port

Generated 2026-09-25. Source of truth: `pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc`
(545 RULECHECK tokens, 466 unique IDs). KLayout side: `libs.tech/drc/` (163 checks).
Method: family-level crosswalk + value extraction from the official `@` comments
vs `ics55_rules.json`. The official deck is an 8-metal-capable deck
(T2/T4/T8 top-metal options); the KLayout port targets the released 6-metal
profile (TOTALMETAL=6, top_metal=1).

## 1. Coverage matrix

| Official family | # rules | KLayout port | Notes |
|---|---|---|---|
| ACT (AA width/space/area) | 31 | `active.act.*` width/space/area | EN (well enclosure), L (max AA length), R (AA-implant rules), D (density) NOT ported |
| PO (poly) | 45 | `poly.poly.*` width/space/area, gate overhang | PO_EX_2 ported EXACT; PO_EX_1, PO_EN, PO_L, PO_D NOT ported |
| NW1 (N-well) | 9 | `well.nw.*` width/space | values MISMATCH official (see below) |
| MET1 (M1) | 15 | `metal.m1.*` width/space/area | wide-metal cap 12um NOT ported (20um placeholder) |
| M2..M5 / T2M1 / T4M1 / T8M1 | ~70 | `metal.m2..tm2.*` width/space/area | measured values; density/dummy variants NOT ported |
| Vias (V1-V4 / TV2) | T2Vn/T4Vn/T8Vn (11/9/7 each) | `via.v1..tv2.*` width/space/enc/area | official via rules are parameterized by the metal-count option; the port covers the 6-metal-profile subset. Via-bar rules (SRCK_11d: TVn bar width 0.36, enc 0.375/0.5) and redundant-via rules (T2V1_R_*) NOT ported |
| CT (contacts) | inside ESDN/ESDP + SRCK | `cont.ct.*` width/space/enc/area | official CT rules are the ESD source/drain extension & space rules (ESDN_1_SEDP_1: ACT ext of CT on SOURCE >= 0.15, ESDN_2_ESDP_2: CT-to-poly space >= 0.15, ESDN_6_ESDP_6: SAB-to-CT-on-Drain >= 0.21) and the seal-ring bar rules; the port's ct.* are generic checks without direct official IDs |
| MOM | 3 | `mom.m2.*` width/space | space 0.11 official vs 0.1 ported (measured) |
| TGOX / DGOX / SAB / IOACT | (inside ACT/PO) | `well.tgox.*`, `well.dgox.*`, `impl.sab.*`, `active.ioact.*` | derived IOACT = ACT & TGOX |
| DNW | 11 | — | NOT implemented (logged in README, deferred) |
| PSUB | 16 | — | NOT implemented (logged, deferred) |
| ESD / ESDN / ESDP | 22 | `impl.esd.space` (1 check) | mostly NOT implemented |
| LU (latch-up) | 12 | — | NOT implemented (logged, deferred) |
| SRCK (seal ring) | 50 | — | NOT implemented (seal-ring geometry, RDL/RV clearances, ring widths) |
| CB / COVER / DEUPAD | 12 | `pad.alpad/rdl/cover.*` (partial) | DEUPAD NOT ported; CB checks NOT ported |
| CHIPEDGE / SL (seal) | 6 | — | NOT implemented |
| AADUM / PODUM / T*DUM (dummy fill) | 189 | — | NOT implemented (fill generation is a Phase-4 item) |
| `_R` recommended rules | ~40 | — | design-for-yield; NOT implemented by design |

## 2. Value-level comparison (directly ported rules)

| Official rule | Official value | KLayout value | Status |
|---|---|---|---|
| ACT_W_1 (AA width) | >= 0.08 um | 0.081 | match |
| ACT_S_1 (AA space) | >= 0.11 um | 0.101 | **looser by 8%** |
| ACT_A_1 (AA area) | >= 0.0384 um2 | 0.0555 | tighter by 31% (conservative) |
| PO_W_1 (poly width) | >= 0.06 um | 0.06 | match |
| PO_S_1 (poly space) | >= 0.12 um | 0.11 | **looser by 8%** |
| PO_A_1 (poly area) | >= 0.04 um2 | 0.0388 | match |
| PO_EX_2 (gate overhang) | >= 0.14 um | 0.14 | **exact** |
| NW1_W_1 (N-well width) | >= 0.47 um | 0.47 | corrected 2026-09-25 (was 0.361) |
| NW1_S_1 (N-well space) | >= 0.47 um | 0.47 | corrected 2026-09-25 (was 0.4) |
| ESD_S_1 (ESD space) | >= 0.47 um | 0.47 | corrected 2026-09-25 (was 0.4) |
| MOM_S_1 (MOM space) | >= 0.11 um | 0.1 | NOT a pairing: the official rule is the MOM-metal-to-via space, not the M2 spacing; m2_space stays LEF 0.1 |
| MET1_W_1 (M1 wide cap) | <= 12.0 um | 20 (placeholder) | not ported |
| PO_D_1 (poly density) | 14% .. 40% | 12% .. 55% | user-specified window |
| ACT_D_4 (AA density) | <= 75% (window) | 20% .. 65% | user-specified window |

Per-voltage channel lengths (PO_W_2a..2f: 0.06/0.20/0.28/0.38/0.40 um for
0.9/1.2/1.8/2.5/3.3V) exist in the official deck; the port uses a single
`poly_width` 0.06 and does not distinguish IO/LDMOS channel lengths.

## 3. Caution items

1. Five loose values were corrected to the official numbers on 2026-09-25:
   NW1_W_1/NW1_S_1/ESD_S_1 0.47, ACT_S_1 0.11, PO_S_1 0.12 (also nw_act_enc ->
   ACT_EN_1 0.15, which was 1nm tighter than the official and flagged every
   cell's exactly-0.15 enclosure).  MOM_S_1 was a false pairing (metal-to-via
   rule).  Provenance in `ics55_rules.json` now says `official` with the rule
   IDs.
2. `ACT_A_1` (0.0555 vs official 0.0384) is conservative, not wrong.
3. Wide-metal cap: official 12 um vs 20 um placeholder - not ported.
4. Density windows are user-specified, not official (14-40% poly, <=75% AA
   window per the official deck).
5. Seal-ring (SRCK), latch-up (LU), DNW, PSUB, dummy-fill (DUM), ESDN/ESDP,
   DEUPAD, CHIPEDGE, SL families have NO ported counterpart.
6. ABUT<90 qualifier difference (verified on SDFFNRX2H7R): the official
   INT/EXT ... ABUT<90 SINGULAR REGION waives 90-degree notch and colocated
   edge pairs; the KLayout plain width/space/sep flag them (well-tap notch
   0.36um well width, poly-strap ACT extension 0.065).  KLayout's angle_limit
   goes the wrong direction (more flags), so no clean replication in 0.30.9 -
   documented in the DRC README; the ported checks are stricter than the
   official in these configurations.
7. CT-to-M1 enclosure: the LEF-derived cont.ct.enc.m1 (0.04) flags every std
   cell (cells draw 0.025); the official deck has no such rule.  Kept as the
   LEF router constraint; documented.

## 4. Artifacts

- Machine-readable per-rule records: `drc_rule_comparison.json` (name-matched,
  raw; use this table for semantics).
- Official RULECHECK IDs: `drc_rule_ids.json` (466 unique).
- Layer crosswalk: `layer_crosswalk.json`.
