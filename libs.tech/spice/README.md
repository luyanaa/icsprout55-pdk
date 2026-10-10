# ICsprout55 SPICE device models — FOUNDRY DATA

**This directory now holds the ICsprout foundry model set, not
reverse-engineered substitute cards.** The previous PTM-based fitted library
(`models/fitted/`), the fitting harness (`models/fit/`) and the TBD stub
library (`models/ics55.m`, `mos_core.l`, `mos_io.l`, `diode.l`, `resistor.l`,
`capacitor.l`, `corners/`, `monte_carlo/`, `aging_noise/`) have been removed.

## Licence and provenance — read first

The files under `foundry/` are **ICsprout vendor data**. They are **not**
covered by this repository's Apache-2.0 licence and are **not** released PDK
collateral. They are included **for educational / research evaluation only**.
Redistribution and commercial use are governed by the vendor's terms. Obtain
the models from ICsprout for any production or signoff use.

Every imported file carries a provenance banner naming the vendor, the
upstream mirror, the pinned commit and the licence position. `foundry/ORIGIN.json`
records the upstream URL and the SHA-256 of both the upstream and imported
bytes for all 54 files. Re-import with:

```sh
python3 libs.tech/spice/import_foundry_models.py
```

Source: `https://github.com/ckdur/icsprout55-openpdk`, path
`icsprout55/libs.tech/{hspice,ngspice}`, pinned commit
`195870e61e9fa92d049df2daa4a7f5000c6aad3e` (2026-10-08).

## Contents

```
foundry/
├── ORIGIN.json            upstream commit + per-file SHA-256 manifest
├── hspice/                vendor "hspice" variant (upstream hspice/ tree)
│   ├── ICsprout_55LLULP1225_V1p1_hsp.lib   top .lib with corner sections
│   ├── model_wrapper1_hsp.lib              MOS corners + mos_total wrappers
│   ├── model_wrapper2_hsp.lib              bjt/dio/res/var/mom corners
│   ├── mos/*.mdl                           BSIM4 4.5 model cards (binned)
│   ├── bjt/ dio/ res/ var/ mom/            device model/subckt files
│   └── readme.txt                          vendor usage notes (release 1.1)
└── ngspice/               vendor "ngspice" variant (byte-differs from hspice)
```

Both variants define the same devices and the same 13 MOS subcircuits
(`nm1p2_{svt,lvt,hvt}_lp`, `pm1p2_{svt,lvt,hvt}_lp`, `nnat1p2_lp`,
`nm2p5_lp`/`pm2p5_lp`, `nmod3p3_lp`/`pmod3p3_lp`, `nnat2p5_lp`,
`nnatod3p3_lp`) covering exactly the model names used by the released
standard-cell and IO CDL.

## Which variant to use

Measured with `validate_model_variants.py` (3 repeats per case; artifact
`/tmp/ics55_model_variant_validation.json`):

| variant | ngspice | Xyce |
|---|---|---|
| `hspice/` | parses; **non-reproducible** (wrapper defaults `mismod=1`, so the `agauss` mismatch terms are live in ngspice) | parses; reproducible |
| `ngspice/` | parses; **reproducible** (wrapper defaults `mismod=0`) | parses; reproducible |

Recommendation:

- **ngspice → `foundry/ngspice/`.** Its wrapper defaults `mismod=0`, so a
  plain `op` is deterministic (~`-5.4295e-10 A` for the probe device). With
  the `hspice` tree every run differs. Enable mismatch explicitly with
  `mismod=1` when you actually want Monte Carlo sampling; ngspice's RNG is
  then seeded from `.spiceinit` / `set rndseed=...`.
- **Xyce → either tree.** Xyce produces identical results from both because
  it does not evaluate the wrapper's `agauss` mismatch terms outside a Monte
  Carlo analysis. Prefer `foundry/hspice/` so the simulator matches the
  vendor's documented tool, and rely on Xyce's own Monte Carlo for sampling.

The two trees are byte-identical for the top `.lib`, `readme.txt`, all BJT and
diode models, and `model_wrapper2_hsp.lib`. Real differences:

1. wrapper default `mismod` in `model_wrapper1_hsp.lib`, `mom/mom.ckt`,
   `res/resistor.ckt`, `var/varactor.ckt` (`1` in hspice, `0` in ngspice);
2. bin-boundary numeric literal precision (e.g. `5.4E-8` vs `5.39946e-08`)
   in the `mos/*.mdl` cards;
3. a duplicated `+` continuation in a few expression strings.

## Usage

```spice
* ngspice, typical corner
.lib 'libs.tech/spice/foundry/ngspice/ICsprout_55LLULP1225_V1p1_hsp.lib' tt_mos
X1 d g s b nm1p2_lvt_lp w=1u l=60n nf=1 mismod=0
```

```spice
* Xyce, typical corner
.lib 'libs.tech/spice/foundry/hspice/ICsprout_55LLULP1225_V1p1_hsp.lib' tt_mos
X1 d g s b nm1p2_lvt_lp w=1u l=60n nf=1
```

Corner sections: `tt_mos`, `ss_mos`, `ff_mos`, `snfp_mos`, `fnsp_mos`,
`mc_mos`; passives: `tt_/ff_/ss_/mc_{bjt,dio,res,var,mom}`; plus `pre_layout`.
The vendor requires `SCALE = 0.9` (already set inside the corner sections) and
`pre_layout=1` only for pre-layout contact-to-poly parasitic estimation.

## Notes and limits

- The BSIM4 cards are version 4.5; Xyce warns and uses its oldest supported
  version (4.6.1). ngspice 47 evaluates them directly.
- Some `pbswgd`/`pbswgs` values are below 0.1; Xyce clamps them and warns.
  These warnings are expected and non-fatal.
- Resident internal models use vendor binned cards (`binunit=2`); instance
  `w`/`l`/`nf`/`sa`/`sb` must be passed through the wrapper subcircuits.
- Parasitic-estimation tooling no longer depends on these files; see
  `../pex/README.md` for the RC extraction stack and its StarRC calibration.
