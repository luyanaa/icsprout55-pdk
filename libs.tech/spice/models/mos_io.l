* ============================================================================
* ICsprout55 - 3.3V thick-oxide IO MOS (nm3p3_lp / pm3p3_lp)
* ============================================================================
* Released data (IO CDL P65_1233):
*   nm3p3_lp : NMOS 3.3V thick oxide, drawn L = 500 nm
*              (IO driver fingers W = 20-25 um, m = 1-20)
*   pm3p3_lp : PMOS 3.3V thick oxide, drawn L = 400-650 nm
*              (W = 4-25 um, m = 1-18)
*   VDDIO = 3.3V nominal (2.97-3.63V), temp -40..125C
*   Schmitt IO thresholds: VT+ 1.88-2.0V, VT- 1.36-1.55V (PBMUX)
*   Output drivers 2/8/10/16 mA programmable (PBMUX)
* NOT RELEASED: model parameters - stubs below are placeholders.

* Placeholder only: explicit level=1 keeps Xyce parsing structural cards.
.model nm3p3_lp nmos level=1

* Placeholder only: PMOS parameters are not released.
.model pm3p3_lp pmos level=1


* Known usage from IO CDL:
*   P65_1233_PAR:  pm3p3_lp W=25u L=650n m=18 ; nm3p3_lp W=25u L=500n m=20
*   MUX_PAD:       nm3p3_lp W=160u L=500n m=1 ; pm3p3_lp W=20u L=400n m=...
*   level shifter: pm3p3_lp L=400n ; nm3p3_lp L=500n
