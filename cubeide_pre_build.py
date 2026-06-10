#!/usr/bin/env python3
"""cubeide_pre_build.py — STM32CubeIDE pre-build step: build-date stamping.

Injects the current build date into the project's version.h, writing the three
integer macros named by ``date.defines`` in the shared config
(cubeide_build.config.json). Run as a *pre*-build step on the Release config so
the date is compiled into the binary (e.g. the CANopen OD firmwareBuildDate).

Independent of fw_release_tool.py / cubeide_post_build.py. Idempotent within a
day; rewrites version.h in place (expect it to show as modified after a build).

CubeIDE integration (Project ▸ Properties ▸ C/C++ Build ▸ Settings ▸ Build
Steps ▸ Pre-build):

    python3 "${ProjDirPath}/Tools/cubeide_pre_build.py"

Config (cubeide_build.config.json), date block:

    "date": { "defines": { "year": "FW_BUILD_YEAR",
                            "month": "FW_BUILD_MONTH",
                            "day": "FW_BUILD_DAY" } }

Paths in the config are relative to this script's directory (the Tools/ folder).
"""
import datetime
import json
import re
import sys
from pathlib import Path

CONFIG_NAME = "cubeide_build.config.json"
DEFAULT_DATE_DEFINES = {"year": "FW_BUILD_YEAR",
                        "month": "FW_BUILD_MONTH",
                        "day": "FW_BUILD_DAY"}


def find_config(script_dir: Path) -> Path:
    """Auto-discover the shared config (CWD first, then the script directory)."""
    cwd = Path.cwd()
    for base in (cwd, cwd / "tools", script_dir, script_dir / "tools"):
        c = base / CONFIG_NAME
        if c.exists():
            return c
    raise FileNotFoundError(f"{CONFIG_NAME} not found in execution path or script folder.")


def resolve_from_script(path_str: str, script_dir: Path) -> Path:
    """Resolve a config path relative to the script directory (or use as-is if absolute)."""
    p = Path(path_str)
    return p if p.is_absolute() else (script_dir / p).resolve()


def inject_define(text: str, define_name: str, value: int) -> str:
    """Rewrite ``#define NAME <number>`` in place, preserving any trailing
    comment/suffix. Accepts a decimal or hex literal. Raises if not found."""
    pattern = re.compile(
        rf'^(\s*#define\s+{re.escape(define_name)}\s+)([0-9]+|0[xX][0-9a-fA-F]+)(\b.*)$',
        re.M,
    )
    new_text, n = pattern.subn(rf'\g<1>{value}\g<3>', text)
    if n == 0:
        raise RuntimeError(f"Define {define_name} not found in header.")
    return new_text


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    try:
        cfg_path = find_config(script_dir)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - surface a one-line failure to the build
        print(f"FAIL cubeide_pre_build: {e}")
        return 1

    header_str = (cfg.get("paths") or {}).get("header", "")
    if not header_str:
        print("FAIL cubeide_pre_build: missing 'paths.header' in config.")
        return 1
    header = resolve_from_script(header_str, script_dir)

    names = ((cfg.get("date") or {}).get("defines")) or DEFAULT_DATE_DEFINES

    try:
        today = datetime.date.today()
        text = header.read_text(encoding="utf-8", errors="ignore")
        text = inject_define(text, names.get("year", "FW_BUILD_YEAR"), today.year)
        text = inject_define(text, names.get("month", "FW_BUILD_MONTH"), today.month)
        text = inject_define(text, names.get("day", "FW_BUILD_DAY"), today.day)
        header.write_text(text, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL cubeide_pre_build: {e}")
        return 1

    print(f"OK build date {today.isoformat()} -> {header.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
