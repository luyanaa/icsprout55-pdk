#!/usr/bin/env python3
"""Audit an expanded fit manifest on train and disjoint extracted splits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import fit_expanded as fx

HERE = Path(__file__).resolve().parent
FLAVORS = ("svt", "lvt", "hvt")


def audit_one(initial, start, row, flavor, dataset):
    data = json.loads((HERE / ("data_%s_%s.json" % (dataset, flavor))).read_text())
    cards = fx.make_cards(flavor, start, row["values"])
    simulated = fx.leakage_rows(flavor, data, cards)
    return fx.leakage_rms(data, simulated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--initial", default=str(HERE / "INITIAL_VALUES.json"))
    parser.add_argument("--datasets", default="train37,holdout2")
    args = parser.parse_args()
    initial = fx.load_initial(Path(args.initial).expanduser())
    start = fx.load_fit_start()
    results = json.loads(Path(args.results).expanduser().read_text())
    report = {}
    for flavor in FLAVORS:
        report[flavor] = {}
        for dataset in [x for x in args.datasets.split(",") if x]:
            report[flavor][dataset] = audit_one(
                initial, start, results[flavor], flavor, dataset)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
