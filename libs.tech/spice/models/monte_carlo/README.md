# ICsprout55 - Monte Carlo model template

**Status: TBD.** No foundry statistical data is released with this PDK
(no mismatch/variation model files). This directory is reserved for:

- `ics55_mc.mm` — Monte Carlo parameter deck (process + mismatch)
- `ics55_mismatch.md` — documented mismatch coefficients (once available)

When foundry models arrive, add the `.model` parameter distributions here
and include from `../ics55.m`:

```
.include monte_carlo/ics55_mc.mm
```

Recommended structure (to be filled):

```
* ics55_mc.mm - Monte Carlo (TBD: foundry parameters)
.param mc_run = 0          * set 1 to enable MC
* process variation (TBD):
* .param sigma_vth = ...   * mV
* mismatch (TBD): typically sigma(Vth) ~ A/sqrt(W*L) + B
```

Nothing here is usable for design until populated with foundry data.
