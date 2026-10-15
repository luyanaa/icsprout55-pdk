# ICS55 PV alignment regression

This directory holds the deterministic regression scaffold for aligning the
open-source KLayout DRC/LVS ports (`libs.tech/drc`, `libs.tech/lvs`) with the
officially released Calibre physical-verification collateral (`pv/DRC`,
`pv/LVS`).

The alignment is **semantic and structural**, never a line-by-line syntax port.
The official `pv/**` files are the immutable source of truth; the KLayout ports
must be traceable to them through crosswalks and this regression harness.

## Oracle contract (read first)

- No local Calibre executable or official run artifacts were found during this
  audit. License availability is unverified.
- Consequences (fail-closed policy):
  - `official_oracle` is `UNAVAILABLE`.
  - Cross-tool equivalence (KLayout vs Calibre) is `BLOCKED`, never `PASS`.
  - KLayout self-consistency and successful deck execution are local evidence,
    not Calibre parity.
- The runner does not parse Calibre reports. Adding a report path to the
  manifest alone cannot upgrade a result; equivalence requires a same-GDS,
  same-top, same-profile comparison with retained tool/deck/input provenance.

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

### Calibre DRC profile (frozen)

Source: `pv/DRC/ICsprout_CalDRC_55LLULP1233_REV1_0_OS.drc` and `.ant`.

| Option | Value |
|---|---|
| `total_metal` / `top_metal` | 6 / 1 |
| Top stack | T4V2/T4M2 enabled; T2V1/T2M1, T2V2/T2M2, T4V1/T4M1, T8V1/T8M1, T8V2/T8M2 disabled |
| `OPEN_RECOMMENDED_ON` | NO |
| `Density_rules` | YES |
| `LATCH_UP_CHECK`, `DUP_CHECK`, `Metal_Slot_CHECK`, `MOM_CHECK` | YES |
| `ESD_CHECK`, `Poly_EFuse_CHECK` | YES (despite contradictory nearby comments) |
| Main DRC max results | ALL |
| Antenna max results / vertices | 1000 / 199 |


## Files

- `klayout_alignment_manifest.json` — frozen matrix: official profile, oracle
  state, core cell matrix (H7H/H7L/H7R), stress sentinels, DRC rule-family
  coverage, and expected hashes.
- `official/rule_map.json` — explicit Calibre↔KLayout LVS device crosswalk;
  absent entries are not claimed equivalent. The DRC name/value inventory is
  `official/drc_rule_comparison.json`; its `covered` labels do not mean
  semantic equivalence.
- `run_alignment.py` — invokes the existing LVS/DRC runners, hashes observed
  inputs/decks/outputs, normalizes MOS graphs, and emits `PASS | FAIL | BLOCKED |
  UNAVAILABLE` records. It recalculates the static DRC crosswalk counts.
- `normalize_lvs.py` — canonical MOS-graph normalizer for extracted netlists
  and CDL-derived expectations (model names case-folded, named-net aliasing,
  units, optional geometry presence vs zero).
- `layer_map_check.py` — layer-mapping consistency harness: cross-checks the
  official Calibre LAYER MAP tables (`pv/DRC`, `pv/LVS`), the official GDS
  layer map (`techfile/icsprout55.layermap`), the KLayout stream map
  (`libs.tech/klayout/tech/ics55.map`), and the deck `input(g, d)` usage
  (`layers_def.drc`, `layers_definitions.lvs`).  Also evaluates which metal
  and via gates the official DRC deck enables for the frozen profile and
  requires the KLayout port to cover exactly that set.  Catches silent
  stream-in drops (e.g. an unmapped metal) and misaliased layer numbers.
  Plain `python3`, no nix-shell needed.
- `lef_liberty_check.py` — LEF↔Liberty pin-direction consistency per
  `libs.ref` library (cell set agreement, per-pin directions, corner
  agreement).  Would have caught the IO LEF pin-direction bug fixed by the
  upstream merge.  Libs without a local Liberty (std-cell liberties are a
  `make` download) are SKIPPED.  Plain `python3`.
- `drc_fixture_check.py` + `make_fixtures.rb` — exact-category KLayout
  source-behavior fixtures for FEOL/BEOL, dummy/slot, special, density, and
  MOM profiles. They cover strict area/hole boundaries, strict and near-threshold
  density boundaries, NODRC/SRAMALL waivers, source via-bar/rotation behavior,
  density backup windows, small-layout padding and dummy halos, MOM stack
  labels, and pad/special marker relations. Reports record profile/version and
  input hashes. This is not Calibre differential evidence. Missing KLayout is
  `BLOCKED` (exit 2), not a passing check.
- `out/` — generated outputs.

Frozen-input policy: `frozen_hashes` pins both LVS and DRC runners/rule
modules, the official Calibre DRC sources, DRC layer maps, selected DRC profile,
crosswalk, and fixture inputs. Any missing or changed hash fails the run.
Regenerate deliberately after intentional changes with `run_alignment.py --update-hashes`.

## Usage

```sh
nix-shell ~/Documents/librelane --run 'python3 tests/regression/run_alignment.py --cells INVX1H7H,INVX3H7H,INVX4H7H'
python3 tests/regression/layer_map_check.py
python3 tests/regression/lef_liberty_check.py
python3 tests/regression/drc_fixture_check.py            # klayout via nix-shell
```

See `run_alignment.py --help` for options (`--drc`, `--klayout`, `--manifest`,
`--out`, `--no-run`, `--update-hashes`). `--drc` runs the fixture suite and the
full KLayout DRC on each selected GDS/top; findings are retained, not compared
to Calibre.

CI (`.github/workflows/pv-regression.yml`) runs the layer-map and LEF/Liberty
checks on every push, and the DRC fixtures under KLayout via the public
LibreLane nix shell (`github.com/librelane/librelane`, pinned by its flake).
The LVS matrix is not in CI: it needs the `make`-downloaded std-cell GDS.
