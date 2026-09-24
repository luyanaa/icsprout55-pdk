#!/usr/bin/env python3
"""Constrained, prior-regularized BSIM4 fit using the three PTM source cards.

This is the next stage after the original six-parameter leakage fit.  It keeps
PTM 45 nm LP as the simulator card and uses the interpolated 45/65 nm values
as soft priors. With `--freeze-legacy`, the shipped leakage-calibrated
VTH0/VOFF/DIBL values are held exactly while newly exposed parameters are
searched. Without that flag, the six legacy controls are also exploratory
parameters and the result must not be compared to the shipped fit as a
non-degrading extension.

The current objective is nominal TT cell leakage.  C-V and transient drive are
separate observables and are not silently folded into a leakage-only score.
The output is an experiment manifest; `write_model.py` consumes it only after
explicit promotion to the shipped FIT_PARAMS schema.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Tuple

import optuna
from optuna.samplers import TPESampler

FITDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FITDIR))
import initial_values as iv  # noqa: E402
import simulate as sm  # noqa: E402

PM = os.path.expanduser("~/Downloads/45nm_LP.pm")
FITTED = FITDIR.parent / "fitted" / "FIT_PARAMS.json"
FLAVORS = ("svt", "lvt", "hvt")

# Values are parameterized as scales about the source/data-informed initial
# value.  VTH0 stays in volts because it changes sign for PMOS.
SCALE_SPECS = {
    "voff_n": (0.50, 2.00, 0.18),
    "voff_p": (0.50, 2.00, 0.18),
    "dibl_n": (0.25, 2.50, 0.30),
    "dibl_p": (0.25, 2.50, 0.30),
    "nf_n": (0.80, 1.25, 0.12),
    "nf_p": (0.80, 1.25, 0.12),
    "eta_n": (0.50, 2.00, 0.18),
    "eta_p": (0.50, 2.00, 0.18),
    "dsub_n": (0.50, 2.00, 0.18),
    "dsub_p": (0.50, 2.00, 0.18),
    "tox_n": (0.85, 1.15, 0.10),
    "tox_p": (0.85, 1.15, 0.10),
    "u0_n": (0.50, 2.00, 0.20),
    "u0_p": (0.50, 2.00, 0.20),
    "pclm_n": (0.50, 2.00, 0.20),
    "pclm_p": (0.50, 2.00, 0.20),
    "drout_n": (0.50, 2.00, 0.20),
    "drout_p": (0.50, 2.00, 0.20),
}
VTH_SPECS = {
    "vth0n": (0.45, 1.15),
    "vth0p": (0.15, 1.20),
}
PRIOR_PARAMETER = {
    "voff": "voff",
    "dibl": "pdiblc1",
    "nf": "nfactor",
    "eta": "eta0",
    "dsub": "dsub",
    "tox": "toxe",
    "u0": "u0",
    "pclm": "pclm",
    "drout": "drout",
}
PRIOR_WEIGHT = 0.002


def load_initial(path: Path) -> Mapping[str, object]:
    return json.loads(path.read_text())


def load_fit_start(fit_path: Path = FITTED) -> Mapping[str, object]:
    """Build a non-degrading start from the shipped six-parameter fit.

    The source-derived manifest remains the prior.  The simulator start keeps
    the shipped leakage calibration for VTH0, VOFF, and DIBL, while all newly
    exposed parameters start at the 45 nm LP card values.  This prevents a
    source-card interpolation from silently replacing a previously verified
    leakage fit before the new parameters have earned a change.
    """
    cards = iv.parse_model_cards(Path(PM))
    fitted = json.loads(fit_path.read_text())
    flavors = fitted.get("flavors", fitted)
    result = {"flavors": {}}
    for flavor in FLAVORS:
        params = flavors[flavor]["params"]
        n = dict(cards["nmos"])
        p = dict(cards["pmos"])
        n["vth0"] = params["vth0n"]
        p["vth0"] = -abs(params["vth0p"])
        for typ, target, prefix in (("nmos", n, "n"), ("pmos", p, "p")):
            target["voff"] = cards[typ]["voff"] * params["voff_%s" % prefix]
            for name in ("pdiblc1", "pdiblc2", "pdiblcb"):
                target[name] = cards[typ][name] * params["dibl_%s" % prefix]
        result["flavors"][flavor] = {
            "devices": {"nmos": n, "pmos": p},
        }
    return result


def _device_initial(initial: Mapping[str, object], flavor: str, typ: str) -> Dict[str, float]:
    return dict(initial["flavors"][flavor]["devices"][typ]["initial"])


def _device_start(start: Mapping[str, object], flavor: str, typ: str) -> Dict[str, float]:
    return dict(start["flavors"][flavor]["devices"][typ])
def legacy_values(start: Mapping[str, object], flavor: str) -> Dict[str, float]:
    """Recover the six shipped-fit controls from a direct start card."""
    base = iv.parse_model_cards(Path(PM))
    n = _device_start(start, flavor, "nmos")
    p = _device_start(start, flavor, "pmos")
    return {
        "vth0n": n["vth0"],
        "vth0p": abs(p["vth0"]),
        "dibl_n": n["pdiblc1"] / base["nmos"]["pdiblc1"],
        "dibl_p": p["pdiblc1"] / base["pmos"]["pdiblc1"],
        "voff_n": n["voff"] / base["nmos"]["voff"],
        "voff_p": p["voff"] / base["pmos"]["voff"],
    }




def suggest(trial: optuna.Trial, names=None, fixed_vth=None,
            fixed_legacy=None) -> Dict[str, float]:
    names = set(names or list(VTH_SPECS) + list(SCALE_SPECS))
    fixed_legacy = fixed_legacy or {}
    values: Dict[str, float] = {}
    for name, (lo, hi) in VTH_SPECS.items():
        if fixed_vth is None:
            values[name] = trial.suggest_float(name, lo, hi)
        else:
            values[name] = fixed_vth[name]
    for name, (lo, hi, _) in SCALE_SPECS.items():
        if name in fixed_legacy:
            values[name] = fixed_legacy[name]
        elif name in names:
            values[name] = trial.suggest_float(name, lo, hi)
        else:
            values[name] = 1.0
    return values


def _scaled(value: float, scale: float) -> float:
    return value * scale


def overrides(start: Mapping[str, object], flavor: str,
              values: Mapping[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Return only newly fitted direct overrides.

    The six shipped leakage controls are passed through the legacy arguments
    of `make_model_cards`; re-emitting every PTM scalar rounds tiny HVT
    currents and can turn the Xyce gmin-corrected result negative.
    """
    n_base = _device_start(start, flavor, "nmos")
    p_base = _device_start(start, flavor, "pmos")
    n: Dict[str, float] = {}
    p: Dict[str, float] = {}
    for base, target, prefix in (
            (n_base, n, "n"), (p_base, p, "p")):
        for parameter, family in (
                ("nfactor", "nf"), ("eta0", "eta"), ("dsub", "dsub"),
                ("u0", "u0"), ("pclm", "pclm"), ("drout", "drout")):
            scale = values["%s_%s" % (family, prefix)]
            if scale != 1.0:
                target[parameter] = _scaled(base[parameter], scale)
        tox = values["tox_%s" % prefix]
        if tox != 1.0:
            for parameter in ("toxe", "toxm"):
                target[parameter] = _scaled(base[parameter], tox)
            target["toxref"] = _scaled(
                base.get("toxref", base["toxe"]), tox)
    return n, p


GMIN_CORRECT_BY_FLAVOR = {"svt": True, "lvt": True, "hvt": False}


def make_cards(flavor: str, start: Mapping[str, object],
               values: Mapping[str, float]) -> str:
    """Render a card with legacy controls plus sparse added-parameter edits."""
    legacy = {
        "vth0n": values["vth0n"],
        "vth0p": values["vth0p"],
        "dibl_n": values["dibl_n"],
        "dibl_p": values["dibl_p"],
        "voff_n": values["voff_n"],
        "voff_p": values["voff_p"],
    }
    n, p = overrides(start, flavor, values)
    return sm.make_model_cards(
        PM, "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
        vth0n=legacy["vth0n"], vth0p=legacy["vth0p"],
        dibl_scale_n=legacy["dibl_n"], dibl_scale_p=legacy["dibl_p"],
        voff_scale_n=legacy["voff_n"], voff_scale_p=legacy["voff_p"],
        overrides_n=n, overrides_p=p,
    )


def leakage_rows(flavor: str, data, cards):
    """Simulate with the numerical floor policy appropriate to the flavor."""
    return sm.sim_leakage(
        data, cards, vdd=1.2, temp=25,
        gmin_correct=GMIN_CORRECT_BY_FLAVOR[flavor],
    )




def leakage_rms(data, rows) -> float:
    by_cell: Dict[str, list] = {}
    for (_, cell, _, measured, simulated) in rows:
        if simulated is None or measured <= 0 or simulated <= 0:
            return 1e6
        by_cell.setdefault(cell, []).append((measured, simulated))
    errors = []
    for entries in by_cell.values():
        measured = sum(x for x, _ in entries) / len(entries)
        simulated = sum(y for _, y in entries) / len(entries)
        errors.append(math.log10(simulated / measured))
    if not errors:
        return 1e6
    return math.sqrt(sum(x * x for x in errors) / len(errors))


def _source_scale(initial: Mapping[str, object],
                  start: Mapping[str, object], flavor: str,
                  name: str) -> float:
    family, prefix = name.rsplit("_", 1)
    parameter = PRIOR_PARAMETER[family]
    typ = "nmos" if prefix == "n" else "pmos"
    source = _device_initial(initial, flavor, typ)[parameter]
    base = _device_start(start, flavor, typ)[parameter]
    if abs(source) < 1e-12 or abs(base) < 1e-12 or source * base <= 0:
        return 1.0
    return abs(source / base)


def prior_penalty(values: Mapping[str, float], active_names,
                  initial: Mapping[str, object],
                  start: Mapping[str, object], flavor: str) -> float:
    terms = []
    for name in active_names:
        if name not in SCALE_SPECS:
            continue
        _, _, sigma = SCALE_SPECS[name]
        center = _source_scale(initial, start, flavor, name)
        terms.append(math.log(values[name] / center) / sigma)
    return math.sqrt(sum(x * x for x in terms) / len(terms)) if terms else 0.0


def score(data, initial, start, flavor: str, values: Mapping[str, float],
          active_names) -> Tuple[float, float, float]:
    cards = make_cards(flavor, start, values)
    rows = leakage_rows(flavor, data, cards)
    rms = leakage_rms(data, rows)
    penalty = prior_penalty(values, active_names, initial, start, flavor)
    # Data fit remains primary; source interpolation is a soft prior.
    total = math.sqrt(rms * rms + PRIOR_WEIGHT * penalty * penalty)
    return total, rms, penalty
def fit(flavor: str, dataset: str, initial: Mapping[str, object],
        start: Mapping[str, object], trials: int, seed: int,
        active_names, freeze_legacy: bool = False) -> Dict[str, object]:
    data = json.loads((FITDIR / ("data_%s_%s.json" % (dataset, flavor))).read_text())
    study = optuna.create_study(direction="minimize", sampler=TPESampler(seed=seed))
    fixed_vth = None
    fixed_legacy = None
    if freeze_legacy:
        fixed_vth = {
            "vth0n": _device_start(start, flavor, "nmos")["vth0"],
            "vth0p": abs(_device_start(start, flavor, "pmos")["vth0"]),
        }
        legacy = legacy_values(start, flavor)
        fixed_legacy = {
            name: legacy[name] for name in ("voff_n", "voff_p", "dibl_n", "dibl_p")
        }
    seed_values = {name: 1.0 for name in SCALE_SPECS}
    seed_values.update({"vth0n": _device_start(start, flavor, "nmos")["vth0"],
                        "vth0p": abs(_device_start(start, flavor, "pmos")["vth0"])})
    if fixed_legacy:
        seed_values.update(fixed_legacy)
    study.enqueue_trial(seed_values)

    def objective(trial):
        values = suggest(
            trial, active_names, fixed_vth=fixed_vth,
            fixed_legacy=fixed_legacy)
        total, rms, penalty = score(
            data, initial, start, flavor, values, active_names)
        trial.set_user_attr("leakage_rms", rms)
        trial.set_user_attr("prior_penalty", penalty)
        return total

    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    best = dict(study.best_trial.params)
    best.update({
        "vth0n": best.get("vth0n", _device_start(start, flavor, "nmos")["vth0"]),
        "vth0p": best.get("vth0p", abs(_device_start(start, flavor, "pmos")["vth0"])),
    })
    for name in SCALE_SPECS:
        best[name] = best.get(name, fixed_legacy.get(name, 1.0)
                              if fixed_legacy else 1.0)
    # Recompute in the same process and retain all objective terms.
    total, rms, penalty = score(
        data, initial, start, flavor, best, active_names)
    return {
        "freeze_legacy": freeze_legacy,
        "fixed_legacy_values": fixed_legacy or {},
        "base_model": PM,
        "start_model": "shipped six-parameter fit plus 45nm LP values",
        "active_parameters": list(active_names),
        "gmin_correct": GMIN_CORRECT_BY_FLAVOR[flavor],
        "gmin_policy": (
            "subtract Xyce gmin floor"
            if GMIN_CORRECT_BY_FLAVOR[flavor]
            else "retain raw Xyce current; correction produced negative HVT currents"
        ),
        "objective": "sqrt(leakage_rms^2 + %.4g*source_prior_penalty^2)" % PRIOR_WEIGHT,
        "values": best,
        "total": total,
        "leakage_rms": rms,
        "prior_penalty": penalty,
        "trials": trials,
        "seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("flavor", choices=FLAVORS, nargs="+")
    parser.add_argument("--dataset", default="train37")
    parser.add_argument("--initial", default=str(FITDIR / "INITIAL_VALUES.json"))
    parser.add_argument("--fitted", default=str(FITTED))
    parser.add_argument("--trials", type=int, default=120)
    parser.add_argument("--seed", type=int, default=211)
    parser.add_argument("--params", default=",")
    parser.add_argument("--freeze-legacy", action="store_true",
                        help="hold shipped VTH0/VOFF/DIBL while fitting additions")
    parser.add_argument("--out", default="expanded_fit_results.json")
    args = parser.parse_args()
    initial = load_initial(Path(args.initial).expanduser())
    start = load_fit_start(Path(args.fitted).expanduser())
    default_names = list(SCALE_SPECS)
    active = default_names if args.params in ("", ",") else [x for x in args.params.split(",") if x]
    unknown = set(active) - set(SCALE_SPECS)
    if unknown:
        raise SystemExit("unknown scale parameters: %s" % ", ".join(sorted(unknown)))
    result = {}
    for offset, flavor in enumerate(args.flavor):
        row = fit(flavor, args.dataset, initial, start, args.trials,
                  args.seed + 2 * offset, active, args.freeze_legacy)
        result[flavor] = row
        print(flavor, "total=%.6f leakage=%.6f prior=%.6f" %
              (row["total"], row["leakage_rms"], row["prior_penalty"]), flush=True)
        print("  ", {k: round(v, 6) for k, v in row["values"].items()})
    Path(args.out).expanduser().write_text(json.dumps(result, indent=2) + "\n")
    print(Path(args.out).expanduser())


if __name__ == "__main__":
    main()
