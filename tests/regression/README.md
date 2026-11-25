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

`ERC_CHECK TRUE` enables the ERC section. Ten checks are named in
`ERC SELECT CHECK`; the three bare PATHCHK statements are defined but not
selected by the official profile. The KLayout port implements all ten
selected checks and reports the three unselected PATHCHK statements as
diagnostics; the diagnostics do not change `ICS55_ERC`. ERC coverage,
differences, and the `--no-erc` switch are documented in
`libs.tech/lvs/README.md`; this remains local self-consistency, not a Calibre
ERC differential.

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
- `lvs_fixture_check.py` + `make_lvs_fixtures.rb` — exact-category KLayout
  LVS source-behavior fixtures.  Cases assert exact MOS/resistor/diode class
  counts, distinct resistor
  terminals, direct top-level ports, stack selection, and schematic-derived
  bulk aliases. A matching extracted/reference pair and an intentionally wrong
  schematic verify that the LVS wrapper returns 0 and nonzero, respectively.
  A MOS child with a physical wrapper tap additionally checks that strict
  comparison defaults to flat extraction: omitted/explicit-flat modes match,
  explicit-deep rejects the hierarchy mismatch, and a 0.01 um W error fails
  close.  `rf_nmos_4t` covers the 4T RF MOS wrapper: the layout extracts the
  core `NM1P2_SVT_LP`, and a wrapper instance must compare only when `wf*nf`
  and `l` match the drawn geometry.  A five-case wrapper smoke then maps each
  RF wrapper family onto its extracted device: `nmos_4t` matches and a 1.5x
  width is rejected, while `nmos_5t`, `nmos_6t`, and `pmos_5t` compare against
  `ICS55_RF_{N,P}MOS_SVT_{5T,6T}` with their extra DNW/PSUB/SUB terminals.
  An ERC smoke runs seven fixtures: a clean inverter, an NMOS tied between
  VDD and VSS (`erc_mn2pg`), ground-only and power-only chains (diagnostics
  only), an unlabeled device (selected `erc_pathcheck_bad` plus diagnostic),
  and bad p-tap/n-tap layouts in `no_well_ties` mode (selected tap and well
  checks). Each case asserts the exact compare verdict, per-check counts,
  and the `checks=10`/`diagnostics=3` summary split.
  These validate local extraction/comparison only; Calibre equivalence stays
  `BLOCKED`.
- `em_deck_check.py` — EM-fixture / stackup / de-embedding contract for the
  RF passives flow.  Asserts the manufacturing `ics55_ind` carries no fixture
  shapes (M1 plane 81/1, ports 300/1-301/1, PGS return 302/1) while the
  generated decks do; runs all four shield variants (`no_pgs`, `pgs_float`,
  `pgs`, `ideal_gnd`) with the dut and pad-only open deck and checks the
  shape counts, spiral removal and ideal-ground geometry equality; exercises
  the structure/feed variants — a `transformer` deck (4 ports on
  300/1-301/1 + 310/1-311/1, two shield rings, 4 PGS_RTN vias per ring, four
  terminal pads in the open deck) and a `cpw` feed (4 TM2 ground strips with
  8 ground vias, 12 total with PGS, shield geometry unchanged, fail-closed
  without the 302/1 `PGS_RTN` stackup layer); verifies
  the `t4` stackup is M1-M4 + T4M1/T4M2 with T4V1/T4V2 and no M5, aligned to
  the LVS `t4` connect chain, and that `PGS_RTN` is a 302 via from the PGS
  top to M1 only when requested; and verifies open-fixture Y de-embedding
  recovers a known series R/L from synthetic S-parameters (needs numpy;
  skipped without it).  Missing KLayout is exit 2 with
  `--require-klayout`.
- `rf_calibration_check.py` — regression for `libs.tech/pex/rf_calib.py`.
  Synthesizes a two-port from an analytic `R + jwL` branch shunted by `C`,
  then asserts the recovered R/L/Q and the interpolated SRF match the closed
  form, that a golden reference reports `CALIBRATED`, that a 20 % detuned
  reference reports `MISMATCH` with a nonzero exit, and that the TT/SS/FF
  varactor sweep returns physical, monotonic C(V,f) while staying
  `UNCALIBRATED`.  Skips only the varactor case when ngspice is unavailable.
- `spice_include_check.py` — resolves every `.include`/`.lib` of the shipped
  foundry SPICE models and reports the resolved file for each, so a clean
  checkout cannot silently miss a dependency (100 includes).  Plain
  `python3`.
- `spice_varactor_check.py` — drives the released varactor subcircuits
  (`var1p2_npd_nw_lp`, `var2p5_npd_nw_lp`) at TT/SS/FF with a 1 V AC
  stimulus while stepping the DC bias: `|C| = |Im(I)|/(2πf)` must stay
  finite and positive, grow with bias, and never jump by more than 1.6x
  between adjacent 0.1 V/0.2 V points.  Requires ngspice (retries without a
  caller-supplied `LD_LIBRARY_PATH` if the C++ runtime is shadowed).
- `magic_lvs_check.py` + `magic_fixtures.rb` + `magic_hier_fixture.rb` +
  `magic_diode_fixture.rb` + `magic_resistor_fixture.rb` — Magic/netgen regression for the promoted tech
  (`libs.tech/magic/ics55.tech`) and the LVS runner
  (`libs.tech/netgen/run_lvs.py`).  Checks exact-centre contact/via stacks at
  CT/V1 through V4/TV2 (`stackable`), n+/p+ tap connectivity, 10x10 um plate
  capacitance against the released LEF area + edge seeds (M1/M2/TM2, 0.5%),
  junction diode extraction (one `dio_1p2_pp_nw_lvt_lp` at 10 um^2/14 um and
  one `dio_1p2_np_pw_lvt_lp` at 10 um^2/13 um, and zero diodes from a plain
  contacted tap cell), hierarchical macro LVS (a `MAGIC_HIER` cell instancing
  `INVX1H7R`, once with the child subckts inline and once as a top-only CDL
  plus `--library`), and eight standard cells across H7CR/H7CL/H7CH.  Six must
  match; OAI33 and INVX16 must report property errors (the documented foundry
  width deviations) with the topology still matching.  The `SNAKE`
  resistor fixture checks four SAB poly segments and their netgen series
  fold into one W/L.  26 checks, ~110 s.
  Missing magic/netgen/klayout is exit 2; a failed check is exit 1.
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
python3 tests/regression/spice_include_check.py
python3 tests/regression/spice_varactor_check.py
python3 tests/regression/drc_fixture_check.py --librelane ../librelane
python3 tests/regression/lvs_fixture_check.py --librelane ../librelane
python3 tests/regression/em_deck_check.py --librelane ../librelane
python3 tests/regression/rf_calibration_check.py
python3 tests/regression/magic_lvs_check.py
```

See `run_alignment.py --help` for options (`--drc`, `--klayout`, `--manifest`,
`--out`, `--no-run`, `--update-hashes`). `--drc` runs the fixture suite and the
full KLayout DRC on each selected GDS/top; findings are retained, not compared
to Calibre.

CI (`.github/workflows/pv-regression.yml`) runs the layer-map, LEF/Liberty,
SPICE-include and varactor checks plus the RF calibration harness on every
push, and the DRC/LVS fixtures plus the EM deck checks under
KLayout via the public LibreLane nix shell
(`github.com/librelane/librelane`, pinned by its flake).
The LVS matrix is not in CI: it needs the `make`-downloaded std-cell GDS.
