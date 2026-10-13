# SPDX-License-Identifier: Apache-2.0
"""ICsprout55 1.2-V RF MOS PCell, v0.1 (candidate geometry, NOT DRC-qualified).

The geometry builder is dependency-free for deterministic unit tests and fixture
GDS generation. Import into KLayout's Python macro editor to register the PCell.

Layer numbers: ICsprout55 public layermap. Dimensions are DRAWN microns.
In particular `wf` is per-finger width; the ICS55 vendor SPICE wrapper expects
`w=wf*nf` as total drawn channel width and separately `nf=nf`.

This file implements only SVT 4T n/p MOS, no DNW, RFSD marker, or calibrated RF
parasitics. DO NOT claim DRC/LVS success until checked with official decks.
"""
from dataclasses import dataclass
from typing import List, Tuple

# (layer, datatype)
L = {
    "ACT": (2, 1), "NW": (9, 1), "POLY": (41, 1),
    "NP": (52, 1), "PP": (53, 1), "CT": (72, 1),
    "M1": (81, 1), "M1LBL": (81, 6),
    "M2": (82, 1), "M2LBL": (82, 6), "V1": (91, 1),
}

@dataclass(frozen=True)
class Shape:
    layer: str
    bbox: Tuple[float, float, float, float]
    net: str = ""       # intended net for metal/contact continuity assertions

@dataclass(frozen=True)
class Label:
    layer: str
    name: str
    x: float
    y: float


class RFMOSGeometry:
    """Plan a continuous-AA, shared-diffusion multi-finger four-terminal MOS.

    Routing strategy: diffusion CT -> dedicated M1 bars -> off-AA V1 ->
    separate M2 buses; gate CT -> M1 gate bus beyond active region;
    isolated separate AA body tap -> M1 body pin.
    """
    def __init__(self, polarity="n", wf=2.0, l=0.06, nf=4,
                 gate_contact="single", body_tie="bar", source_left=True):
        if polarity not in ("n", "p"):
            raise ValueError("polarity must be n or p")
        if not isinstance(nf, int) or not 1 <= nf <= 128:
            raise ValueError("nf must be an integer in [1,128]")
        if wf < 1.0 or l < 0.06:
            raise ValueError("v0.1 RF PCell requires wf >= 1um, L >= 0.06um")
        if gate_contact not in ("single", "double"):
            raise ValueError("gate_contact must be single or double")
        if body_tie not in ("bar", "none"):
            raise ValueError("body_tie must be bar or none")
        self.polarity, self.wf, self.l, self.nf = polarity, wf, l, nf
        self.gate_contact, self.body_tie = gate_contact, body_tie
        self.source_left = bool(source_left)
        self.shapes: List[Shape] = []
        self.labels: List[Label] = []
        self.pitch = max(0.36, l + 0.30)  # 0.36um for 60nm gate
        self.end_diff = 0.24
        self._draw()

    def add(self, layer, x0, y0, x1, y1, net=""):
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"invalid shape {layer}: {x0,y0,x1,y1}")
        self.shapes.append(Shape(layer, (x0,y0,x1,y1), net))

    def label(self, layer, name, x, y):
        self.labels.append(Label(layer, name, x, y))

    def _draw(self):
        wf, ln, nf = self.wf, self.l, self.nf
        p = self.pitch
        g = [(i - (nf-1)/2.0)*p for i in range(nf)]
        aa_left = g[0]-ln/2-self.end_diff
        aa_right = g[-1]+ln/2+self.end_diff
        ylo,yhi = -wf/2, wf/2

        self.add("ACT",aa_left,ylo,aa_right,yhi)
        core_implant = "NP" if self.polarity == "n" else "PP"
        tap_implant = "PP" if self.polarity == "n" else "NP"
        self.add(core_implant,aa_left-.20,ylo-.20,aa_right+.20,yhi+.20)

        # gate bars and contact dogbones: wider poly contact pads are OUTSIDE AA
        # gate pitch leaves >0.18um spacing between the 0.15um contact pads.
        for xc in g:
            self.add("POLY", xc-ln/2,ylo-(.82 if self.gate_contact=="double" else .19),xc+ln/2,yhi+.82,"G")
            for sign in (1,-1) if self.gate_contact=="double" else (1,):
                yc=sign*(wf/2+.61)
                self.add("POLY",xc-.075,yc-.18,xc+.075,yc+.18,"G")
                self.add("CT",xc-.045,yc-.045,xc+.045,yc+.045,"G")
        # Gate contact buses on M1, never connected to diffusion M1 bars
        x0g, x1g = g[0]-.12,g[-1]+.12
        self.add("M1",x0g,yhi+.50,x1g,yhi+.72,"G")
        self.label("M1LBL","G",(x0g+x1g)/2,yhi+.61)
        if self.gate_contact=="double":
            self.add("M1",x0g,ylo-.72,x1g,ylo-.50,"G")

        # each diffusion column is between gates or at the two terminal ends
        sd_x=[g[0]-ln/2-self.end_diff/2]
        sd_x += [(g[i]+g[i+1])/2 for i in range(nf-1)]
        sd_x += [g[-1]+ln/2+self.end_diff/2]

        # source/drain buses are on M2, outside the active strip
        s_rail=ylo-.98
        d_rail=yhi+1.08
        rail_left,rail_right = sd_x[0]-.16,sd_x[-1]+.16
        self.add("M2",rail_left,s_rail-.12,rail_right,s_rail+.12,"S")
        self.add("M2",rail_left,d_rail-.12,rail_right,d_rail+.12,"D")
        self.label("M2LBL","S",(rail_left+rail_right)/2,s_rail)
        self.label("M2LBL","D",(rail_left+rail_right)/2,d_rail)
        for i,x in enumerate(sd_x):
            net=("S" if i%2==0 else "D") if self.source_left else ("D" if i%2==0 else "S")
            via_y = ylo-.18 if net=="S" else yhi+.18
            # metal1 diffusion/contact strap; shared diffusion is ONE column
            self.add("M1",x-.10,min(ylo+.07,via_y-.10),
                     x+.10,max(yhi-.07,via_y+.10),net)
            # CT array keeps 0.2um spacing and stays inside AA
            ys=[]
            yy=ylo+.19
            while yy <= yhi-.19+1e-9:
                ys.append(yy)
                yy+=.29
            if not ys:
                ys=[0.0]
            for yy in ys:
                self.add("CT",x-.045,yy-.045,x+.045,yy+.045,net)
            # Via is intentionally outside ACT to avoid CT/V1 stacking.
            self.add("V1",x-.045,via_y-.045,x+.045,via_y+.045,net)
            self.add("M2",x-.11,min(via_y-.10,s_rail-.12 if net=="S" else d_rail-.12),
                     x+.11,max(via_y+.10,s_rail+.12 if net=="S" else d_rail+.12),net)

        # body strap: separate diffused bar, never butted to core active.
        tap_x0=aa_right+.80
        tap_x1=tap_x0+.36
        if self.body_tie=="bar":
            self.add("ACT",tap_x0,ylo,tap_x1,yhi,"B")
            self.add(tap_implant,tap_x0-.20,ylo-.20,tap_x1+.20,yhi+.20)
            xc=(tap_x0+tap_x1)/2
            self.add("M1",xc-.12,ylo+.06,xc+.12,yhi-.06,"B")
            yy=ylo+.20
            while yy <= yhi-.20+1e-9:
                self.add("CT",xc-.045,yy-.045,xc+.045,yy+.045,"B")
                yy+=.29
            self.label("M1LBL","B",xc,0)
        if self.polarity=="p":
            # NW encloses both P+ core and N+ body tap; conservative margin.
            xmax=(tap_x1 if self.body_tie=="bar" else aa_right)
            self.add("NW",aa_left-.50,ylo-.50,xmax+.50,yhi+.50)

    @property
    def instance_params(self):
        """Drawn geometry metadata; `sa/sb/sd` need foundry LVS correlation."""
        return {"wf":self.wf,"w_total":self.wf*self.nf,"l":self.l,
                "nf":self.nf,"gate_pitch":self.pitch,
                "sa_drawn":self.end_diff,"sb_drawn":self.end_diff,
                "sd_drawn":self.pitch-self.l}


# Register as a KLayout PCell if KLayout Python runtime is available.
try:
    import klayout.db as db
except ImportError:
    db = None

if db is not None:
    class Ics55RFMOS(db.PCellDeclarationHelper):
        def __init__(self):
            super().__init__()
            self.param("polarity",self.TypeString,"Channel n/p",default="n")
            self.param("wf",self.TypeDouble,"Width per finger (um)",default=2.0)
            self.param("l",self.TypeDouble,"Drawn gate length (um)",default=0.06)
            self.param("nf",self.TypeInt,"Number of fingers",default=4)
            self.param("gate_contact",self.TypeString,"single/double",default="single")
            self.param("body_tie",self.TypeString,"bar/none",default="bar")
            self.param("source_left",self.TypeBoolean,"Leftmost diffusion is S",default=True)

        def display_text_impl(self):
            return f"ics55_rf_{self.polarity}mos_4t(wf={self.wf}u,l={self.l}u,nf={self.nf})"

        def coerce_parameters_impl(self):
            self.wf=max(1.,self.wf)
            self.l=max(.06,self.l)
            self.nf=max(1,min(128,self.nf))

        def produce_impl(self):
            geom=RFMOSGeometry(self.polarity,self.wf,self.l,self.nf,
                               self.gate_contact,self.body_tie,self.source_left)
            dbu=self.layout.dbu
            u=lambda f: int(round(f/dbu))
            for s in geom.shapes:
                lay=self.layout.layer(db.LayerInfo(*L[s.layer]))
                x0,y0,x1,y1=s.bbox
                self.cell.shapes(lay).insert(db.Box(u(x0),u(y0),u(x1),u(y1)))
            for label in geom.labels:
                lay=self.layout.layer(db.LayerInfo(*L[label.layer]))
                self.cell.shapes(lay).insert(db.Text(label.name,db.Trans(u(label.x),u(label.y))))

    lib=db.Library.library_by_name("ICsprout55")
    if lib is None:
        lib=db.Library()
        lib.description="ICsprout55 analog and RF PCells"
        lib.register("ICsprout55")
    if "ics55_rf_mos" not in lib.layout().pcell_names():
        lib.layout().register_pcell("ics55_rf_mos",Ics55RFMOS())
