# Rule-to-rule comparison: official Calibre LVS vs KLayout port

Updated 2026-09-27. Source of truth:
`pv/LVS/ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs` (277 LAYER MAP entries).
KLayout side: `libs.tech/lvs/ics55.lvs` + `rule_decks/`.

## 1. Device class coverage

Official Calibre `DEVICE` families and derivation rules vs the supported
KLayout extraction classes (`mos_extraction.lvs` and `res_diode_*`):

| Official device/model | KLayout class or selector | Status |
|---|---|---|
| nm1p2_svt/lvt/hvt_lp / pm1p2_svt/lvt/hvt_lp | `NM1P2_*_LP` / `PM1P2_*_LP` | 6 core MOS classes; source marker selectors |
| nm3p3_lp / pm3p3_lp | `NM3P3_LP` / `PM3P3_LP` | 2 TGOX IO MOS classes |
| `re_ppo_sab_2t` | `RE_PPO_SAB_2T` | ported; Calibre `rsh_rppo=10.252 Ω/□` |
| metal resistors (`STNP*`/`STPPU*`) | `RE_M1..M5_{2T,3T}` or `RE_TM1/TM2_{2T,3T}` | ported by selected stack |
| ALPAD/RDL resistors | `RE_ALPA_{2T,3T}` | ported |
| `dio_3p3_pp_nw_lp` | `DIO_3P3_PP_NW_LP` | ported with DIODE 191/12 and TGOX selectors |
| 2.5V, native, overdrive-3.3V MOS | — | not extracted |
| MOM capacitors (DPNP*) | — | not extracted |
| Q BJTs (30 official flavors) | — | not extracted |
| additional diode flavors (including parasitics) | — | not extracted |

The deck currently exposes 8 MOS classes, 1 diode class, and 13 resistor
classes on the M1-M5 stack or 15 on the T4 stack. MOM capacitors, the other MOS
families, BJTs, and additional diode flavors remain unsupported; unknown
structures are not silently assigned to a supported class.

## 2. Compare parameters

| Parameter | Official (Calibre) | KLayout port | Verdict |
|---|---|---|---|
| L compare | PROPERTY ... L L mos_err (10%) | exact (0.0, 0.0) | port stricter |
| W compare | PROPERTY ... W W mos_err (10%) | 10% relative (0.0, 0.10) | aligned to official; 5-10% band warns (audit_w) |
| series/parallel reduction | Calibre `REDUCE PARALLEL/SERIES YES` (MOS, R, D) | KLayout built-in reduction is opt-in (`--combine-devices`) | Not equivalent by default |
| max resistance | (implied) | max_res(1e9) | port explicit |
| min capacitance | (implied) | min_caps(1e-18) | port explicit |
| matcher limits | no Calibre counterpart | max_depth(8), max_branch_complexity(1024) | KLayout-only search budget; the 2RW macro report under a 50-unit branch limit required at least 992 |
| gate recognition | LVS RECOGNIZE GATES NONE | gate = poly & active (per class) | equivalent for the cell libraries |

The W compare now matches the official `mos_err 0.1` (10%); the L compare is
still exact (the official also uses mos_err for the L - the port's exact L is
stricter).  The KLayout deck emits a WARNING for every device in the 5-10%
band (e.g. TBUFX8H7* -8%) while >10% deviations still fail: INVX16H7* +27%,
OAI33X0P5H7* +33%, INVX7H7* +14-15%, NAND3BBX0P7H7* -14% (the latter also
carries the topology waiver).

## 3. Ports and body connectivity

| Rule | Official Calibre | KLayout port | Status |
|---|---|---|---|
| Top-level ports | `PORT DEPTH 0` | Direct top-cell text on selected M1-M5 or T4 conductors and AP layers | Child labels remain nets; disconnected duplicate top labels fail |
| Body ties | Soft substrate/well connections through physical taps | Standard-cell mode globally ties PSUB/NW; `no_well_ties=true` uses CT-qualified taps | Physical-tap mode is intended for macros |
| Primary circuit case | `CASE_SENSITIVITY TRUE`, source/layout/compare case YES | Normalize only a case-equivalent parsed root circuit name | No net, pin, or device label is rewritten |

## 4. Local regression evidence (2026-09-27)

- KLayout LVS fixture suite: 15/15 extraction cases PASS, including core/IO
  MOS selectors, CT-bar handling, resistor terminal separation, DIODE-marker
  selection, both metal stacks, direct top-level ports, and CDL-derived bulk
  aliases. This is extraction self-consistency, not Calibre parity.
- Historical standard-cell sweep (2026-09-25): 2307/2313 cells PASS across
  771 cells × 3 libraries (H7CR/H7CL/H7CH). Six NAND3BBX0P5/X0P7H7* cases
  have the NMOS stack reversed vs CDL (layout VSS-A1N-A2N-C-Y vs CDL
  Y-A1N-A2N-C-VSS); topology mismatch remains documented.
- Historical spot anchors: INVX1, AND2X8, SDFFNRX2, AOI2BB2X2, and ADDFX1
  passed on 2026-09-25; not rerun in this selector audit.

## 5. Open gaps

- 2.5V/native/overdrive MOS, MOM capacitors, BJTs, and additional diode
  flavors are not extracted.
- IO-cell LVS comparison (multi-finger topology plus IO CDL) remains
  unvalidated; see `libs.tech/lvs/README.md`.
- The deck now uses CT/via-bar unions, official TGOX/DGOX selectors, DIODE
  191/12, stack-specific T4/ALPAD/RDL connectivity, and PSUB marker 261/12
  selector exclusions. The local fixtures do not establish equivalence for
  every source rule.
- No same-input Calibre run/report is available. Cross-tool equivalence stays
  `BLOCKED`; this KLayout deck is not foundry signoff.
