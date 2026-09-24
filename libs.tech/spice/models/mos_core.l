* ============================================================================
* ICsprout55 - core 1.2V MOS (nm1p2/pm1p2 {svt,lvt,hvt}_lp)
* ============================================================================
* Released data: CDL uses these exact model names with terminal order
*                D G S B and drawn L = 60 nm.  Std cells: W 150-380 nm
*                per finger; IO logic (lvt): W 1-4 um, m up to 5.
*                Supplies: VDD 1.2V nominal (1.08-1.32V).
* NOT RELEASED: model parameters (Vth, k, tox, etc.). Stubs below are
*               placeholders -- replace with foundry model cards.
*
* Device           | usage            | Vt split (relative)
* ---------------- | ---------------- | -------------------
* nm1p2_svt_lp     | std cells (RVT)  | standard
* nm1p2_lvt_lp     | IO logic (LVT)   | lower Vt (LVT implant layers 17/18)
* nm1p2_hvt_lp     | std cells (HVT)  | higher Vt (HVT implant layers 21/22)
* (same for pm1p2)
*
* Layout template: see libs.tech/klayout/pcells/ics55_mos_analog.py

* Placeholder only: explicit level=1 keeps Xyce parsing structural cards.
.model nm1p2_svt_lp nmos level=1

* Placeholder only: LVT parameters are not released.
.model nm1p2_lvt_lp nmos level=1

* Placeholder only: HVT parameters are not released.
.model nm1p2_hvt_lp nmos level=1

* Placeholder only: PMOS parameters are not released.
.model pm1p2_svt_lp pmos level=1

* Placeholder only: PMOS LVT parameters are not released.
.model pm1p2_lvt_lp pmos level=1

* Placeholder only: PMOS HVT parameters are not released.
.model pm1p2_hvt_lp pmos level=1



* Known geometry (measured from GDS, all Vt flavors identical):
*   drawn gate length L = 0.06 um
*   gate (poly) pitch     = 0.25 um (typical)
*   poly min spacing      = 0.12 um (measured min)
*   contact CT            = 0.09 um
*   INVX1: nw 0.21 um / pw 0.27 um ; INVX3: nw 0.45 um (2f) / pw 0.57 um (3f)
