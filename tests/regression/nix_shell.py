"""Build nix-shell commands using the nixpkgs revision locked by LibreLane."""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Sequence


def command(librelane: str | Path, shell_command: str | Sequence[str]) -> list[str]:
    """Use LibreLane's shell with its locked nixpkgs available via NIX_PATH."""
    shell_path = Path(librelane).expanduser()
    lock_path = shell_path / "flake.lock"
    if not lock_path.is_file():
        raise FileNotFoundError(f"LibreLane flake.lock not found: {lock_path}")

    lock = json.loads(lock_path.read_text())
    try:
        locked = lock["nodes"]["nixpkgs"]["locked"]
    except KeyError as error:
        raise ValueError(f"LibreLane flake.lock lacks a locked nixpkgs input: {lock_path}") from error

    nixpkgs_url = locked.get("url")
    if not nixpkgs_url and locked.get("type") == "github":
        owner, repo, revision = locked.get("owner"), locked.get("repo"), locked.get("rev")
        if owner and repo and revision:
            nixpkgs_url = f"https://github.com/{owner}/{repo}/archive/{revision}.tar.gz"
    if not nixpkgs_url:
        raise ValueError(f"LibreLane flake.lock has no resolvable nixpkgs source: {lock_path}")

    command_text = shell_command if isinstance(shell_command, str) else shlex.join(shell_command)
    return [
        "nix-shell", "-I", f"nixpkgs={nixpkgs_url}", str(shell_path),
        "--run", command_text,
    ]
