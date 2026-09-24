# ICsprout55 - aging / noise model templates

**Status: TBD.** No foundry aging (BTI/HCI) or noise (flicker/thermal)
parameters are released with this PDK. Reserved structure:

- `ics55_aging.scs` — aging model (ΔVth vs stress time, BTI/HCI)
- `ics55_noise.scs` — noise parameters (KF/AF flicker, NLEV, thermal)

Once available, populate and include from `../ics55.m`. The MOS models in
`../mos_core.l` carry the noise parameters (KF/AF etc. in BSIM); the aging
extensions belong here or in a dedicated reliability model.

Reference: 65nm-class LP processes typically show ~30-60 mV BTI shift at
10y/1.1V-class stress; flicker noise KF in the 1e-25..1e-24 range (BSIM3
units) — **these are textbook references, NOT this foundry's data**.
