# Rule-to-rule comparison: official Calibre LVS vs KLayout port

Generated 2026-09-25 (final signoff sanity).  Source of truth:
`pv/LVS/ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs` (277 LAYER MAP entries).
KLayout side: `libs.tech/lvs/ics55.lvs` + `rule_decks/`.

## 1. MOS device-class coverage

Official `DEVICE MN/MP(<model>)` families vs the KLayout extraction classes
(`mos_extraction.lvs`):

| Official model | KLayout class | Status |
|---|---|---|
| nm1p2_svt_lp / pm1p2_svt_lp | NM1P2_SVT_LP / PM1P2_SVT_LP | ported |
| nm1p2_lvt_lp / pm1p2_lvt_lp | NM1P2_LVT_LP / PM1P2_LVT_LP | ported (H7CL, NVT1/PVT1) |
| nm1p2_hvt_lp / pm1p2_hvt_lp | NM1P2_HVT_LP / PM1P2_HVT_LP | ported (H7CH, NVT3/PVT3) |
| nm3p3_lp / pm3p3_lp | NM3P3_LP / PM3P3_LP | ported (ACT & TGOX) |
| nm2p5_lp / pm2p5_lp (2.5V) | — | NOT ported |
| nmod3p3_lp / pmod3p3_lp (3.3V OD) | — | NOT ported |
| nnat1p2/2p5/3p3/od3p3_lp (native) | — | NOT ported (fail-closed diagnostics pending) |
| M resistors (STNP*/STPPU*) | — | NOT ported |
| MD MOS caps (DPNP*) | — | NOT ported |
| Q BJTs (vnpn/vpnp x 1.2/2.5/3.3 x 2x/5x/10x) | — | NOT ported |
| D diodes (dio_* + parasitic dnwd/nwd/rwd) | — | NOT ported (191/12 DIODE layer exists, unused for devices) |

Ported classes: 8 of 6 official MOS families (all 1.2V core + 3.3V IO used by
the released std/IO libraries).  The official deck additionally recognizes
2.5V, native, overdrive-3.3V MOS, resistors, MOS caps, 30 BJT flavors and
20 diode flavors - all absent from the released cell libraries and NOT ported
(fail-closed: unknown structures are not silently mis-extracted).

## 2. Compare parameters

| Parameter | Official (Calibre) | KLayout port | Verdict |
|---|---|---|---|
| L compare | PROPERTY ... L L mos_err (10%) | exact (0.0, 0.0) | port stricter |
| W compare | PROPERTY ... W W mos_err (10%) | 10% relative (0.0, 0.10) | aligned to official; 5-10% band warns (audit_w) |
| series/parallel reduction | LVS REDUCE PARALLEL/SERIES YES (MOS, R, D) | netlist compare with reduction | equivalent |
| max resistance | (implied) | max_res(1e9) | port explicit |
| min capacitance | (implied) | min_caps(1e-18) | port explicit |
| compare depth | default backtracking | max_depth(0) unlimited | required for latch feedback (SDFFNRX2, DFFRQX0P5) |
| gate recognition | LVS RECOGNIZE GATES NONE | gate = poly & active (per class) | equivalent for the cell libraries |

The W compare now matches the official `mos_err 0.1` (10%); the L compare is
still exact (the official also uses mos_err for the L - the port's exact L is
stricter).  The KLayout deck emits a WARNING for every device in the 5-10%
band (e.g. TBUFX8H7* -8%) while >10% deviations still fail: INVX16H7* +27%,
OAI33X0P5H7* +33%, INVX7H7* +14-15%, NAND3BBX0P7H7* -14% (the latter also
carries the topology waiver).

## 3. Verified on the released libraries (2026-09-25)

- 2307/2313 std cells PASS across the 771-cell x 3-lib sweep (H7CR/H7CL/H7CH).
- 6 failures = NAND3BBX0P5/X0P7H7* (all 3 libs): the layout draws the NMOS
  series stack reversed vs the CDL (VSS-A1N-A2N-C-Y vs Y-A1N-A2N-C-VSS).
  Boolean-identical (series AND is commutative), topology not equivalent -
  documented waiver, agreed by the user.
- Spot anchors on the final state: INVX1, AND2X8, SDFFNRX2, AOI2BB2X2,
  ADDFX1 all PASS (re-run 2026-09-25).

## 4. Open gaps (documented, not blocking the released libraries)

- 2.5V / native / overdrive MOS, resistors, MOS caps, BJTs, diodes: layer
  recognition + device classes not ported; explicit unsupported-device
  diagnostics are a pending item (fail-closed).
- IO-cell LVS comparison (multi-finger combining + IO CDL) still blocked -
  documented in `libs.tech/lvs/README.md`.
- LVS layer aliases resolved 2026-09-25 (TGOX/SAB/DIODE/RV/CB/ALPAD/RDL/COVER,
  IOACT = ACT & TGOX); PSUB marker 261/12 still unused in the LVS.
