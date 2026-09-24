* ============================================================================
* ICsprout55 - corner definitions
* ============================================================================
* The released digital liberty files define these operating corners
* (std-cell lib ics55_LLSC_H7CR, IO lib ICSIOA_N55_3P3):
*
*   tt_1p2_25c        (typ/typ, 1.2V,  25C)
*   ss_1p08_m40       (slow/slow, 1.08V, -40C)
*   ss_1p08_125       (slow/slow, 1.08V, 125C)
*   ss_rcworst_1p2_m40 (slow RC-worst, 1.2V, -40C)
*   ff_1p32_m40       (fast/fast, 1.32V, -40C)
*   ff_1p32_125       (fast/fast, 1.32V, 125C)
*   ff_rcbest_1p32_m40 / ff_cbest_1p32_125 / ff_rcbest_1p08_125
*   IO: ss_1p08_2p97_m40/125, tt_1p2_3p3_25c, ff_1p32_3p63[..]_0c/125/m40
*
* The five standard corners below are structural. Scale factors are NOT
* foundry data - they default to 1.0 and must be replaced with the values
* that come with the foundry models.  MOS/device models must be switched
* per corner (e.g. .lib "corner.lib" SS ...) once released.
*
* Usage:
*   .include "ics55.m"     (includes tt by default)
*   -or-  .include "corners/ss.mod" after ics55.m
*   -or-  ngspice -b -a ... with .option file
* ============================================================================

* --- global scale factors (TBD: foundry values) ---
.param corner_vdd  = 1.2
* core supply for this corner (V)
.param corner_vddio = 3.3
* IO supply for this corner (V)
.param corner_temp = 25
* junction temperature (C)
.param k_rs_poly = 1.0
* TBD: poly resistor corner factor
.param k_rs_metal = 1.0
* TBD: metal resistor corner factor
.param k_cap = 1.0
* TBD: capacitance corner factor
.param k_via = 1.0
* TBD: via resistance corner factor
.param k_mos = 1.0
* TBD: MOS global corner factor
