"""
Anno 117 Map Template Editor — Persistent Settings
Stores user preferences in the platform-appropriate config directory.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import os
import json
import platform

APP_NAME = "Anno117MapEditor"

def _settings_dir() -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:  # Linux and others
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path

def _settings_file() -> str:
    return os.path.join(_settings_dir(), "settings.json")

def load() -> dict:
    try:
        with open(_settings_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save(data: dict) -> None:
    try:
        with open(_settings_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[settings] Could not save settings: {e}")

def get(key: str, default=None):
    return load().get(key, default)

def set(key: str, value) -> None:
    data = load()
    data[key] = value
    save(data)