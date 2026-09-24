# ICsprout55 SPICE models — status

| File | Content | Status |
|---|---|---|
| `ics55.m` | master include | OK for names and structural includes |
| `mos_core.l` | `nm1p2/pm1p2_{svt,lvt,hvt}_lp` | **TBD** (names/pins/geometry real; parameters not released) |
| `fitted/ics55_mos_core.l` | PTM BSIM4 cards fitted to released TT Liberty leakage | **Exploratory only**; not foundry data |
| `fitted/FIT_PARAMS.json` | parameters and dataset metadata used for the fitted cards | audit metadata |
| `mos_io.l` | `nm3p3_lp` / `pm3p3_lp` | **TBD** (names/pins/geometry real) |
| `diode.l` | `dio_1p2*`, `dio_3p3_pp_nw_lp` | **TBD** |
| `resistor.l` | `re_*` family | partial: real sheet-R for metal (LEF) + `re_ppo_sab` (~850 ohm/sq derived); diffusion/well/HRPO TBD |
| `capacitor.l` | `mom_2t/3t` | **TBD** (1 pF placeholder — do not trust) |
| `varactor.l` | `var1p2/var3p3_npd_nw_lp` | **TBD** |
| `corners/` | tt/ff/ss/fs/sf structure | **TBD**; no fitted corner cards are shipped |
| `monte_carlo/` | `ics55_mc.mm` | **TBD**; no statistical data released |
| `aging_noise/` | templates | **TBD**; no foundry reliability/noise data released |
| BJT / inductor | — | **not present** in released PDK data |

The fitted core cards are calibrated only for leakage trends at the exact
Liberty TT point (1.2 V, 25 C) and are useful for first-order exploratory
transistor experiments. Read `fitted/FIT_REPORT.md` before using them: the
independent cell holdout is materially less accurate, C-V and drive are not
matched signoff quantities, and PVT/noise/mismatch/aging are unvalidated.

**Hard rule:** placeholder values marked `TBD` or `[ref …]` are not foundry
data. Only the measured/LEF values (sheet resistances, via R, capacitance
densities, geometry), device names, and pin orders are real. Do not use any
current model file for tapeout or signoff.

## Measured / LEF constants used

- `re_ppo_sab` Rsq approximately 850 ohm/sq nominal (derived from IO pads)
- Metal Rsq (LEF): M1 0.1122, M2–M4 0.0914, T4M2 0.0239, RDL 0.0151 ohm/sq
- Via R (LEF): 2.5 ohm per via (VIA1–4, T4V2, RV)
- Area cap (LEF, pF/um^2): M1 0.763e-3, M2–4 1.107e-3, M5 0.626e-3,
  T4M2 0.130e-3, RDL 0.057e-3; edge cap 28–41 aF/um
- MOS drawn L = 60 nm (core), 400–650 nm (3.3 V IO); VDD 1.2 V / VDDIO 3.3 V

## Usage

Use the fitted cards with Xyce (the complete PTM BSIM4 card is not supported
by the reduced ngspice BSIM4 implementation):

```spice
.include libs.tech/spice/models/fitted/ics55_mos_core.l
```

The fitted file supplies six model names:
`nm1p2_{svt,lvt,hvt}_lp` and `pm1p2_{svt,lvt,hvt}_lp`.
Temperature must be set through the simulator's supported device-temperature
option; the fitting harness uses Xyce `.options device temp = <Celsius>`.

For structural placeholder names, use the master include instead:

```spice
.include libs.tech/spice/models/ics55.m
X1 a b re_ppo_sab_2t W=2u L=30u
```

The files under `corners/`, `monte_carlo/`, and `aging_noise/` are templates,
not calibrated modifiers. Including `corners/ss.mod` or `monte_carlo/ics55_mc.mm`
does not turn the fitted cards into validated SS/FF or statistical models.
