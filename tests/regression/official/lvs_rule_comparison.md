# Rule-to-rule comparison: official Calibre LVS vs KLayout port

Updated 2026-11-13. Source of truth:
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
| series/parallel reduction | Calibre `REDUCE PARALLEL/SERIES YES` (MOS, R, D) and `REDUCE SPLIT GATES YES` | KLayout `simplify` plus opt-in `--combine-devices`; physical-parallel rule only | split-gate folds stay unreduced: false mismatches (stricter) |
| max resistance | (implied) | max_res(1e9) | port explicit |
| min capacitance | (implied) | min_caps(1e-18) | port explicit |
| matcher limits | no Calibre counterpart | max_depth(8), max_branch_complexity(1024) | KLayout-only search budget; the 2RW macro report under a 50-unit branch limit required at least 992 |
| gate recognition | LVS RECOGNIZE GATES NONE | gate = poly & active (per class) | equivalent for the cell libraries |

The W compare now matches the official `mos_err 0.1` (10%); the L compare is
still exact (the official also uses mos_err for the L - the port's exact L is
stricter).  The KLayout deck emits a WARNING for every device in the 5-10%
band (e.g. TBUFX8H7* -8%) while >10% deviations still fail: INVX16H7* +27%,
OAI33X0P5H7* +33% NMOS / +47% PMOS, INVX7H7* +14-15%.  NAND3BBX0P7H7* widths
now match the CDL multiset; its mismatch is the NMOS stack order below.

## 3. Ports and body connectivity

| Rule | Official Calibre | KLayout port | Status |
|---|---|---|---|
| Top-level ports | `PORT DEPTH 0` | Direct top-cell text on selected M1-M5 or T4 conductors and AP layers | Child labels remain nets; disconnected duplicate top labels fail |
| Body ties | Soft substrate/well connections through physical taps | Standard-cell mode globally ties PSUB/NW; `no_well_ties=true` uses CT-qualified taps | Physical-tap mode is intended for macros |
| Primary circuit case | `CASE_SENSITIVITY TRUE`, source/layout/compare case YES | Normalize only a case-equivalent parsed root circuit name | No net, pin, or device label is rewritten |

## 4. ERC checks

Official source: `pv/LVS/ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs:9089-9310`
plus the frozen profile options. The KLayout port is
`rule_decks/erc.lvs`; it runs on the pre-reduction netlist after PORT DEPTH 0
pins are created.

`ERC SELECT CHECK` restricts the reported set. The always-selected list has
eight checks; `NWELL_NOT_TO_POWER_CHECK TRUE` and
`PWELL_NOT_TO_GROUND_CHECK TRUE` add two more (gate-floating and
nWell-floating are off). The three bare `ERC PATHCHK` statements are not
named in any SELECT list, so they are not reported by the official profile.

| Official check | KLayout implementation | Status |
|---|---|---|
| `erc_pTap_to_power` | p-tap conductor net name must match power | ported |
| `erc_nTap_to_ground` | n-tap conductor net name must match ground | ported |
| `erc_mp2pg` / `erc_mn2pg` | SVT PMOS/NMOS S/D nets include both power and ground | ported (core classes) |
| `erc_mp2pghvt` / `erc_mn2pghvt` | same for HVT PMOS/NMOS | ported |
| `erc_ptap_outside_dnw_non_ground` | p-tap not in SRINGBLK/DNW must be on ground | ported |
| `erc_pathcheck_bad` | component without power, ground, or labeled net | ported; missing `nw_para_diode_all` exclusion (stricter) |
| `erc_nWell_not_to_power` | nWell (minus BJT/NW1res) with n-tap must be on power | ported; global ties can satisfy by construction |
| `erc_pWell_not_to_ground` | p-tap (minus SRINGBLK) must be on ground | ported; global ties can satisfy by construction |
| bare `ERC PATHCHK` (ground/power/unlabeled) | same graph walk, reported as diagnostics | not selected by the official profile; no verdict effect |
| `erc_gate_floating`, `erc_nWell_floating`, DFM group | — | disabled in the vendor profile; not evaluated |

Power/ground matching follows `LVS POWER NAME "?VDD?" "?POWER?"` and
`LVS GROUND NAME "?VSS?" "?GND?"`; extracted combined rail names are split
on `|`. PATHCHK edges follow MOS source/drain and resistor A/B terminals;
gates, MOS bulk, diode terminals, and capacitors are open, matching the
Calibre path graph.

## 5. Local regression evidence (2026-11-13)

- KLayout LVS fixture suite: 16/16 extraction cases PASS, covering core/IO
  MOS selectors, CT-bar handling, resistor terminal separation, DIODE-marker
  selection, both metal stacks, direct top-level ports, CDL-derived bulk
  aliases, and the strict-flat parent/mode controls; the compare-verdict
  smoke also passes. This is extraction self-consistency, not Calibre parity.
- ERC fixture smoke: 7/7 PASS. A clean inverter, a VDD-VSS NMOS
  (`erc_mn2pg=1`), ground-only/power-only diagnostic chains, an unlabeled
  device (`erc_pathcheck_bad=3` plus diagnostics), and bad p-tap/n-tap
  layouts (`erc_bad_ptap`: three selected checks; `erc_bad_ntap`: two
  selected checks). Every case asserts the exact per-check counts and the
  `checks=10`/`diagnostics=3` summary.
- Released-cell ERC sweep, 59 cells across H7CH/H7CL/H7CR (including
  TIEHI/TIELO/FILLCAP/ANT/FILLER and the INVX1/NAND2X1/DFFX1/OAI33X0P5
  families): `ICS55_ERC=PASS` for every cell; the five nonzero exits are
  the known W-tolerance compare failures (ANT4H7H, INVX16H7L/R,
  OAI33X0P5H7L/R), not ERC.
- Frozen alignment matrix: 9/9 cells (INVX1/X3/X4 x H7H/H7L/H7R) PASS with
  the expected two-device topology, terminals, and W values.
- Full released-cell sweep: 2355 cells (785 tops x 3 libraries), direct
  KLayout with `run_mode=deep`, `threads=1`, `combine_devices=true`:
  - H7CH 746/785 PASS, H7CL 746/785 PASS, H7CR 746/785 PASS; 39 failures
    per library with identical families.
  - 32 split-gate folds (AND2/AND3, AOI211/221/222/22/2BB2,
    NAND2B/NAND4BB, OAI31/OAI32, TBUFX2): the layout draws each series
    transistor as parallel fingers with private midpoint nets; the circuits
    are electrically equivalent, so these are false mismatches.
  - 2 unsupported 1.2V antenna diodes (ANT2, ANT4): device-class gap.
  - 2 NAND3BBX0P5/X0P7 NMOS-stack reversals: foundry data.
  - 3 width >10% cells: INVX7 (+14%), INVX16 (+27%), OAI33X0P5
    (+33% NMOS / +47% PMOS): foundry data.
- The earlier 2307/2313 sweep over 771 tops x 3 (2026-09-25) is superseded
  by the current deck and harness; its spot anchors are historical only.

## 6. Open gaps

- ERC ports the ten selected checks and reports the three unselected PATHCHK
  statements as diagnostics. Remaining differences (all stricter or
  structural): `erc_pathcheck_bad` omits the `nw_para_diode_all` exclusion
  because that device class is unsupported; default global well ties make
  the nWell/pWell checks pass by construction unless `--no-well-ties` is
  used; `erc_gate_floating`, `erc_nWell_floating`, and the DFM ERC group are
  disabled in the vendor profile and are not evaluated. No Calibre ERC
  differential exists, so this is not a signoff result.
- `LVS REDUCE SPLIT GATES YES` is not implemented; 32 released families per
  library report false topology mismatches. This errs on the strict side and
  is not a false pass.
- ANT2/ANT4 antenna diodes reference 1.2V diode flavors that are not
  extracted.
- 2.5V/native/overdrive MOS, MOM capacitors, BJTs, and additional diode
  flavors are not extracted.
- IO-cell LVS comparison (multi-finger topology plus IO CDL) remains
  unvalidated; see `libs.tech/lvs/README.md`.
- The deck uses CT/via-bar unions, official TGOX/DGOX selectors, DIODE
  191/12, stack-specific T4/ALPAD/RDL connectivity, and PSUB marker 261/12
  selector exclusions. The local fixtures do not establish equivalence for
  every source rule.
- No same-input Calibre run/report is available. Cross-tool equivalence stays
  `BLOCKED`; this KLayout deck is not foundry signoff.
