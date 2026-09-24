# ICsprout55 corners

Five standard corners: `tt.mod`, `ff.mod`, `ss.mod`, `fs.mod`, `sf.mod`.

The released liberty sets only define TT/SS/FF operating conditions
(voltage/temperature); FS/SF are structural corners with no data.
All scale factors default to 1.0 and are **TBD until foundry models are
released** — they are placeholders, not foundry values.

Liberty corner conditions (released): see the header of each .mod and the
std-cell/IO liberty filenames:
  tt_1p2_25c, ss_1p08_m40, ss_1p08_125, ss_rcworst_1p2_m40,
  ff_1p32_m40, ff_1p32_125, ff_rcbest_1p32_m40, ff_cbest_1p32_125,
  ff_rcbest_1p08_125
  IO: ss_1p08_2p97_{m40,125}, tt_1p2_3p3_25c, ff_1p32_3p63{,_v}[..]
