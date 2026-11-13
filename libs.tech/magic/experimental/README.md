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

## Current result (baseline copy)

Both stacks fail.  The `.ext` file shows the contact/via layers as
standalone nodes rather than connections:

```
node "a_n4_n4#" ... ct        # the CT shape
node "a_n100_n100#" ... p     # poly, separate
node "P" ... m1               # label moved to metal1
equiv "P" "M1_CT"

node "m1_300_n100#" ... m1    # M1 pad
node "M1_V" ... m2            # label moved to metal2
equiv "M1_V" "M2_V"
```

The V1 shape is not a node at all; the CT is a node of type `ct`.  In
`ext2spice` the two sides therefore remain separate nets.

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

## Tried variants (all rejected)

1. size/overlap on `contact v1` — that syntax belongs to `wiring`, not
   `extract`; the tech fails to load.
2. remove `v1` from the `metal1` alias / add a `cut` plane — `types` has no
   `cut` plane and `connect`/`extract` report an unknown type.
3. rename `v1` to `via1` and keep `v1` as the connect alias (the sky130
   `via1`/`v1` split) — the tech loads, but the stack still extracts as
   separate nodes.
4. add `v1/a`, `v1/m1`, `ct/a` contact-area terms to `connect` — parser
   accepts some forms but the contact is not formed.

The next iteration should define CT/V1 as true cut types in the copy,
mirroring the KLayout `CT -> M1 -> V1` chain, and keep the stack regression
as the gate.
