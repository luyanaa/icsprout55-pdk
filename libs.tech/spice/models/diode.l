* ============================================================================
* ICsprout55 - diodes / ESD
* ============================================================================
* Released data (IO CDL): junction diodes with AREA/PERI (PJ) modeling,
* used for ESD clamps and IO protection.  AREA in m^2, PJ in m.
*
*   dio_3p3_pp_nw_lp      : 3.3V P+/N-well diode (ESD, IO)
*                            PAR: M=10 AREA=20p PJ=24u
*                            CUT: M=4  AREA=29.5875p PJ=42.45u
*   dio_1p2_pp_nw_lp      : 1.2V P+/N-well diode
*   dio_1p2_pp_nw_lvt_lp  : 1.2V P+/N-well diode, LVT flavor
*   dio_1p2_pp_nw_hvt_lp  : 1.2V P+/N-well diode, HVT flavor
*   dio_1p2_np_pw_lp      : 1.2V N+/P-well diode
*   dio_1p2_np_pw_lvt_lp  : 1.2V N+/P-well diode, LVT flavor
*   dio_1p2_np_pw_hvt_lp  : 1.2V N+/P-well diode, HVT flavor
*
* Terminal order used in CDL: Dxx anode cathode dio_xxx M=.. AREA=.. PJ=..
* NOT RELEASED: Is, n, Cj, breakdown, etc. - stubs below are placeholders.

* Placeholder only: explicit level=1 keeps Xyce parsing structural cards.
.model dio_3p3_pp_nw_lp d level=1

* Placeholder only: parameters are not released.
.model dio_1p2_pp_nw_lp d level=1

* Placeholder only: LVT parameters are not released.
.model dio_1p2_pp_nw_lvt_lp d level=1

* Placeholder only: HVT parameters are not released.
.model dio_1p2_pp_nw_hvt_lp d level=1

* Placeholder only: parameters are not released.
.model dio_1p2_np_pw_lp d level=1

* Placeholder only: LVT parameters are not released.
.model dio_1p2_np_pw_lvt_lp d level=1

* Placeholder only: HVT parameters are not released.
.model dio_1p2_np_pw_hvt_lp d level=1


* ESD context (IO library): P+/N-well diodes on every pad (area-scaled),
* 50k pull-up/pull-down resistors, 300R/5R analog series resistors.
