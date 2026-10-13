#!/usr/bin/env python3
"""Generate schematic-independent GDS fixtures without KLayout installed.

Minimal GDSII rectangle/text writer for CI preview only. Native production
PCell is libs.tech/klayout/pcells/ics55_rf_mos.py.
"""
import importlib.util
import json
import math
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/'libs.tech/klayout/pcells/ics55_rf_mos.py'
spec=importlib.util.spec_from_file_location('ics55_rf_mos',SRC)
import sys
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


def rec(rtype, dtype=0, data=b''):
    assert (len(data)+4)%2==0
    return struct.pack('>HBB',4+len(data),rtype,dtype)+data


def asc(s):
    b=s.encode('ascii')
    return b + (b'\0' if len(b)%2 else b'')


def real8(x):
    if not x: return b'\0'*8
    sign=0x80 if x<0 else 0
    a=abs(x)
    exp=math.floor(math.log(a,16))+1
    mant=round(a/16**exp * 2**56)
    if mant==2**56:
        exp+=1
        mant//=16
    return bytes([sign|int(exp+64)])+int(mant).to_bytes(7,'big')


def export(path, cells):
    t=b'\0'*24
    out=bytearray()
    out+=rec(0,2,struct.pack('>h',600))
    out+=rec(1,2,t)
    out+=rec(2,6,asc('ICS55_RF_MOS_CANDIDATE'))
    out+=rec(3,5,real8(.001)+real8(1e-9))
    for name,geom in cells:
        out+=rec(5,2,t)
        out+=rec(6,6,asc(name))
        db=lambda x:int(round(x*1000))
        for sh in geom.shapes:
            x0,y0,x1,y1=sh.bbox
            out+=rec(8)
            out+=rec(13,2,struct.pack('>h',mod.L[sh.layer][0]))
            out+=rec(14,2,struct.pack('>h',mod.L[sh.layer][1]))
            out+=rec(16,3,struct.pack('>10i',db(x0),db(y0),db(x1),db(y0),db(x1),db(y1),db(x0),db(y1),db(x0),db(y0)))
            out+=rec(17)
        for lab in geom.labels:
            out+=rec(12)
            out+=rec(13,2,struct.pack('>h',mod.L[lab.layer][0]))
            out+=rec(22,2,struct.pack('>h',mod.L[lab.layer][1]))
            out+=rec(16,3,struct.pack('>2i',db(lab.x),db(lab.y)))
            out+=rec(25,6,asc(lab.name))
            out+=rec(17)
        out+=rec(7)
    out+=rec(4)
    path.write_bytes(out)


if __name__=='__main__':
    choices=[('RF_NMOS_F1',mod.RFMOSGeometry('n',wf=2,nf=1)),
             ('RF_NMOS_F2',mod.RFMOSGeometry('n',wf=2,nf=2)),
             ('RF_NMOS_F8',mod.RFMOSGeometry('n',wf=5,nf=8)),
             ('RF_PMOS_F4',mod.RFMOSGeometry('p',wf=2,nf=4))]
    dest=ROOT/'examples/ics55_rf_mos_fixtures.gds'
    export(dest,choices)
    (ROOT/'examples/geometry_manifest.json').write_text(json.dumps({name:g.instance_params for name,g in choices},indent=2)+'\n')
    print('Generated',dest)
