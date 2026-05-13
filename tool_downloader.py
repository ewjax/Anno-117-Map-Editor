"""
Anno 117 Map Template Editor - Tool Auto-Downloader

Downloads FileDBReader and RdaConsole from their GitHub releases and installs them to config.TOOLS_INSTALL_DIR (C:\\tools on Windows).
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import io
import json
import os
import urllib.request
import zipfile
from typing import Callable, Optional, Tuple

import config

# GitHub repository info per tool
# zip_name: exact release asset filename to download (None = use heuristic)
TOOL_INFO = {
    "FileDBReader": {
        "repo":     "anno-mods/FileDBReader",
        "exe_name": "FileDBReader.exe" if config.IS_WINDOWS else "FileDBReader",
        "zip_name": "FileDBReader.zip",
    },
    "RdaConsole": {
        "repo":     "anno-mods/RdaConsole",
        "exe_name": "RdaConsole.exe" if config.IS_WINDOWS else "RdaConsole",
        "zip_name": None,  # use heuristic
    },
}

_API_HEADERS = {"User-Agent": "anno117-mapeditor/1.0"}


def get_install_path(tool_name: str) -> str:
    """Return the full path where the tool will be installed."""
    return os.path.join(config.TOOLS_INSTALL_DIR, TOOL_INFO[tool_name]["exe_name"])


def fetch_latest_asset(repo: str, exe_name: str,
                       zip_name: Optional[str] = None) -> Tuple[str, str]:
    """
    Query GitHub releases API and return (download_url, asset_filename).

    If zip_name is given, matches that exact filename first.
    Otherwise falls back to: win*.zip > any*.zip > *.exe.
    Raises RuntimeError if no suitable asset is found.
    """
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(api_url, headers=_API_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    assets = data.get("assets", [])
    if not assets:
        raise RuntimeError(f"No release assets found for {repo}.")

    # Exact name match first
    if zip_name:
        for asset in assets:
            if asset["name"].lower() == zip_name.lower():
                return asset["browser_download_url"], asset["name"]

    # Heuristic fallback: win*.zip > any*.zip > *.exe
    for pattern in (
        lambda n: "win" in n and n.endswith(".zip"),
        lambda n: n.endswith(".zip"),
        lambda n: n.endswith(".exe"),
    ):
        for asset in assets:
            if pattern(asset["name"].lower()):
                return asset["browser_download_url"], asset["name"]

    raise RuntimeError(
        f"No suitable Windows asset found in {repo} latest release.\n"
        f"Available: {[a['name'] for a in assets]}"
    )


def download_and_install(
    tool_name: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Download the latest release of tool_name and install it to TOOLS_INSTALL_DIR.

    progress_cb(bytes_done, total_bytes) is called periodically during download.
    Returns the path to the installed executable.
    Raises RuntimeError on any failure.
    """
    info = TOOL_INFO[tool_name]
    url, filename = fetch_latest_asset(info["repo"], info["exe_name"], info.get("zip_name"))

    os.makedirs(config.TOOLS_INSTALL_DIR, exist_ok=True)
    dest = get_install_path(tool_name)

    # ── Download into memory ─────────────────────────────────────────────────
    req = urllib.request.Request(url, headers=_API_HEADERS)
    buf = io.BytesIO()
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        while chunk := resp.read(65536):
            buf.write(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)

    buf.seek(0)

    # ── Extract or write ─────────────────────────────────────────────────────
    if filename.lower().endswith(".zip"):
        exe_name_lower = info["exe_name"].lower()
        with zipfile.ZipFile(buf) as zf:
            # Find the exe entry to determine its prefix inside the zip
            exe_entry = next(
                (n for n in zf.namelist()
                 if os.path.basename(n).lower() == exe_name_lower),
                None,
            )
            if exe_entry is None:
                raise RuntimeError(
                    f"{info['exe_name']} not found inside {filename}.\n"
                    f"Contents: {zf.namelist()}"
                )
            # Everything at the same level as the exe (strip zip-internal prefix)
            prefix = exe_entry[: len(exe_entry) - len(os.path.basename(exe_entry))]
            for entry in zf.namelist():
                if not entry.startswith(prefix):
                    continue
                rel = entry[len(prefix):]   # path relative to the exe's folder
                if not rel:                 # skip the folder entry itself
                    continue
                out_path = os.path.join(config.TOOLS_INSTALL_DIR, rel)
                if entry.endswith("/"):     # directory
                    os.makedirs(out_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as fh:
                        fh.write(zf.read(entry))
    else:
        with open(dest, "wb") as fh:
            fh.write(buf.read())

    # Mark executable on Unix
    if not config.IS_WINDOWS:
        os.chmod(dest, 0o755)

    return dest
