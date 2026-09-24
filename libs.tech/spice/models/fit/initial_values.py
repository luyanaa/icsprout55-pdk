#!/usr/bin/env python3
"""Calculate BSIM4 fit priors from the released PTM cards and evidence.

The ICS55 process is a 55 nm, 1.2 V low-power library without foundry MOS
cards.  This script does not pretend that a 45 nm or 65 nm PTM card is a
measured ICS55 card.  It computes a reproducible starting prior:

* logarithmic interpolation of positive PTM parameters between 45 nm LP and
  65 nm bulk at 55 nm;
* linear interpolation for signed/linear parameters;
* current leakage-fit values for VTH0, VOFF, and DIBL as data-informed
  flavor-specific re-centering;
* source-card envelopes and conservative fit bounds for parameters that have
  an observable in the current Liberty/CDL evidence.

The parameter-extraction order follows the BSIM4 extraction literature:
threshold/subthreshold first, mobility and series resistance next, then C-V
parameters only when an explicit capacitance objective is supplied.  The
result is an initial-value manifest, not a fitted model.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Mapping

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "INITIAL_VALUES.json"
DEFAULT_FIT = HERE.parent / "fitted" / "FIT_PARAMS.json"

SOURCE_PATHS = {
    "bulk65": Path(os.path.expanduser("~/Downloads/65nm_bulk.pm")),
    "lp45": Path(os.path.expanduser("~/Downloads/45nm_LP.pm")),
    "hp45": Path(os.path.expanduser("~/Downloads/45nm_HP.pm")),
}

# Observable groups.  Gate-current, junction, noise, mismatch, and aging
# parameters are intentionally not included: the current evidence has no
# corresponding measurements and a free fit would be non-identifiable.
FIT_GROUPS = {
    "leakage": (
        "vth0", "voff", "nfactor", "eta0", "dvt0", "dvt1", "dsub",
        "pdiblc1", "pdiblc2", "pdiblcb", "pclm", "drout",
    ),
    "drive": (
        "u0", "ua", "ub", "uc", "vsat", "rdsw", "rsw", "rdw",
        "a0", "ags", "keta",
    ),
    "cv": (
        "toxe", "toxp", "toxm", "cgso", "cgdo", "cgbo", "cgdl",
        "cgsl", "ckappas", "ckappad", "moin", "noff", "voffcv",
    ),
}

# Initial flavor re-centering from the current six-parameter TT leakage fit.
# These values are read from FIT_PARAMS.json at runtime; the table only gives
# the observables used to estimate a conservative drive prior.
DRIVE_DELAY_MODEL_OVER_TARGET = {"svt": 1.93, "lvt": 1.31, "hvt": 3.79}

PAPER_SOURCES = [
    {
        "citation": "Cao and Zhao, Predictive Technology Model for Nano-CMOS Design Exploration",
        "doi": "10.1109/nanonet.2006.346227",
        "url": "https://doi.org/10.1109/nanonet.2006.346227",
        "use": "PTM scaling and a small set of primary technology parameters.",
    },
    {
        "citation": "Zhao and Cao, New Generation of Predictive Technology Model for Sub-45 nm Early Design Exploration",
        "doi": "10.1109/ted.2006.884077",
        "url": "https://doi.org/10.1109/ted.2006.884077",
        "use": "45 nm PTM process class and correlated parameter trends.",
    },
    {
        "citation": "Assenmacher, BSIM4 Modeling and Parameter Extraction",
        "url": "https://ewh.ieee.org/r5/denver/sscs/References/2003_03_Assenmacher.pdf",
        "use": "Extraction order: VTH0/K1/K2/DVTP0, NFACTOR/VOFF/MINV, TOXP/NGATE, and U0/UA/UB/UC.",
    },
    {
        "citation": "Li et al., An ultra-compact virtual source FET model for deeply-scaled devices",
        "url": "http://dspace.mit.edu/bitstream/handle/1721.1/92430/Li-Yu-final-ASPDAC2013.pdf;sequence=1",
        "use": "Separate C-V, subthreshold, and full-region objectives rather than one unconstrained fit.",
    },
    {
        "citation": "University of Minnesota PTM project",
        "url": "https://mec.umn.edu/ptm",
        "use": "Authoritative index for the 45 nm HP/LP and 65 nm bulk source cards.",
    },
]


def parse_model_cards(path: Path) -> Dict[str, Dict[str, float]]:
    """Parse the scalar assignments from the two level-54 BSIM4 cards."""
    text = path.read_text()
    result: Dict[str, Dict[str, float]] = {}
    pattern = re.compile(
        r"\.model\s+(nmos|pmos)\s+\1\s+level\s*=\s*54(.*?)(?=\.model\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    number = re.compile(
        r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*=\s*"
        r"([+\-]?\d*\.?\d+(?:[eE][+\-]?\d+)?)"
    )
    for match in pattern.finditer(text):
        values: Dict[str, float] = {}
        for item in number.finditer(match.group(2)):
            values[item.group(1).lower()] = float(item.group(2))
        result[match.group(1).lower()] = values
    if set(result) != {"nmos", "pmos"}:
        raise ValueError("expected nmos and pmos cards in %s" % path)
    return result


def _is_positive(values: Iterable[float]) -> bool:
    return all(value > 0 for value in values)


def interpolate(values45: float, values65: float, fraction65: float) -> float:
    """Interpolate physical positive values in log space, signed values linear."""
    if values45 > 0 and values65 > 0:
        return math.exp(
            (1.0 - fraction65) * math.log(values45)
            + fraction65 * math.log(values65)
        )
    return (1.0 - fraction65) * values45 + fraction65 * values65


def source_prior(cards: Mapping[str, Mapping[str, Mapping[str, float]]],
                 typ: str, parameter: str, fraction65: float) -> float:
    lp = cards["lp45"][typ][parameter]
    bulk = cards["bulk65"][typ][parameter]
    return interpolate(lp, bulk, fraction65)


def source_envelope(cards: Mapping[str, Mapping[str, Mapping[str, float]]],
                    typ: str, parameter: str) -> Dict[str, float]:
    values = [cards[key][typ][parameter] for key in ("bulk65", "lp45", "hp45")]
    return {"min": min(values), "max": max(values), "source": values}


def multiplier_bounds(value: float, envelope: Mapping[str, float]) -> Dict[str, float]:
    """Return conservative positive scale bounds around a source prior."""
    # Values close to zero, especially PMOS pdiblcb, are not usefully bounded
    # by a multiplicative interval.  Keep those parameters near the source
    # value; the fit can still move them additively in a later device-data flow.
    if abs(value) < 1e-10:
        return {"kind": "freeze", "lower": value, "upper": value}
    return {"kind": "scale", "lower": 0.5, "upper": 2.0}


def build_manifest(fit_path: Path = DEFAULT_FIT) -> Dict[str, object]:
    cards = {name: parse_model_cards(path) for name, path in SOURCE_PATHS.items()}
    fraction65 = (55.0 - 45.0) / (65.0 - 45.0)
    current_fit = json.loads(fit_path.read_text()) if fit_path.exists() else {}
    current_flavors = current_fit.get("flavors", current_fit)

    group_for = {
        name: group for group, names in FIT_GROUPS.items() for name in names
    }
    all_nonzero: Dict[str, object] = {}
    for typ in ("nmos", "pmos"):
        names = (set(cards["bulk65"][typ])
                 & set(cards["lp45"][typ])
                 & set(cards["hp45"][typ]))
        rows: Dict[str, object] = {}
        for name in sorted(names):
            values = [cards[key][typ][name]
                      for key in ("bulk65", "lp45", "hp45")]
            if not any(value != 0 for value in values):
                continue
            rows[name] = {
                "initial_55nm": source_prior(cards, typ, name, fraction65),
                "source_envelope": source_envelope(cards, typ, name),
                "group": group_for.get(name),
                "status": ("fit-candidate" if name in group_for
                           else "frozen-no-current-observable"),
            }
        all_nonzero[typ] = rows

    flavors: Dict[str, object] = {}
    for flavor in ("svt", "lvt", "hvt"):
        fitted = current_flavors.get(flavor, {}).get("params", {})
        devices: Dict[str, object] = {}
        for typ in ("nmos", "pmos"):
            initial: Dict[str, float] = {}
            bounds: Dict[str, object] = {}
            envelope: Dict[str, object] = {}
            for group, names in FIT_GROUPS.items():
                for name in names:
                    if (name not in cards["lp45"][typ]
                            or name not in cards["bulk65"][typ]):
                        continue
                    value = source_prior(cards, typ, name, fraction65)
                    # The current leakage fit is stronger evidence for the
                    # three parameters it directly observed than PTM scaling.
                    if name == "vth0":
                        value = fitted.get(
                            "vth0n" if typ == "nmos" else "vth0p", value)
                        if typ == "pmos":
                            value = abs(value)
                    elif name == "voff":
                        scale = fitted.get(
                            "voff_n" if typ == "nmos" else "voff_p", 1.0)
                        value = cards["lp45"][typ][name] * scale
                    elif name in ("pdiblc1", "pdiblc2", "pdiblcb"):
                        scale = fitted.get(
                            "dibl_n" if typ == "nmos" else "dibl_p", 1.0)
                        value = cards["lp45"][typ][name] * scale
                    initial[name] = value
                    envelope[name] = source_envelope(cards, typ, name)
                    bounds[name] = multiplier_bounds(value, envelope[name])
            devices[typ] = {
                "initial": initial,
                "source_envelope": envelope,
                "bounds": bounds,
                "conventions": {
                    "vth0": (
                        "positive magnitude for PMOS, signed value for NMOS"
                        if typ == "pmos" else "signed NMOS voltage"
                    ),
                },
            }
        flavors[flavor] = {
            "devices": devices,
            "drive_delay_model_over_target": DRIVE_DELAY_MODEL_OVER_TARGET[flavor],
        }

    return {
        "technology_target": {
            "node_nm": 55,
            "vdd_v": 1.2,
            "temperature_c": 25,
            "interpolation": "geometric for positive parameters, linear otherwise",
            "fraction_from_45nm_to_65nm": fraction65,
        },
        "source_cards": {name: str(path) for name, path in SOURCE_PATHS.items()},
        "all_nonzero_common_parameters": all_nonzero,
        "fit_groups": FIT_GROUPS,
        "flavors": flavors,
        "paper_sources": PAPER_SOURCES,
        "limitations": [
            "PTM cards are priors, not ICS55 measurements.",
            "Leakage identifies threshold/subthreshold combinations better than mobility or C-V parameters.",
            "Parameters without direct I-V, C-V, gate-current, noise, mismatch, or aging data remain frozen.",
            "The current drive ratios are Liberty-versus-shipped-model evidence, not transistor measurements.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit-params", default=str(DEFAULT_FIT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    manifest = build_manifest(Path(args.fit_params).expanduser())
    Path(args.out).expanduser().write_text(json.dumps(manifest, indent=2) + "\n")
    for flavor, entry in manifest["flavors"].items():
        print(flavor)
        for typ, dev in entry["devices"].items():
            vals = dev["initial"]
            print("  %s:" % typ, " ".join("%s=%.8g" % (name, vals[name])
                                              for name in FIT_GROUPS["leakage"]))
    print(Path(args.out).expanduser())


if __name__ == "__main__":
    main()
