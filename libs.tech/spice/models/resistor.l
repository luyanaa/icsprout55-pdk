* ============================================================================
* ICsprout55 - resistors (re_* family)
* ============================================================================
* Terminal orders from released CDL / device stubs:
*   re_*_2t : POS NEG
*   re_*_3t : POS NEG SUB
* Instance syntax:  Xname POS NEG re_<type>_2t W=<um> L=<um> M=<m>
*
* MEASURED / RELEASED constants:
*   re_ppo_sab (P+ poly, salicide blocked):
*       from P65_1233_PAR - 300R: W=8u L=3.34u  => Rsq ~ 718 ohm/sq
*                           -   5R: W=78u L=0.4u => Rsq ~ 975 ohm/sq
*       nominal design Rsq ~ 850 ohm/sq (range 700-1000; end/contact
*       resistance contributes, use for estimates only)
*   Metal resistors (LEF sheet resistance):
*       re_m1   = 0.1122 ohm/sq   (M1)
*       re_m2..re_m4 = 0.0914 ohm/sq  (M2-M4)
*       re_tm2  = 0.0239 ohm/sq   (T4M2 thick top metal)
*       re_alpa = 0.0151 ohm/sq   (RDL / Al)
*   Via resistance (LEF): VIA1-4, T4V2, RV = 2.5 ohm per via
*
* NOT RELEASED: diffusion / well / non-SAB poly / HRPO parameters.
* Values in brackets are 65nm-class textbook references, NOT foundry data.

* ---------------------------------------------------------------------------
* P+ poly, salicide blocked (the workhorse of the IO library)
* ---------------------------------------------------------------------------
.subckt re_ppo_sab_2t POS NEG W=8u L=3.34u M=1
* Rsq derived ~718-975 ohm/sq, nominal 850
Rbody POS NEG { 'M * 850.0 * L / W' }
.ends

.subckt re_ppo_sab_3t POS NEG SUB W=8u L=3.34u M=1
Rbody POS NEG { 'M * 850.0 * L / W' }
.ends

* ---------------------------------------------------------------------------
* P+ poly, salicided
* ---------------------------------------------------------------------------
.subckt re_ppo_2t POS NEG W=2u L=5u M=1
* TBD: salicided poly sheet resistance not released [ref ~5-10 ohm/sq]
Rbody POS NEG { 'M * 7.0 * L / W' }
.ends

.subckt re_ppo_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 7.0 * L / W' }
.ends

* ---------------------------------------------------------------------------
* N+ / P+ poly (non-PPO flavors kept for completeness)
* ---------------------------------------------------------------------------
.subckt re_npo_2t POS NEG W=2u L=5u M=1
* TBD: N+ poly Rsq not released
Rbody POS NEG { 'M * 100.0 * L / W' }
.ends
.subckt re_npo_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 100.0 * L / W' }
.ends
.subckt re_npo_sab_2t POS NEG W=2u L=5u M=1
* TBD: N+ poly SAB Rsq not released
Rbody POS NEG { 'M * 850.0 * L / W' }
.ends
.subckt re_npo_sab_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 850.0 * L / W' }
.ends

* ---------------------------------------------------------------------------
* High-res poly (HRPO)
* ---------------------------------------------------------------------------
.subckt re_hrpo_2t POS NEG W=1u L=10u M=1
* TBD: HRPO sheet resistance not released [ref 65nm ~1-2 kohm/sq]
Rbody POS NEG { 'M * 1500.0 * L / W' }
.ends
.subckt re_hrpo_3t POS NEG SUB W=1u L=10u M=1
Rbody POS NEG { 'M * 1500.0 * L / W' }
.ends

* ---------------------------------------------------------------------------
* Diffusion resistors (N+/P+, with/without SAB)
* ---------------------------------------------------------------------------
.subckt re_ndif_2t POS NEG W=2u L=5u M=1
* TBD: N+ diffusion Rsq not released [ref ~50-150 ohm/sq]
Rbody POS NEG { 'M * 100.0 * L / W' }
.ends
.subckt re_ndif_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 100.0 * L / W' }
.ends
.subckt re_ndif_sab_2t POS NEG W=2u L=5u M=1
* TBD: N+ diffusion SAB Rsq not released [ref ~200-400 ohm/sq]
Rbody POS NEG { 'M * 300.0 * L / W' }
.ends
.subckt re_ndif_sab_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 300.0 * L / W' }
.ends
.subckt re_pdif_2t POS NEG W=2u L=5u M=1
* TBD: P+ diffusion Rsq not released [ref ~100-200 ohm/sq]
Rbody POS NEG { 'M * 150.0 * L / W' }
.ends
.subckt re_pdif_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 150.0 * L / W' }
.ends
.subckt re_pdif_sab_2t POS NEG W=2u L=5u M=1
* TBD: P+ diffusion SAB Rsq not released [ref ~200-400 ohm/sq]
Rbody POS NEG { 'M * 300.0 * L / W' }
.ends
.subckt re_pdif_sab_3t POS NEG SUB W=2u L=5u M=1
Rbody POS NEG { 'M * 300.0 * L / W' }
.ends

* ---------------------------------------------------------------------------
* Well resistors (N-well, AA or STI isolated)
* ---------------------------------------------------------------------------
.subckt re_nwaa_2t POS NEG W=2u L=10u M=1
* TBD: N-well Rsq not released [ref ~0.5-1.5 kohm/sq]
Rbody POS NEG { 'M * 1000.0 * L / W' }
.ends
.subckt re_nwaa_3t POS NEG SUB W=2u L=10u M=1
Rbody POS NEG { 'M * 1000.0 * L / W' }
.ends
.subckt re_nwsti_2t POS NEG W=2u L=10u M=1
* TBD: N-well STI Rsq not released [ref ~1-2 kohm/sq]
Rbody POS NEG { 'M * 1500.0 * L / W' }
.ends
.subckt re_nwsti_3t POS NEG SUB W=2u L=10u M=1
Rbody POS NEG { 'M * 1500.0 * L / W' }
.ends

* ---------------------------------------------------------------------------
* Metal resistors (sheet resistance from tech LEF)
* ---------------------------------------------------------------------------
.subckt re_m1_2t POS NEG W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.1122 * L / W' }
.ends
.subckt re_m1_3t POS NEG SUB W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.1122 * L / W' }
.ends
.subckt re_m2_2t POS NEG W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.0914 * L / W' }
.ends
.subckt re_m2_3t POS NEG SUB W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.0914 * L / W' }
.ends
.subckt re_m3_2t POS NEG W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.0914 * L / W' }
.ends
.subckt re_m3_3t POS NEG SUB W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.0914 * L / W' }
.ends
.subckt re_m4_2t POS NEG W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.0914 * L / W' }
.ends
.subckt re_m4_3t POS NEG SUB W=0.2u L=10u M=1
Rbody POS NEG { 'M * 0.0914 * L / W' }
.ends
.subckt re_tm2_2t POS NEG W=0.4u L=10u M=1
Rbody POS NEG { 'M * 0.0239 * L / W' }
.ends
.subckt re_tm2_3t POS NEG SUB W=0.4u L=10u M=1
Rbody POS NEG { 'M * 0.0239 * L / W' }
.ends
.subckt re_alpa_2t POS NEG W=3u L=10u M=1
Rbody POS NEG { 'M * 0.0151 * L / W' }
.ends
.subckt re_alpa_3t POS NEG SUB W=3u L=10u M=1
Rbody POS NEG { 'M * 0.0151 * L / W' }
.ends
