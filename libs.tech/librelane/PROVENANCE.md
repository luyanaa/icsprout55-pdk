# libs.tech/librelane - LibreLane flow integration for ICsprout55

The files in this directory come from the open-source LibreLane implementation
flow for the ICsprout55 PDK:

    https://github.com/ckdur/icsprout55-openpdk

(upstream path `icsprout55/libs.tech/librelane/`, commit as fetched 2026-09-25).
They are integrated here with their original Apache-2.0 headers preserved.

## What is integrated (all non-RCX assets)

- `config.tcl` - LibreLane flow configuration (process, standard-cell and IO
  libraries, power nets, technology LEF, timing corners, routing layers,
  GDS stream-out).
- `ICsprout_55LLULP1233_IO_251013/config.tcl` - IO-library flow configuration.
- `ics55_LLSC_H7CR/config.tcl` - standard-cell flow configuration.
- `ics55_LLSC_H7CR/{latch,mux2,mux4,tribuff}_map.v` - synthesis cell mappings.
- `ics55_LLSC_H7CR/{pnr,synth}_exclude.cells` - cell exclusion lists.
- `ics55_LLSC_H7{C,R,L,H}/tracks.info` - routing tracks.
- `N551P6M_ecos.lef` - the released technology LEF (from the PDK itself,
  `prtech/techLEF/N551P6M_ecos.lef`, not an upstream artifact).
- `librelane_plugin_ics55/` - LibreLane plugin providing the
  `ICS55.KLayoutLVS` step (upstream `KLayout.LVS` only runs for the IHP
  PDKs).  Modelled on upstream `icsprout55/libs.tech/librelane/
  librelane_plugin_ics55/`; this copy also converts the library CDLs with
  `scripts/cdl_convert.py` before concatenating them with the design CDL
  (upstream performs the same conversion at install time via `install.sh`,
  whereas our `libs.ref/` keeps the vendor CDLs verbatim).
- `scripts/cdl_convert.py` - upstream `hacking/cdl_convert.py`, verbatim
  except for the relocated header path.  Renames per-library helper
  subckts (INV/NAND2/TG/TSINV in the std cells; `nand2`/`nor2`/`MUX_PAD`/
  `inv*` in the IO) so the merged LVS netlist parses cleanly.
- `examples/counter/` - worked example: RTL-to-GDS through the Classic
  flow with `ICS55.KLayoutLVS` substituted for `Netgen.LVS` (see its
  README.md for the exact invocation).

## LEF/GDS pairing gotcha (inherited)

The `_ecos` cell LEF places signal pins on MET2 (+VIA1); the matching
layout is `gds/<lib>_M2.gds`.  The plain `<lib>.gds` keeps pins on MET1 and
makes every routed pin open in LVS.  `config.tcl` already pairs
`CELL_LEFS=<lib>_ecos.lef` with `CELL_GDS=<lib>_M2.gds` for the 7-track
libraries — keep them in sync if a new SCL is added.

## What is EXCLUDED (RCX-related, deliberately)

The upstream repository also publishes RC extraction data under
`hacking/decrypted_output/` (StarRC-format `kItf*.txt` / `kCaptab*.txt` for
all corners) and the `generate_rcx_rules/` OpenRCX generation scripts.

**Those values are NOT clean-room and are NOT integrated here.**  They were
obtained by XOR-decrypting the proprietary ECOS iRCX library
(`libircx_ics55.so` from openecos-projects/ecc-tools); the upstream's own
`hacking/NOTES.md` documents the decryption (ghidra addresses, XOR keys,
ciphertext offsets).  The released ICS55 PDK contains no absolute thicknesses,
permittivities or capacitance tables - the only clean-room RC sources are the
released LEFs (RPSQ, via resistance, capacitance seeds), which is what
`libs.tech/pex/` and the palace stackup use.

Anyone who wants the foundry-accurate RC values may use the upstream's
decrypted values instead of our clean-room estimates - at their own
discretion regarding the provenance/legal status of that data.  See
`libs.tech/pex/README.md` "RCX provenance limit" for the full statement.

## License

Copyright 2026 Ckristian Duran.  Licensed under the Apache License, Version
2.0.  The tcl/verilog files carry the header inline; the data files
(tracks.info, *.cells) are machine-parsed formats that cannot contain
comments - their license is covered by this file and the repository LICENSE.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
