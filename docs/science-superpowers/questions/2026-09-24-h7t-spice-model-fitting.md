# HVT pre-silicon BSIM4 fitting feasibility (H7CH / H7H reference subset)

**Research question:** Can a single HVT BSIM4 card, calibrated in staged order (threshold/subthreshold → drive → C-V) from released INVX1H7H/INVX3H7H/INVX4H7H cell evidence with physical priors, reproduce held-out CDL–GDS-consistent HVT cells within pre-specified tolerances while remaining physically plausible for DC + transient/AC analog use pending silicon calibration?

**Background / motivation:** The ICS55 PDK releases no public analog SPICE models (analog device models are NDA-encumbered), so a provisional open-source model must be fitted from public evidence before a test-tapeout device matrix can provide silicon calibration data. The current fit exhibits significant PMOS/NMOS mismatch and a suspicious series-resistance asymmetry (`rdsw_n 0.522` / `rdsw_p 1.844`, inverted relative to the `u0`/`vsat` pattern). Fitting failures cascade across cells because of non-standard geometry (RVT has NMOS/PMOS widths nearly switched; OAI finger widths differ from W/L). Anchoring the first fit on a geometry-consistent HVT inverter subset isolates model feasibility from geometry inconsistency.

**Hypotheses:**
- H0 (null): The staged, geometry-consistent, physically regularized strategy fails — it does not improve aligned-cell holdout prediction over the current fit, yields parameters outside physical plausibility bounds, or cannot meet tolerance on leakage and timing.
- H1 (alternative): The strategy yields an identifiable card that (a) fits INVX1/3/4 leakage then timing within tolerance, (b) predicts held-out aligned HVT cells within tolerance, (c) yields physically plausible parameter ratios (`u0`/`vsat`/`rdsw` within ranges justified by priors — directly testing whether the current `rdsw` inversion is a fitting artifact), and (d) shows non-pathological analog behavior (gm, output resistance, Cgg/Cgd/Cgs at nominal bias).

**Population & unit of analysis:** Unit = HVT standard cell × operating state × observable. Population = HVT (H7CH / `H7H`) released cells only. Fit subset = INVX1H7H, INVX3H7H, INVX4H7H. Confirmatory holdout = remaining combinational cells whose CDL and GDS-extracted W/L agree (exactly or nearly). Diagnostic tier = cells that are layout-valid but CDL-inconsistent (reported separately; cannot fail the core claim alone).

**Key variables (operationalized):**
- Outcome: per-state Liberty `leakage_power` (nW); NLDM cell delay and output transition (ps) over released input-slew/output-load grids; pin capacitance (fF) — each versus its Xyce-simulated counterpart under the candidate card + extracted M1 RC.
- Predictor(s): staged parameter groups — threshold/subthreshold (`vth0`, DIBL scale, `voff`) → drive (`u0`, `vsat`, `rdsw`) → C-V — with CDL device geometry (W, L, fingers, m-count) and GDS-agreement tier as fixed cell descriptors.
- Covariates / potential confounders: PTM-interpolated priors (`INITIAL_VALUES.json`); Xyce gmin floor under the documented HVT raw-current policy; manual M1-only RC extraction boundary; fixed finite driver (INVX4) for timing arcs; TT 1.2 V / 25 °C as the primary corner.

**What counts as an answer:** Exact decision thresholds are fixed at the pre-registration/design stage before any fitting outcome is examined: train-subset fit within tolerance, aligned-holdout leakage/delay/slew errors within tolerance, parameter plausibility bounds passed, and analog sanity checks passed. Failure of (b), (c), or (d) disconfirms H1.

**Scope & exclusions:** HVT only — RVT/LVT are explicitly deferred (their non-standard geometry is out of this stage). Claim is a pre-silicon provisional model only; no silicon-accuracy claim, mismatch, noise, aging, or reliability. Non-TT corners are secondary/exploratory. No proprietary or NDA model access. Compact-model form fixed to BSIM4 (no empirical wrappers or lookup-table alternatives in this stage).

**Open questions for prior-work survey:** staged BSIM4 extraction methodology; physical plausibility ranges for `u0`/`vsat`/`rdsw` at 55 nm-class nodes; identifiability of drive parameters from cell-level NLDM evidence; Xyce gmin-floor treatment in subthreshold leakage fitting; prior art on fitting under schematic↔extracted geometry mismatch.
