# ICsprout55 BSIM4 model fitting report (provisional)

**Date:** 2026-09-23  
**Toolchain:** Python 3.14, Optuna 5.0, XyceNF 7.10.0  
**Deliverables:** `fitted/ics55_mos_core.l`, `fitted/FIT_PARAMS.json`

## Executive decision

The fitted cards are usable for **first-order TT leakage, RC-aware inverter
timing at the fitted Liberty point, and qualitative analog experiments only**.
They are not foundry models and are not suitable for timing closure, noise,
mismatch, reliability, or PVT-corner claims.

The previous statement that `RMS(log10) ~= 0.11` meant "30% relative error" was
wrong. `10^RMS` is a multiplicative RMS factor in log space, not an arithmetic
mean relative error. On the expanded training split the arithmetic mean
absolute error is 25--32%; on the independent holdout it is 25--47%, depending
on flavor. The worst individual cell is 2.40--3.22x on the independent holdout.

## 1. Source data and objective

The PDK contains no released SPICE device cards. This work starts from the
released standard-cell CDL and Liberty data and uses the 65 nm bulk plus 45 nm
HP/LP PTM cards as source priors.[^ptm] `fit/initial_values.py` interpolates
those cards to a 55 nm prior; positive parameters use geometric interpolation
and signed parameters use linear interpolation. The shipped six leakage
parameters then re-center the threshold, offset, and DIBL priors per flavor.
The complete source/interpolation manifest is `fit/INITIAL_VALUES.json`.

Across the source cards, the manifest inventories 167 NMOS and 169 PMOS scalar
parameters; 35 per device are marked fit candidates and the rest stay frozen
because the released observables do not identify them. This is an evidence
boundary, not a claim that the frozen PTM values are foundry-correct.

The targets are Liberty per-state `leakage_power` values at nominal TT (1.2 V,
25 C), averaged within each cell. The cited compact-model extraction workflow
fits threshold/subthreshold behavior before mobility/output terms and treats
C-V and temperature as separate evidence streams.[^extraction] These sources
provide priors and extraction-order guidance, not ICSprout55 foundry
measurements.
The fitting objective is:

```text
RMS = sqrt(mean(log10(mean(simulated state leakage) /
                         mean(measured state leakage))^2))
```

The simulator is Xyce. Its DC gmin contribution is subtracted analytically for
SVT/LVT. HVT raw Xyce currents are retained because the same correction
over-subtracts several positive HVT leakage states and makes them negative.
The generated deck uses:

```text
.options device temp = <degrees-C>
```

Xyce 7.10 ignored the SPICE `.temp` card in this workflow; leaving only `.temp`
made every historical run operate at the PTM `tnom` of 27 C. That simulator bug
is fixed in `fit/simulate.py` and is part of the verification smoke test.

### Splits

The old `data_main`/`data_val` split is not an independent validation design:
`data_val` shares 8 of its 10 cells with `data_main`, and it contains unstable
sequential/pass-gate cells. The current extraction script creates:

- `data_fit_*`: 17 stable cells from the historical 20-cell sample.
- `data_holdout_*`: 20 disjoint combinational cells used to enlarge the train
  split.
- `data_train37_*`: the 37-cell fit split shipped below.
- `data_holdout2_*`: 20 disjoint combinational cells never used in fitting.
- `data_main_*`, `data_val_*`, `data_all_*`: retained historical comparisons.

`DFFX1`, `MUX2X1`, and `DFFQX1` are excluded from `data_fit`; their static CDL
states contain floating/pass-gate behavior that is not a unique DC leakage
problem for this flattened model.

The leakage fit includes six per flavor/device controls: `vth0`, DIBL scale
(`pdiblc1/2/b`), and `voff` scale. The rendered cards now also carry
provisional per-flavor/device `u0`, `vsat`, and `rdsw` overrides from the
RC-aware inverter timing experiment below. All remaining PTM parameters stay
unchanged unless explicitly listed.

| flavor | vth0n | vth0p | diblN | diblP | voffN | voffP | train RMS | factor `10^RMS` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SVT | 0.8673 | 0.4851 | 0.5042 | 0.6930 | 0.1993 | 1.1690 | 0.1363 | 1.369x |
| LVT | 0.6610 | 0.2876 | 0.0513 | 0.8999 | 0.5561 | 0.2552 | 0.1659 | 1.465x |
| HVT | 1.0360 | 0.8125 | 0.1213 | 0.7407 | 0.7292 | 0.0852 | 0.1252 | 1.334x |

The shipped cards reproduce these numbers in three repeated in-process
checks. The more representative 37-cell fit intentionally gives up some
17-cell in-sample score to improve behavior outside the original small sample.

### Error metrics

| SVT | train37 | 37 | 0.1363 | 1.369x | 28.6% | 19.1% | 2.95x |
| LVT | train37 | 37 | 0.1659 | 1.465x | 32.1% | 25.1% | 2.71x |
| HVT | train37 | 37 | 0.1252 | 1.334x | 25.3% | 17.9% | 2.54x |
| SVT | independent holdout2 | 20 | 0.1621 | 1.453x | 36.5% | 25.4% | 2.80x |
| LVT | independent holdout2 | 20 | 0.2241 | 1.675x | 46.9% | 22.9% | 3.22x |
| HVT | independent holdout2 | 20 | 0.1257 | 1.336x | 24.9% | 16.4% | 2.40x |

Therefore `~1.3x` is a compact log-space spread description, not a promise
that every cell is within 30%. The independent holdout is the relevant
generalization check; it is materially worse than the training score.

## 3. Parameter robustness

The checked-in `finalize_fit.py` provides a legacy, one-at-a-time `+/-5%`
exploration on the 17-cell `data_fit_*` sample. It is not a joint perturbation,
does not use the current 37-cell release split, and is not a release
acceptance criterion. It also does not cover the added leakage or drive
parameters explored below.

The fitted values are empirical PTM substitutions, not process distributions.
No tolerance or model-corner qualification is claimed.

## 4. PVT corner audit

The released Liberty contains non-TT characterization, but no foundry BSIM
corner cards. Applying the TT-fitted cards at each exact Liberty PVT point
shows that a single TT PTM card does not extrapolate to those corners:

| flavor | SS 1.20/-40 | SS 1.08/-40 | SS 1.08/125 | FF 1.32/-40 | FF 1.08/125 | FF 1.32/125 |
|---|---:|---:|---:|---:|---:|---:|
| SVT RMS log10 | 1.160 | 1.169 | 0.739 | 0.285 | 1.840 | 1.836 |
| LVT RMS log10 | 1.786 | 1.763 | 0.122 | 0.895 | 1.647 | 1.704 |
| HVT RMS log10 | 0.561 | 0.458 | 2.465 | 0.116 | 2.768 | 2.379 |

These are factors of roughly 1.3x to more than 500x depending on cell and
flavor. The result is a model-form/process-corner mismatch, not something that
can be repaired honestly by applying the existing placeholder scale factors.
No fitted corner cards are shipped. `models/corners/*.mod` remain structural
TBD templates until process-specific device data exists.

## 5. C-V and drive evidence

### C-V / input capacitance

A 1 kHz small-signal AC check on the stable 17-cell sample compared intrinsic
model input capacitance against Liberty input-pin capacitance. Across 33 input
pins, the model/Liberty ratios were:

| flavor | median ratio | mean ratio | mean absolute relative error |
|---|---:|---:|---:|
| SVT | 0.743 | 0.735 | 26.5% |
| LVT | 0.703 | 0.698 | 30.2% |
| HVT | 0.613 | 0.608 | 39.2% |

For `INVX1`, the earlier floating-output 1 kHz procedure gives 0.729 fF
versus 0.846 fF in Liberty; the controlled output-clamped-high 1 MHz probe
used below gives 0.779 fF under a different bias boundary. Both are below the
Liberty pin value. Liberty pin capacitance includes cell-level wiring/context;
it is not a pure intrinsic MOS `Cgg` measurement. Do not silently change
`toxe` or intrinsic overlap parameters from this comparison alone. A useful
fix requires foundry C-V data or explicit cell parasitic capacitors separated
from the core MOS model.

### Geometry, junction, and LDE audit

`fit/audit_geometry.py` was run against all three released CDL variants and
the rendered cards. The structural result is:

| check | result |
|---|---|
| CDL cells / MOS devices per flavor | 786 / 10,290 |
| explicit instance fields | W, L, and `m` on every MOS |
| `m` / multi-finger fields | `m=1` everywhere; no `NF` |
| omitted instance fields | no `AS`, `AD`, `PS`, `PD`, `SA`, `SB`, `SD`, `XL`, or `LINT` |
| drawn lengths | 60, 120, 180, 240, 380, 1180, 2780, and 5980 nm |
| rendered model geometry | `GEOMOD=1`, `LINT=0`, no model `XL` |
| LDE coefficients | `LPE0`, `LPEB`, `DMCG`, `DMCI`, `DMDG`, `DMCGT`, `DWJ`, `XGW`, and `XGL` are all zero |

Consequently, for every released MOS, the current model evaluates
`L_eff = L_drawn + XL - 2*LINT` as `L_drawn`; there is no hidden instance
length correction to add. Xyce 7.10 rejects `XL`, `LINT`, and `GEO` as instance
fields, so adding them to the CDL would be both unsupported and contrary to
the released netlist. The supported model-level `GEOMOD=1` is active:
temporarily changing it to `GEOMOD=0/2` changed the SVT `INVX1H7R` falling
delay from 100.856 ps to 102.617 ps at the RC-aware probe point.

The absence of `AS/AD/PS/PD` is syntactically consistent with the CDL, but it
is not proof that the physical junction geometry is zero. The representative
`INVX1H7R` GDS has two ACT regions with 0.1584 um² of non-gate diffusion
extension area. Without LVS there is no safe mapping of those regions to
individual CDL source/drain terminals, so no instance values were invented.
A controlled Xyce probe showed that the omitted source/drain-area pair
(`CJS/CJD`) had no measurable effect on this inverter, while the gate-edge
sidewall pair (`CJSWGS/CJSWGD`) did: zeroing that pair changed the same
falling delay from 100.856 ps to 99.091 ps. Zeroing `CJSWS/CJSWD` had no
change. The current cards therefore use Xyce's default omitted-field behavior
and are not a foundry-extracted junction-area model; the missing area mapping
is a known limitation, not a reason to add guessed parameters.

### CAPMOD and overlap-capacitance audit

The rendered cards use `CAPMOD=2`, `CGSO=CGDO=1.1e-10 F/m`, and the remaining
PTM overlap/fringe terms. At 1 MHz with the inverter output clamped high, the
current SVT `INVX1H7R` card gives 0.779 fF at its input versus 0.846 fF in
Liberty. The corresponding model/Liberty ratios for SVT `INVX1/3/4` are
0.921, 0.834, and 0.808. LVT/HVT Liberty input capacitances also differ even
though the CDL W/L are identical across flavors, so the boundary pin values
include cell/context or corner information not represented by one common
intrinsic MOS overlap value.

The sensitivity check does not support calling `CAPMOD` the timing failure:
at the RC-aware SVT `INVX1H7R` point, falling delay was 100.856 ps for
`CAPMOD=2`, 100.960 ps for `CAPMOD=1`, and 100.306 ps for `CAPMOD=0`.
Doubling `CGSO/CGDO` to `2.2e-10 F/m` changed it to 101.910 ps. Increasing
overlap can move the input-capacitance ratio toward one for a selected cell,
but no single value matches `INVX1`, `INVX3`, and `INVX4` simultaneously.
Therefore the current C-V mismatch is real evidence that the PTM overlap
terms are not validated for ICS55, but it is not evidence for a unique core
parameter correction. No `AS/AD/PS/PD` instance parameters were added and no
`CGSO/CGDO` or `CAPMOD` candidate was promoted.

### Cwire pin-capacitance compensation

`fit/cap_compensation.py` measured each selected inverter input with the
current Xyce card at 1 MHz, 0 V input bias, and the output clamped high. The
per-cell residual is:

| flavor | cell | Liberty Cpin (fF) | model AC probe (fF) | `Cdiff` / `Cwire` (fF) | model/Liberty |
|---|---|---:|---:|---:|---:|
| SVT | INVX1 | 0.8460 | 0.7788 | 0.0671 | 0.9207 |
| SVT | INVX3 | 2.0183 | 1.6835 | 0.3348 | 0.8341 |
| SVT | INVX4 | 2.7912 | 2.2544 | 0.5368 | 0.8077 |
| LVT | INVX1 | 0.8971 | 0.7726 | 0.1244 | 0.8613 |
| LVT | INVX3 | 2.1259 | 1.6695 | 0.4564 | 0.7853 |
| LVT | INVX4 | 2.9452 | 2.2356 | 0.7096 | 0.7591 |
| HVT | INVX1 | 1.0338 | 0.7778 | 0.2560 | 0.7524 |
| HVT | INVX3 | 2.4079 | 1.6821 | 0.7258 | 0.6986 |
| HVT | INVX4 | 3.4558 | 2.2526 | 1.2033 | 0.6518 |

The generated wrapper adds `Cwire` from the input pin to `VSS` and uses
`C={Cdiff*(1+alpha*(V(pin)-Vbias))}`. With `alpha=0.10 V^-1`, the compensated
AC ratios were 1.000000 (within the Xyce probe numerical residual) for all
nine rows. The voltage coefficient is deliberately an explicit behavioral
extrapolation: one Liberty Cpin value identifies only the small-signal
capacitance at the probe bias, not a physical voltage-nonlinearity curve.
The wrapper is emitted separately; released CDL and the BSIM4 core remain
unchanged. A width-linear fit is descriptive only; its intercept is negative
for all three flavors, so it must not be extrapolated outside the measured
cell sizes.
The descriptive width fits were:

| flavor | intercept (fF) | slope (fF/µm) | maximum residual (fF) |
|---|---:|---:|---:|
| SVT | -0.1926 | 0.5302 | 0.0135 |
| LVT | -0.1994 | 0.6604 | 0.0178 |
| HVT | -0.2799 | 1.0576 | 0.0731 |


The Cwire wrappers were also inserted into the train37 DC decks for the
selected cells. Leakage RMS was unchanged within numerical noise:
SVT 0.135826, LVT 0.167860, and HVT 0.125445. This is expected for an ideal
capacitor in `.op`, but it verifies that the generated network does not create
a DC leakage path.

### Multi-bias / multi-flavor Cwire wrapper export

The core-model decision is now explicit: keep one baseline BSIM4 C-V/geometry
card per VT flavor and do not add flavor-specific overrides for `DLC`, `DWC`,
`CF`, or `VFBCV`. `cap_compensation.py` enforces this for checked-in
`FIT_PARAMS.json` drive overrides and emits the cell-boundary correction only
in the wrapper layer.

The default export now probes two static working-bias profiles, `0 V` and
`VDD/2 = 0.6 V`, for each requested flavor. Wrapper names encode flavor and
bias, for example `INVX1H7R_CWIRE_SVT_BP0P6_A`. The generated JSON retains
all profiles; its flat `records` view selects one explicit profile with
`--records-bias` for `cell_parasitics.py` compatibility.

For SVT/LVT/HVT and `INVX1/3/4`, the export produced 18 wrapper subcircuits.
Direct Xyce AC checks against the corresponding Liberty pin capacitances gave
a maximum absolute residual of `1.4e-11 fF` across all 18 wrappers. Direct
Xyce `.op` checks against the unwrapped core gave zero current difference at
the printed precision for all 18 profiles. The wrapper therefore absorbs the
working-bias and VT-flavor boundary residual without creating a DC path.

The default `alpha=0` makes each profile a static Cwire. A nonzero `--alpha`
may still be requested, but it is an explicit local behavioral extrapolation
around that profile bias and is not a physical BSIM4 C-V parameter.


### Model-level CJSWGS/CJSWGD and CGSO/CGDO sweep

The temporary model-level sweep used the representative GDS evidence
(`0.1584 um²` non-gate diffusion extension area) but did not assign it to a
source or drain without LVS. The current sidewall values are
`CJSWGS=3e-10 F/m` and `CJSWGD=5e-10 F/m`.

| flavor | `CJSWGS`-only scale 0 / 4 | `CJSWGD` scale 0 / 1 / 4 | shipped timing RMS |
|---|---:|---:|---:|
| SVT | 0.1209 / 0.1209 | 0.1171 / 0.1209 / 0.1358 | 0.1209 |
| LVT | 0.1332 / 0.1332 | 0.1408 / 0.1332 / 0.1186 | 0.1332 |
| HVT | 0.1849 / 0.1849 | 0.1733 / 0.1849 / 0.2204 | 0.1849 |

`CJSWGS` is inert in these inverter timing probes; `CJSWGD` controls the
observed change because the output node is the drain side. Its preferred
direction is contradictory across VT flavors. The train37 leakage RMS stayed
at 0.135826 / 0.167860 / 0.125445 for SVT/LVT/HVT across the tested sidewall
values, so leakage does not select a physical candidate. No sidewall value was
promoted.

`GEOMOD=1` is already explicit in the rendered cards. The overlap sweep gives
the following model/Liberty input-capacitance ratios for `INVX1/3/4`:

| `CGSO=CGDO` (F/m) | SVT | LVT | HVT |
|---:|---|---|---|
| `1.25e-10` | 0.937 / 0.849 / 0.822 | 0.877 / 0.799 / 0.773 | 0.766 / 0.711 / 0.663 |
| `1.30e-10` | 0.942 / 0.854 / 0.827 | 0.882 / 0.804 / 0.777 | 0.770 / 0.715 / 0.667 |
| `1.35e-10` | 0.948 / 0.859 / 0.832 | 0.887 / 0.809 / 0.782 | 0.775 / 0.719 / 0.671 |
| `1.80e-10` | 0.997 / 0.904 / 0.875 | 0.933 / 0.851 / 0.823 | 0.815 / 0.757 / 0.706 |

Thus `1.25e-10`–`1.35e-10 F/m` does not raise SVT `INVX1` to 0.98–1.00
(it reaches only 0.937–0.948), and it leaves the larger cells and HVT much
lower. The `1.80e-10` SVT `INVX1` match is cell-specific and increases the
three-cell timing RMS from 0.1209 to 0.1221. Leakage RMS was unchanged in the
tested overlap sweep. No global `CGSO/CGDO` change was promoted.

### Core size/bias C-V parameter audit

`fit/cv_core_sweep.py` separates simulator support, observable sensitivity,
and promotion. It probes `INVX1/3/4` at 1 MHz with the output clamped high and
all inputs at the selected DC bias. The Liberty number is repeated only as a
boundary reference; it is not interpreted as a measured intrinsic C-V curve.
The available Liberty/CDL evidence does not provide terminal-charge or
small-signal matrix targets that separate intrinsic `Cgg`, `Cgd`, and `Cgs`.
The input-pin capacitance therefore cannot be converted into three independent
targets. `Cwire` compensation can close the cell-boundary input-capacitance
residual, but it does not validate or identify intrinsic `Cgd`/`Cgs`.

The current rendered cards contain the following C-V fields:

| parameter | current card value | temporary Xyce override |
|---|---:|---|
| `DLC`, `DWC`, `CF`, `VFBCV` | omitted | accepted |
| `CGSL`, `CGDL` | `2.653e-10 F/m` | accepted |
| `CGBO` | `2.56e-11 F/m` | accepted |
| `MOIN`, `NOFF`, `VOFFCV` | `15`, `0.9`, `0.02 V` | accepted |

“Accepted” means that Xyce 7.10 parsed the temporary card and produced an AC
probe result; it does not establish process validity. The omitted fields use
Xyce's model defaults in the shipped cards.

The baseline model input capacitance (fF) changes materially with bias:

| flavor / cell | 0.0 V | 0.3 V | 0.6 V | 0.9 V | 1.2 V |
|---|---:|---:|---:|---:|---:|
| SVT `INVX1` | 0.779 | 0.757 | 0.688 | 0.622 | 0.667 |
| SVT `INVX3` | 1.683 | 1.637 | 1.487 | 1.351 | 1.452 |
| SVT `INVX4` | 2.254 | 2.192 | 1.992 | 1.809 | 1.944 |
| LVT `INVX1` | 0.773 | 0.764 | 0.763 | 0.726 | 0.664 |
| LVT `INVX3` | 1.670 | 1.652 | 1.650 | 1.576 | 1.445 |
| LVT `INVX4` | 2.236 | 2.212 | 2.210 | 2.111 | 1.935 |
| HVT `INVX1` | 0.778 | 0.679 | 0.519 | 0.526 | 0.679 |
| HVT `INVX3` | 1.682 | 1.469 | 1.123 | 1.139 | 1.477 |
| HVT `INVX4` | 2.253 | 1.967 | 1.504 | 1.525 | 1.978 |

Across the three selected cell sizes, baseline log-space RMS against the
single Liberty boundary value is:

| flavor | 0.0 V | 0.6 V |
|---|---:|---:|
| SVT | 0.0733 | 0.1253 |
| LVT | 0.0993 | 0.1043 |
| HVT | 0.1572 | 0.3316 |
The same rows expressed as conventional relative RMS error are 15.4%/24.9%
for SVT, 20.3%/21.2% for LVT, and 30.2%/53.3% for HVT at `0.0/0.6 V`.
Even the best tested one-at-a-time LVT `DLC=-20 nm` direction remained
`0.02795` log-RMS at `0.6 V` (above the approximately `0.0212` log-RMS
equivalent of a 5% multiplicative RMS target) and was not promoted.
The full LVT `--validate` sweep confirmed the guardrails for every tested
one-at-a-time candidate. The best C-V direction (`DLC=-20 nm`) gave timing
log-RMS `0.1311` and unchanged train37 leakage log-RMS `0.1679`; no candidate
simultaneously approaches the timing and capacitance thresholds. The manifest
is `/tmp/lvt_cv_core_sweep_validate.json`.

The one-at-a-time geometry/overlap sweep found a direction but not an
identified solution. `DLC=-20 nm` was the best tested 0 V direction for LVT
and HVT and remained beneficial for LVT at 0.6 V; SVT preferred approximately
`DLC=-10 nm` at 0 V and `-20 nm` at 0.6 V. `DWC=-20` to `-40 nm` and
doubling `CGSL`/`CGDL` also raised the probe capacitance, but their preferred
values differed by flavor and bias. `CGBO` had only a marginal effect, while
the tested `CF` range did not resolve HVT's bias dependence. A combined
`DLC=-20 nm`, `DWC=-40 nm` override was non-additive: aggregate C-V RMS was
0.1258 at 0 V and 0.1411 at 0.6 V, versus 0.1153 and 0.2133 for the shipped
cards.

The bias-transition sweep was largely non-identifying in this deck:
`VFBCV` from `-0.2` to `0.4 V` produced no measurable change in the probe,
`MOIN` and `NOFF` moved RMS only slightly, and `VOFFCV` changed the result
without a unique target. These parameters must not be selected from the
Liberty boundary number.

Temporary validation kept `VTH0`, `U0`, and all junction parameters fixed.
For the selected three-cell RC-aware timing point, timing RMS changed from
`0.1209/0.1332/0.1849` to `0.1219/0.1311/0.1872` for the
`DLC=-20 nm` trial in SVT/LVT/HVT; the corresponding train37 leakage RMS
remained `0.1358/0.1679/0.1254` within the reported precision. The `DWC`
trial gave timing RMS `0.1228/0.1300/0.1923` with the same leakage result.
These are guardrails, not evidence that either geometry correction is
physical.

Decision: do not promote `DLC`, `DWC`, `CF`, `CGBO`, `VFBCV`, `MOIN`, `NOFF`,
or `VOFFCV` into the released core. Freeze the shipped DC/drive calibration,
fit size/overlap only when an extracted intrinsic target or measured C-V
curve is available, then fit bias C-V and fringe terms against that curve.
Keep `CJSWGS/CJSWGD` and the other junction terms fixed without LVS-mapped
geometry. The existing immutable Cwire wrapper remains the honest path for
cell-boundary Liberty capacitance. The old `CF/CLC/DROUT` stage remains
blocked for the same identifiability reason.


### LDE decision

`SA/SB/SD` are absent from every released CDL. Xyce accepts temporary
`SA/SB/SD` fields, but with the current all-zero LDE coefficients they are
inert at the probe point. The LDE fields therefore remain frozen and the
AOI22/CV fitting stage remains blocked until foundry LDE/C-V data or a
separate extracted cell-parasitic model is available. This avoids absorbing
unidentified layout/context effects into `CF`, `CLC`, `CGSO`, `CGDO`, or
`DROUT`.

### Drive strength

At TT, using an inverter input slew of 98.5 ps and a 6.63 fF load, the Liberty
`INVX1` falling-delay targets are SVT 71.4 ps, LVT 57.8 ps, and HVT 82.9 ps.
The leakage-only cards measured 137.5 ps, 75.5 ps, and 314.5 ps respectively.
The promoted RC-aware cards measure 102.2 ps, 63.3 ps, and 165.3 ps at that
same point. This improves the one-point timing error but does not validate all
slews/loads or replace measured I-V/drive evidence.

### Fast-slew / large-load diagnostic and LINT probe

The current RC-aware cards were also exercised at a 12.196 ps input slew.
`Cload=0` was compared with the nearest Liberty low-load point
(0.523 fF); `Cload=50 fF` was compared with the nearest available Liberty
maximum (SVT 55.107 fF, LVT 58.123 fF, HVT 41.067 fF). Values below are
simulated / Liberty propagation delays in ps, using a long-period pulse for
the slow HVT large-load transition.

| flavor | near-zero load rise | near-zero load fall | large load rise | large load fall |
|---|---:|---:|---:|---:|
| SVT | 9.0 / 12.7 | 11.6 / 10.6 | 346.2 / 392.5 | 435.7 / 288.4 |
| LVT | 6.8 / 11.8 | 7.3 / 8.6 | 285.1 / 378.1 | 226.7 / 233.1 |
| HVT | 15.7 / 19.3 | 23.0 / 15.2 | 666.8 / 424.9 | 1068.1 / 287.9 |

The residual is not a uniform `Cgg` or junction-capacitance error. SVT and HVT
falling delay becomes substantially too slow only under large load, while LVT
falling delay is close there; that pattern points more strongly to
polarity-/corner-dependent `Idsat`/`Rds` and model form than to `CAPMOD`,
`CJS`, or `L_eff` alone. The zero-load points still expose separate
drive/capacitance residuals, so this is a diagnostic split, not a signoff
conclusion.

A temporary model-level `LINT` sweep was then run without adding any instance
parameters. The normal three-cell RC-aware timing RMS and leakage side effect
were:

| flavor | shipped `LINT=0` timing RMS | temporary timing minimum | leakage result |
|---|---:|---:|---|
| SVT | 0.1209 | 0.1115 at NMOS `LINT=+1 nm` | Xyce leakage simulations failed |
| LVT | 0.1332 | 0.1024 at PMOS `LINT=-1 nm` | Xyce DC sweep failed |
| HVT | 0.1849 | 0.0623 at NMOS `LINT=+2 nm` | leakage RMS 6.208 (train37), 6.103 (holdout2) |

The timing-only minima are therefore compensating the existing provisional
drive/model error, not validating a physical channel-length correction.
`LINT=0` remains unchanged, no explicit parameter was added, and further
`CF/CLC/DROUT` fitting stays blocked.

### RC-aware drive-parameter experiment

`fit/drive.py` extracts rising and falling inverter points from Liberty, while
`fit/rc_extraction.py` adds the frozen manual signal-net RC. Device-owned GDS
layers are excluded; VDD/VSS rails are excluded from signal timing RC; and
unlabeled internal interconnect fails closed because LVS is not available.
`fit/fit_drive.py` fits `u0`, `vsat`, and `rdsw` with the shipped leakage
controls held fixed. The promoted candidate used 36 trials per flavor, seed
2911, leakage weight 4.0, and `--rc`.

| flavor | fit timing base → RC fit | holdout timing base → RC fit | holdout2 timing base → RC fit | train37 leakage base → RC fit |
|---|---:|---:|---:|---:|
| SVT | 0.2014 → 0.1209 | 0.1986 → 0.1270 | 0.2459 → 0.2023 | 0.1363 → 0.1358 |
| LVT | 0.2070 → 0.1332 | 0.2915 → 0.2129 | 0.9234 → 0.6632 | 0.1659 → 0.1679 |
| HVT | 0.3257 → 0.1849 | 0.3336 → 0.1910 | 0.2439 → 0.1490 | 0.1252 → 0.1254 |

The same direction holds on the independent holdout2 leakage audit:
SVT 0.1621 → 0.1564, LVT 0.2241 → 0.2194, and HVT 0.1257 → 0.1258.
The `u0`/`vsat`/`rdsw` overrides are therefore rendered into the current
provisional core cards. This is a timing calibration at one characterized
slew/load point, not a transistor I-V/C-V extraction or signoff model.
 
An additional bounded six-parameter timing-only sweep used 48 Optuna trials
with leakage weight zero. It reduced the fit-set timing log-RMS from `0.1332`
to `0.0920`, but increased train37 leakage log-RMS from `0.1679` to `0.2509`;
the best scales incurred a source-prior penalty of `1.558`. A second 48-trial
run with leakage weight `0.25` reached timing log-RMS `0.0913` and leakage
log-RMS `0.2501`, so it did not restore the leakage guardrail. These are
timing/leakage tradeoffs, not model improvements; neither temporary result in
`/tmp/lvt_drive_timing_only.json` or `/tmp/lvt_drive_balanced_w025.json` was
promoted.

### LVT full-grid residual, finite-driver, and Cwire-wrapper audit

`fit/timing_residual_analysis.py` expands the released LVT `cell_rise` and
`cell_fall` tables over all 7×7 slew/load points for train37 `INVX1`,
`INVX3`, and `INVX4`, plus holdout2 `INVX20`. Each point uses the manual GDS
RC deck. The generated JSON compares four variants: an ideal source, an ideal
source with a formal local Cwire wrapper, a finite `INVX4` train37 driver
(including its mapped RC), and that finite driver with Cwire. The 0.6 V
profile is used for the Cwire variants.
Finite-driver decks use a 1 ns source delay and 3 ns period to settle the
driver/DUT operating point before either edge. The finite-driver target is
interpolated from Liberty at the measured DUT-input slew; comparing against
the unbuffered source slew is invalid. Direct RMS percentage fields are
reported alongside the existing log-space and delay-floor metrics.

The holdout2 ideal-source baseline has 91 valid residuals out of 98 points.
Its timing RMS is 0.3353 in
`sqrt(mean(log10(t_sim/t_lib)^2))`, mean signed relative error is +33.4%,
and mean absolute error is 37.4 ps. Seven points are excluded fail-closed:
three have non-positive Liberty delays, three have no simulated rising 50%
crossing, and one has a non-positive simulated delay. This full 7×7 result is
not numerically interchangeable with the earlier 0.6632 holdout2 single-point
audit.

The residual is not a single global offset:

- holdout2 rising transitions average −38.5% signed error;
- falling transitions average +103.8%;
- the largest absolute error is 256.2 ps at 0.795659 ns input slew and
  0.381806 pF load (rising, −58.8%);
- the largest relative outlier is +2332% at 0.197642 ns and 0.000523292 pF
  (falling, 1.58 ps Liberty target versus 38.4 ps simulated).

Thus slow/large-load rising error and small-target falling outliers coexist;
the relative-error tail is not evidence for one uniform capacitance bias.
Holdout2 `R_net` is constant for the only timing-evaluable cell
(`INVX20`: 0.11015 Ω), so no within-holdout `R_net` slope is identifiable.

The corrected finite-driver path changes the timing environment rather than
merely relabeling the ideal source. It now measures the preconditioned
driver/DUT waveform, rejects non-positive propagation delays, and interpolates
the Liberty target at the measured DUT-input slew. For `INVX4`, the train37
aggregate is 290/294 valid with log-RMS `0.10564` and direct timing RMS
`27.48%`; holdout2 is 93/98 valid with log-RMS `0.20303` and direct timing RMS
`74.87%`. The corresponding output-slew direct RMS is `24.63%`/`26.19%`, and
the derived `I_eff` direct RMS is `34.18%`/`39.17%` for train37/holdout2.

The bounded holdout2 `INVX20` wrapper has zero Cwire by policy, so
finite-driver+Cwire is identical to finite-driver and does not claim a
physical holdout capacitance correction. The four non-positive Liberty targets
and finite-driver negative-delay crossings remain explicit failures; they are
not imputed or converted into small positive delays. These results still miss
the requested 5%/10% thresholds by a wide margin.

The Cmodel policy is now explicit. For LVT `INVX20`, the raw AC model is
0.0112930 pF at 0 V and 0.0111630 pF at 0.6 V versus Liberty Cpin
0.0109647 pF, leaving raw negative Cwire residuals of −0.0003283 pF and
−0.0001983 pF. The default `bound` policy preserves those raw measurements
and excess fields, exports a zero-Cwire wrapper marked `bounded`, and reports
the uncompensated AC ratio (>1). `raw` preserves the negative residual for
audit and `reject` omits the wrapper. This is an export-feasibility bound,
not a BSIM4 C-V repair.

The RC-space audit separates feature availability from timing-safe topology.
Train37 has 36/37 output-Y RC records, but only 11/37 are fully mapped;
holdout2 has 20/20 output-Y records, but only 1/20 is fully mapped. In the
requested `Cnet=0.35–1.0 fF` band, train37 has two output-Y records but only
one timing-safe record (`INVX4`); holdout2 has nine output-Y records but only
one timing-safe record (`INVX20`). The polygon audit attributes the unmapped
train/holdout interconnect to 44/34 unlabeled M1 polygons, with no non-M1
interconnect in these splits. Without LVS or an equivalent net-connectivity
map, assigning those internal polygons to signal pins would be fabricated
coverage; full Pi/T RC expansion therefore remains blocked.

Artifacts: `/tmp/lvt_timing_driver_sweep_corrected/lvt_timing_residuals.json`,
`lvt_holdout2_residuals_baseline.png`, `lvt_holdout2_residuals_cwire.png`,
`lvt_residuals_by_cell.png`, and the finite-driver per-strength plots.

### Driver-strength sensitivity sweep

The corrected full-grid experiment was rerun with finite `INVX1`, `INVX4`, and
`INVX8` drivers. `INVX1` and `INVX4` came from the generated train37 split;
`INVX8` was loaded from the released LVT CDL/Liberty source because it is not
in that split. Its manual-GDS driver RC was fully mapped (`A`: 0.0341 ohm /
0.0002709 pF, `Y`: 0.1565 ohm / 0.0006332 pF); no interconnect layer was
silently omitted.

Holdout2 metrics use direct conventional RMS percentage error; `t_slew` and
`I_eff` exclude rows without a valid positive transition measurement:

| driver | source | timing valid | `t_pd` log RMS | `t_pd` RMS | `t_slew` RMS | `I_eff` RMS | mean signed `t_pd` | floor RMS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| INVX1 | train37 | 88/98 | 0.3827 | 260.6% | 24.4% | 35.5% | +82.6% | 204.9% |
| INVX4 | train37 | 93/98 | 0.2030 | 74.9% | 26.2% | 39.2% | +21.8% | 74.9% |
| INVX8 | released source | 94/98 | 0.1648 | 49.9% | 27.4% | 41.3% | +12.2% | 49.9% |

The corresponding train37 `t_pd` log/direct RMS values are `0.1423/37.5%`,
`0.1056/27.5%`, and `0.0946/23.8%` for `INVX1`, `INVX4`, and `INVX8`.
`INVX8` minimizes holdout timing residuals, but it worsens the output-slew
and derived-current residuals relative to `INVX1`; no driver reaches the
requested thresholds. The bounded holdout2 `INVX20` Cmodel exports zero Cwire,
so `driver+Cwire - driver` is exactly zero and this sweep isolates source-driver
strength rather than a physical holdout pin-capacitance correction.

The sweep does not identify the real signoff driver: Liberty tables provide DUT
targets but not the upstream CTS/STA driver cell or its extracted
interconnect. Keep `INVX4` as the middle-strength default and use `INVX1`/`INVX8`
as a bracket until a signoff netlist supplies the actual driver, input-slew
distribution, and RC. Do not promote `INVX8` solely because it has the lowest
timing residual in this model-form audit.

Artifacts: `/tmp/lvt_timing_driver_sweep_corrected/lvt_timing_residuals.json`,
`lvt_driver_sensitivity.png`, and the six per-driver holdout plots.

These remain **unvalidated and intentionally unfitted**:

- The PTM source cards carry `fnoimod=1` but do not provide foundry-calibrated
  `KF`/`AF` values; no noise claim is made.
- No mismatch/Monte Carlo distributions are released. `monte_carlo/ics55_mc.mm`
  is a template only.
- No BTI/HCI stress data or aging compact model is released.
  `aging_noise/ics55_aging.scs` and `ics55_noise.scs` remain TBD templates.
- Temperature and voltage behavior outside the exact TT leakage target are not
  calibrated; the corner table above demonstrates the risk.

It would be fabrication to fill these values from textbook defaults. Required
inputs are foundry BSIM/statistical/reliability cards or silicon measurements
with defined test structures, bias, geometry, temperature, and uncertainty.

## 7. Reproduction

```sh
# Regenerate data_fit, holdout, train37, holdout2, and historical splits.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/extract_data.py

# Recompute source-card priors and the 55 nm initial-value manifest.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/initial_values.py \
  --out /tmp/ics55_initial_values.json

# Refit the shipped six-parameter TT split.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/fit_clean.py \
  svt lvt hvt --dataset train37 --trials 120 --seed 211 \
  --out /tmp/fit_train37_best.json

# Run the non-promoted added-leakage experiment and the promoted RC-aware drive experiment.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/fit_expanded.py \
  svt lvt hvt --dataset train37 \
  --params nf_n,nf_p,eta_n,eta_p,dsub_n,dsub_p,tox_n,tox_p,\
  u0_n,u0_p,pclm_n,pclm_p,drout_n,drout_p \
  --freeze-legacy --trials 120 --seed 1211
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/fit_drive.py \
  svt lvt hvt --dataset fit --trials 36 --seed 2911 \
  --leakage-weight 4.0 --rc --out /tmp/drive_fit_rc_candidate.json
python3 libs.tech/spice/models/fit/rc_extraction.py \
  --root . --flavor svt --cell INVX1 --pins A,Y

# Render only the checked-in, promoted manifest.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/write_model.py \
  --params libs.tech/spice/models/fitted/FIT_PARAMS.json \
  --out libs.tech/spice/models/fitted/ics55_mos_core.l
# Verify CDL drawn geometry, omitted instance fields, CAPMOD/GEOMOD, and LDE.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/audit_geometry.py
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/cap_compensation.py \
  --flavors svt lvt hvt --cells INVX1,INVX3,INVX4 \
  --rail VSS --biases 0,0.6 --records-bias 0.6 \
  --out /tmp/cap_compensation.json \
  --spice-out /tmp/cwire_wrappers.cir
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/cap_compensation.py \
  --flavors lvt --cells INVX1,INVX3,INVX4,INVX20 \
  --datasets fit,holdout2 --biases 0,0.6 --records-bias 0.6 \
  --cmodel-policy bound \
  --out /tmp/lvt_cwire_bounded.json \
  --spice-out /tmp/lvt_cwire_bounded.cir
uv run --isolated --no-project --python 3.13 \
  --with "matplotlib==3.11.1" --with "optuna==5.0.0" \
  python libs.tech/spice/models/fit/timing_residual_analysis.py \
  --cwire-json /tmp/lvt_cwire_bounded.json --bias-v 0.6 \
  --driver-cells INVX1,INVX4,INVX8 --delay-floor-ps 5 \
  --out-dir /tmp/lvt_timing_driver_sweep_corrected
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/cap_model_sweep.py \
  --flavors svt lvt hvt --cells INVX1,INVX3,INVX4 \
  --out /tmp/cap_model_sweep.json
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/cv_core_sweep.py \
  --flavors svt lvt hvt --cells INVX1,INVX3,INVX4 \
  --out /tmp/cv_core_sweep.json
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/cv_core_sweep.py \
  --flavors lvt --cells INVX1,INVX3,INVX4 --biases 0,0.6 --validate \
  --out /tmp/lvt_cv_core_sweep_validate.json
# Add --validate to run timing and train37 leakage guardrails per candidate.
# Add --leakage-dataset train37 to run the leakage guardrail sweep.


# Audit train, independent holdout, staged candidates, and released corners.
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/audit_fit.py \
  --dataset train37 --params libs.tech/spice/models/fitted/FIT_PARAMS.json
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/audit_fit.py \
  --dataset holdout2 --params libs.tech/spice/models/fitted/FIT_PARAMS.json
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/audit_expanded.py \
  --results /tmp/expanded_fit_candidate.json
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/audit_drive.py \
  --results /tmp/drive_fit_rc_candidate.json
/tmp/optuna_env/bin/python libs.tech/spice/models/fit/audit_corners.py \
  --params libs.tech/spice/models/fitted/FIT_PARAMS.json
```

`FIT_PARAMS.json` records the parameters used to generate the shipped cards.
`drive` entries store the direct `u0`/`vsat`/`rdsw` overrides and the RC source
boundary. `simulate.py` subtracts the DC gmin floor for SVT/LVT and retains
raw Xyce current for HVT. ngspice is not a compatible validation simulator for
the full PTM BSIM4 cards. Candidate manifests are not shipped automatically.

## 8. What would make this solid

A foundry-validated BSIM4/BSIM-CMG card set per process corner, plus measured
or trusted characterized data for Id-Vg/Id-Vd, C-V, drive current/delay,
leakage over voltage and temperature, mismatch distributions, noise spectra,
and BTI/HCI aging is required. Then fit separate process/corner cards with
multi-objective acceptance criteria and validate on cells/geometries excluded
from fitting. Until then, keep this file scoped to exploratory TT leakage,
RC-aware inverter timing, and qualitative transistor behavior.

## 9. External references

[^ptm]: University of Minnesota, “Predictive Technology Model (PTM),”
  https://mec.umn.edu/ptm; Cao and Zhao, “A New Perspective of Predictive
  Technology Model for Nano-CMOS Design,”
  https://doi.org/10.1109/NANONET.2006.346227; Zhao and Cao, “New Generation
  of Predictive Technology Model for Sub-45nm Early Design Exploration,”
  https://doi.org/10.1109/TED.2006.884077.

[^extraction]: Assenmacher, “BSIM4 Modeling and Parameter Extraction,”
  https://ewh.ieee.org/r5/denver/sscs/References/2003_03_Assenmacher.pdf;
  Li et al., “A Practical Approach to Compact Model Parameter Extraction,”
  http://dspace.mit.edu/bitstream/handle/1721.1/92430/Li-Yu-final-ASPDAC2013.pdf;sequence=1.
