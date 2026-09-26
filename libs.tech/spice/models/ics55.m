* ============================================================================
* ICsprout55 analog SPICE model library - master include
* ============================================================================
* Process: ICsprout 55nm (65nm-class) 1.2V/3.3V LP, salicide
* Status : PROVISIONAL - derived from the released digital PDK
*          (tech LEF, std-cell/IO CDL, GDS analysis)
* License: Apache-2.0 (see PDK root LICENSE)
*
* IMPORTANT
* --------
* No foundry SPICE models are released with this PDK. This library provides:
*   (a) exact primitive names / terminal orders / drawn geometry, as used in
*       the released CDL netlists, so testbenches and schematics remain valid
*       when real models arrive;
*   (b) measured or LEF-derived electrical constants (sheet resistances,
*       via resistance, capacitance densities);
*   (c) clearly marked TBD stubs for parameters that are NOT released.
* Do NOT use the TBD values for design decisions or tapeout.
*
* Device inventory (from libs.ref/*/cdl + IO datasheet):
*   MOS 1.2V  : nm1p2/pm1p2_{svt,lvt,hvt}_lp   (L = 60 nm drawn)
*   MOS 3.3V  : nm3p3_lp / pm3p3_lp            (L = 400-650 nm drawn)
*   Diodes    : dio_1p2_{pp_nw,np_pw}[_{lvt,hvt}]_lp, dio_3p3_pp_nw_lp
*   Resistors : re_{ndif,pdif,nwaa,nwsti,npo,ppo,hrpo,m1..m4,tm2,alpa}[_sab]
*               _2t/_3t
*   Caps      : mom_2t, mom_3t
*   Varactors : var1p2_npd_nw_lp, var3p3_npd_nw_lp
*   BJT       : not present in released data
*   Inductor  : not present in released data
*
* Corner setup: .include "corners/tt.mod"  (tt/ff/ss/fs/sf, plus the
* released liberty corner conditions listed in corners/README.md)
* ============================================================================

.include mos_core.l
.include mos_io.l
.include diode.l
.include resistor.l
.include capacitor.l

* -- corner selection (override with your own include order) --
.include corners/tt.mod
