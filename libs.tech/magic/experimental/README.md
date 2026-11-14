# ics55 Magic tech: PEX/contact work copy

This directory is a **copy** of `../ics55.tech` for the CT/V1 extraction
repair.  The released tech is untouched until the copy passes the minimal
stack regression.

```sh
klayout -b -r make_stack.py -z          # -> via_stack.gds
magic -dnull -noconsole -rcfile ics55_pex.magicrc extract_stack.tcl
```

`via_stack.gds` has two independent stacks:

* poly -- CT -- M1 (gate-contact connectivity)
* M1 -- V1 -- M2 (via connectivity)

## Current result (work copy)

All three minimal stacks now pass:

```
C0 M1_V   SUB 2.162f     # M1 + M2 on one node
C1 P_FULL SUB 2.162f     # poly + CT + M1 + V1 + M2 on one node
C2 P      SUB 0.899f     # poly + CT + M1 on one node
```

**The V1 must be offset from the CT.**  A V1 stacked exactly on a CT makes
Magic lose the lower contact; the full stack then opens on the poly side
(`P_FULL` becomes m1+m2 only).  The rule used by the row is a 0.12 um
y-offset between the cascode-drain CT and its V1.  The M1 island is tall
enough; the M2 cd route is extended to the V1.

The fix is in the `connect` section: use the contact-area entries that the
sky130/scmos techs use, and join the fet types to the poly plane:

```
poly,nfet,pfet,...,ct/a    poly,nfet,pfet,...,ct/a
m1,ct/m1,v1/a,v1/m1        m1,ct/m1,v1/a,v1/m1
m2,v1/a,v1/m2,v2/a,v2/m2   ...
```

The 8-cell block then extracts with 34 devices and 37 capacitors and the
MOS gates are named (`M1000 ... db_b0_0`, `M1025 iout d_b0_0 ...`), so the
poly CT, V1 and gate labels work.

**Still open:** the diffusion CT to M1 local interconnect.  The `.ext`
shows the mirror/cascode md nodes as diffusion-only (`a_3100_n800#`,
`a_7600_n800#` with `pd` but no `m1`), so the 8-cell PEX has no current path
and settles at 0 LSB while the schematic CDL gives 1/3/7 LSB for codes
1/3/7.  The next iteration is the `ct ndiff/pdiff m1` contact plus
`ndiff,ct/a` / `m1,ct/m1` path; `ct act m1` and removing `,ct` from the
device model did not change it.  The full-row PEX is still blocked on this.

## KLayout LVS reference

The lower-layer chain in `libs.tech/lvs/rule_decks/devices_connections.lvs`
is the reference:

```
NSD/PSD/POLY_CON -> CT -> M1 -> V1 -> M2 -> V2 -> M3 ...
```

The KLayout device extraction additionally has:

* RF MOS 5T/6T (DNW-qualified NMOS/PMOS), varactors and inductors
  (`rule_decks/rf_extraction.lvs`);
* MOM capacitors are **not** extracted (`ics55.lvs` says "MOM cap: not
  extracted"), so that is a known KLayout gap, not something to copy into
  Magic yet.

Magic currently extracts only the core `nfet`/`pfet` devices; RF MOS,
varactors, inductors and MOM are absent.  A full parity pass is a separate
task after the CT/V1 contact stack works.

## Tried variants

1. size/overlap on `contact v1` — that syntax belongs to `wiring`, not
   `extract`; the tech fails to load.
2. remove `v1` from the `metal1` alias / add a `cut` plane — `types` has no
   `cut` plane and `connect`/`extract` report an unknown type.
3. rename `v1` to `via1` and keep `v1` as the connect alias — loads, but the
   stack still splits.
4. add `v1/a`, `v1/m1`, `ct/a` contact-area terms to `connect` — **this is
   the fix for V1 and the poly CT**; the stacks now pass.
5. `ct act m1`, or removing `,ct` from the device model — no change for the
   diffusion CT; the md nodes stay diffusion-only.

The next iteration is the diffusion CT path; the stack regression and the
8-cell PEX comparison (`analog/video_ics55/block8_pex.py`) are the gates.
