#!/usr/bin/env python3
"""Import the ICsprout foundry SPICE model set from the upstream open PDK.

Downloads the `hspice/` and `ngspice/` model trees from the pinned upstream
commit and writes them under `libs.tech/spice/foundry/<variant>/`, prepending
a provenance banner to every file and recording upstream/imported hashes.

Provenance banner text is intentionally explicit: these device models come
from ICsprout (the foundry), are NOT covered by this repository's Apache-2.0
license, and are included for educational / research evaluation only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

UPSTREAM_REPO = "ckdur/icsprout55-openpdk"
UPSTREAM_COMMIT = "195870e61e9fa92d049df2daa4a7f5000c6aad3e"
UPSTREAM_COMMIT_DATE = "2026-10-08T15:20:54Z"
UPSTREAM_SUBDIR = "icsprout55/libs.tech"

SPICE_DIR = Path(__file__).resolve().parent
FOUNDRY_DIR = SPICE_DIR / "foundry"

VARIANTS = ("hspice", "ngspice")

FILES = (
    "ICsprout_55LLULP1225_V1p1_hsp.lib",
    "readme.txt",
    "model_wrapper1_hsp.lib",
    "model_wrapper2_hsp.lib",
    "mos/nsvt.mdl",
    "mos/nlvt.mdl",
    "mos/nhvt.mdl",
    "mos/psvt.mdl",
    "mos/plvt.mdl",
    "mos/phvt.mdl",
    "mos/nnat1p2_lp.mdl",
    "mos/nio25.mdl",
    "mos/nio25od33.mdl",
    "mos/nt25.mdl",
    "mos/nt25od33.mdl",
    "mos/pio25.mdl",
    "mos/piood33.mdl",
    "bjt/npn12_lp.mdl",
    "bjt/npn25_lp.mdl",
    "bjt/pnp12_lp.mdl",
    "bjt/pnp25_lp.mdl",
    "dio/dio_core.mdl",
    "dio/dio_io25.mdl",
    "dio/dio_well.mdl",
    "mom/mom.ckt",
    "res/resistor.ckt",
    "var/varactor.ckt",
)

BANNER = """\
* ============================================================================
* PROVENANCE - DO NOT RELICENSE
* ============================================================================
* Source   : ICsprout 55nm Logic Salicide 1.2/2.5V SPICE model release
*            "ICsprout_55LLULP1225_V1p1_hsp.lib" (release version 1.1)
* Vendor   : ICsprout (foundry).
* Mirror   : https://github.com/{repo}
*            path {subdir}/{variant}/{relpath}
*            pinned commit {commit} ({date})
* License  : Vendor supplied. NOT covered by this repository's Apache-2.0
*            license. Included for educational / research evaluation only.
*            Redistribution and commercial use are governed by the vendor
*            terms; obtain the models from ICsprout for any production use.
* Note     : Everything below this banner is byte-identical to the upstream
*            file. See ORIGIN.json for upstream and imported SHA-256 hashes.
* ============================================================================
"""


def upstream_url(variant: str, relpath: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_COMMIT}"
        f"/{UPSTREAM_SUBDIR}/{variant}/{relpath}"
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="use an existing cache instead of downloading")
    parser.add_argument("--cache", type=Path, default=Path("/tmp/up"),
                        help="local mirror of the upstream tree for --offline")
    args = parser.parse_args()

    manifest = {
        "upstream_repo": UPSTREAM_REPO,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_commit_date": UPSTREAM_COMMIT_DATE,
        "upstream_subdir": UPSTREAM_SUBDIR,
        "release": "ICsprout_55LLULP1225_V1p1 (hspice readme revision 1.1)",
        "license": (
            "Vendor (ICsprout). Not Apache-2.0. Educational / research "
            "evaluation only."
        ),
        "variants": {},
    }
    for variant in VARIANTS:
        entries = {}
        for relpath in FILES:
            if args.offline:
                local = args.cache / UPSTREAM_SUBDIR / variant / relpath
                raw = local.read_bytes()
            else:
                raw = fetch(upstream_url(variant, relpath))
            banner = BANNER.format(
                repo=UPSTREAM_REPO,
                subdir=UPSTREAM_SUBDIR,
                variant=variant,
                relpath=relpath,
                commit=UPSTREAM_COMMIT,
                date=UPSTREAM_COMMIT_DATE,
            )
            imported = banner.encode() + raw
            target = FOUNDRY_DIR / variant / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(imported)
            entries[relpath] = {
                "upstream_url": upstream_url(variant, relpath),
                "upstream_sha256": sha256(raw),
                "upstream_bytes": len(raw),
                "imported_sha256": sha256(imported),
                "imported_bytes": len(imported),
            }
        manifest["variants"][variant] = entries
        print(f"{variant}: {len(entries)} files -> {FOUNDRY_DIR / variant}")

    (FOUNDRY_DIR / "ORIGIN.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(FOUNDRY_DIR / "ORIGIN.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
