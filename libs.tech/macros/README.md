# ICsprout55 macros (reserved)

**Status: reserved** — analog macro library placeholder. When the foundry
releases analog cells, they belong here (one subdirectory per macro with
`cdl/`, `gds/`, `lef/`, `doc/`), mirroring the released IP layout:

```
macros/<macro_name>/
├── cdl/        # extracted netlists
├── gds/
├── lef/
├── doc/
└── verilog/
```

## Known analog-capable cells already released in the IO library

From `IP/IO/ICsprout_55LLULP1233_IO_251013` (use as reference macros):

| Cell | Function |
|---|---|
| P65_1233_PAR | analog pad, 300R poly series resistor, 22um metal, 10mA |
| P65_1233_PAR_5 | analog pad, 5R series resistor |
| P65_1233_PBMUX | bidirectional pad with analog pin, 50k PU/PD, 2-16mA driver |
| P65_1233_PWE | crystal oscillator pad (3.3V, ~20MHz) |
| P65_1233_VDD1A / VSS1A | analog power/ground pads |
| P65_1233_CUT | power-cut cell (digital/analog rail split) |

Primitives for user macros: see `../spice/models/` (device inventory) and
`../klayout/pcells/` (analog MOS, guard ring, resistor, MOM templates).
