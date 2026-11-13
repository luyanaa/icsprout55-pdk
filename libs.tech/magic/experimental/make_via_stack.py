import klayout.db as db
ly=db.Layout(); ly.dbu=0.001
c=ly.create_cell('VIA')
def box(l,x1,y1,x2,y2): c.shapes(ly.layer(*l)).insert(db.Box(int(x1*1000),int(y1*1000),int(x2*1000),int(y2*1000)))
def text(s,x,y,l=(81,1)): c.shapes(ly.layer(*l)).insert(db.Text(s,db.Trans(int(x*1000),int(y*1000))))
box((81,1),-1,-1,1,1); text('A', -0.5, 0)
box((91,1),-0.045,-0.045,0.045,0.045)
box((82,1),-1,-1,1,1); text('B', 0.5, 0, (82,1))
ly.write('/tmp/opencode/viatest.gds')
print('wrote')
