#!/usr/bin/env python3
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
# ICsprout55 gds2palace model script (AWS Palace EM + Elmer thermal)
# ============================================================================
# Creates a FEM model from an ICsprout55 GDSII layout:
#   default   : AWS Palace 3D full-wave EM model (gmsh mesh + config.json)
#               -> frequency-dependent S-parameters -> R/L/C.
#   --thermal : Elmer steady-state thermal model (case.sif + mesh)
#               -> temperature field from heatsources + const-temp boundaries.
#
# The EM deck is the 1TM(TM2 9kA) + ALPA(RDL 14.5kA) inductor family:
#   - TM2 (103/1) spiral, RDL (123/1) underpass, RV (120/1) transitions
#   - PGS (AA, layer 2) patterned shield + solid ring
#   - 300/1 and 301/1 are the gds2palace port sources (thin line under the
#     signal pad).  The port is a vertical 50 ohm sheet from PGS.zmax up to
#     TM2.zmin (IHP via-port recipe), so the two ports share the PGS ground.
#
# Requires:  pip install gds2palace   (gdspy, gmsh, numpy, shapely)
#            the Palace solver (EM) / Elmer FEM (thermal) installed separately.
#
# Usage:
#   python run_model.py --gds ics55_ind_em.gds --freq 1.0
#   python run_model.py --gds ics55_ind_em.gds --freq 0.1 1 2 5 10 \
#                       --cellsize 0.5 --max-mesh 5
#   python run_model.py --thermal --gds <file.gds>
# ============================================================================

import argparse
import os
import sys

# gds2palace package (pip install gds2palace)
from gds2palace import *

# ======================== command line =====================================

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--gds", default=os.path.join(HERE, "ics55_ind_em.gds"),
                help="GDSII layout with the device and the port source shapes")
ap.add_argument("--stackup", default=os.path.join(HERE, "ics55_stackup.xml"),
                help="gds2palace stackup XML (default: typ corner)")
ap.add_argument("--name", default="ics55_ind",
                help="model basename (output goes to palace_model/<name>_data)")
ap.add_argument("--thermal", action="store_true", help="Elmer thermal model")
ap.add_argument("--gui", action="store_true", help="show the gmsh viewers")
ap.add_argument("--freq", type=float, nargs="+", default=[1.0],
                help="EM frequencies in GHz (discrete points, default 1.0)")
ap.add_argument("--cellsize", type=float, default=1.0,
                help="mesh cell size in the conductor region (um)")
ap.add_argument("--max-mesh", type=float, default=10.0,
                help="global mesh size cap (um)")
ap.add_argument("--order", type=int, default=2, choices=(1, 2, 3),
                help="FEM basis order (1 saves memory)")
ap.add_argument("--margin", type=float, default=50.0,
                help="GDS boundary to simulation boundary (um)")
args = ap.parse_args()

thermal_mode = args.thermal
preview_gui = args.gui

# ======================== input files ======================================

gds_filename = args.gds
XML_filename = args.stackup

# merge via polygons with distance less than this (um); 0 disables
merge_polygon_size = 0

# ======================== simulation settings ==============================

settings = {}
settings['unit'] = 1e-6       # geometry units: microns
settings['margin'] = args.margin

if not thermal_mode:
    # --- AWS Palace full-wave EM ------------------------------------------
    # discrete frequency points in Hz (gds2palace writes them in GHz)
    settings['fpoint'] = [f * 1e9 for f in args.freq]
    settings['refined_cellsize'] = args.cellsize
    settings['cells_per_wavelength'] = 10
    settings['meshsize_max'] = args.max_mesh
    settings['adaptive_mesh_iterations'] = 0
    settings['order'] = args.order
else:
    # --- Elmer steady-state thermal ---------------------------------------
    settings['refined_cellsize'] = 1.0
    settings['meshsize_max'] = 20.0
    settings['iterative'] = True

# headless operation (no gmsh viewer); use --gui to preview the model
settings['no_gui'] = not preview_gui

# ======================== EM ports (Palace mode) ============================
# The inductor EM deck: one vertical via port per signal pad, from the M1
# fixture ground plane up to TM2.  The source shape on 300/301 is a thin line
# along the pad (x for pad A, the pad-B exit axis for pad B), so the port
# sheet is a 10 um wide vertical 50 ohm connection between the ground plane
# and the top metal.  The M1 frame does NOT touch the 10 ohm/sq PGS ring
# (0.05 um PMD gap); the PGS stays a floating eddy-current shield and the
# shared return is the low-ohmic M1 plane.
simulation_ports = simulation_setup.all_simulation_ports()
simulation_ports.add_port(simulation_setup.simulation_port(
    portnumber=1, voltage=1, port_Z0=50,
    source_layernum=300, from_layername='M1', to_layername='TM2', direction='z'))
simulation_ports.add_port(simulation_setup.simulation_port(
    portnumber=2, voltage=1, port_Z0=50,
    source_layernum=301, from_layername='M1', to_layername='TM2', direction='z'))

# ======================== thermal objects (--thermal mode) ==================
# Heat sources and constant-temperature boundaries, one per GDS source layer.
thermal_objects = simulation_setup.all_thermal_objects()
# thermal_objects.add_heatsource(simulation_setup.heatsource(
#     power=0.1, source_layernum=400, target_layername='M1'))
# thermal_objects.add_consttemp(simulation_setup.constanttemp(
#     temp=298, source_layernum=401, target_layername='M1'))

# ======================== model creation ===================================

model_basename = args.name
sim_path = utilities.create_sim_path(HERE, model_basename)
os.chdir(HERE)

materials_list, dielectrics_list, metals_list = stackup_reader.read_substrate(XML_filename)

if thermal_mode:
    layernumbers = metals_list.getlayernumbers()
    layernumbers.extend(thermal_objects.layers)
    settings['thermal_objects'] = thermal_objects
else:
    layernumbers = metals_list.getlayernumbers()
    layernumbers.extend(simulation_ports.portlayers)
    settings['simulation_ports'] = simulation_ports

# ICsprout55 GDS layers use data type 1 (purpose [0] would read nothing)
allpolygons = gds_reader.read_gds(
    gds_filename, layernumbers, purposelist=[1],
    metals_list=metals_list, preprocess=False,
    merge_polygon_size=merge_polygon_size)

settings['materials_list'] = materials_list
settings['dielectrics_list'] = dielectrics_list
settings['metals_list'] = metals_list
settings['layernumbers'] = layernumbers
settings['allpolygons'] = allpolygons
settings['sim_path'] = sim_path
settings['model_basename'] = model_basename

if thermal_mode:
    config_name, data_dir = simulation_setup.create_elmer_thermal(settings)
    print("Elmer thermal model written to", sim_path)
    print("Run Elmer with:  cd %s && ./run_sim" % sim_path)
else:
    excite_ports = simulation_ports.all_active_excitations()
    config_name, data_dir = simulation_setup.create_palace(excite_ports, settings)
    utilities.create_run_script(sim_path)
    print("Palace model written to", sim_path)
    print("Run Palace with:  cd %s && ./run_sim" % sim_path)
