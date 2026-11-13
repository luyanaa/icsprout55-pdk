# ICsprout55 openEMS FDTD workflow

3D full-wave EM simulation of the 1TM+ALPA1 inductor (`ics55_ind`) using the
locally installed openEMS FDTD solver.  This is a cross-check of the Palace
frequency-domain model in `libs.tech/pex/palace/` — same EM deck
(`palace/ics55_ind_em.gds`) and the same stackup (`palace/ics55_stackup.xml`),
different solver engine and port realization.

## Environment

- openEMS installed at `/opt/openEMS` (solver `bin/openEMS`, viewer
  `bin/AppCSXCAD`, Python bindings in `venv/`).
- Run everything with `/opt/openEMS/venv/bin/python` (has CSXCAD, openEMS,
  numpy, matplotlib; `gds2palace` is also installed there for the Palace
  flow).
- For the `--preview` 3D viewer, put `/opt/openEMS/bin` on `PATH` so
  `AppCSXCAD` resolves.

## Usage

```sh
export PATH=/opt/openEMS/bin:$PATH

# 1) build the model and inspect it in AppCSXCAD (writes CSX, no solve)
/opt/openEMS/venv/bin/python run_inductor_2port.py --preview

# 2) run the 0.1-10 GHz FDTD sweep and post-process
/opt/openEMS/venv/bin/python run_inductor_2port.py --simulate

# 3) reuse existing FDTD data
/opt/openEMS/venv/bin/python run_inductor_2port.py --postprocess
```

Outputs land in `openems/output/ics55_ind_2port_data/`:

- `ics55_ind_2port.s2p` — Touchstone S-parameters
- printed L/Q/Csh table (series branch of the pi equivalent, same convention
  as `palace/extract_lq.py`: `Zs = -1/Y21`)
- PNG plots (`S-parameters.png`, `Inductance.png`, `Q factor.png`)

## Model

- GDS: `../palace/ics55_ind_em.gds` (TM2 spiral 103/1, RDL underpass 123/1,
  RV 120/1, PGS stripes on layer 2, M1 fixture ground plane 81/1,
  port-source lines 300/1 and 301/1 — all purpose 1).
- Ports: two vertical lumped via-ports, M1 ground plane → TM2, 50 ohm,
  following the IHP via-port recipe.  Port excitation is simulated
  separately per port and combined into the two-port S-matrix.
- Sweep: Gauss pulse covering 0.1–10 GHz, `--fstart/--fstop/--numfreq`
  control the sampling.  Default boundary: PEC on all six faces
  (`--boundary MUR|PML_8` for radiating structures).
- Mesh: `--cellsize` in the conductor region (default 1.0 µm; the PGS uses
  the 2/2 µm EM-deck stripes, not the 1/1 µm production ones),
  `cells_per_wavelength=20` sets the global cap at fstop.

## Files

- `run_inductor_2port.py` — model script (IHP `run_inductor_2port.py` port).
- `modules/` — generic workflow modules copied from the IHP SG13G2 openEMS
  workflow (`openems_ihp_sg13g2`, Volker Muehlhaus).  Adaptations:
  - `util_stackup_reader.py` tolerates missing `Permittivity` /
    `DielectricLossTangent` attributes on conductors (the gds2palace
    stackup schema omits them; conductors default to eps=1, tand=0).
  - `util_simulation_setup.py` only launches AppCSXCAD in `--preview`
    mode (a failed viewer warns instead of `sys.exit(1)`), and the
    z-mesh exclusion list now names the ICS55 thin dielectrics
    (IMD1–5, PMD, RDLILD) instead of IHP SiO2/LBE.  The 200 µm
    `Substrate` stays meshed because it is the lossy return path that
    sets the inductor Q.

## Caveats

- ICS55 stackup Z values are absolute (substrate top at 200 µm); the XML
  has no `<Substrate Offset>` element, which is correct for this schema.
- The M1 layer in the EM deck is the fixture ground plane, not a signal
  layer — via ports land on it by name.  Do not re-purpose the M1 EM-GND
  plane in the deck.
- The RV/RDL stack forces ~3 nm vertical cells near z=204.3 um (RV
  thickness and adjacent interfaces), so the CFL timestep is ~1e-17 s
  regardless of the xy cellsize.  A broadband 0.1-10 GHz Gauss pulse
  therefore needs tens of millions of timesteps; plan overnight runs for
  signoff-quality data, or use `--nr-ts` to bound the sweep and accept a
  truncated low-frequency skirt.
- IMPORTANT: openEMS only writes the port_ut_N / port_it_N ASCII files at
  the END of a run.  A run killed early (OOM, reboot, Ctrl-C) leaves a
  one-line file and no recoverable S-parameters.  Always give `--nr-ts`
  enough headroom that the run can finish; do not count on the et/ht
  dumps for post-processing.
- Smoke status (Nov 2026): model builds headless (189 k cells at
  `--cellsize 3.0 --margin 100`), both excitations step correctly at
  ~62 MC/s; a 300 k-step run completed and wrote port data, but a
  follow-on host restart truncated the evaluation before `.s2p` was
  written.  End-to-end validation of the post-processing chain is still
  open.
