#!/usr/bin/env python3
"""Fit BSIM4 topology parameters against multi-input Liberty timing arcs.

Two deliberately separate exploratory stages are supported:

* ``short``: K1/K2/A0/A1/A2 on NAND2/NOR2.
* ``cv``: CF/CLC/DROUT on AOI22.  AOI22 internal unlabeled M1 is omitted from
  RC injection; labeled signal RC remains enabled.  Strict RC extraction still
  fails closed elsewhere.

The shipped leakage and inverter-drive controls are fixed.  Results are
experiment manifests until independently audited and explicitly promoted.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, Mapping, MutableMapping, Tuple

import optuna
from optuna.samplers import TPESampler

FITDIR = Path(__file__).resolve().parent
ROOT = FITDIR.parents[3]
sys.path.insert(0, str(FITDIR))
import drive as inv_drive  # noqa: E402
import fit_expanded as fx  # noqa: E402
import gate_drive as gd  # noqa: E402
import simulate as sm  # noqa: E402

FLAVORS = ("svt", "lvt", "hvt")
FITTED = FITDIR.parent / "fitted" / "FIT_PARAMS.json"

# Direct BSIM4 values.  Bounds are intentionally narrow around the PTM card;
# they are search guardrails, not process limits or extraction uncertainty.
SHORT_SPECS = {
    "k1_n": (0.20, 0.80, 0.40, 0.20),
    "k1_p": (0.20, 0.80, 0.40, 0.20),
    "k2_n": (-0.15, 0.15, 0.00, 0.10),
    "k2_p": (-0.15, 0.15, -0.01, 0.10),
    "a0_n": (0.25, 2.00, 1.00, 0.50),
    "a0_p": (0.25, 2.00, 1.00, 0.50),
    "a1_n": (0.00, 0.50, 0.00, 0.15),
    "a1_p": (0.00, 0.50, 0.00, 0.15),
    "a2_n": (0.25, 1.75, 1.00, 0.50),
    "a2_p": (0.25, 1.75, 1.00, 0.50),
}

# CF is F/m and CLC is m in BSIM4.  These are exploratory numerical bounds;
# no process prior is available because the PTM source cards omit both fields.
CV_SPECS = {
    "cf_n": (0.0, 5.0e-10, 0.0, 2.5e-10),
    "cf_p": (0.0, 5.0e-10, 0.0, 2.5e-10),
    "clc_n": (0.0, 5.0e-7, 0.0, 2.5e-7),
    "clc_p": (0.0, 5.0e-7, 0.0, 2.5e-7),
    "drout_n": (0.10, 1.50, 0.50, 0.50),
    "drout_p": (0.10, 1.50, 0.56, 0.50),
}

STAGES = {
    "short": {
        "specs": SHORT_SPECS,
        "fit_cells": ("NAND2X1", "NOR2X1", "NAND2X2", "NOR2X2"),
        "audit_cells": ("NAND2X3", "NOR2X3", "NAND2X4", "NOR2X4"),
        # Larger cells contain unlabeled internal M1.  Use labeled signal RC
        # only; strict extraction remains the default in gate_drive.evaluate.
        "allow_unmapped_internal": True,
    },
    "cv": {
        "specs": CV_SPECS,
        "fit_cells": ("AOI22X1", "AOI22X2"),
        "audit_cells": ("AOI22X3",),
        "allow_unmapped_internal": True,
    },
}


def _loaded_fit(path: Path) -> Mapping[str, object]:
    raw = json.loads(path.read_text())
    return raw.get("flavors", raw)


def _merged_overrides(flavor: str, base_results: Mapping[str, object] | None,
                      fitted: Mapping[str, object]) -> Tuple[Dict[str, float], Dict[str, float]]:
    current = fitted[flavor].get("drive", {})
    n = dict(current.get("overrides_n", {}))
    p = dict(current.get("overrides_p", {}))
    if base_results and flavor in base_results:
        row = base_results[flavor]
        n.update(row.get("overrides_n", {}))
        p.update(row.get("overrides_p", {}))
    return n, p


def _apply_values(n: MutableMapping[str, float], p: MutableMapping[str, float],
                  values: Mapping[str, float]) -> None:
    mapping = {
        "k1": "k1", "k2": "k2", "a0": "a0", "a1": "a1",
        "a2": "a2", "cf": "cf", "clc": "clc", "drout": "drout",
    }
    for name, value in values.items():
        family, prefix = name.rsplit("_", 1)
        target = n if prefix == "n" else p
        target[mapping[family]] = float(value)


def _cards(flavor: str, values: Mapping[str, float], base_results,
           fitted, start) -> str:
    legacy = fx.legacy_values(start, flavor)
    n, p = _merged_overrides(flavor, base_results, fitted)
    _apply_values(n, p, values)
    return sm.make_model_cards(
        fx.PM, "nm1p2_%s_lp" % flavor, "pm1p2_%s_lp" % flavor,
        vth0n=legacy["vth0n"], vth0p=legacy["vth0p"],
        dibl_scale_n=legacy["dibl_n"], dibl_scale_p=legacy["dibl_p"],
        voff_scale_n=legacy["voff_n"], voff_scale_p=legacy["voff_p"],
        overrides_n=n, overrides_p=p,
    )


def _timing_rows(cards: str, flavor: str, cells: Iterable[str],
                 allow_unmapped_internal: bool):
    rows = []
    for cell in cells:
        arcs = gd.timing_arcs(flavor, cell)
        rows.extend(gd.evaluate(
            cards, flavor, cell, arcs, rc=True,
            allow_unmapped_internal=allow_unmapped_internal))
    return rows


def _rms(rows) -> float:
    if not rows:
        return 1e6
    errors = [float(row["log10_ratio"]) for row in rows]
    return math.sqrt(sum(error * error for error in errors) / len(errors))


def _prior(values: Mapping[str, float], specs) -> float:
    terms = []
    for name, value in values.items():
        _, _, center, sigma = specs[name]
        scale = max(abs(sigma), 1.0e-15)
        terms.append((float(value) - center) / scale)
    return math.sqrt(sum(term * term for term in terms) / len(terms)) if terms else 0.0


def fit_one(flavor: str, stage_name: str, trials: int, seed: int,
            leakage_weight: float, base_results, fitted, start):
    stage = STAGES[stage_name]
    specs = stage["specs"]
    leakage_data = inv_drive.load_data(flavor, "train37")
    study = optuna.create_study(
        direction="minimize", sampler=TPESampler(seed=seed))

    def objective(trial):
        values = {
            name: trial.suggest_float(name, bounds[0], bounds[1])
            for name, bounds in specs.items()
        }
        try:
            cards = _cards(flavor, values, base_results, fitted, start)
            timing = _timing_rows(
                cards, flavor, stage["fit_cells"],
                stage["allow_unmapped_internal"])
            timing_rms = _rms(timing)
            leakage = fx.leakage_rms(
                leakage_data, fx.leakage_rows(flavor, leakage_data, cards))
        except (KeyError, OSError, RuntimeError, ValueError):
            return 1e6
        prior = _prior(values, specs)
        total = math.sqrt(
            timing_rms * timing_rms + leakage_weight * leakage * leakage
            + 0.002 * prior * prior)
        trial.set_user_attr("timing_rms", timing_rms)
        trial.set_user_attr("leakage_rms", leakage)
        trial.set_user_attr("prior", prior)
        return total

    study.enqueue_trial({name: bounds[2] for name, bounds in specs.items()})
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    values = dict(study.best_trial.params)
    values.update({name: values.get(name, bounds[2])
                   for name, bounds in specs.items()})
    cards = _cards(flavor, values, base_results, fitted, start)
    timing = _timing_rows(
        cards, flavor, stage["fit_cells"], stage["allow_unmapped_internal"])
    leakage = fx.leakage_rms(
        leakage_data, fx.leakage_rows(flavor, leakage_data, cards))
    timing_rms = _rms(timing)
    prior = _prior(values, specs)
    total = math.sqrt(timing_rms * timing_rms + leakage_weight * leakage * leakage
                      + 0.002 * prior * prior)
    n, p = _merged_overrides(flavor, base_results, fitted)
    _apply_values(n, p, values)
    return {
        "stage": stage_name,
        "base_model": fx.PM,
        "fit_cells": list(stage["fit_cells"]),
        "audit_cells": list(stage["audit_cells"]),
        "rc_enabled": True,
        "allow_unmapped_internal": stage["allow_unmapped_internal"],
        "active_parameters": list(specs),
        "values": values,
        "overrides_n": n,
        "overrides_p": p,
        "objective": "sqrt(timing_rms^2 + %.4g*leakage_rms^2 + 0.002*prior^2)" % leakage_weight,
        "leakage_weight": leakage_weight,
        "timing_rms": timing_rms,
        "leakage_rms": leakage,
        "prior": prior,
        "total": total,
        "timing": timing,
        "trials": trials,
        "seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=tuple(STAGES))
    parser.add_argument("flavor", choices=FLAVORS, nargs="+")
    parser.add_argument("--fitted", default=str(FITTED))
    parser.add_argument("--base-results", default="")
    parser.add_argument("--trials", type=int, default=36)
    parser.add_argument("--seed", type=int, default=4211)
    parser.add_argument("--leakage-weight", type=float, default=4.0)
    parser.add_argument("--out", default="gate_fit_results.json")
    args = parser.parse_args()
    fitted = _loaded_fit(Path(args.fitted).expanduser())
    base_results = None
    if args.base_results:
        base_results = json.loads(Path(args.base_results).expanduser().read_text())
    start = fx.load_fit_start(Path(args.fitted).expanduser())
    result = {}
    for offset, flavor in enumerate(args.flavor):
        row = fit_one(
            flavor, args.stage, args.trials, args.seed + 2 * offset,
            args.leakage_weight, base_results, fitted, start)
        result[flavor] = row
        print(flavor, "total=%.6f timing=%.6f leakage=%.6f prior=%.6f" % (
            row["total"], row["timing_rms"], row["leakage_rms"], row["prior"]),
              flush=True)
        print("  ", {k: round(v, 8) for k, v in row["values"].items()}, flush=True)
    path = Path(args.out).expanduser()
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
