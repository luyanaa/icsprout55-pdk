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
# This is the 3D / RLC / thermal extension of libs.tech/pex (the 2D seed-based
# rcx.py).  The stackup (libs.tech/pex/palace/ics55_stackup.xml) carries the
# released LEF seeds + user-approved estimates (electrical AND thermal; see the
# XML header for provenance).
#
# Requires:  pip install gds2palace   (gdspy, gmsh, numpy, shapely)
#            the Palace solver (EM) / Elmer FEM (thermal) installed separately.
#
# Usage:
#   python run_model.py [--thermal] [--nogui] [--gds <file.gds>] [--stackup <file.xml>]
#
# The GDS must contain shape polygons on the port/source layers declared in the
# port (EM) and thermal-object (thermal) sections below: one port or thermal
# object per source layer.  Geometry units are microns (unit = 1e-6).
# ============================================================================

import os
import sys

# gds2palace package (pip install gds2palace)
from gds2palace import *

# ======================== command line =====================================

thermal_mode = '--thermal' in sys.argv
preview_gui  = '--gui' in sys.argv

# ======================== input files ======================================

# GDSII with the layout to simulate (std cell, IO cell or a routed block).
# Add the port / thermal-object shape polygons on the source layers below.
gds_filename = "ics55_demo.gds"

# technology stackup (clean-room estimates; provenance in the XML header)
XML_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "ics55_stackup.xml")

# merge via polygons with distance less than this (um); 0 disables
merge_polygon_size = 0

# ======================== simulation settings ==============================

settings = {}
settings['unit']  = 1e-6     # geometry units: microns
settings['margin'] = 50.0    # um from GDS geometry boundary to sim boundary

if not thermal_mode:
    # --- AWS Palace full-wave EM ------------------------------------------
    # user-selected default: single-frequency analysis at 1 GHz
    # (a sweep is also possible: fstart/fstop/fstep, or a list in fpoint)
    settings['fpoint'] = 1e9     # 1 GHz, in Hz

    # user-selected default: fine mesh
    settings['refined_cellsize'] = 0.25      # mesh cell size in conductor region (um)
    settings['cells_per_wavelength'] = 10    # must be >= 10
    settings['meshsize_max'] = 10.0          # global cap (um)
    settings['adaptive_mesh_iterations'] = 0
else:
    # --- Elmer steady-state thermal ---------------------------------------
    # mesh is refined only near the heat sources for the thermal solve
    settings['refined_cellsize'] = 1.0
    settings['meshsize_max'] = 20.0
    settings['iterative'] = True   # BiCGStab; False = direct UMFPACK

# headless operation (no gmsh viewer); use --gui to preview the model
settings['no_gui'] = not preview_gui

# ======================== EM ports (Palace mode) ============================
# One port per source layer.  Two examples:
#   in-plane port on M1 (direction x, target layer M1):
#       source_layernum=300, target_layername='M1', direction='x'
#   vertical via port from M1 to M2 (direction z):
#       source_layernum=301, from_layername='M1', to_layername='M2', direction='z'
# Remove the examples and add the real ports for the structure under test.
simulation_ports = simulation_setup.all_simulation_ports()
simulation_ports.add_port(simulation_setup.simulation_port(
    portnumber=1, voltage=1, port_Z0=50,
    source_layernum=300, target_layername='M1', direction='x'))
simulation_ports.add_port(simulation_setup.simulation_port(
    portnumber=2, voltage=1, port_Z0=50,
    source_layernum=301, from_layername='M1', to_layername='M2', direction='z'))

# ======================== thermal objects (--thermal mode) ==================
# Heat sources and constant-temperature boundaries, one per GDS source layer.
# Examples:
#   heatsource(power=0.1, source_layernum=400, target_layername='M1')   # 100 mW
#   constanttemp(temp=298, source_layernum=401, target_layername='M1')  # 25 C
thermal_objects = simulation_setup.all_thermal_objects()
# thermal_objects.add_heatsource(simulation_setup.heatsource(
#     power=0.1, source_layernum=400, target_layername='M1'))
# thermal_objects.add_consttemp(simulation_setup.constanttemp(
#     temp=298, source_layernum=401, target_layername='M1'))

# ======================== model creation ===================================

model_basename = os.path.splitext(os.path.basename(__file__))[0]
sim_path = utilities.create_sim_path(os.getcwd(), model_basename)
os.chdir(os.path.dirname(os.path.abspath(__file__)))

materials_list, dielectrics_list, metals_list = stackup_reader.read_substrate(XML_filename)

if thermal_mode:
    layernumbers = metals_list.getlayernumbers()
    layernumbers.extend(thermal_objects.layers)
    settings['thermal_objects'] = thermal_objects
else:
    layernumbers = metals_list.getlayernumbers()
    layernumbers.extend(simulation_ports.portlayers)
    settings['simulation_ports'] = simulation_ports

allpolygons = gds_reader.read_gds(
    gds_filename, layernumbers, purposelist=[0],
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
