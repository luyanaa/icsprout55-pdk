# ICsprout55 — provisional analog kit (`libs.tech/`)

Analog-facing companion to the released digital ICsprout55 PDK
(65nm-class 1.2V/3.3V LP, salicide). Built entirely from **released data**
(tech LEF, std-cell/IO CDL, IO datasheet, GDS analysis) — see the
`spice/models/README.md` for what is real vs. placeholder.

## Layout

```
libs.tech/
├── klayout/    KLayout technology + layer map + analog PCells
├── spice/models  SPICE device inventory, corners, MC/aging/noise stubs
├── xschem/     schematic symbols for all primitives
├── drc/        KLayout DRC deck (LEF-derived, provisional)
├── lvs/        LVS setup (reserved) + device recognition map
├── macros/     analog macro library (reserved) + IO analog cell inventory
├── pex/        LEF RC seeds + clean-room routed RCX/SPEF extraction
```

## Provisional RCX extraction

`pex/rcx.py` consumes normalized routed geometry JSON and emits one SPEF per
corner.  It can merge released technology-LEF resistance/ground-capacitance
seeds with an explicit process JSON.  Coupling is fail-closed: without
calibrated coupling tables the result is marked `seed_only` and is not
signoff-quality RCX.

```sh
python3 libs.tech/pex/rcx.py \
  --input routed_geometry.json \
  --lef prtech/techLEF/N551P6M_ecos.lef \
  --process-json rcx_process.json \
  --out-dir spef
```

## Static ICS55 binary reconnaissance

For clean-room boundary checking, a pinned upstream `libircx_ics55.so`
(`5c3ac6c3d92fe07ae8620bed5da547b833bea8f53f628db41dcc446e0444d036`)
was inspected with ELF tools and Ghidra on an x86-64 VM. The `.so` was
never loaded or executed. These are reverse-engineering observations, not
released foundry data and not signoff inputs.

The binary exposes a staged module inventory through embedded source paths:
`DataManager`, `TopoBuilder`, `EnvBuilder`, `VarProcessor`, `ResExtractor`,
`CapExtractor`, and `SPEFWriter`. Configuration metadata includes a
`std::vector<ircx::Corner>` plus `corner_name`, `tmpr_list`, ITF source/file,
captable source/file, mapping source/file, thread count, output directory,
and per-stage temporary directories. Built-in corner names/resources include
`TYP`/`TYPICAL`, `RCBEST`, and `RCWORST` with `.itf` and `.captab` files.
The corner/model selector also recognizes `CBEST` and `CWORST`; unknown
selectors fall through to a separate fallback class. The `C` prefix suggests
a capacitance-corner family, but that interpretation and the numerical tables
were not independently recovered.

The process-variable vocabulary is table-driven and substantially richer than
the seed model above:

- scalar keys: `THICKNESS`, `RPSQ`, `ETCH`, `CRT1`, `CRT2`, `RHO`, `RPV`,
  `AREA`, `GLOBAL_TEMPERATURE`, and `HALF_NODE_SCALE_FACTOR`;
- one-dimensional families: `RPSQ_VS_WIDTH`, `CRT1_VS_WIDTH`,
  `CRT2_VS_WIDTH`, `RPSQ_VS_SI_WIDTH`, `CRT_VS_SI_WIDTH`,
  `RPV_VS_AREA`, `CRT1_VS_AREA`, `CRT2_VS_AREA`;
- multi-dimensional families: `RPSQ_VS_WS`, `RHO_VS_WT`,
  `RHO_VS_WS`, `RPSQ_VS_WIDTH_AND_SPACING`,
  `RHO_VS_WIDTH_AND_SPACING`, `ETCH_VS_WIDTH_AND_SPACING`,
  `RHO_VS_SI_WIDTH_AND_THICKNESS`, and `ETCH_VS_WIDTH_AND_LENGTH`;
- selectors/axes: `VALUES`, `SPACINGS`, `WIDTHS`, `LENGTHS`,
  `RESISTIVE_ONLY`, `CAPACITIVE_ONLY`, `CONDUCTOR`, `VIA`, and `VIA_ETCH`.

The clean-room extractor has an explicit opt-in alignment mode for the
recovered scalar and RPSQ-vs-width subset.  It is disabled by default so the
ordinary LEF/process-JSON path remains unchanged:

```json
{
  "ics55_static": {
    "enabled": true,
    "model": "TYP",
    "present_keys": ["TYP|M1|RPSQ"],
    "apply_fields": [
      "thickness_um",
      "resistance_ohm_per_square",
      "resistance_by_width"
    ]
  }
}
```

`libs.tech/pex/ics55_static.py` prints the recovered parameter inventory
without loading the binary:

```sh
python3 libs.tech/pex/ics55_static.py --model TYP --layer M1
```

Recovered scalar/table behavior:

- exact scalar key: `model|layer|parameter`;
- exact RPSQ-vs-width entry key:
  `model|layer|RPSQ_VS_WIDTH|index`;
- 64-bit FNV-1a with offset `0xcbf29ce484222325`, prime
  `0x100000001b3`, and centered 16-bit slices;
- absent-key fallbacks: THICKNESS `1.0001667048142213`, RPSQ
  `1.00023338673991`, ETCH `1.0001333638513772`, CRT1/CRT2
  `1.0001000228885328`;
- recovered layer/corner multiplier arrays and selector classes are emitted
  in the readout;
- THICKNESS → `thickness_um`, RPSQ →
  `resistance_ohm_per_square`, and RPSQ_VS_WIDTH →
  `resistance_by_width` are the only applied mappings.  The width-table
  values use the recovered `q_11*0.006 + q_29*0.002` perturbation;
- ETCH, CRT1/CRT2, RHO/RPV/AREA, and all remaining table families stay
  readout-only.

`present_keys` must come from an actual ITF/CAPTAB source; listing a scalar
key only selects the recovered hashed branch and does not fabricate a process
value.  The extractor still does not claim proprietary ITF/CAPTAB
interpolation or signoff coupling data.  The static alignment report is
included in each summary and names every unapplied parameter family.

Topology evidence is direct: RTTI/string metadata names `IdbNet`, `IdbPin`,
`IdbSpecialWireSegment`, `IdbVia`, routing/cut/masterslice/implant layers,
layer and parallel-spacing tables, `IdbInstance`, and `IdbHalo`. Diagnostics
refer to track/pin grids, via removal, stripe cutting, segment connectivity,
via masters, illegal cut layers, and missing pin layer shapes. The current
clean-room extractor therefore stays normalized-geometry based and
fail-closed; it does not claim IDB/DEF compatibility.

## Analog primitives covered

| Family | Devices | Status |
|---|---|---|
| Core MOS | nm1p2/pm1p2 {svt,lvt,hvt}\_lp (L=60n) | names/geometry real; model params TBD |
| IO MOS | nm3p3_lp / pm3p3_lp (L=400-650n) | names/geometry real; model params TBD |
| Resistors | re_ndif/pdif/nwaa/nwsti/npo/ppo/hrpo/m1..m4/tm2/alpa [\_sab] 2t/3t | metal Rsq real (LEF); re_ppo_sab ≈850 Ω/sq derived; rest TBD |
| Caps | mom_2t/3t | TBD |
| Varactors | var1p2/var3p3_npd_nw_lp | TBD |
| Diodes/ESD | dio_1p2\* (pp_nw/np_pw, lvt/hvt), dio_3p3_pp_nw_lp | TBD |
| Guard rings / multi-finger | PCells + xschem symbols | layout templates (measured geometry) |
| BJT / inductors | — | **not present** in released data |

## Provenance & honesty notes

- Every layer number, device name, terminal order, drawn gate length and
  sheet resistance in this tree traces to a file in the released PDK or to
  GDS measurements (methods: klayout scripting, geometry extraction).
- Values marked `TBD` / `[ref …]` are **not** foundry data. Do not use
  them for tapeout decisions.
- The PDK README states silicon verification is pending (first engineering
  shuttle Dec 2025); treat all parameters as pre-silicon.
- License: Apache-2.0 (same as the PDK).
