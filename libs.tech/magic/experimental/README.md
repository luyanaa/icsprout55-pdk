# ics55 Magic tech: historical CT/V1 work copy (promoted)

This directory held the work copy used to repair CT/V1 connectivity.  It has
been **promoted into `../ics55.tech`**; the files here are kept only for
provenance and are no longer the supported technology.  Use
`libs.tech/magic/ics55.tech`.

## What the work established

- The original `connect` section connected bare layer names, so Magic merged
  every contact at a coordinate and fragmented poly/diffusion nets.  The
  promoted tech qualifies each contact by the layers it touches
  (`ct/a`, `ct/m1`, `v1/a`, ...).
- A contact and a via drawn at exactly the same centre are handled by
  `stackable` in the `contact` section.  Earlier notes claimed the V1 had to
  be offset from the CT; that workaround is obsolete.  The promoted tech
  passes exact-centre stacks at CT/V1, V1/V2, V2/V3, V3/V4 and V4/TV2.
- The promoted tech adds `ct -> m1` rules for the composed lvt/hvt/IO
  diffusion types and the tap rules (`nwell,ndiff`, substrate
  `pdiff,lvtpdiff,hvtpdiff,iopdiff,pwell,space/w`).
- The former minimal stack fixture produced `M1_V 2.162f`, `P_FULL 2.162f`
  and `P 0.899f`; the same connectivity is now covered by the consolidated
  regression.

## Status

Superseded.  Do not edit the copy; make changes in `../ics55.tech` and run
`python3 tests/regression/magic_lvs_check.py`.
