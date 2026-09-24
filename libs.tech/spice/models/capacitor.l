* ============================================================================
* ICsprout55 - capacitors (MOM) and varactors
* ============================================================================
* Released data: device stubs exist for mom_2t / mom_3t / var1p2_npd_nw_lp /
* var3p3_npd_nw_lp.  No electrical parameters are released.
*
* MOM (metal-oxide-metal, mom_2t/mom_3t):
*   terminal order: mom_2t PLUS MINUS ; mom_3t PLUS MINUS B
*   Reference only (NOT foundry data): lateral MOM density at 65nm-class
*   nodes ~1-2 fF/um2.  Tech LEF area caps to ground (pF/um2):
*     M1 0.763e-3, M2-M4 1.107e-3, M5 0.626e-3, T4M2 0.130e-3, RDL 0.057e-3
*   Layout template: libs.tech/klayout/pcells/ics55_mom.py

.subckt mom_2t PLUS MINUS
* TBD: foundry MOM model / capacitance density not released
Cmom PLUS MINUS 1p
.ends

.subckt mom_3t PLUS MINUS B
* TBD: foundry MOM model not released (B = back-plate / shield terminal)
Cmom PLUS MINUS 1p
.ends

* ============================================================================
* Varactors (NMOS-in-N-well, 2-terminal)
* ============================================================================
* var1p2_npd_nw_lp : 1.2V NMOS varactor (N+ poly / N-well diode varactor)
* var3p3_npd_nw_lp : 3.3V NMOS varactor
* terminal order: POS NEG
* NOT RELEASED: C-V curve, tuning range, Q - stubs below are placeholders.

.subckt var1p2_npd_nw_lp POS NEG
* TBD: foundry varactor model not released
Cvar POS NEG 1p
.ends

.subckt var3p3_npd_nw_lp POS NEG
* TBD: foundry varactor model not released
Cvar POS NEG 1p
.ends
