#!/usr/bin/env python3
"""Check that every .INC/.include target in the foundry SPICE tree exists.

The foundry wrappers resolve relative includes against the including file's
directory, which is also how ngspice and HSPICE resolve them in this PDK.
A file that exists only in a developer's working tree (for example because a
generic .gitignore rule hid it) must fail this check in a clean checkout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOUNDRY = ROOT / "libs.tech" / "spice" / "foundry"
INCLUDE = re.compile(r"^\s*\.(?:inc|include)\s+(.+?)\s*$", re.IGNORECASE)


def include_targets(path: Path) -> list[str]:
    targets = []
    for line in path.read_text(errors="replace").splitlines():
        match = INCLUDE.match(line)
        if not match:
            continue
        target = match.group(1).split(";", 1)[0].strip()
        if target[:1] in {"'", '"'} and target[-1:] == target[:1]:
            target = target[1:-1]
        targets.append(target)
    return targets


def main() -> int:
    missing: list[str] = []
    checked = 0
    for path in sorted(FOUNDRY.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".lib", ".sp", ".ckt", ".mdl", ".inc"}:
            continue
        for target in include_targets(path):
            checked += 1
            candidate = Path(target)
            candidates = [candidate] if candidate.is_absolute() else [
                path.parent / candidate,
                ROOT / candidate,
            ]
            if not any(item.is_file() for item in candidates):
                missing.append(f"{path.relative_to(ROOT)}: {target}")

    if missing:
        print("FAIL: unresolved SPICE includes:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"PASS: {checked} SPICE includes resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
