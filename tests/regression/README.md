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
  An explicit compare mismatch is `FAIL`; runner/extraction errors are
  `BLOCKED`, and failed runs never consume extracted netlists.
- `nix_shell.py` — supplies LibreLane’s locked nixpkgs revision to `nix-shell`;
  explicit `--librelane` uses this shell before any host KLayout binary.
  Alignment and DRC harnesses expand `~` before shell selection, so quoted
  `--librelane` paths still select the pinned environment.
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
  MOM profiles. Added width/spacing and enclosure checks include strict
  threshold pairs for POLY width/space, CT active enclosure, M1 spacing,
  ordinary via spacing/upper enclosure, and T4V2 spacing/lower/upper enclosure
  plus datatype-7 bar width.
  Existing cases cover bar-via source unions, metal-slot spacing masks,
  strict area/hole and density boundaries, marker waivers, backup windows,
  dummy halos, MOM labels, and special-marker relations. Generic
  space/enclosure operators do not reproduce every Calibre ABUT/SINGULAR or
  directional GOOD qualifier; this is not a Calibre differential. Missing
  KLayout is `BLOCKED` (exit 2).
  cases assert exact MOS/resistor/diode class counts, distinct resistor
  terminals, direct top-level ports, stack selection, and schematic-derived
  bulk aliases. A matching extracted/reference pair and an intentionally wrong
  schematic verify that the LVS wrapper returns 0 and nonzero, respectively.
  A MOS child with a physical wrapper tap additionally checks that strict
  comparison defaults to flat extraction: omitted/explicit-flat modes match,
  explicit-deep rejects the hierarchy mismatch, and a 0.01 um W error fails
  the unchanged exact strict W/L contract.
  These validate local extraction/comparison only; Calibre equivalence stays
  `BLOCKED`.
- `out/drc_fixtures/` and `out/lvs_fixtures/` — default fixture reports and
  generated inputs. `drc_fixture_check.py` writes its report to
  `out/drc_fixtures/drc_fixture_check.json`.

Frozen-input policy: `frozen_hashes` pins LVS/DRC runners and rule modules,
fixture harnesses and generators, the locked Nix-shell helper, official
Calibre DRC sources, layer maps, the selected DRC profile, and crosswalk data.
Any missing or changed hash fails the run. Regenerate deliberately after
intentional changes with `run_alignment.py --update-hashes`.

## Usage

```sh
python3 tests/regression/run_alignment.py --librelane ../librelane --cells INVX1H7H,INVX3H7H,INVX4H7H
python3 tests/regression/layer_map_check.py
python3 tests/regression/lef_liberty_check.py
python3 tests/regression/drc_fixture_check.py --librelane ../librelane
python3 tests/regression/lvs_fixture_check.py --librelane ../librelane
```

See `run_alignment.py --help` for options (`--drc`, `--klayout`, `--manifest`,
`--out`, `--no-run`, `--update-hashes`). `--drc` runs the fixture suite and the
full KLayout DRC on each selected GDS/top; findings are retained, not compared
to Calibre.

CI (`.github/workflows/pv-regression.yml`) runs the layer-map and LEF/Liberty
checks on every push, and the DRC fixtures under KLayout via the public
LibreLane nix shell (`github.com/librelane/librelane`, pinned by its flake).
The LVS matrix is not in CI: it needs the `make`-downloaded std-cell GDS.
