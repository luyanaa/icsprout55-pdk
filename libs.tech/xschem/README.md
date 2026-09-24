# ICsprout55 xschem library (provisional)

## Contents

- `symbols/` — schematic symbols for the analog primitives:
  - `ics55_nmos.sym` — 1.2V core NMOS (nm1p2_svt/lvt/hvt_lp), pins D G S B
  - `ics55_pmos.sym` — 1.2V core PMOS
  - `ics55_mos_3p3.sym` — 3.3V thick-oxide IO MOS (nm3p3_lp/pm3p3_lp)
  - `ics55_res_2t.sym` / `ics55_res_3t.sym` — re_*_2t / re_*_3t
  - `ics55_mom.sym` — MOM cap (mom_2t/mom_3t), pins PLUS MINUS [B]
  - `ics55_varactor.sym` — var1p2/var3p3_npd_nw_lp, pins POS NEG
  - `ics55_diode.sym` — dio_* diodes (AREA/PJ params), pins A K
  - `ics55_guard_ring.sym` — layout-only marker (netlists as a comment)
- `xschemrc` — adds the symbols directory to the xschem library path

## Usage

```
xschem --rcfile /path/to/libs.tech/xschem/xschemrc &
```

(any rc mechanism that sets `XSCHEM_LIBRARY_PATH` to
`.../libs.tech/xschem/symbols` works; the default xschemrc is in
`$XSCHEM` or the current directory.)

## Netlisting behavior

- MOS / diode → SPICE primitive devices (`M1 D G S B nm1p2_svt_lp ...`,
  `D1 A K dio_3p3_pp_nw_lp AREA=... PJ=...`); model cards are in
  `../spice/models/mos_core.l`, `mos_io.l`, `diode.l`.
- Resistors / MOM / varactors → subcircuit calls
  (`XR1 POS NEG re_ppo_sab_2t W=... L=... M=...`); definitions in
  `../spice/models/resistor.l`, `capacitor.l`.
- Terminal order matches the released CDL usage exactly, so netlists stay
  valid when foundry models arrive.
- Instance parameters shown on symbols: `R=expr_eng(850*L/W/M)` is the
  derived re_ppo_sab estimate — replace when foundry data ships.

## Notes

- BJT / inductor: not present in the released PDK data → no symbols.
- Guard rings are layout constructs (see `../klayout/pcells/`); the symbol
  exists for schematic documentation only and does not netlist a device.
