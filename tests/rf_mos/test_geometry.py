"""Pure-Python connectivity/spacing sanity, NOT a foundry DRC or LVS run."""
import importlib.util
from pathlib import Path
from shapely.geometry import box

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'libs.tech/klayout/pcells/ics55_rf_mos.py'
spec=importlib.util.spec_from_file_location('ics55_rf_mos', PATH)
import sys
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


def shapes(geom, layer=None, net=None):
    return [box(*s.bbox) for s in geom.shapes
            if (layer is None or s.layer==layer) and (net is None or s.net==net)]


def no_cross_net_short(geom, layer):
    by_net={n:shapes(geom,layer,n) for n in ('D','G','S','B')}
    nets=list(by_net)
    for i,n in enumerate(nets):
        for m in nets[i+1:]:
            for a in by_net[n]:
                for b in by_net[m]:
                    assert not a.intersects(b), (layer,n,m,a.bounds,b.bounds)


def via_lands(geom):
    # Each V1 must overlap same-net M1 and M2 by its full bounding box.
    for v in [s for s in geom.shapes if s.layer=='V1']:
        vg=box(*v.bbox)
        assert any(m.covers(vg) for m in shapes(geom,'M1',v.net))
        assert any(m.covers(vg) for m in shapes(geom,'M2',v.net))


def ct_lands(geom):
    for v in [s for s in geom.shapes if s.layer=='CT']:
        vg=box(*v.bbox)
        assert any(m.covers(vg) for m in shapes(geom,'M1',v.net))
        l='POLY' if v.net=='G' else 'ACT'
        assert any(m.covers(vg) for m in shapes(geom,l))


def test_all_combinations():
    for polarity in ('n','p'):
        for nf in (1,2,3,4,8,16):
            for gc in ('single','double'):
                for source_left in (True,False):
                    g=mod.RFMOSGeometry(polarity=polarity,wf=2.0,l=.06,nf=nf,
                                        gate_contact=gc,source_left=source_left)
                    assert g.instance_params['w_total']==2*nf
                    assert set(x.name for x in g.labels)=={'D','G','S','B'}
                    assert len(shapes(g,'ACT'))==2
                    assert len(shapes(g,'POLY'))>=nf
                    assert len(shapes(g,'V1'))==nf+1
                    for layer in ('M1','M2'):
                        no_cross_net_short(g,layer)
                    via_lands(g)
                    ct_lands(g)


def test_minimum_geometry():
    for polarity in ('n','p'):
        for nf in (1,2,8):
            g=mod.RFMOSGeometry(polarity=polarity,wf=1.0,l=.06,nf=nf)
            no_cross_net_short(g,'M1')
            no_cross_net_short(g,'M2')
            ct_lands(g)
            via_lands(g)


def test_bad_input():
    import pytest
    for kwargs in ({'nf':0},{'wf':.5},{'l':.05},{'polarity':'x'}):
        with pytest.raises(ValueError):
            mod.RFMOSGeometry(**kwargs)
