#!/usr/bin/env python3
"""Import the StarRC ITF/CAPTAB files with an explicit provenance banner.

Copies the upstream `hacking/decrypted_output/` files into
`libs.tech/pex/starrc/` and prepends a banner stating where they came from,
how they were obtained, and that they are vendor data included only for
educational / offline-comparison purposes.

The StarRC ITF format has no documented comment syntax, so the banner uses a
`*` line prefix and `--no-banner` is provided for consumers that reject it.
`ORIGIN.json` always records the exact upstream and imported SHA-256 so the
unmodified upstream bytes remain verifiable either way.
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
UPSTREAM_SUBDIR = "hacking/decrypted_output"

HERE = Path(__file__).resolve().parent
TARGET_DIR = HERE / "starrc"

FILES = (
    "kMapping.txt",
    "kItfTyp.txt",
    "kItfRcbest.txt",
    "kItfRcworst.txt",
    "kItfRcbest_21eac0.txt",
    "kItfCworst.txt",
    "kCaptabTyp.txt",
    "kCaptabRcbest.txt",
    "kCaptabRcworst.txt",
    "kCaptabCbest.txt",
    "kCaptabCworst.txt",
)

# Upstream filename -> local filename.  The upstream extractor named one blob
# after the symbol it was found under ("kItfRcbest_21eac0") but the payload's
# own TECHNOLOGY header says Cbest, and it is the dielectric-only C-best stack
# that pairs with kCaptabCbest.txt.  Import it under the correct corner name so
# a consumer cannot silently pair the wrong ITF with a CAPTAB; ORIGIN.json
# keeps upstream_relpath for byte traceability.
RENAME = {
    "kItfRcbest_21eac0.txt": "kItfCbest.txt",
}

BANNER = """\
* ============================================================================
* PROVENANCE - VENDOR DATA, UNVERIFIED REDISTRIBUTION STATUS
* ============================================================================
* Content : ICsprout 55nm StarRC RC technology data
*           ({kind}: {technology})
* Vendor  : ICsprout (foundry), delivered inside the proprietary ECOS iRCX
*           library libircx_ics55.so as XOR-ciphertext blobs.
* Origin  : decrypted by the upstream open-PDK project and published at
*           https://github.com/{repo}
*           path {subdir}/{relpath}
*           pinned commit {commit} ({date})
* License : Vendor (ICsprout). NOT Apache-2.0. These files are NOT part of the
*           released ICsprout PDK and were NOT obtained under a redistribution
*           grant. Included strictly for educational study and offline
*           comparison against the clean-room RC stack.
* Warning : Do not treat as signoff data. Do not redistribute. Use the
*           released LEFs plus independent extraction for production flows.
* Note    : Everything below this banner is byte-identical to the upstream
*           file; see ORIGIN.json for SHA-256 hashes of both.
* ============================================================================
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify(name: str) -> str:
    if name.startswith("kCaptab"):
        return "CAPTAB capacitance table"
    if name.startswith("kItf"):
        return "ITF process description"
    return "layer mapping"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache", type=Path, default=Path("/tmp/up"))
    parser.add_argument("--no-banner", action="store_true",
                        help="write upstream bytes verbatim (no provenance line)")
    args = parser.parse_args()

    manifest = {
        "upstream_repo": UPSTREAM_REPO,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_commit_date": UPSTREAM_COMMIT_DATE,
        "upstream_subdir": UPSTREAM_SUBDIR,
        "obtained_by": (
            "XOR decryption of the ECOS iRCX library libircx_ics55.so by the "
            "upstream project (see upstream hacking/NOTES.md, hacking/extractor.py)"
        ),
        "license": (
            "Vendor (ICsprout). Not Apache-2.0. Not released PDK collateral; "
            "educational / offline comparison only."
        ),
        "banner_applied": not args.no_banner,
        "files": {},
    }
    for relpath in FILES:
        url = (f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/"
               f"{UPSTREAM_COMMIT}/{UPSTREAM_SUBDIR}/{relpath}")
        if args.offline:
            raw = (args.cache / UPSTREAM_SUBDIR / relpath).read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=120) as response:
                raw = response.read()
        if args.no_banner:
            imported = raw
        else:
            banner = BANNER.format(
                kind=classify(relpath),
                technology=raw.splitlines()[0].decode().strip()
                if relpath.startswith("kItf") else relpath,
                repo=UPSTREAM_REPO,
                subdir=UPSTREAM_SUBDIR,
                relpath=relpath,
                commit=UPSTREAM_COMMIT,
                date=UPSTREAM_COMMIT_DATE,
            )
            imported = banner.encode() + raw
        local_name = RENAME.get(relpath, relpath)
        target = TARGET_DIR / local_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(imported)
        manifest["files"][local_name] = {
            "upstream_relpath": relpath,
            "renamed_from": relpath if local_name != relpath else None,
            "upstream_url": url,
            "upstream_sha256": sha256(raw),
            "upstream_bytes": len(raw),
            "imported_sha256": sha256(imported),
            "imported_bytes": len(imported),
        }
        print(f"{relpath}: {len(raw)} upstream bytes -> {target}")

    (TARGET_DIR / "ORIGIN.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(TARGET_DIR / "ORIGIN.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
