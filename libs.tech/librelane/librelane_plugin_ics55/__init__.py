# Copyright 2026 ICsprout Integrated Circuit Co., Ltd.
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
"""LibreLane plugin for the ICS55 (icsprout55) PDK.

LibreLane discovers every importable module named ``librelane_plugin_*``, so
adding ``$PDK_ROOT/$PDK/libs.tech/librelane`` to ``PYTHONPATH`` is enough to
register the steps below.

Steps:
  ICS55.KLayoutLVS  KLayout LVS with the PDK runset (KLAYOUT_LVS_SCRIPT).
                    Upstream ``KLayout.LVS`` only runs for the IHP PDKs; the
                    invocation itself is PDK independent (design CDL merged
                    with CELL_CDLS / EXTRA_CDLS / PAD_CDLS, options from
                    KLAYOUT_LVS_OPTIONS), so this step reuses the same
                    implementation and widens the match patterns for our deck.

Use it in place of Netgen.LVS, after OpenROAD.WriteCDL:
  meta:
    flow: Classic
    substituting_steps:
      Magic.DRC: null
      Checker.MagicDRC: null
      Magic.SpiceExtraction: null
      Magic.StreamOut: null
      Magic.WriteLEF: null
      Odb.CheckDesignAntennaProperties: null
      Checker.IllegalOverlap: null
      KLayout.XOR: null
      Checker.XOR: null
      "-Netgen.LVS": OpenROAD.WriteCDL
      Netgen.LVS: ICS55.KLayoutLVS

Our deck prints ``CONGRATULATIONS! Netlists match.`` (uppercase, no ``INFO :``
prefix) while the upstream IHP deck prints ``INFO : Congratulations! Netlists
match.`` — both spellings are accepted here.
"""

import os
import subprocess
import sys
from os.path import abspath
from tempfile import NamedTemporaryFile

from librelane.common import Path, mkdirp
from librelane.state import DesignFormat
from librelane.steps import Step
from librelane.steps.klayout import LVS as KLayoutLVS

# cdl_convert.py lives next to this plugin (libs.tech/librelane/scripts/).
_CDL_CONVERT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "cdl_convert.py",
)


def _convert_cdl(src, workdir):
    """Return a path to an LVS-ready copy of ``src`` inside ``workdir``.

    The vendor CDLs cannot be concatenated as shipped: helper subckts such
    as INV/NAND2/TG/TSINV are defined repeatedly and collide (case-insens-
    itively) across the std-cell and IO libraries.  cdl_convert.py renames
    the per-library helpers and normalises the CDL syntax; the design CDL
    written by OpenROAD.WriteCDL is already clean and is passed through.
    """
    dst = os.path.join(workdir, os.path.basename(src))
    if os.path.abspath(src) == os.path.abspath(dst):
        return src
    subprocess.run(
        [sys.executable, _CDL_CONVERT, src, dst],
        check=True,
        capture_output=True,
    )
    return dst


@Step.factory.register()
class ICS55KLayoutLVS(KLayoutLVS):
    """
    Layout vs. schematic with KLayout and the ICS55 LVS runset.
    """

    id = "ICS55.KLayoutLVS"
    name = "Layout Versus Schematic (KLayout, ICS55)"

    def run(self, state_in, **kwargs):
        # The ICS55 deck (libs.tech/lvs/ics55.lvs) honours the same -rd
        # contract as the IHP one (input / schematic / report /
        # target_netlist, plus PDK-specific switches via KLAYOUT_LVS_OPTIONS).
        # Reuse the upstream implementation, but with our verdict strings.
        kwargs, env = self.extract_env(kwargs)

        lvs_script_path = self.config["KLAYOUT_LVS_SCRIPT"]

        reports_dir = os.path.join(self.step_dir, "reports")
        mkdirp(reports_dir)
        lvsdb_report = os.path.join(reports_dir, "lvs.klayout.lvsdb")

        input_view_gds = state_in[DesignFormat.GDS]
        input_view_cdl = state_in[DesignFormat.CDL]

        output_spice = os.path.join(
            self.step_dir,
            f"{self.config['DESIGN_NAME']}.{DesignFormat.SPICE.value.extension}",
        )

        conv_dir = os.path.join(self.step_dir, "converted_cdls")
        mkdirp(conv_dir)

        with NamedTemporaryFile("w", suffix=".cdl") as f:
            # The design CDL from OpenROAD.WriteCDL is already clean.  The
            # library CDLs (std-cell + pad) are converted first: their helper
            # subckts collide case-insensitively when concatenated.
            cdl_lst = [input_view_cdl]
            for lib_cdl in (
                list(self.config["CELL_CDLS"] or [])
                + list(self.config["EXTRA_CDLS"] or [])
                + list(self.config["PAD_CDLS"] or [])
            ):
                cdl_lst.append(_convert_cdl(lib_cdl, conv_dir))

            for fn in cdl_lst:
                with open(fn, "r") as cdl_fh:
                    f.write(cdl_fh.read())
            f.flush()

            opts = []
            if self.config["KLAYOUT_LVS_OPTIONS"]:
                for k, v in self.config["KLAYOUT_LVS_OPTIONS"].items():
                    opts.extend(["-rd", f"{k}={v}"])

            subprocess_result = self.run_subprocess(
                [
                    "klayout",
                    "-b",
                    "-zz",
                    "-r",
                    lvs_script_path,
                    "-rd",
                    f"input={abspath(input_view_gds)}",
                    "-rd",
                    f"schematic={abspath(f.name)}",
                    "-rd",
                    f"report={abspath(lvsdb_report)}",
                    "-rd",
                    f"target_netlist={abspath(output_spice)}",
                ]
                + opts,
                env=env,
            )

            ok = False
            erc_ok = True
            with open(subprocess_result["log_path"]) as fh:
                for line in fh:
                    if "ICS55_ERC=FAIL" in line:
                        erc_ok = False
                    # Accept both our deck's banner and the upstream IHP one.
                    if (
                        "ICS55_LVS_COMPARE=PASS" in line
                        or "Congratulations! Netlists match" in line
                    ):
                        ok = True
                        break
                    elif (
                        "ICS55_LVS_COMPARE=FAIL" in line
                        or "Netlists don't match" in line
                    ):
                        ok = False
                        break

        views_updates = {
            DesignFormat.SPICE: Path(output_spice),
        }
        metrics_updates = {
            "design__lvs_error__count": 0 if (ok and erc_ok) else 1,
        }

        return views_updates, metrics_updates
