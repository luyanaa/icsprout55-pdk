# ICS55 PV alignment regression

This directory holds the deterministic regression scaffold for aligning the
open-source KLayout DRC/LVS ports (`libs.tech/drc`, `libs.tech/lvs`) with the
officially released Calibre physical-verification collateral (`pv/DRC`,
`pv/LVS`).

The alignment is **semantic and structural**, never a line-by-line syntax port.
The official `pv/**` files are the immutable source of truth; the KLayout ports
must be traceable to them through crosswalks and this regression harness.

## Oracle contract (read first)

- No Calibre binary is available locally and the released quick-start PDF
  documents a GUI-only flow. There are therefore **no official Calibre result
  artifacts in the repository**.
- Consequences (fail-closed policy):
  - `official_oracle` is `UNAVAILABLE` for every fixture.
  - Cross-tool equivalence (KLayout vs Calibre) is `BLOCKED`, never `PASS`.
  - A KLayout self-consistency `PASS` (extracted vs CDL) is *not* evidence of
    Calibre parity and must not be presented as such.
  - `PASS` for a fixture requires provenance hashes and the absence of any
    unsupported-semantic diagnostic.
- To upgrade a fixture from `BLOCKED` to `PASS` against the official deck, an
  external Calibre run report plus its hashes must be supplied and registered
  in `klayout_alignment_manifest.json` (`official_reports`).

## Official default profile (frozen)

Frozen from `pv/LVS/ICsprout_CalLVS_55LLULP1233_REV1_0_OS.lvs:19-179` and
`pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc:13-305`. The KLayout ports
are aligned to this profile first; other profiles remain explicit gaps.

| Option | Value |
|---|---|
| HALF_NODE | TRUE |
| IO | TGOX_33 |
| TOTALMETAL | 6 |
| TOP_METAL_NUM | SINGLE |
| TM1_TYPE | 4 |
| TM2_TYPE | 4 |
| RC_EXTRACT | FALSE (LVS-only) |
| RC_EXTRACT_FLOW | CCI |
| BACK_ANNOTATION_FLOW | 2 |
| ERC_CHECK | TRUE |
| GATE_FLOATING_CHECK | FALSE |
| NWELL_FLOATING_CHECK | FALSE |
| NWELL_NOT_TO_POWER_CHECK | TRUE |
| PWELL_NOT_TO_GROUND_CHECK | TRUE |
| CASE_SENSITIVITY | TRUE |
| SOFT_CHECK | TRUE |
| WELL_PIN | YES |

## Files

- `klayout_alignment_manifest.json` — frozen matrix: official profile, oracle
  state, core cell matrix (H7H/H7L/H7R), stress sentinels, DRC rule-family
  coverage, and expected hashes.
- `official/rule_map.json` — explicit Calibre↔KLayout rule/device equivalence
  map; populated as phases land. Entries absent from this map are not claimed
  equivalent.
- `run_alignment.py` — invokes the existing LVS/DRC runners, hashes every
  input/deck/output, normalizes MOS graphs, and emits `PASS | FAIL | BLOCKED |
  UNAVAILABLE` records.
- `normalize_lvs.py` — canonical MOS-graph normalizer for extracted netlists
  and CDL-derived expectations (model names case-folded, named-net aliasing,
  units, optional geometry presence vs zero).
- `out/` — generated outputs (git-ignored).

## Usage

```sh
nix-shell ~/Documents/librelane --run 'python3 tests/regression/run_alignment.py --cells INVX1H7H,INVX3H7H,INVX4H7H'
```

See `run_alignment.py --help` for options (`--drc`, `--manifest`, `--out`,
`--no-run`).
