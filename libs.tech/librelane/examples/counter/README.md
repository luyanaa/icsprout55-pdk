# LibreLane flow example — `counter`

Minimal RTL-to-GDS run through LibreLane + OpenROAD + KLayout, exercising the
ICS55 PDK integration shipped under `libs.tech/librelane/` and
`libs.tech/{drc,lvs,klayout,magic,pex}/`.

## Prerequisites

- `klayout` (>= 0.30), `librelane` (>= 3.0), `openroad`, `yosys`, `magic`
- PDK views populated: run `make unzip` at the repo root (pulls `libs.ref/`
  GDS + liberty tarballs). `libs.ref/` must exist before the flow runs.

## Run

The LibreLane config resolves views as `$PDK_ROOT/$PDK/libs.{tech,ref}/...`,
so `PDK_ROOT` must contain a `ics55/` directory that holds this repo's
`libs.tech` and `libs.ref`.  A symlink farm in `/tmp` (or a worktree) is the
simplest way — nothing inside the checkout needs to move:

```bash
export PDK_ROOT=/tmp/ics55_pdkroot
mkdir -p $PDK_ROOT/ics55
ln -sfn /grid/icsprout55-pdk/libs.tech $PDK_ROOT/ics55/libs.tech
ln -sfn /grid/icsprout55-pdk/libs.ref  $PDK_ROOT/ics55/libs.ref
export PDK=ics55

# Register the ICS55.KLayoutLVS step (substitutes Netgen.LVS, see config.yaml)
export PYTHONPATH=/grid/icsprout55-pdk/libs.tech/librelane${PYTHONPATH:+:$PYTHONPATH}

cd /grid/icsprout55-pdk/libs.tech/librelane/examples/counter
librelane config.yaml --pdk ics55 --pdk-root $PDK_ROOT --manual-pdk \
    --run-tag counter_ics55 --overwrite
```

## What the flow runs

`meta.flow: Classic` with the following substitutions (see `config.yaml`):

- `OpenROAD.WriteCDL` inserted before LVS — emits the design CDL from ODB.
- `ICS55.KLayoutLVS` replaces `Netgen.LVS` — runs
  `libs.tech/lvs/ics55.lvs` on the KLayout-streamed GDS against the merged
  CDL (design + std-cell + IO).  The plugin converts the library CDLs with
  `scripts/cdl_convert.py` before concatenation, because the vendor CDLs
  share helper-subckt names (e.g. `NAND2`/`nand2`, `TG`, `TSINV`) that
  collide case-insensitively.
- `Magic.DRC`, `Magic.SpiceExtraction`, `Magic.StreamOut`, `Magic.WriteLEF`,
  `Odb.CheckDesignAntennaProperties`, `KLayout.XOR` and their checkers are
  disabled: the Magic tech file only models parasitic extraction (no
  DRC/LEF-stream-out support; `Odb.CheckDesignAntennaProperties` consumes
  the LEF that `Magic.WriteLEF` would have produced), and XOR against a
  golden GDS is not part of this flow.

`Checker.LVS` (metric `design__lvs_error__count`) fails the flow if the
KLayout LVS verdict is not `ICS55_LVS_COMPARE=PASS` /
`Congratulations! Netlists match`.

## KLayout LVS / DRC outside the flow

For ad-hoc runs use the same deck directly:

```bash
klayout -b -r libs.tech/lvs/ics55.lvs -rd input=<cell.gds> -rd top=<CELL> \
        -rd schematic=<cell.cdl> -rd report=<out.lvsdb>
klayout -b -r libs.tech/drc/ics55_drc.drc -rd input=<cell.gds> -rd report=<out.lyrdb>
```

`libs.tech/lvs/run_lvs.py` wraps the LVS invocation with result parsing.
