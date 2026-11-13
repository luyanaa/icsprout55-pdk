# Copyright 2026 Yan Lu with DeepSeek V4 Flash and GPT-5.6-Luna
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ============================================================================
# ICsprout55 openEMS FDTD model script — 2-port inductor EM simulation.
#
# Ported from the IHP SG13G2 openEMS workflow
# (libs.tech/openems/openems_ihp_sg13g2, Volker Muehlhaus) using the local
# modules/ copies.  The EM deck is the same ics55_ind_em.gds as the Palace
# flow: TM2 spiral + RDL underpass + RV transitions, PGS patterned shield,
# M1 fixture ground plane, and the gds2palace port-source lines on 300/301
# (vertical via-ports from the M1 ground plane up to TM2).
#
# Environment:
#   /opt/openEMS/venv/bin/python run_inductor_2port.py [--simulate|--postprocess]
#
#   --preview     (default) build the model, write CSX, launch AppCSXCAD
#   --simulate    run the FDTD sweep and write .s2p + printed L/Q table
#   --postprocess reuse existing FDTD data, skip the solve
#
# openEMS binaries must be on PATH (export PATH=/opt/openEMS/bin:$PATH) for
# the AppCSXCAD preview; the solver itself is invoked through the openEMS
# Python module.
# ============================================================================

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'modules'))

import util_stackup_reader as stackup_reader       # noqa: E402
import util_gds_reader as gds_reader               # noqa: E402
import util_utilities as utilities                 # noqa: E402
import util_simulation_setup as simulation_setup   # noqa: E402
import util_meshlines as util_meshlines            # noqa: E402

from openEMS import openEMS                        # noqa: E402
import numpy as np                                 # noqa: E402

# ======================== command line =====================================

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
mode = ap.add_mutually_exclusive_group()
mode.add_argument('--preview', action='store_true',
                  help='build the model and open AppCSXCAD (default)')
mode.add_argument('--simulate', action='store_true',
                  help='run the FDTD sweep and post-process')
mode.add_argument('--postprocess', action='store_true',
                  help='reuse existing FDTD data without re-running')
ap.add_argument('--gds', default=os.path.join(HERE, '..', 'palace', 'ics55_ind_em.gds'),
                help='GDSII with device and port-source shapes (300/301)')
ap.add_argument('--stackup', default=os.path.join(HERE, '..', 'palace', 'ics55_stackup.xml'),
                help='stackup XML (gds2palace schemaVersion 2.0)')
ap.add_argument('--name', default='ics55_ind_2port', help='model basename')
ap.add_argument('--fstart', type=float, default=0.1e9, help='sweep start (Hz)')
ap.add_argument('--fstop', type=float, default=10e9, help='sweep stop (Hz)')
ap.add_argument('--pulse-width', type=float, default=0.0,
                help='Gauss pulse width in s (0 = derive from fstop)')
ap.add_argument('--numfreq', type=int, default=201, help='S-parameter sample count')
ap.add_argument('--cellsize', type=float, default=1.0,
                help='mesh cell size in the conductor region (um)')
ap.add_argument('--cells-per-wavelength', type=int, default=20)
ap.add_argument('--energy-limit', type=float, default=-50.0,
                help='end criteria, residual energy (dB)')
ap.add_argument('--margin', type=float, default=200.0,
                help='GDS boundary to simulation boundary (um)')
ap.add_argument('--boundary', default='PEC',
                choices=['PEC', 'PMC', 'MUR', 'PML_8'],
                help='boundary condition on all six faces')
ap.add_argument('--nr-ts', type=int, default=0,
                help='max timesteps (0 = openEMS default; raise if energy stalls)')
ap.add_argument('--target-freq', type=float, default=1.0e9,
                help='frequency for the printed L/R/Q summary (Hz)')
args = ap.parse_args()

preview_only = not (args.simulate or args.postprocess)
postprocess_only = args.postprocess

# ======================== input files ======================================

gds_filename = args.gds
XML_filename = args.stackup

# ICS55 GDS polygons use data type 1; the port-source lines (300/301) also
# use purpose 1 (see pcells/ics55_ind.py em_ports section).
purposelist = [1]

# merge via polygons with distance less than this (um); 0 disables
merge_polygon_size = 0

model_basename = args.name
sim_path = utilities.create_sim_path(HERE, model_basename)
print('Simulation data directory: ', sim_path)

# ======================== simulation settings ==============================

unit = 1e-6       # geometry units: microns
margin = args.margin

fstart = args.fstart
fstop = args.fstop
numfreq = args.numfreq

refined_cellsize = args.cellsize
Boundaries = [args.boundary] * 6
cells_per_wavelength = args.cells_per_wavelength
energy_limit = args.energy_limit

# via ports from the M1 fixture ground plane up to TM2, one per signal pad;
# the thin source lines on 300/301 define the port sheet position.  The M1
# layer in the stackup must be the fixture ground plane, not ordinary M1:
# 300/301 sit under the pads and only touch the drawn M1 EM-GND plane.
simulation_ports = simulation_setup.all_simulation_ports()
simulation_ports.add_port(simulation_setup.simulation_port(
    portnumber=1, voltage=1, port_Z0=50,
    source_layernum=300, from_layername='M1', to_layername='TM2', direction='z'))
simulation_ports.add_port(simulation_setup.simulation_port(
    portnumber=2, voltage=1, port_Z0=50,
    source_layernum=301, from_layername='M1', to_layername='TM2', direction='z'))

# ======================== model ============================================

materials_list, dielectrics_list, metals_list = stackup_reader.read_substrate(XML_filename)

layernumbers = metals_list.getlayernumbers()
layernumbers.extend(simulation_ports.portlayers)

allpolygons = gds_reader.read_gds(
    gds_filename, layernumbers, purposelist=purposelist,
    metals_list=metals_list, preprocess=False,
    merge_polygon_size=merge_polygon_size)

# maximum cellsize from the shortest wavelength in the highest-eps material
wavelength_air = 3e8 / fstop / unit
max_cellsize = wavelength_air / (np.sqrt(materials_list.eps_max) * cells_per_wavelength)

# ======================== run ==============================================

data_paths = []
for excite_ports in [[1], [2]]:
    kwargs = {}
    if args.nr_ts:
        kwargs['NrTS'] = args.nr_ts
    FDTD = openEMS(EndCriteria=np.exp(energy_limit / 10 * np.log(10)), **kwargs)
    # SetGaussExcite(f0, fc) generates a pulse whose spectrum is centered on
    # f0 with half-power width 2*fc; fstart/fstop only sample the result.
    # Cutting the pulse at NrTS truncates the low-frequency skirt, so give
    # the 0.1 GHz corner room to ring down.
    f0 = (fstart + fstop) / 2
    fc = args.pulse_width if args.pulse_width else (fstop - fstart) / 2
    FDTD.SetGaussExcite(f0, fc)
    FDTD.SetBoundaryCond(Boundaries)
    FDTD = simulation_setup.setupSimulation(
        excite_ports, simulation_ports, FDTD,
        materials_list, dielectrics_list, metals_list, allpolygons,
        max_cellsize, refined_cellsize, margin, unit,
        xy_mesh_function=util_meshlines.create_xy_mesh_from_polygons)
    data_paths.append(simulation_setup.runSimulation(
        excite_ports, FDTD, sim_path, model_basename,
        preview_only, postprocess_only))

# ======================== post-process =====================================

if not preview_only:
    print('Begin data evaluation')

    def dB(value):
        return 20.0 * np.log10(np.abs(value))

    f = np.linspace(fstart, fstop, numfreq)

    s11 = utilities.calculate_Sij(1, 1, f, sim_path, simulation_ports)
    s21 = utilities.calculate_Sij(2, 1, f, sim_path, simulation_ports)
    s12 = utilities.calculate_Sij(1, 2, f, sim_path, simulation_ports)
    s22 = utilities.calculate_Sij(2, 2, f, sim_path, simulation_ports)

    s2p_name = os.path.join(sim_path, model_basename + '.s2p')
    utilities.write_snp(np.array([[s11, s21], [s12, s22]]), f, s2p_name)

    # series-branch Z parameters of the pi-equivalent (same convention as
    # palace/extract_lq.py: Zs = -1/Y21 of the two-port)
    y11 = utilities.calculate_Yij_2port(1, 1, f, sim_path, simulation_ports)
    y21 = utilities.calculate_Yij_2port(2, 1, f, sim_path, simulation_ports)

    np.seterr(divide='ignore', invalid='ignore')
    zs = -1.0 / y21
    omega = 2 * np.pi * f
    Ls = zs.imag / omega
    Rs = zs.real
    Q = zs.imag / zs.real
    csh = (y11 + y21).imag / omega   # pad-to-shield shunt capacitance

    # printed table
    print('\n  f (GHz)    Re Zs (ohm)   L (nH)      Q      Csh (fF)')
    for idx in range(0, numfreq, max(1, numfreq // 25)):
        print('  %8.3f   %10.4f  %9.4f  %8.3f  %9.3f'
              % (f[idx] / 1e9, Rs[idx], Ls[idx] * 1e9, Q[idx], csh[idx] * 1e15))

    findex = np.abs(f - args.target_freq).argmin()
    print('\nAt %.3f GHz:' % (f[findex] / 1e9))
    print('  Series L  [nH] : %.4f' % (Ls[findex] * 1e9))
    print('  Series R  [Ohm]: %.4f' % Rs[findex])
    print('  Q factor       : %.3f' % Q[findex])
    print('  S-parameter file:', s2p_name)

    # plots
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axis = plt.subplots(num='S-parameters', tight_layout=True)
    axis.plot(f / 1e9, dB(s11), 'k-', linewidth=2, label='S11 (dB)')
    axis.plot(f / 1e9, dB(s22), 'r--', linewidth=2, label='S22 (dB)')
    axis.plot(f / 1e9, dB(s21), 'b-', linewidth=2, label='S21 (dB)')
    axis.grid()
    axis.set_xlabel('Frequency (GHz)')
    axis.legend()

    fig, axis = plt.subplots(num='Inductance', tight_layout=True)
    axis.plot(f / 1e9, Ls * 1e9, 'k-', linewidth=2, label='Lseries [nH]')
    axis.grid()
    axis.set_xlabel('Frequency (GHz)')
    axis.legend()

    fig, axis = plt.subplots(num='Q factor', tight_layout=True)
    axis.plot(f / 1e9, Q, 'k-', linewidth=2, label='Q')
    axis.grid()
    axis.set_xlabel('Frequency (GHz)')
    axis.legend()

    for name in ('S-parameters', 'Inductance', 'Q factor'):
        plt.figure(name).savefig(os.path.join(sim_path, name.replace(' ', '_') + '.png'))
    print('Plots saved to', sim_path)
