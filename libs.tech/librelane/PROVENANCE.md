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
