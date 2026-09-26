# ICsprout55 model fitting workspace (`libs.tech/spice/models/fit/`)

This workspace fits provisional BSIM4 core cards from released standard-cell
CDL and Liberty data. The shipped result is
`../fitted/ics55_mos_core.l`; evidence and limits are in
`../fitted/FIT_REPORT.md`.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1 | `extract_data.py` | `data_fit_*`, `data_train37_*`, `data_holdout2_*`, plus historical splits |
| 2 | `initial_values.py` | `INITIAL_VALUES.json` from 65 nm bulk and 45 nm HP/LP source cards |
| 3 | `simulate.py` | Xyce per-state cell leakage in nW |
| 4 | `fit_clean.py` | deterministic in-process Optuna fit and repeated verification |
| 5 | `fit_optuna.py` | exploratory parallel TPE/CMA-ES/NSGA-II/Random search |
| 6 | `fit_expanded.py` | prior-regularized nonzero leakage-parameter experiments |
| 7 | `drive.py`, `fit_drive.py` | Liberty inverter timing extraction and RC-aware guarded `u0`/`vsat`/`rdsw` experiments |
| 8 | `rc_extraction.py` | manual GDS M1 signal-net RC extraction for timing decks |
| 9 | `audit_fit.py`, `audit_expanded.py`, `audit_drive.py` | train/holdout leakage and timing audits |
| 10 | `audit_corners.py` | released Liberty non-TT corner extrapolation audit |
| 11 | `audit_geometry.py` | CDL drawn-L, finger, junction, CAPMOD, GEOMOD, and LDE structural audit |
| 12 | `cap_compensation.py` | Xyce AC `Cdiff` extraction and immutable Cwire wrapper generation |
| 13 | `cap_model_sweep.py` | temporary CJSWGS/CJSWGD and CGSO/CGDO sensitivity audit |
| 14 | `cv_core_sweep.py` | temporary size/bias BSIM4 C-V parameter support and sensitivity audit |
| 15 | `write_model.py` | render `fitted/ics55_mos_core.l` from `FIT_PARAMS.json` |
| 16 | `finalize_fit.py` | legacy one-at-a-time ±5% robustness exploration |
| 17 | `timing_residual_analysis.py` | LVT full-grid residuals, ideal-vs-finite-driver timing, multi-driver sensitivity, Cwire comparison, delay/slew/I_eff metrics, floor-weighted metrics, and RC-space coverage |

`CANDIDATE_FIT_SUMMARY.json` records the staged experiments and promotion
decisions. The leakage-only expansion remains separate. The RC-aware drive
calibration is now present in `fitted/FIT_PARAMS.json` and the rendered core
cards, but remains explicitly provisional and non-signoff.

`cap_compensation.py` emits immutable wrapper subcircuits; it does not rewrite
the released CDL or promote pin parasitics into the BSIM4 core. Its JSON also
includes flat `records` with `c_intrinsic_pf`, so it can be passed directly to
`cell_parasitics.py --intrinsic-json` for the existing Layer-2 residual report.
The default `--cmodel-policy bound` is an export-feasibility policy: when the
raw AC Cmodel exceeds Liberty Cpin, it records the raw excess, sets the
exported wrapper Cwire to zero, and marks the row `bounded`. It does not repair
the underlying BSIM4 C-V model. `--cmodel-policy raw` preserves a negative
residual for audit, while `reject` omits that wrapper from export.
A nonzero `--alpha` is a behavioral voltage extrapolation because one Liberty
capacitance value cannot identify voltage nonlinearity. `cap_model_sweep.py`
and `cv_core_sweep.py` likewise record temporary model-level sensitivity only;
neither changes `FIT_PARAMS.json` or the rendered core.
The available Liberty/CDL evidence supplies a boundary input Cpin, not
terminal-charge or small-signal matrix targets for independent intrinsic
`Cgg`, `Cgd`, and `Cgs` validation. Cwire compensation is therefore a
cell-boundary correction, not an intrinsic capacitance fit.

`cap_compensation.py` defaults to two static working-bias profiles, `0 V` and
`VDD/2` (`0.6 V` at the nominal 1.2 V supply). `--biases` accepts a
comma-separated list of explicit profiles. With multiple profiles, the
generated wrapper names encode both VT flavor and bias, for example
`INVX1H7R_CWIRE_SVT_BP0P6_A`. The JSON keeps the full flavor/profile hierarchy
and selects one profile for the flat `records` view using `--records-bias`
(default: first bias), preserving `cell_parasitics.py` compatibility.
For timing residual analysis that includes holdout2 `INVX20`, pass
`--datasets fit,holdout2` to `cap_compensation.py`; this only broadens the
extracted-cell lookup and does not change the core model. The timing analysis
uses a finite train37 inverter driver by default (`INVX4`), reports measured
DUT-input slew, and adds delay-floor, output-slew, and derived effective-current
metrics. Finite-driver rows interpolate Liberty targets at the measured DUT
input slew; they do not compare a buffered DUT against the unbuffered source
slew. `--driver-cells INVX1,INVX4,INVX8` runs a driver-strength sensitivity
sweep; `INVX8` is loaded directly from the released CDL/Liberty source because
it is not part of the generated train37 JSON split. `--driver-cell none` is
reserved for an explicit ideal-source comparison.
Finite-driver decks delay the source pulse by 1 ns and use a 3 ns period so
the driver/DUT operating point is settled before either measured transition;
this avoids counting Xyce startup crossings as timing events.
The wrapper adds no DC path and does not modify the baseline BSIM4 core.

`data_fit_*` contains 17 stable cells from the historical sample. The shipped
cards were fit on `data_train37_*` (those 17 plus 20 disjoint combinational
cells) and checked on `data_holdout2_*`, which is never used by that fit.
`data_main_*`, `data_val_*`, and `data_all_*` remain available for historical
comparisons; `data_val` is not an independent holdout.

## Requirements

- Xyce 7.10 (OpenMPI): `/usr/local/XyceNF_OMPI_7.10/bin/Xyce` with
  `DYLD_LIBRARY_PATH=/opt/homebrew/lib` (set inside `simulate.py`)
- Optuna + cmaes: `/tmp/optuna_env` virtual environment
- PTM source cards: `~/Downloads/45nm_LP.pm`, `~/Downloads/45nm_HP.pm`, and
  `~/Downloads/65nm_bulk.pm`
- Released source data under `libs.ref`

## Important simulator details

- Xyce's DC gmin (`1e-12 S`) sits at the same order as some HVT leakages.
  SVT/LVT audits subtract the analytically reconstructed floor. For HVT, the
  correction can over-subtract and produce negative currents, so the staged
  fitter/audits retain raw Xyce current and record that policy explicitly.
- Xyce 7.10 ignored the SPICE `.temp` card in this workflow. `build_deck`
  therefore emits `.options device temp = <degrees-C>`; do not remove it.
- High input sources follow the requested `vdd`, so corner evaluations do not
  accidentally drive inputs at 1.2 V when the supply is 1.08 or 1.32 V.
- ngspice accepts too little of the full PTM BSIM4 card for validation; use
  Xyce for the fitted cards.
- PTM GIDL is disabled because its uncalibrated floor is above the released
  Liberty off-current targets.

## Manual RC extraction boundary

`rc_extraction.py` parses the released stdcell GDS directly and uses the
released MET1 sheet/area/edge RC values from the ECOS technology LEF. The
ownership rule is deliberately manual until LVS exists:

- `ACT`, `POLY`, contacts, wells, implants, and other device-owned layers
  never receive standalone interconnect RC.
- Only labeled signal M1 polygons receive a series resistance and shunt
  capacitance.
- VDD/VSS rails are recognized but excluded from signal timing RC.
- `rc_extraction.py` reports polygon-level mapping counts, including unlabeled
  M1 versus power-only polygons, so an unmapped warning is auditable.
- Unlabeled internal interconnect is reported and fails RC-enabled timing
  evaluation instead of being guessed. Full Pi/T RC requires LVS or an
  equivalent net-connectivity map.

`timing_residual_analysis.py` reports whether the available output-Y records
cover the requested `Cnet=0.35–1.0 fF` band and separates feature availability
from timing-safe topology. It never synthesizes missing physical cells to fill
that band. Each timing row also records Liberty output-transition targets and
measured output slew. `I_eff` is derived as `VDD*C_load/t_slew`; it is an
effective timing current, not a separately measured transient-current target.
For finite drivers, the Liberty delay and transition targets are interpolated
at the measured DUT-input slew.

The RC path is frozen for the current MOS experiment. Inspect one cell with:

```sh
python3 fit/rc_extraction.py --root . --flavor svt --cell INVX1 --pins A,Y
```


## Initial values and staged experiments

`initial_values.py` interpolates 45 nm LP/HP and 65 nm bulk cards to a 55 nm
prior.[^ptm] Positive parameters use geometric interpolation; signed parameters
use linear interpolation. The shipped six leakage parameters re-center the
threshold, offset, and DIBL priors per flavor. `INITIAL_VALUES.json` preserves
the source values, interpolated values, parameter groups, and provenance.

The extraction order follows published compact-model practice: threshold and
subthreshold terms first, then mobility/series resistance and output
conductance, with C-V and temperature handled as separate evidence streams.[^extraction]
The papers provide priors and workflow guidance, not ICSprout55 foundry
measurements. Parameters without direct current, C-V, gate-leakage, noise,
mismatch, or aging observations remain frozen.

`fit_expanded.py` and `fit_drive.py` produce candidate manifests only.
`write_model.py` renders the explicit manifest; it does not promote a new
candidate automatically. The current manifest contains the RC-aware drive
calibration recorded in `CANDIDATE_FIT_SUMMARY.json`.

## Reproduction

```sh
/tmp/optuna_env/bin/python fit/extract_data.py
/tmp/optuna_env/bin/python fit/initial_values.py \
  --out /tmp/ics55_initial_values.json
/tmp/optuna_env/bin/python fit/fit_clean.py svt lvt hvt \
  --dataset train37 --trials 120 --seed 211 \
  --out /tmp/fit_train37_best.json
/tmp/optuna_env/bin/python fit/fit_expanded.py svt lvt hvt \
  --dataset train37 \
  --params nf_n,nf_p,eta_n,eta_p,dsub_n,dsub_p,tox_n,tox_p,\
  u0_n,u0_p,pclm_n,pclm_p,drout_n,drout_p \
  --freeze-legacy --trials 120 --seed 1211 \
  --out /tmp/expanded_fit_candidate.json
/tmp/optuna_env/bin/python fit/fit_drive.py svt lvt hvt \
  --dataset fit --trials 36 --seed 2911 --leakage-weight 4.0 --rc \
  --out /tmp/drive_fit_rc_candidate.json
/tmp/optuna_env/bin/python fit/cap_compensation.py \
  --flavors svt lvt hvt --cells INVX1,INVX3,INVX4 \
  --biases 0,0.6 --records-bias 0.6 \
  --out /tmp/cap_compensation.json \
  --spice-out /tmp/cwire_wrappers.cir
/tmp/optuna_env/bin/python fit/cap_model_sweep.py \
  --flavors svt lvt hvt --cells INVX1,INVX3,INVX4 \
  --out /tmp/cap_model_sweep.json
/tmp/optuna_env/bin/python fit/cv_core_sweep.py \
  --flavors svt lvt hvt --cells INVX1,INVX3,INVX4 \
  --out /tmp/cv_core_sweep.json
/tmp/optuna_env/bin/python fit/cap_compensation.py \
  --flavors lvt --cells INVX1,INVX3,INVX4,INVX20 \
  --datasets fit,holdout2 --biases 0,0.6 --records-bias 0.6 \
  --cmodel-policy bound \
  --out /tmp/lvt_cwire_bounded.json \
  --spice-out /tmp/lvt_cwire_bounded.cir
uv run --isolated --no-project --python 3.13 \
  --with "matplotlib==3.11.1" --with "optuna==5.0.0" \
  python fit/timing_residual_analysis.py \
  --cwire-json /tmp/lvt_cwire_bounded.json --bias-v 0.6 \
  --driver-cell INVX4 --delay-floor-ps 5 \
  --out-dir /tmp/lvt_timing_driver_bounded
uv run --isolated --no-project --python 3.13 \
  --with "matplotlib==3.11.1" --with "optuna==5.0.0" \
  python fit/timing_residual_analysis.py \
  --cwire-json /tmp/lvt_cwire_bounded.json --bias-v 0.6 \
  --driver-cells INVX1,INVX4,INVX8 --delay-floor-ps 5 \
  --out-dir /tmp/lvt_timing_driver_sweep_corrected
/tmp/optuna_env/bin/python fit/write_model.py \
  --params fitted/FIT_PARAMS.json --out fitted/ics55_mos_core.l
/tmp/optuna_env/bin/python fit/audit_fit.py --dataset train37 \
  --params fitted/FIT_PARAMS.json
/tmp/optuna_env/bin/python fit/audit_fit.py --dataset holdout2 \
  --params fitted/FIT_PARAMS.json
/tmp/optuna_env/bin/python fit/audit_expanded.py \
  --results /tmp/expanded_fit_candidate.json
/tmp/optuna_env/bin/python fit/audit_drive.py \
  --results /tmp/drive_fit_rc_candidate.json
/tmp/optuna_env/bin/python fit/audit_corners.py \
  --params fitted/FIT_PARAMS.json

```

`fitted/FIT_PARAMS.json` is the parameter manifest used to generate the
shipped model. It is not required by SPICE. The fit is still exploratory:
independent holdout error, C-V, drive, non-TT PVT, noise, mismatch, and aging
must be reviewed before using the cards for any design decision.

[^ptm]: University of Minnesota, “Predictive Technology Model (PTM),”
  https://mec.umn.edu/ptm; Cao and Zhao,
  https://doi.org/10.1109/NANONET.2006.346227; Zhao and Cao,
  https://doi.org/10.1109/TED.2006.884077.

[^extraction]: Assenmacher, “BSIM4 Modeling and Parameter Extraction,”
  https://ewh.ieee.org/r5/denver/sscs/References/2003_03_Assenmacher.pdf;
  Li et al.,
  http://dspace.mit.edu/bitstream/handle/1721.1/92430/Li-Yu-final-ASPDAC2013.pdf;sequence=1.
