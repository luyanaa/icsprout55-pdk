# Run inside KLayout: klayout -b -r tests/rf_mos/run_klayout.py -z
# Produces isolated test structures (not a tapeout-ready test chip).
import sys
from pathlib import Path
import klayout.db as db

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'libs.tech/klayout/pcells'))
import ics55_rf_mos  # noqa: F401: registers PCell

ly=db.Layout()
ly.dbu=.001
names=[
    ('RF_NMOS_F1', dict(polarity='n',wf=2.,l=.06,nf=1)),
    ('RF_NMOS_F2', dict(polarity='n',wf=2.,l=.06,nf=2)),
    ('RF_NMOS_F8', dict(polarity='n',wf=5.,l=.06,nf=8)),
    ('RF_PMOS_F4', dict(polarity='p',wf=2.,l=.06,nf=4)),
]
for name,params in names:
    c=ly.create_cell('ics55_rf_mos','ICsprout55',params)
    cell=ly.create_cell(name)
    cell.insert(db.CellInstArray(c.cell_index(),db.Trans()))
output=str(root/'examples/ics55_rf_mos_klayout.gds')
for arg in sys.argv:
    if arg.startswith('gds='):
        output=arg.split('=',1)[1]
Path(output).parent.mkdir(parents=True, exist_ok=True)
ly.write(output)
print('Wrote',output)
